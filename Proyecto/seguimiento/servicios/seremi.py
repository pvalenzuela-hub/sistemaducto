"""Servicio de Seguimiento Ingreso SEREMI: datos del trámite del proyecto y su bitácora ducto.ProyectoSeremi_SEG.

Procedimientos del escritorio que usa:
    ducto.SEG_ProyectoSEREMI_WEB  listado
    CO_tEstado_SegIngSEREMI       estados que se pueden elegir en el módulo
    CO_Proyecto_SEG_SEREMI        bitácora del proyecto
"""
from datetime import date, datetime

from django.db import connection, transaction
from django.utils import timezone

from ..models import Proyecto, tusuario
from . import proyectos

TIPO_ESTADO_PROYECTO = 2
MAX_COMENTARIO = 2000

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


class ErrorValidacion(ValueError):
    pass


def estados():
    """CO_tEstado_SegIngSEREMI: [(código tEstado, nombre)] que se pueden elegir en este módulo."""
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC CO_tEstado_SegIngSEREMI')
        return [(cod, (descrip or '').strip()) for cod, descrip in cursor.fetchall()]


def colores_estado():
    with connection.cursor() as cursor:
        cursor.execute('SELECT CodEstado, Color FROM tEstado WHERE TipoEstado = %s', [TIPO_ESTADO_PROYECTO])
        return {cod: (color or '').strip() for cod, color in cursor.fetchall()}


def nombre_estado(cod_estado):
    with connection.cursor() as cursor:
        cursor.execute('SELECT Descrip FROM tEstado WHERE TipoEstado = %s AND CodEstado = %s', [TIPO_ESTADO_PROYECTO, cod_estado])
        fila = cursor.fetchone()
    return (fila[0] or '').strip() if fila else ''


def nombre_region(codregion):
    with connection.cursor() as cursor:
        cursor.execute('SELECT Descrip FROM tRegion WHERE CodRegion = %s', [codregion])
        fila = cursor.fetchone()
    return (fila[0] or '').strip() if fila else ''


def consultar(tipo_filtro, cod_estado, texto):
    """ducto.SEG_ProyectoSEREMI_WEB. Sin parámetros: el listado por defecto del escritorio. Filas como dict."""
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC ducto.SEG_ProyectoSEREMI_WEB %s, %s, %s', [tipo_filtro, cod_estado, texto])
        columnas = [c[0] for c in cursor.description]
        return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def ficha():
    """Proyecto con cotización, mandante y contacto cargados."""
    return Proyecto.objects.select_related('idcotizacion__idcliente', 'idcotizacion__idcontacto')


def comentarios(idproyecto):
    """CO_Proyecto_SEG_SEREMI, en el mismo orden del escritorio (por día)."""
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC CO_Proyecto_SEG_SEREMI %s', [idproyecto])
        return [{'id': r[0], 'fecha': r[2] or '', 'comentario': (r[3] or '').rstrip(), 'usuario': r[4] or ''}
                for r in cursor.fetchall()]


def operadores(actual):
    """Usuarios activos que pueden ser operador; incluye al operador actual aunque esté inactivo."""
    usuarios = list(tusuario.objects.filter(estado='A').order_by('nombreusuario').values_list('idusuario', 'nombreusuario'))
    if actual and actual not in {u for u, _ in usuarios}:
        extra = tusuario.objects.filter(idusuario=actual).values_list('idusuario', 'nombreusuario').first()
        usuarios.append(extra or (actual, actual))
    return [{'id': u, 'nombre': (n or u).strip()} for u, n in usuarios]


def guardar_datos(proyecto, valores):
    """Igual que ProyectoSeremi: solo se graban los campos con valor (un campo vacío no borra el dato guardado).
    'valores' son los textos del formulario por campo (CAMPOS_DATOS)."""
    cambios = {}
    for campo, modelo, tipo, largo in CAMPOS_DATOS:
        valor = (valores.get(campo) or '').strip()
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
    if not cambios:
        raise ErrorValidacion('No hay datos para grabar.')
    Proyecto.objects.filter(pk=proyecto.pk).update(**cambios)


def _insertar_comentario(idproyecto, fecha, comentario, usuario):
    with connection.cursor() as cursor:
        cursor.execute('INSERT INTO ducto.ProyectoSeremi_SEG (IdProyecto, Fecha, Comentario, IdUsuario) VALUES (%s, %s, %s, %s)',
                       [idproyecto, fecha, comentario, (usuario or '')[:50]])


def cambiar_estado(proyecto, nuevo, comentario, usuario):
    """Igual que VisorProyectoSeremi: estado distinto al actual y comentario obligatorio, que queda en la bitácora.
    'nuevo' es el código tEstado. Devuelve el nombre del nuevo estado."""
    validos = dict(estados())
    if nuevo not in validos:
        raise ErrorValidacion('Debe seleccionar un estado.')
    if not comentario:
        raise ErrorValidacion('Debe ingresar un comentario.')
    if nuevo == proyecto.estado:
        raise ErrorValidacion('No existen cambios para actualizar.')
    with transaction.atomic():
        Proyecto.objects.filter(pk=proyecto.pk).update(estado=nuevo, estadoproyecto_id=proyectos.estado_web(nuevo))
        _insertar_comentario(int(proyecto.pk), timezone.localtime().replace(tzinfo=None), comentario, usuario)
    return validos[nuevo]


def agregar_comentario(idproyecto, comentario, usuario, fecha_texto=None):
    """Igual que SeguimientoSeremi: fecha elegida (AAAA-MM-DD, con la hora actual; hoy si no viene) y comentario."""
    if not comentario:
        raise ErrorValidacion('Debe ingresar un comentario.')
    if len(comentario) > MAX_COMENTARIO:
        raise ErrorValidacion('El comentario admite hasta 2.000 caracteres.')
    ahora = timezone.localtime().replace(tzinfo=None)
    try:
        dia = date.fromisoformat(fecha_texto) if fecha_texto else ahora.date()
    except ValueError:
        raise ErrorValidacion('Fecha inválida.')
    _insertar_comentario(int(idproyecto), datetime.combine(dia, ahora.time()), comentario, usuario)


def eliminar_comentario(idproyecto, idcomentario):
    with connection.cursor() as cursor:
        cursor.execute('DELETE FROM ducto.ProyectoSeremi_SEG WHERE Id = %s AND IdProyecto = %s', [idcomentario, idproyecto])
