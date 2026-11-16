"""Endpoints de proyectos y cotizaciones."""
from collections import defaultdict

from django.db import transaction
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from seguimiento.models import (
    Cotizacion, CotizacionFpago, CotizacionNota, CotizacionValor, EntregaProyecto, Estadocotizacion, Factura,
    Proyecto, Tregion, estadoproyecto,
)

from . import seg
from .auth import api_key_required
from .models import ApiCambio
from .views import (
    ParamError, _clean_comentario, _error, _estados_factura, _json, _paginate, _parse_date, _parse_int,
    _parse_int_list, _parse_rut, _pesos, _read_body, _serialize_cliente,
)

ESTADO_FACTURA_NULA = 6
ESTADO_ENTREGA_ENTREGADA = 5  # T_EstadosEntrega: 'Entregado a Cliente'


# ---------------------------------------------------------------- utilidades

def _num(value):
    """Decimal/float de la BD -> int si es entero, si no float."""
    if value is None:
        return None
    value = float(value)
    return int(value) if value.is_integer() else round(value, 4)


def _numero_cotizacion(c):
    numero = int(c.numcotizacion) if c.numcotizacion is not None else c.idcotizacion
    return f"{numero}-{(c.numcorr or 0):03d}"


def _regiones(codigos):
    codigos = {c for c in codigos if c is not None}
    if not codigos:
        return {}
    return dict(Tregion.objects.filter(codregion__in=codigos).values_list('codregion', 'descrip'))


def _estado(obj):
    return {'id': obj.pk, 'nombre': obj.nombre} if obj else None


def _filtrar_por_cliente(params, qs, campos):
    """Filtra por idcliente o rut en cualquiera de los campos de cliente indicados."""
    if params.get('idcliente'):
        idcliente = _parse_int(params['idcliente'], 'idcliente')
        cond = Q()
        for campo in campos:
            cond |= Q(**{f'{campo}_id': idcliente})
        qs = qs.filter(cond)
    if params.get('rut'):
        rut = _parse_rut(params['rut'])
        cond = Q()
        for campo in campos:
            cond |= Q(**{f'{campo}__rut': rut})
        qs = qs.filter(cond)
    return qs


def _es_seremi(valor):
    """Item de SEREMI según su glosa (el número de item es solo la posición en la cotización)."""
    return 'SEREMI' in (valor.glosa or '').upper()


def _local(dt):
    """Las fechas-hora se guardan en hora local de Chile sin zona; el ORM las marca como UTC. Se devuelven sin zona."""
    return dt.replace(tzinfo=None) if dt is not None and dt.tzinfo is not None else dt


def _resumen_items(valores):
    """Montos (sin y con opcionales) y si la cotización incluye trámite SEREMI."""
    monto = sum(float(v.valor or 0) for v in valores if (v.opcional or 'N') != 'S')
    monto_con_opcionales = sum(float(v.valor or 0) for v in valores)
    seremi = [v for v in valores if _es_seremi(v)]
    return {
        'monto': _num(monto),
        'monto_con_opcionales': _num(monto_con_opcionales),
        'incluye_tramite_seremi': any((v.opcional or 'N') != 'S' for v in seremi),
        'tramite_seremi_opcional': any((v.opcional or 'N') == 'S' for v in seremi),
    }


def _serialize_items(valores):
    return [{
        'item': v.item,
        'glosa': v.glosa,
        'valor': _num(v.valor),
        'opcional': (v.opcional or 'N') == 'S',
        'seremi': _es_seremi(v),
    } for v in valores]


def _valores_por_cotizacion(ids):
    por_cot = defaultdict(list)
    for v in CotizacionValor.objects.filter(idcotizacion_id__in=list(ids)).order_by('item'):
        por_cot[v.idcotizacion_id].append(v)
    return por_cot


def _facturado_por_proyecto(proyectos):
    """{idproyecto: % facturado}. Usa PorcFact de cada factura no nula o, si falta, su monto / valor del proyecto."""
    valor = {int(p.idproyecto): float(p.valor or 0) for p in proyectos}
    if not valor:
        return {}
    porcentaje = defaultdict(float)
    filas = Factura.objects.filter(idproyecto_id__in=list(valor)).exclude(estado=ESTADO_FACTURA_NULA) \
        .values_list('idproyecto_id', 'porcfact', 'valortotal')
    for idproyecto, porcfact, valortotal in filas:
        idproyecto = int(idproyecto)
        if porcfact is not None:
            porcentaje[idproyecto] += float(porcfact)
        elif valortotal is not None and valor[idproyecto] > 0:
            porcentaje[idproyecto] += float(valortotal) / valor[idproyecto] * 100
    return {pid: round(porcentaje.get(pid, 0.0), 2) for pid in valor}


# ---------------------------------------------------------------- proyectos

def _proyectos_qs():
    return Proyecto.objects.select_related('idcliente', 'estadoproyecto', 'idcotizacion__idcliente')


def _serialize_proyecto(p, comentario, porcentaje, regiones):
    cot = p.idcotizacion
    monto = _num(p.valor)
    return {
        'idproyecto': int(p.idproyecto),
        'nombre': cot.nombreproyecto,
        'direccion': cot.dirproyecto,
        'region': regiones.get(cot.codregion),
        'fecha_creacion': p.fechacreacion,
        'estado': _estado(p.estadoproyecto),
        'cliente': _serialize_cliente(p.idcliente),
        'mandante': _serialize_cliente(cot.idcliente),
        'cotizacion': {'idcotizacion': cot.idcotizacion, 'numero': _numero_cotizacion(cot)},
        'moneda': p.moneda or None,
        'monto': monto,
        'monto_uf': monto if p.moneda == 'UF' else None,
        'porcentaje_facturado': porcentaje,
        'fecha_ultimo_seguimiento': p.fechaultseg,
        'ultimo_comentario': comentario,
    }


def _serialize_proyecto_detalle(p):
    cot = p.idcotizacion
    valores = list(CotizacionValor.objects.filter(idcotizacion=cot).order_by('item'))
    resumen = _resumen_items(valores)
    porcentaje = _facturado_por_proyecto([p])[int(p.idproyecto)]
    comentarios = seg.proyecto.listar(p.idproyecto)
    data = _serialize_proyecto(p, comentarios[0]['comentario'] if comentarios else None, porcentaje,
                               _regiones([cot.codregion]))

    entregas = list(EntregaProyecto.objects.filter(idproyecto=p).select_related('idtipoentrega', 'idestadoentrega')
                    .order_by('fechaentrega', 'identrega'))
    estados_factura = _estados_factura()
    facturas = list(Factura.objects.filter(idproyecto=p).order_by('fechaemision', 'idfactura'))
    contacto = p.idcontactofacturacion

    data.update({
        'forma_pago': p.fpago,
        'contacto_facturacion': {
            'idcontacto': contacto.idcontacto,
            'nombre': contacto.nombrecontacto,
            'email': p.emailcontactofacturacion or contacto.email,
            'telefono': contacto.telefono,
        } if contacto else None,
        'confirmacion': {'numero': p.numconf, 'medio': p.medioconf, 'fecha': p.fechaconf},
        'requiere': {'hes': p.conhes == 'S', 'eepp': p.coneepp == 'S', 'otro': p.conotro == 'S'},
        'incobrable': bool(p.incobrable),
        'seremi': {
            'n_tramite': p.ntramiteseremi,
            'fecha_solicitud_ingreso': p.fechasolingreso,
            'fecha_ingreso': p.fechaingresoseremi,
            'fecha_aprobacion': p.fechaaprobseremi,
            'arancel': _num(p.arancel),
            'fecha_pago_arancel': p.fechapagoarancel,
            'fecha_ingreso_timbraje': p.fechaingresotimbraje,
            'fecha_aprobacion_timbraje': p.fechaaprobtimbraje,
        },
        'cotizacion': {
            'idcotizacion': cot.idcotizacion,
            'numero': _numero_cotizacion(cot),
            'fecha': cot.fecha,
            'moneda': cot.moneda,
            **resumen,
            'monto_uf': resumen['monto'] if cot.moneda == 'UF' else None,
            'items': _serialize_items(valores),
            'forma_pago': list(CotizacionFpago.objects.filter(idcotizacion=cot).order_by('linea')
                               .values_list('concepto', flat=True)),
        },
        'versiones_entregadas': sum(1 for e in entregas if e.idestadoentrega_id == ESTADO_ENTREGA_ENTREGADA),
        'entregas': [{
            'identrega': e.identrega,
            'tipo': e.idtipoentrega.descripcion if e.idtipoentrega else None,
            'estado': e.idestadoentrega.descrip if e.idestadoentrega else None,
            'entregada': e.idestadoentrega_id == ESTADO_ENTREGA_ENTREGADA,
            'fecha_entrega': e.fechaentrega,
            'fecha_creacion': _local(e.fechacreacion),
        } for e in entregas],
        'facturas': [{
            'idfactura': f.idfactura,
            'folio': int(f.numfactura) if f.numfactura is not None else None,
            'fecha_emision': f.fechaemision,
            'total': _pesos(f.valortotalpesos),
            'porcentaje': _num(f.porcfact),
            'estado': f.estado,
            'estado_nombre': estados_factura.get(f.estado),
        } for f in facturas],
    })
    return data


@csrf_exempt
@require_http_methods(['GET'])
@api_key_required()
def proyectos_list(request):
    """Filtros: estado (ids con comas), idcliente, rut (cliente o mandante), desde, hasta (fecha de creación), q."""
    params = request.GET
    qs = _proyectos_qs()
    try:
        if params.get('estado'):
            qs = qs.filter(estadoproyecto_id__in=_parse_int_list(params['estado'], 'estado'))
        qs = _filtrar_por_cliente(params, qs, ['idcliente', 'idcotizacion__idcliente'])
        if params.get('desde'):
            qs = qs.filter(fechacreacion__gte=_parse_date(params['desde'], 'desde'))
        if params.get('hasta'):
            qs = qs.filter(fechacreacion__lte=_parse_date(params['hasta'], 'hasta'))
        q = params.get('q', '').strip()
        if q:
            cond = Q(idcotizacion__nombreproyecto__icontains=q)
            if q.isdigit():
                cond |= Q(idproyecto=int(q)) | Q(idcotizacion__numcotizacion=int(q))
            qs = qs.filter(cond)
        proyectos, meta = _paginate(request, qs.order_by('-idproyecto'))
    except ParamError as e:
        return _error(str(e))

    comentarios = seg.proyecto.ultimos(int(p.idproyecto) for p in proyectos)
    porcentajes = _facturado_por_proyecto(proyectos)
    regiones = _regiones(p.idcotizacion.codregion for p in proyectos)
    results = [_serialize_proyecto(p, comentarios.get(int(p.idproyecto)), porcentajes[int(p.idproyecto)], regiones)
               for p in proyectos]
    return _json({**meta, 'results': results})


@csrf_exempt
@require_http_methods(['GET', 'PATCH'])
@api_key_required({'PATCH': 'editar'})
def proyecto_detail(request, idproyecto):
    proyecto = _proyectos_qs().select_related('idcontactofacturacion').filter(pk=idproyecto).first()
    if proyecto is None:
        return _error('Proyecto no encontrado', 404)

    if request.method == 'PATCH':
        try:
            _actualizar_proyecto(request, proyecto)
        except ParamError as e:
            return _error(str(e))
        proyecto = _proyectos_qs().select_related('idcontactofacturacion').get(pk=idproyecto)

    return _json(_serialize_proyecto_detalle(proyecto))


def _actualizar_proyecto(request, proyecto):
    """PATCH: cambia el estado (exige comentario, igual que la web) y/o agrega un comentario a la bitácora."""
    data = _read_body(request)
    permitidos = {'estado', 'comentario'}
    desconocidos = set(data) - permitidos
    if desconocidos:
        raise ParamError(f"Campos no permitidos: {', '.join(sorted(desconocidos))}. Use: {', '.join(sorted(permitidos))}")
    if not data:
        raise ParamError("Indique al menos uno de: estado, comentario")

    estados = dict(estadoproyecto.objects.values_list('id', 'nombre'))
    estado_actual = proyecto.estadoproyecto_id
    nuevo_estado = estado_actual
    if 'estado' in data:
        if not isinstance(data['estado'], int) or isinstance(data['estado'], bool) or data['estado'] not in estados:
            validos = ', '.join(f"{k}={v.strip()}" for k, v in sorted(estados.items()))
            raise ParamError(f"'estado' inválido. Valores: {validos}")
        nuevo_estado = data['estado']

    comentario = _clean_comentario(data['comentario']) if 'comentario' in data else None
    cambia_estado = nuevo_estado != estado_actual
    if cambia_estado and not comentario:
        raise ParamError("Para cambiar el estado se requiere 'comentario', igual que en la aplicación web")

    usuario = request.api_key.usuario_seg
    with transaction.atomic():
        if cambia_estado:
            # La web guarda el mismo valor en Estado y estadoproyecto_id
            Proyecto.objects.filter(pk=proyecto.pk).update(estadoproyecto_id=nuevo_estado, estado=nuevo_estado)
            ApiCambio.registrar(request, 'proyecto', int(proyecto.pk), 'editar',
                                antes={'estado': estado_actual}, despues={'estado': nuevo_estado})
        if comentario:
            if cambia_estado:
                comentario = f"[API] Estado: {(estados.get(estado_actual) or '-').strip()} -> " \
                             f"{estados[nuevo_estado].strip()}. {comentario}"
            nuevo = seg.proyecto.agregar(proyecto.pk, comentario, usuario, estado=nuevo_estado)
            ApiCambio.registrar(request, 'proyecto_comentario', f"{int(proyecto.pk)}/{nuevo['idreg']}", 'comentar',
                                despues={'comentario': comentario})


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@api_key_required({'POST': 'comentar'})
def proyecto_comentarios(request, idproyecto):
    proyecto = Proyecto.objects.filter(pk=idproyecto).only('idproyecto', 'estadoproyecto_id').first()
    if proyecto is None:
        return _error('Proyecto no encontrado', 404)

    if request.method == 'POST':
        try:
            comentario = _clean_comentario(_read_body(request).get('comentario'))
        except ParamError as e:
            return _error(str(e))
        with transaction.atomic():
            nuevo = seg.proyecto.agregar(proyecto.pk, comentario, request.api_key.usuario_seg,
                                         estado=proyecto.estadoproyecto_id)
            ApiCambio.registrar(request, 'proyecto_comentario', f"{int(proyecto.pk)}/{nuevo['idreg']}", 'comentar',
                                despues={'comentario': comentario})
        return _json(nuevo, status=201)

    return _json(seg.proyecto.listar(proyecto.pk))


@csrf_exempt
@require_http_methods(['GET'])
@api_key_required()
def proyecto_estados(request):
    return _json([{'id': k, 'nombre': v.strip()} for k, v in estadoproyecto.objects.order_by('id').values_list('id', 'nombre')])


# ---------------------------------------------------------------- cotizaciones

def _cotizaciones_qs():
    return Cotizacion.objects.select_related('idcliente', 'idcontacto', 'estadocotizacion')


def _proyectos_por_cotizacion(ids):
    por_cot = defaultdict(list)
    for idcot, idproy in Proyecto.objects.filter(idcotizacion_id__in=list(ids)).values_list('idcotizacion_id', 'idproyecto'):
        por_cot[idcot].append(int(idproy))
    return por_cot


def _serialize_cotizacion(c, valores, proyectos, regiones):
    resumen = _resumen_items(valores)
    return {
        'idcotizacion': c.idcotizacion,
        'numero': _numero_cotizacion(c),
        'fecha': c.fecha,
        'nombre_proyecto': c.nombreproyecto,
        'direccion': c.dirproyecto,
        'region': regiones.get(c.codregion),
        'estado': _estado(c.estadocotizacion),
        'cliente': _serialize_cliente(c.idcliente),
        'moneda': c.moneda,
        **resumen,
        'monto_uf': resumen['monto'] if c.moneda == 'UF' else None,
        'proyectos': proyectos,
    }


@csrf_exempt
@require_http_methods(['GET'])
@api_key_required()
def cotizaciones_list(request):
    """Filtros: estado (ids con comas), idcliente, rut, desde, hasta (fecha), q (nombre o número)."""
    params = request.GET
    qs = _cotizaciones_qs()
    try:
        if params.get('estado'):
            qs = qs.filter(estadocotizacion_id__in=_parse_int_list(params['estado'], 'estado'))
        qs = _filtrar_por_cliente(params, qs, ['idcliente'])
        if params.get('desde'):
            qs = qs.filter(fecha__gte=_parse_date(params['desde'], 'desde'))
        if params.get('hasta'):
            qs = qs.filter(fecha__lte=_parse_date(params['hasta'], 'hasta'))
        q = params.get('q', '').strip()
        if q:
            cond = Q(nombreproyecto__icontains=q)
            numero = q.split('-')[0]
            if numero.isdigit():
                cond |= Q(numcotizacion=int(numero))
            qs = qs.filter(cond)
        cotizaciones, meta = _paginate(request, qs.order_by('-fecha', '-idcotizacion'))
    except ParamError as e:
        return _error(str(e))

    ids = [c.idcotizacion for c in cotizaciones]
    valores = _valores_por_cotizacion(ids)
    proyectos = _proyectos_por_cotizacion(ids)
    regiones = _regiones(c.codregion for c in cotizaciones)
    results = [_serialize_cotizacion(c, valores[c.idcotizacion], proyectos[c.idcotizacion], regiones)
               for c in cotizaciones]
    return _json({**meta, 'results': results})


@csrf_exempt
@require_http_methods(['GET'])
@api_key_required()
def cotizacion_detail(request, idcotizacion):
    c = _cotizaciones_qs().filter(pk=idcotizacion).first()
    if c is None:
        return _error('Cotización no encontrada', 404)

    valores = list(CotizacionValor.objects.filter(idcotizacion=c).order_by('item'))
    data = _serialize_cotizacion(c, valores, _proyectos_por_cotizacion([c.pk])[c.pk], _regiones([c.codregion]))
    contacto = c.idcontacto
    data.update({
        'version': c.numcorr or 0,
        'destino': c.destino,
        'pisos': c.pisos,
        'edificios': c.edificios,
        'm2': c.mt2,
        'contacto': {
            'idcontacto': contacto.idcontacto,
            'nombre': contacto.nombrecontacto,
            'email': contacto.email,
            'telefono': contacto.telefono,
        } if contacto else None,
        'fecha_aceptacion': c.fechaaceptacion,
        'items': _serialize_items(valores),
        'forma_pago': list(CotizacionFpago.objects.filter(idcotizacion=c).order_by('linea')
                           .values_list('concepto', flat=True)),
        'notas': list(CotizacionNota.objects.filter(idcotizacion=c).order_by('idcotizacionnota')
                      .values_list('idnota__nota', flat=True)),
    })
    return _json(data)


@csrf_exempt
@require_http_methods(['GET'])
@api_key_required()
def cotizacion_estados(request):
    return _json([{'id': e.pk, 'nombre': e.nombre} for e in Estadocotizacion.objects.order_by('pk')])
