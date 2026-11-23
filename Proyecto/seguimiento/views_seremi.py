"""Seguimiento Ingreso SEREMI: réplica web de SEGProyectoSeremi del sistema VB.NET.

Pantallas del escritorio que reúne: SEGProyectoSeremi (listado), ProyectoSeremi (datos del trámite),
VisorProyectoSeremi (ficha y cambio de estado) y SeguimientoSeremi (bitácora ducto.ProyectoSeremi_SEG).
Las vistas leen la solicitud y arman la respuesta; datos, procedimientos y reglas están en servicios.seremi.
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .servicios import proyectos as srv_proyectos
from .servicios import seremi as srv
from .servicios.seremi import ErrorValidacion

ESTADOS_SEREMI_LISTADO = (4, 5, 6, 11, 12, 13, 14, 16, 17)  # los que muestra el listado por defecto
TIPOS_FILTRO = [(1, 'N° Proy.'), (2, 'Proyecto'), (3, 'N° Trámite')]
COLORES_OSCUROS = {'purple', 'dodgerblue', 'saddlebrown', 'green', 'red'}


def _usuario(request):
    return (request.user.username or '')[:50]


def _fila(r):
    color = (r.get('Color') or 'White').strip()
    return {
        'idproyecto': int(r['N° Proyecto']),
        'nombre': r['NombreProyecto'] or '',
        'propietario_rut': (r['Propietario-Rut'] or '').strip('-'),
        'operador': r['Operador'] or '',
        'n_tramite': r['NtramiteSeremi'] or '',
        'estado': (r['Estado'] or '').strip(),
        'cod_estado': r['CodEstado'],
        'ultimo_seg': r['UltimoSegSeremi'] or '',
        'mandante': r['Mandante'] or '',
        'ingreso_seremi': r['FecIngresoSeremi'] or '',
        'color': color,
        'texto_claro': color.lower() in COLORES_OSCUROS,
    }


@login_required
@require_GET
def seremi_seguimiento(request):
    estados = srv.estados()
    validos = {cod for cod, _ in estados}
    # Estados con selección múltiple. Al abrir: los del listado por defecto del escritorio.
    filtrado = 'filtrado' in request.GET or 'estado' in request.GET
    if request.GET.get('todo') == '1':
        estados_sel = sorted(validos)
    elif filtrado:
        estados_sel = sorted({int(e) for e in request.GET.getlist('estado') if e.strip().isdigit()} & validos)
    else:
        estados_sel = list(ESTADOS_SEREMI_LISTADO)
    try:
        tipo = int(request.GET.get('tipo') or 0)
    except ValueError:
        tipo = 0
    texto = (request.GET.get('texto') or '').strip()
    error = ''

    if texto and tipo in dict(TIPOS_FILTRO):
        if tipo == 1 and not texto.isdigit():
            error = 'El N° de proyecto debe ser un número.'
            filas = []
        else:
            filas = srv.consultar(tipo, None, texto[:80])
    elif sorted(estados_sel) == sorted(ESTADOS_SEREMI_LISTADO):
        filas = srv.consultar(None, None, None)  # mismo listado por defecto del escritorio
    else:
        filas = []
        for cod in estados_sel:  # el procedimiento filtra un estado a la vez
            filas += srv.consultar(0, cod, None)
        filas.sort(key=lambda r: -int(r['N° Proyecto']))

    colores = srv.colores_estado()
    return render(request, 'seremi_seguimiento.html', {
        'titulo': 'Seguimiento Ingreso SEREMI',
        'encabezado': 'Seguimiento Ingreso SEREMI',
        'menu': 'Proyectos',
        'submenu': 'Seguimiento Ingreso SEREMI',
        'filas': [_fila(r) for r in filas],
        'estados': [{'codigo': c, 'nombre': n, 'color': colores.get(c, 'White')} for c, n in estados],
        'estados_marcados': estados_sel,
        'estados_defecto': list(ESTADOS_SEREMI_LISTADO),
        'filtro_tipo': tipo if tipo in dict(TIPOS_FILTRO) else 1,
        'filtro_texto': texto,
        'tipos_filtro': TIPOS_FILTRO,
        'error': error,
    })


def _fecha_iso(valor):
    return valor.isoformat() if valor else ''


@login_required
@require_GET
def seremi_proyecto(request, idproyecto):
    p = get_object_or_404(srv.ficha(), pk=idproyecto)
    cot = p.idcotizacion
    return JsonResponse({
        'idproyecto': int(p.idproyecto),
        'nombre': cot.nombreproyecto or '',
        'region': srv.nombre_region(cot.codregion),
        'mandante': cot.idcliente.razonsocial if cot.idcliente_id else '',
        'contacto_mandante': cot.idcontacto.nombrecontacto if cot.idcontacto_id else '',
        'cod_estado': p.estado,
        'estado': srv.nombre_estado(p.estado),
        'datos': {
            'propietario': p.propietario or '',
            'rut_propietario': p.rutpropietario or '',
            'operador': p.idoperador or '',
            'transfer_arancel': p.transferarancel or '',
            'arancel': p.arancel if p.arancel is not None else '',
            'n_tramite': p.ntramiteseremi or '',
            'fecha_sol_acreditacion': _fecha_iso(p.fechasolacreditacion),
            'fecha_sol_ingreso': _fecha_iso(p.fechasolingreso),
            'fecha_carga_exp': _fecha_iso(p.fechacargaexp),
            'fecha_pago_arancel': _fecha_iso(p.fechapagoarancel),
            'fecha_ingreso_timbraje': _fecha_iso(p.fechaingresotimbraje),
            'fecha_aprob_timbraje': _fecha_iso(p.fechaaprobtimbraje),
            'fecha_ingreso_seremi': _fecha_iso(p.fechaingresoseremi),
            'fecha_aprob_seremi': _fecha_iso(p.fechaaprobseremi),
            'nombre_rep_legal': p.nombrereplegal or '',
            'rut_rep_legal': p.rutreplegal or '',
        },
        'operadores': srv.operadores(p.idoperador),
        'comentarios': srv.comentarios(int(p.idproyecto)),
    })


@login_required
@require_POST
def seremi_guardar_datos(request, idproyecto):
    """Igual que ProyectoSeremi: solo se graban los campos con valor (un campo vacío no borra el dato guardado)."""
    proyecto = get_object_or_404(srv_proyectos.todos(), pk=idproyecto)
    try:
        srv.guardar_datos(proyecto, request.POST)
    except ErrorValidacion as e:
        return JsonResponse({'ok': False, 'message': str(e)}, status=400)
    return JsonResponse({'ok': True, 'message': 'Datos SEREMI grabados.'})


@login_required
@require_POST
def seremi_cambiar_estado(request, idproyecto):
    """Igual que VisorProyectoSeremi: estado distinto al actual y comentario obligatorio, que queda en la bitácora."""
    proyecto = get_object_or_404(srv_proyectos.todos(), pk=idproyecto)
    try:
        nuevo = int(request.POST.get('estado'))
    except (TypeError, ValueError):
        nuevo = None
    try:
        nombre = srv.cambiar_estado(proyecto, nuevo, (request.POST.get('comentario') or '').strip(), _usuario(request))
    except ErrorValidacion as e:
        return JsonResponse({'ok': False, 'message': str(e)}, status=400)
    return JsonResponse({'ok': True, 'message': f'Estado cambiado a "{nombre}".',
                         'comentarios': srv.comentarios(int(proyecto.pk))})


@login_required
@require_POST
def seremi_comentario_agregar(request, idproyecto):
    """Igual que SeguimientoSeremi: fecha elegida (con la hora actual) y comentario."""
    proyecto = get_object_or_404(srv_proyectos.todos(), pk=idproyecto)
    try:
        srv.agregar_comentario(proyecto.pk, (request.POST.get('comentario') or '').strip(), _usuario(request),
                               request.POST.get('fecha') or None)
    except ErrorValidacion as e:
        return JsonResponse({'ok': False, 'message': str(e)}, status=400)
    return JsonResponse({'ok': True, 'comentarios': srv.comentarios(int(proyecto.pk))})


@login_required
@require_POST
def seremi_comentario_eliminar(request, idproyecto, idcomentario):
    get_object_or_404(srv_proyectos.todos(), pk=idproyecto)
    srv.eliminar_comentario(idproyecto, idcomentario)
    return JsonResponse({'ok': True, 'comentarios': srv.comentarios(int(idproyecto))})
