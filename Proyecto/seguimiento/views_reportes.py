"""Reportes que reemplazan a los del sistema de escritorio.

Reporte de Facturas: une "Emitidas" (Rep_Factura1) y "Pagadas" (Rep_Factura2), que tenían las mismas columnas y
subtotales por año y mes. Cambiaba la fecha usada para filtrar y agrupar y, en Emitidas, los estados incluidos.
"""
import csv
from collections import OrderedDict
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from functools import wraps
from django.db import connection
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

GRUPO_DIRECTOR = 'Director'


def solo_grupos(*grupos):
    """Solo usuarios de alguno de los grupos indicados (o superusuarios). El resto recibe 403."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not (request.user.is_superuser or request.user.groups.filter(name__in=grupos).exists()):
                raise PermissionDenied('No tiene permiso para este reporte.')
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador


def solo_director(vista):
    """Solo usuarios del grupo Director (o superusuarios). El resto recibe 403."""
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.groups.filter(name=GRUPO_DIRECTOR).exists()):
            raise PermissionDenied('Solo para el perfil Director.')
        return vista(request, *args, **kwargs)
    return envoltura


TIPO_ESTADO_FACTURA = 3
# Emitidas: Estado >= 2 y no 6 (NULA) ni 7 (PAUSA), como Rep_Factura1
ESTADOS_EMITIDAS = [2, 3, 4, 5, 8]
MESES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre',
         'Noviembre', 'Diciembre']


def _estados_factura():
    with connection.cursor() as cursor:
        cursor.execute('SELECT CodEstado, Descrip FROM tEstado WHERE TipoEstado = %s ORDER BY CodEstado',
                       [TIPO_ESTADO_FACTURA])
        return [(cod, (descrip or '').strip()) for cod, descrip in cursor.fetchall()]


def _fecha(valor, defecto):
    try:
        return date.fromisoformat(valor) if valor else defecto
    except ValueError:
        return defecto


def _pesos(valor):
    return f"{float(valor or 0):,.0f}".replace(',', '.')


def _rut(rut, dv):
    return f"{int(rut)}-{dv or ''}" if rut is not None else ''


def _consulta(campo_fecha, desde, hasta, estados, cliente, proyecto):
    columna = 'a.FechaPago' if campo_fecha == 'pago' else 'a.FechaEmision'
    sql = [f'''
        SELECT YEAR({columna}), MONTH({columna}), a.NumFactura, a.FechaEmision, b.RazonSocial, b.Rut, b.DVrut,
               d.NombreProyecto, a.ValorTotalPesos, a.FechaPago, a.Estado, a.IdProyecto
          FROM Factura a
          LEFT OUTER JOIN Cliente b ON b.IdCliente = a.IdCliente
          LEFT OUTER JOIN Proyecto c ON c.IdProyecto = a.IdProyecto
          LEFT OUTER JOIN Cotizacion d ON d.IdCotizacion = c.IdCotizacion
         WHERE {columna} BETWEEN %s AND %s''']
    params = [desde, hasta]
    if estados:
        sql.append(f"AND a.Estado IN ({', '.join(['%s'] * len(estados))})")
        params += estados
    if cliente:
        digitos = cliente.split('-')[0].replace('.', '').strip()
        if digitos.isdigit():
            sql.append('AND (b.RazonSocial LIKE %s OR b.Rut = %s)')
            params += [f'%{cliente}%', int(digitos)]
        else:
            sql.append('AND b.RazonSocial LIKE %s')
            params.append(f'%{cliente}%')
    if proyecto:
        if proyecto.isdigit():
            sql.append('AND (d.NombreProyecto LIKE %s OR a.IdProyecto = %s)')
            params += [f'%{proyecto}%', int(proyecto)]
        else:
            sql.append('AND d.NombreProyecto LIKE %s')
            params.append(f'%{proyecto}%')
    sql.append('ORDER BY 1, 2, 3')
    with connection.cursor() as cursor:
        cursor.execute(' '.join(sql), params)
        return cursor.fetchall()


@login_required
@solo_director
@require_GET
def reporte_facturas(request):
    hoy = timezone.localdate()
    estados_catalogo = _estados_factura()
    validos = {c for c, _ in estados_catalogo}
    consultado = 'desde' in request.GET

    campo_fecha = 'pago' if request.GET.get('fecha') == 'pago' else 'emision'
    desde = _fecha(request.GET.get('desde'), hoy.replace(day=1))
    hasta = _fecha(request.GET.get('hasta'), hoy)
    if hasta < desde:
        desde, hasta = hasta, desde
    if consultado:
        estados = sorted({int(e) for e in request.GET.getlist('estado') if e.isdigit()} & validos)
    else:
        estados = list(ESTADOS_EMITIDAS)  # al abrir: como el reporte "Emitidas" del escritorio
    cliente = (request.GET.get('cliente') or '').strip()[:80]
    proyecto = (request.GET.get('proyecto') or '').strip()[:80]

    nombres_estado = dict(estados_catalogo)
    filas = [{
        'agno': r[0], 'mes': r[1],
        'numfactura': int(r[2]),
        'fecha_emision': r[3].strftime('%d/%m/%Y') if r[3] else '',
        'cliente': r[4] or '',
        'rut': _rut(r[5], r[6]),
        'proyecto': r[7] or '',
        'idproyecto': int(r[11]) if r[11] is not None else '',
        'total': float(r[8] or 0),
        'fecha_pago': r[9].strftime('%d/%m/%Y') if r[9] else '',
        'estado': nombres_estado.get(r[10], ''),
    } for r in _consulta(campo_fecha, desde, hasta, estados, cliente, proyecto)]

    if request.GET.get('formato') == 'csv':
        return _csv(filas, campo_fecha, desde, hasta)

    # Agrupación por año y mes con subtotales, como el reporte del escritorio
    grupos = OrderedDict()
    for f in filas:
        anio = grupos.setdefault(f['agno'], {'meses': OrderedDict(), 'total': 0.0, 'cantidad': 0})
        mes = anio['meses'].setdefault(f['mes'], {'nombre': MESES[f['mes']], 'filas': [], 'total': 0.0})
        mes['filas'].append({**f, 'total_texto': _pesos(f['total'])})
        mes['total'] += f['total']
        anio['total'] += f['total']
        anio['cantidad'] += 1
    for anio in grupos.values():
        anio['total_texto'] = _pesos(anio['total'])
        for mes in anio['meses'].values():
            mes['total_texto'] = _pesos(mes['total'])

    return render(request, 'reporte_facturas.html', {
        'titulo': 'Reporte de Facturas',
        'encabezado': 'Reporte de Facturas',
        'menu': 'Facturas',
        'submenu': 'Reporte de Facturas',
        'grupos': grupos,
        'cantidad': len(filas),
        'total_texto': _pesos(sum(f['total'] for f in filas)),
        'campo_fecha': campo_fecha,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'estados_catalogo': [{'codigo': c, 'nombre': n, 'marcado': c in estados} for c, n in estados_catalogo],
        'estados_emitidas': ESTADOS_EMITIDAS,
        'cliente': cliente,
        'proyecto': proyecto,
        'query_csv': request.GET.urlencode(),
    })


def _csv(filas, campo_fecha, desde, hasta):
    nombre = f"facturas_{'pagadas' if campo_fecha == 'pago' else 'emitidas'}_{desde:%Y%m%d}_{hasta:%Y%m%d}.csv"
    resp = HttpResponse(content_type='text/csv; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="{nombre}"'
    resp.write('﻿')  # BOM: Excel reconoce los acentos
    w = csv.writer(resp, delimiter=';')
    w.writerow(['Año', 'Mes', 'N° Factura', 'F. Emisión', 'Razón Social', 'RUT', 'N° Proyecto', 'Proyecto',
                'Estado', 'F. Pago', 'Valor Total Pesos'])
    for f in filas:
        w.writerow([f['agno'], f['mes'], f['numfactura'], f['fecha_emision'], f['cliente'], f['rut'], f['idproyecto'],
                    f['proyecto'], f['estado'], f['fecha_pago'], round(f['total'])])
    w.writerow([])
    w.writerow(['', '', '', '', '', '', '', '', '', 'Total', round(sum(f['total'] for f in filas))])
    return resp


# ---------------------------------------------------------------------------------------------------------------
# Reporte de Adjudicaciones (REP_Adjudicacion / Report4 del escritorio)
# ---------------------------------------------------------------------------------------------------------------

def _uf(valor):
    return f"{float(valor or 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def _anios_adjudicacion():
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC Consulta_AgnoAdjudicacion')
        return [int(r[0]) for r in cursor.fetchall()]


def _adjudicaciones(desde_anio):
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC REP_Adjudicacion %s', [desde_anio])
        return [{
            'agno': int(r[0]),
            'mes': (r[1] or '').strip(),
            'idproyecto': int(r[2]),
            'cotizacion': r[3] or '',
            'proyecto': r[4] or '',
            'moneda': r[5] or '',
            'valor_uf': float(r[6] or 0),
            'valor_peso': float(r[7] or 0),
            'mandante': r[8] or '',
            'estado': (r[9] or '').strip(),
            'adjudicacion': r[10] or '',
        } for r in cursor.fetchall()]


@login_required
@solo_grupos(GRUPO_DIRECTOR, 'Facturación')  # en el escritorio, solo el perfil 0
@require_GET
def reporte_adjudicaciones(request):
    anios = _anios_adjudicacion()
    try:
        desde_anio = int(request.GET.get('desde') or 0)
    except ValueError:
        desde_anio = 0
    if desde_anio not in anios:
        desde_anio = anios[0] if anios else timezone.localdate().year  # al abrir: el año más reciente
    filas = _adjudicaciones(desde_anio)

    if request.GET.get('formato') == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="adjudicaciones_desde_{desde_anio}.csv"'
        resp.write('﻿')
        w = csv.writer(resp, delimiter=';')
        w.writerow(['Año', 'Mes', 'N° Proyecto', 'N° Cot.', 'Proyecto', 'Moneda', 'Valor UF', 'Valor Peso', 'Mandante',
                    'Estado', 'Adjudicación'])
        for f in filas:
            w.writerow([f['agno'], f['mes'], f['idproyecto'], f['cotizacion'], f['proyecto'], f['moneda'],
                        str(round(f['valor_uf'], 2)).replace('.', ','), round(f['valor_peso']), f['mandante'],
                        f['estado'], f['adjudicacion']])
        w.writerow([])
        w.writerow(['', '', '', '', f'Total ({len(filas)} proyectos)', '',
                    str(round(sum(f['valor_uf'] for f in filas), 2)).replace('.', ','),
                    round(sum(f['valor_peso'] for f in filas))])
        return resp

    grupos = OrderedDict()
    for f in filas:
        anio = grupos.setdefault(f['agno'], {'meses': OrderedDict(), 'uf': 0.0, 'peso': 0.0, 'cantidad': 0})
        mes = anio['meses'].setdefault(f['mes'], {'filas': [], 'uf': 0.0, 'peso': 0.0})
        mes['filas'].append({**f, 'uf_texto': _uf(f['valor_uf']), 'peso_texto': _pesos(f['valor_peso'])})
        for g in (mes, anio):
            g['uf'] += f['valor_uf']
            g['peso'] += f['valor_peso']
        anio['cantidad'] += 1
    for anio in grupos.values():
        anio['uf_texto'], anio['peso_texto'] = _uf(anio['uf']), _pesos(anio['peso'])
        for mes in anio['meses'].values():
            mes['cantidad'] = len(mes['filas'])
            mes['uf_texto'], mes['peso_texto'] = _uf(mes['uf']), _pesos(mes['peso'])

    return render(request, 'reporte_adjudicaciones.html', {
        'titulo': 'Reporte de Adjudicaciones',
        'encabezado': 'Reporte de Proyectos Adjudicados',
        'menu': 'Proyectos',
        'submenu': 'Reporte de Adjudicaciones',
        'anios': anios,
        'desde_anio': desde_anio,
        'grupos': grupos,
        'cantidad': len(filas),
        'total_uf': _uf(sum(f['valor_uf'] for f in filas)),
        'total_peso': _pesos(sum(f['valor_peso'] for f in filas)),
    })
