from datetime import date, datetime

from django.core.paginator import Paginator
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from seguimiento.models import Factura

from .auth import api_key_required

PAGE_SIZE_DEFAULT = 100
PAGE_SIZE_MAX = 500


class ParamError(ValueError):
    pass


def _parse_date(value, name):
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ParamError(f"'{name}' debe tener formato AAAA-MM-DD")


def _parse_datetime(value, name):
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ParamError(f"'{name}' debe tener formato ISO 8601 (AAAA-MM-DD o AAAA-MM-DDTHH:MM:SS)")


def _parse_int(value, name):
    try:
        return int(value)
    except ValueError:
        raise ParamError(f"'{name}' debe ser un número entero")


TIPO_ESTADO_FACTURA = 3  # tEstado.TipoEstado: 1=cotización, 2=proyecto, 3=factura


def _estados_factura():
    with connection.cursor() as cursor:
        cursor.execute('SELECT CodEstado, Descrip FROM tEstado WHERE TipoEstado = %s', [TIPO_ESTADO_FACTURA])
        return {cod: descrip.strip() if descrip else descrip for cod, descrip in cursor.fetchall()}


def _num(value):
    return None if value is None else float(value)


def _serialize_factura(f, estados):
    cliente = f.idcliente
    contacto = f.idcontacto
    return {
        'idfactura': f.idfactura,
        'numfactura': int(f.numfactura) if f.numfactura is not None else None,
        'fechaemision': f.fechaemision,
        'fechapago': f.fechapago,
        'estado': f.estado,
        'estado_nombre': estados.get(f.estado),
        'detalle': f.detalle,
        'moneda': f.moneda,
        'montomonorig': f.montomonorig,
        'valortotal': f.valortotal,
        'valoruf': _num(f.valoruf),
        'valortotalpesos': f.valortotalpesos,
        'porcfact': f.porcfact,
        'vencimiento': f.vencimiento,
        'numhes_eepp': f.numhes_eepp,
        'fechahes_eepp': f.fechahes_eepp,
        'idproyecto': int(f.idproyecto_id) if f.idproyecto_id is not None else None,
        'cliente': {
            'idcliente': cliente.idcliente,
            'rut': f"{int(cliente.rut)}-{cliente.dvrut or ''}" if cliente.rut is not None else None,
            'razonsocial': cliente.razonsocial,
        } if cliente else None,
        'contacto': {
            'idcontacto': contacto.idcontacto,
            'nombre': contacto.nombrecontacto,
            'email': contacto.email,
            'telefono': contacto.telefono,
        } if contacto else None,
        'fecharegistro': f.fecharegistro,
        'fechaact': f.fechaact,
    }


def _base_queryset():
    return Factura.objects.select_related('idcliente', 'idcontacto')


@require_GET
@api_key_required
def facturas_list(request):
    """
    Filtros (query string, todos opcionales):
      desde, hasta            fecha de emisión (AAAA-MM-DD)
      modificado_desde        FechaACT >= valor (para sincronización incremental)
      idcliente, rut          cliente (rut sin dígito verificador)
      idproyecto, numfactura, estado
      page, page_size         paginación (page_size máx. 500)
    """
    params = request.GET
    qs = _base_queryset()
    try:
        if params.get('desde'):
            qs = qs.filter(fechaemision__gte=_parse_date(params['desde'], 'desde'))
        if params.get('hasta'):
            qs = qs.filter(fechaemision__lte=_parse_date(params['hasta'], 'hasta'))
        if params.get('modificado_desde'):
            qs = qs.filter(fechaact__gte=_parse_datetime(params['modificado_desde'], 'modificado_desde'))
        if params.get('idcliente'):
            qs = qs.filter(idcliente_id=_parse_int(params['idcliente'], 'idcliente'))
        if params.get('rut'):
            rut = params['rut'].split('-')[0].replace('.', '')
            qs = qs.filter(idcliente__rut=_parse_int(rut, 'rut'))
        if params.get('idproyecto'):
            qs = qs.filter(idproyecto_id=_parse_int(params['idproyecto'], 'idproyecto'))
        if params.get('numfactura'):
            qs = qs.filter(numfactura=_parse_int(params['numfactura'], 'numfactura'))
        if params.get('estado'):
            qs = qs.filter(estado=_parse_int(params['estado'], 'estado'))

        page_number = _parse_int(params.get('page', '1'), 'page')
        page_size = _parse_int(params.get('page_size', str(PAGE_SIZE_DEFAULT)), 'page_size')
    except ParamError as e:
        return JsonResponse({'error': str(e)}, status=400)

    page_size = max(1, min(page_size, PAGE_SIZE_MAX))
    paginator = Paginator(qs.order_by('-fechaemision', '-idfactura'), page_size)
    if page_number < 1 or (page_number > paginator.num_pages and paginator.count):
        return JsonResponse({'error': f"'page' fuera de rango (1-{paginator.num_pages})"}, status=400)
    page = paginator.page(page_number) if paginator.count else []

    estados = _estados_factura()
    return JsonResponse({
        'count': paginator.count,
        'page': page_number,
        'page_size': page_size,
        'num_pages': paginator.num_pages if paginator.count else 0,
        'results': [_serialize_factura(f, estados) for f in page],
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
@api_key_required
def factura_detail(request, idfactura):
    factura = _base_queryset().filter(pk=idfactura).first()
    if factura is None:
        return JsonResponse({'error': 'Factura no encontrada'}, status=404)
    return JsonResponse(_serialize_factura(factura, _estados_factura()),
                        json_dumps_params={'ensure_ascii': False})
