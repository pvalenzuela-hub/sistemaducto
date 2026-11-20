"""Seguimiento Ingreso SEREMI: réplica web de SEGProyectoSeremi del sistema VB.NET.

Pantallas del escritorio que reúne: SEGProyectoSeremi (listado), ProyectoSeremi (datos del trámite),
VisorProyectoSeremi (ficha y cambio de estado) y SeguimientoSeremi (bitácora ducto.ProyectoSeremi_SEG).
El listado usa el mismo procedimiento del escritorio, ducto.SEG_ProyectoSEREMI_WEB.

Estado del proyecto: el escritorio usa Proyecto.Estado con los códigos de tEstado (0 a 17) y la web usa
estadoproyecto_id, que es el mismo estado + 1 (así lo hace GR_Proyecto_SEG). Aquí se actualizan ambos.
"""
from datetime import date, datetime

from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Proyecto, tusuario

TIPO_ESTADO_PROYECTO = 2
ESTADOS_SEREMI_LISTADO = (4, 5, 6, 11, 12, 13, 14, 16, 17)  # los que muestra el listado por defecto
TIPOS_FILTRO = [(1, 'N° Proy.'), (2, 'Proyecto'), (3, 'N° Trámite')]
COLORES_OSCUROS = {'purple', 'dodgerblue', 'saddlebrown', 'green', 'red'}


class ErrorValidacion(ValueError):
    pass


def estado_web(cod_estado):
    """estadoproyecto_id que corresponde a un código de tEstado (Proyecto.Estado)."""
    return None if cod_estado is None else int(cod_estado) + 1


def _estados_seremi():
    """CO_tEstado_SegIngSEREMI: estados que se pueden elegir en este módulo."""
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC CO_tEstado_SegIngSEREMI')
        return [(cod, (descrip or '').strip()) for cod, descrip in cursor.fetchall()]


def _colores_estado():
    with connection.cursor() as cursor:
        cursor.execute('SELECT CodEstado, Color FROM tEstado WHERE TipoEstado = %s', [TIPO_ESTADO_PROYECTO])
        return {cod: (color or '').strip() for cod, color in cursor.fetchall()}


def _usuario(request):
    return (request.user.username or '')[:50]


def _consultar(tipo_filtro, cod_estado, texto):
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC ducto.SEG_ProyectoSEREMI_WEB %s, %s, %s', [tipo_filtro, cod_estado, texto])
        columnas = [c[0] for c in cursor.description]
        return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


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
    estados = _estados_seremi()
    validos = {cod for cod, _ in estados}
    todo = request.GET.get('todo') == '1'
    try:
        tipo = int(request.GET.get('tipo') or 0)
    except ValueError:
        tipo = 0
    texto = (request.GET.get('texto') or '').strip()
    estado_txt = (request.GET.get('estado') or '').strip()
    error = ''

    if texto and tipo in dict(TIPOS_FILTRO):
        if tipo == 1 and not texto.isdigit():
            error = 'El N° de proyecto debe ser un número.'
            filas = []
        else:
            filas = _consultar(tipo, None, texto[:80])
    elif estado_txt.isdigit() and int(estado_txt) in validos and not todo:
        filas = _consultar(0, int(estado_txt), None)
    else:
        filas = _consultar(None, None, None)

    colores = _colores_estado()
    return render(request, 'seremi_seguimiento.html', {
        'titulo': 'Seguimiento Ingreso SEREMI',
        'encabezado': 'Seguimiento Ingreso SEREMI',
        'menu': 'Proyectos',
        'submenu': 'Seguimiento Ingreso SEREMI',
        'filas': [_fila(r) for r in filas],
        'estados': [{'codigo': c, 'nombre': n, 'color': colores.get(c, 'White')} for c, n in estados],
        'filtro_estado': estado_txt,
        'filtro_tipo': tipo if tipo in dict(TIPOS_FILTRO) else 1,
        'filtro_texto': texto,
        'todo': todo,
        'tipos_filtro': TIPOS_FILTRO,
        'error': error,
    })


def _fecha_iso(valor):
    return valor.isoformat() if valor else ''


def _comentarios(idproyecto):
    """CO_Proyecto_SEG_SEREMI, en el mismo orden del escritorio (por día)."""
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC CO_Proyecto_SEG_SEREMI %s', [idproyecto])
        return [{'id': r[0], 'fecha': r[2] or '', 'comentario': (r[3] or '').rstrip(), 'usuario': r[4] or ''}
                for r in cursor.fetchall()]


def _operadores(actual):
    usuarios = list(tusuario.objects.filter(estado='A').order_by('nombreusuario').values_list('idusuario', 'nombreusuario'))
    if actual and actual not in {u for u, _ in usuarios}:
        extra = tusuario.objects.filter(idusuario=actual).values_list('idusuario', 'nombreusuario').first()
        usuarios.append(extra or (actual, actual))
    return [{'id': u, 'nombre': (n or u).strip()} for u, n in usuarios]


@login_required
@require_GET
def seremi_proyecto(request, idproyecto):
    p = get_object_or_404(Proyecto.objects.select_related('idcotizacion__idcliente', 'idcotizacion__idcontacto'),
                          pk=idproyecto)
    cot = p.idcotizacion
    with connection.cursor() as cursor:
        cursor.execute('SELECT Descrip FROM tEstado WHERE TipoEstado = %s AND CodEstado = %s', [TIPO_ESTADO_PROYECTO, p.estado])
        fila = cursor.fetchone()
        cursor.execute('SELECT Descrip FROM tRegion WHERE CodRegion = %s', [cot.codregion])
        region = cursor.fetchone()
    return JsonResponse({
        'idproyecto': int(p.idproyecto),
        'nombre': cot.nombreproyecto or '',
        'region': (region[0] or '').strip() if region else '',
        'mandante': cot.idcliente.razonsocial if cot.idcliente_id else '',
        'contacto_mandante': cot.idcontacto.nombrecontacto if cot.idcontacto_id else '',
        'cod_estado': p.estado,
        'estado': (fila[0] or '').strip() if fila else '',
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
        'operadores': _operadores(p.idoperador),
        'comentarios': _comentarios(int(p.idproyecto)),
    })


# Campos de "Datos SEREMI": (campo del formulario, campo del modelo, tipo, largo máximo)
CAMPOS_DATOS = [
    ('propietario', 'propietario', 'texto', 100),
    ('rut_propietario', 'rutpropietario', 'texto', 13),
    ('operador', 'idoperador', 'operador', 15),
    ('transfer_arancel', 'transferarancel', 'texto', 50),
    ('arancel', 'arancel', 'numero', None),
    ('n_tramite', 'ntramiteseremi', 'texto', 50),
    ('fecha_sol_acreditacion', 'fechasolacreditacion', 'fecha', None),
    ('fecha_sol_ingreso', 'fechasolingreso', 'fecha', None),
    ('fecha_carga_exp', 'fechacargaexp', 'fecha', None),
    ('fecha_pago_arancel', 'fechapagoarancel', 'fecha', None),
    ('fecha_ingreso_timbraje', 'fechaingresotimbraje', 'fecha', None),
    ('fecha_aprob_timbraje', 'fechaaprobtimbraje', 'fecha', None),
    ('fecha_ingreso_seremi', 'fechaingresoseremi', 'fecha', None),
    ('fecha_aprob_seremi', 'fechaaprobseremi', 'fecha', None),
    ('nombre_rep_legal', 'nombrereplegal', 'texto', 80),
    ('rut_rep_legal', 'rutreplegal', 'texto', 13),
]


@login_required
@require_POST
def seremi_guardar_datos(request, idproyecto):
    """Igual que ProyectoSeremi: solo se graban los campos con valor (un campo vacío no borra el dato guardado)."""
    proyecto = get_object_or_404(Proyecto, pk=idproyecto)
    cambios = {}
    try:
        for campo, modelo, tipo, largo in CAMPOS_DATOS:
            valor = (request.POST.get(campo) or '').strip()
            if not valor:
                continue
            if tipo == 'texto':
                if len(valor) > largo:
                    raise ErrorValidacion(f'"{campo}" admite hasta {largo} caracteres.')
                cambios[modelo] = valor
            elif tipo == 'operador':
                if not tusuario.objects.filter(idusuario=valor).exists():
                    raise ErrorValidacion('Operador no válido.')
                cambios[modelo] = valor
            elif tipo == 'numero':
                texto = valor.replace('.', '').replace(',', '.') if ',' in valor else valor
                try:
                    cambios[modelo] = float(texto)
                except ValueError:
                    raise ErrorValidacion('El arancel debe ser un número.')
            else:
                try:
                    cambios[modelo] = date.fromisoformat(valor)
                except ValueError:
                    raise ErrorValidacion(f'"{campo}": fecha inválida.')
    except ErrorValidacion as e:
        return JsonResponse({'ok': False, 'message': str(e)}, status=400)
    if not cambios:
        return JsonResponse({'ok': False, 'message': 'No hay datos para grabar.'}, status=400)
    Proyecto.objects.filter(pk=proyecto.pk).update(**cambios)
    return JsonResponse({'ok': True, 'message': 'Datos SEREMI grabados.'})


def _agregar_comentario(cursor, idproyecto, fecha, comentario, usuario):
    cursor.execute('INSERT INTO ducto.ProyectoSeremi_SEG (IdProyecto, Fecha, Comentario, IdUsuario) VALUES (%s, %s, %s, %s)',
                   [idproyecto, fecha, comentario, usuario])


@login_required
@require_POST
def seremi_cambiar_estado(request, idproyecto):
    """Igual que VisorProyectoSeremi: estado distinto al actual y comentario obligatorio, que queda en la bitácora."""
    proyecto = get_object_or_404(Proyecto, pk=idproyecto)
    validos = dict(_estados_seremi())
    try:
        nuevo = int(request.POST.get('estado'))
    except (TypeError, ValueError):
        nuevo = None
    comentario = (request.POST.get('comentario') or '').strip()
    if nuevo not in validos:
        return JsonResponse({'ok': False, 'message': 'Debe seleccionar un estado.'}, status=400)
    if not comentario:
        return JsonResponse({'ok': False, 'message': 'Debe ingresar un comentario.'}, status=400)
    if nuevo == proyecto.estado:
        return JsonResponse({'ok': False, 'message': 'No existen cambios para actualizar.'}, status=400)
    with transaction.atomic(), connection.cursor() as cursor:
        Proyecto.objects.filter(pk=proyecto.pk).update(estado=nuevo, estadoproyecto_id=estado_web(nuevo))
        _agregar_comentario(cursor, int(proyecto.pk), timezone.localtime().replace(tzinfo=None), comentario,
                            _usuario(request))
    return JsonResponse({'ok': True, 'message': f'Estado cambiado a "{validos[nuevo]}".',
                         'comentarios': _comentarios(int(proyecto.pk))})


@login_required
@require_POST
def seremi_comentario_agregar(request, idproyecto):
    """Igual que SeguimientoSeremi: fecha elegida (con la hora actual) y comentario."""
    proyecto = get_object_or_404(Proyecto, pk=idproyecto)
    comentario = (request.POST.get('comentario') or '').strip()
    if not comentario:
        return JsonResponse({'ok': False, 'message': 'Debe ingresar un comentario.'}, status=400)
    if len(comentario) > 2000:
        return JsonResponse({'ok': False, 'message': 'El comentario admite hasta 2.000 caracteres.'}, status=400)
    ahora = timezone.localtime().replace(tzinfo=None)
    try:
        dia = date.fromisoformat(request.POST.get('fecha')) if request.POST.get('fecha') else ahora.date()
    except ValueError:
        return JsonResponse({'ok': False, 'message': 'Fecha inválida.'}, status=400)
    fecha = datetime.combine(dia, ahora.time())
    with connection.cursor() as cursor:
        _agregar_comentario(cursor, int(proyecto.pk), fecha, comentario, _usuario(request))
    return JsonResponse({'ok': True, 'comentarios': _comentarios(int(proyecto.pk))})


@login_required
@require_POST
def seremi_comentario_eliminar(request, idproyecto, idcomentario):
    get_object_or_404(Proyecto, pk=idproyecto)
    with connection.cursor() as cursor:
        cursor.execute('DELETE FROM ducto.ProyectoSeremi_SEG WHERE Id = %s AND IdProyecto = %s', [idcomentario, idproyecto])
    return JsonResponse({'ok': True, 'comentarios': _comentarios(int(idproyecto))})
