import json
from datetime import date, datetime

from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import F, Func, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from seguimiento.models import Cliente, Factura

from . import seg
from .auth import api_key_required

PAGE_SIZE_DEFAULT = 100
PAGE_SIZE_MAX = 500
COMENTARIO_MAX = 4000

TIPO_ESTADO_FACTURA = 3  # tEstado.TipoEstado: 1=cotización, 2=proyecto, 3=factura
ESTADOS_PAGADA = {5, 8}  # Factura Pagada, Pago Verificado: exigen fecha de pago


class ParamError(ValueError):
    pass


def _json(data, status=200):
    return JsonResponse(data, status=status, safe=False, json_dumps_params={'ensure_ascii': False})


def _error(msg, status=400):
    return _json({'error': msg}, status=status)


def _parse_date(value, name):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ParamError(f"'{name}' debe tener formato AAAA-MM-DD")


def _parse_datetime(value, name):
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ParamError(f"'{name}' debe tener formato ISO 8601 (AAAA-MM-DD o AAAA-MM-DDTHH:MM:SS)")


def _parse_int(value, name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ParamError(f"'{name}' debe ser un número entero")


def _parse_float(value, name):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ParamError(f"'{name}' debe ser un número")


def _parse_int_list(value, name):
    return [_parse_int(v.strip(), name) for v in value.split(',') if v.strip()]


def _parse_rut(value):
    """'76.123.456-K' -> 76123456"""
    return _parse_int(value.split('-')[0].replace('.', '').strip(), 'rut')


def _read_body(request):
    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        raise ParamError('El cuerpo debe ser JSON válido')
    if not isinstance(data, dict):
        raise ParamError('El cuerpo debe ser un objeto JSON')
    return data


def _clean_comentario(value):
    if not isinstance(value, str) or not value.strip():
        raise ParamError("'comentario' debe ser un texto no vacío")
    if len(value) > COMENTARIO_MAX:
        raise ParamError(f"'comentario' admite hasta {COMENTARIO_MAX} caracteres")
    return value.strip()


def _paginate(request, qs):
    page_number = _parse_int(request.GET.get('page', '1'), 'page')
    page_size = _parse_int(request.GET.get('page_size', str(PAGE_SIZE_DEFAULT)), 'page_size')
    page_size = max(1, min(page_size, PAGE_SIZE_MAX))
    paginator = Paginator(qs, page_size)
    if page_number < 1 or (page_number > paginator.num_pages and paginator.count):
        raise ParamError(f"'page' fuera de rango (1-{paginator.num_pages})")
    items = list(paginator.page(page_number)) if paginator.count else []
    meta = {
        'count': paginator.count,
        'page': page_number,
        'page_size': page_size,
        'num_pages': paginator.num_pages if paginator.count else 0,
    }
    return items, meta


def _estados_factura():
    with connection.cursor() as cursor:
        cursor.execute('SELECT CodEstado, Descrip FROM tEstado WHERE TipoEstado = %s', [TIPO_ESTADO_FACTURA])
        return {cod: descrip.strip() if descrip else descrip for cod, descrip in cursor.fetchall()}


def _rut(cliente):
    if cliente is None or cliente.rut is None:
        return None
    return f"{int(cliente.rut)}-{cliente.dvrut or ''}"


def _pesos(value):
    return None if value is None else round(value)


def _serialize_cliente(c):
    return {'idcliente': c.idcliente, 'rut': _rut(c), 'razonsocial': c.razonsocial} if c else None


def _serialize_factura(f, estados, comentario):
    """Resumen para el listado. Facturas exentas de IVA: neto = total, iva = 0."""
    total = _pesos(f.valortotalpesos)
    proyecto = f.idproyecto
    return {
        'idfactura': f.idfactura,
        'folio': int(f.numfactura) if f.numfactura is not None else None,
        'fecha_emision': f.fechaemision,
        'fecha_pago': f.fechapago,
        'cliente': _serialize_cliente(f.idcliente),
        'proyecto': {
            'idproyecto': int(proyecto.idproyecto),
            'nombre': proyecto.idcotizacion.nombreproyecto if proyecto.idcotizacion_id else None,
        } if proyecto else None,
        'neto': total,
        'iva': 0 if total is not None else None,
        'total': total,
        'estado': f.estado,
        'estado_nombre': estados.get(f.estado),
        'comentario': comentario,
    }


def _serialize_factura_detalle(f, estados):
    data = _serialize_factura(f, estados, None)
    contacto = f.idcontacto
    comentarios = seg.listar(f.idfactura)
    data.update({
        'comentario': comentarios[0]['comentario'] if comentarios else None,
        'glosa': f.detalle,
        'moneda': f.moneda,
        'monto_moneda_original': f.valortotal,
        'valor_uf': float(f.valoruf) if f.valoruf is not None else None,
        'porcentaje_facturado': f.porcfact,
        'vencimiento_dias': f.vencimiento,
        'hes_eepp': {'numero': f.numhes_eepp, 'fecha': f.fechahes_eepp},
        'contacto': {
            'idcontacto': contacto.idcontacto,
            'nombre': contacto.nombrecontacto,
            'email': contacto.email,
            'telefono': contacto.telefono,
        } if contacto else None,
        'fecha_registro': f.fecharegistro,
        'fecha_actualizacion': f.fechaact,
        'comentarios': comentarios,
    })
    return data


def _facturas_qs():
    return Factura.objects.select_related('idcliente', 'idcontacto', 'idproyecto__idcotizacion')


def _filtrar_facturas(params, qs):
    if params.get('desde'):
        qs = qs.filter(fechaemision__gte=_parse_date(params['desde'], 'desde'))
    if params.get('hasta'):
        qs = qs.filter(fechaemision__lte=_parse_date(params['hasta'], 'hasta'))
    if params.get('modificado_desde'):
        qs = qs.filter(fechaact__gte=_parse_datetime(params['modificado_desde'], 'modificado_desde'))
    if params.get('idcliente'):
        qs = qs.filter(idcliente_id=_parse_int(params['idcliente'], 'idcliente'))
    if params.get('rut'):
        qs = qs.filter(idcliente__rut=_parse_rut(params['rut']))
    if params.get('idproyecto'):
        qs = qs.filter(idproyecto_id=_parse_int(params['idproyecto'], 'idproyecto'))
    if params.get('folio'):
        qs = qs.filter(numfactura=_parse_int(params['folio'], 'folio'))
    if params.get('estado'):
        qs = qs.filter(estado__in=_parse_int_list(params['estado'], 'estado'))

    # Monto (total en pesos): rango explícito, o monto ± tolerancia
    if params.get('monto_min'):
        qs = qs.filter(valortotalpesos__gte=_parse_float(params['monto_min'], 'monto_min'))
    if params.get('monto_max'):
        qs = qs.filter(valortotalpesos__lte=_parse_float(params['monto_max'], 'monto_max'))
    if params.get('monto'):
        monto = _parse_float(params['monto'], 'monto')
        tolerancia = _parse_float(params.get('tolerancia', '0'), 'tolerancia')
        if params.get('tolerancia_pct'):
            tolerancia = max(tolerancia, monto * _parse_float(params['tolerancia_pct'], 'tolerancia_pct') / 100)
        if tolerancia < 0:
            raise ParamError("'tolerancia' no puede ser negativa")
        # ±0,5 cubre el redondeo a pesos enteros
        qs = qs.filter(valortotalpesos__gte=monto - tolerancia - 0.5, valortotalpesos__lt=monto + tolerancia + 0.5)
    elif params.get('tolerancia') or params.get('tolerancia_pct'):
        raise ParamError("'tolerancia' requiere 'monto'")
    return qs


@csrf_exempt
@require_http_methods(['GET'])
@api_key_required
def facturas_list(request):
    try:
        qs = _filtrar_facturas(request.GET, _facturas_qs())
        if request.GET.get('monto'):
            # Búsqueda por monto: primero la más cercana al monto buscado
            monto = float(request.GET['monto'])
            qs = qs.annotate(dif=Func(F('valortotalpesos') - monto, function='ABS')).order_by('dif', '-fechaemision')
        else:
            qs = qs.order_by('-fechaemision', '-idfactura')
        facturas, meta = _paginate(request, qs)
    except ParamError as e:
        return _error(str(e))

    estados = _estados_factura()
    comentarios = seg.ultimos([f.idfactura for f in facturas])
    results = [_serialize_factura(f, estados, comentarios.get(f.idfactura)) for f in facturas]
    if request.GET.get('monto'):
        monto = float(request.GET['monto'])
        for r in results:
            r['diferencia'] = None if r['total'] is None else r['total'] - round(monto)
    return _json({**meta, 'results': results})


@csrf_exempt
@require_http_methods(['GET', 'PATCH'])
@api_key_required
def factura_detail(request, idfactura):
    factura = _facturas_qs().filter(pk=idfactura).first()
    if factura is None:
        return _error('Factura no encontrada', 404)

    if request.method == 'PATCH':
        try:
            _actualizar_factura(request, factura)
        except ParamError as e:
            return _error(str(e))
        factura = _facturas_qs().get(pk=idfactura)

    return _json(_serialize_factura_detalle(factura, _estados_factura()))


def _actualizar_factura(request, factura):
    """PATCH: cambia estado / fecha_pago y opcionalmente agrega un comentario. Deja traza en Factura_Seg."""
    data = _read_body(request)
    permitidos = {'estado', 'fecha_pago', 'comentario'}
    desconocidos = set(data) - permitidos
    if desconocidos:
        raise ParamError(f"Campos no permitidos: {', '.join(sorted(desconocidos))}. Use: {', '.join(sorted(permitidos))}")
    if not data:
        raise ParamError("Indique al menos uno de: estado, fecha_pago, comentario")

    estados = _estados_factura()
    nuevo_estado = factura.estado
    if 'estado' in data:
        if not isinstance(data['estado'], int) or data['estado'] not in estados:
            validos = ', '.join(f"{k}={v}" for k, v in sorted(estados.items()))
            raise ParamError(f"'estado' inválido. Valores: {validos}")
        nuevo_estado = data['estado']

    nueva_fecha_pago = factura.fechapago
    if 'fecha_pago' in data:
        nueva_fecha_pago = None if data['fecha_pago'] is None else _parse_date(data['fecha_pago'], 'fecha_pago')
        if nueva_fecha_pago and nueva_fecha_pago > timezone.localdate():
            raise ParamError("'fecha_pago' no puede ser futura")
    if nuevo_estado in ESTADOS_PAGADA and nueva_fecha_pago is None:
        raise ParamError(f"El estado {nuevo_estado} ({estados[nuevo_estado]}) requiere 'fecha_pago'")

    comentario = _clean_comentario(data['comentario']) if 'comentario' in data else None

    cambios = []
    if nuevo_estado != factura.estado:
        cambios.append(f"estado: {estados.get(factura.estado, factura.estado)} -> {estados[nuevo_estado]}")
    if nueva_fecha_pago != factura.fechapago:
        cambios.append(f"fecha de pago: {factura.fechapago or '-'} -> {nueva_fecha_pago or '-'}")

    usuario = request.api_key.usuario_seg
    with transaction.atomic():
        if cambios:
            Factura.objects.filter(pk=factura.pk).update(
                estado=nuevo_estado, fechapago=nueva_fecha_pago, fechaact=timezone.now())
            seg.agregar(factura.pk, f"[API] {'; '.join(cambios)}", usuario)
        if comentario:
            seg.agregar(factura.pk, comentario, usuario)
            if not cambios:
                Factura.objects.filter(pk=factura.pk).update(fechaact=timezone.now())


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@api_key_required
def factura_comentarios(request, idfactura):
    if not Factura.objects.filter(pk=idfactura).exists():
        return _error('Factura no encontrada', 404)

    if request.method == 'POST':
        try:
            comentario = _clean_comentario(_read_body(request).get('comentario'))
        except ParamError as e:
            return _error(str(e))
        with transaction.atomic():
            nuevo = seg.agregar(idfactura, comentario, request.api_key.usuario_seg)
            Factura.objects.filter(pk=idfactura).update(fechaact=timezone.now())
        return _json(nuevo, status=201)

    return _json(seg.listar(idfactura))


@csrf_exempt
@require_http_methods(['GET', 'PATCH'])
@api_key_required
def factura_comentario_detail(request, idfactura, idreg):
    actual = seg.obtener(idfactura, idreg)
    if actual is None:
        return _error('Comentario no encontrado', 404)

    if request.method == 'PATCH':
        if actual['usuario'] != request.api_key.usuario_seg:
            return _error('Solo se pueden editar comentarios creados con esta API Key', 403)
        try:
            comentario = _clean_comentario(_read_body(request).get('comentario'))
        except ParamError as e:
            return _error(str(e))
        with transaction.atomic():
            actual = seg.editar(idfactura, idreg, comentario)
            Factura.objects.filter(pk=idfactura).update(fechaact=timezone.now())

    return _json(actual)


@csrf_exempt
@require_http_methods(['GET'])
@api_key_required
def clientes_list(request):
    """Filtros: q (razón social o RUT), rut."""
    qs = Cliente.objects.all()
    try:
        if request.GET.get('rut'):
            qs = qs.filter(rut=_parse_rut(request.GET['rut']))
        q = request.GET.get('q', '').strip()
        if q:
            cond = Q(razonsocial__icontains=q)
            digits = q.split('-')[0].replace('.', '').strip()
            if digits.isdigit():
                cond |= Q(rut=int(digits))
            qs = qs.filter(cond)
        clientes, meta = _paginate(request, qs.order_by('razonsocial', 'idcliente'))
    except ParamError as e:
        return _error(str(e))
    return _json({**meta, 'results': [_serialize_cliente(c) for c in clientes]})
