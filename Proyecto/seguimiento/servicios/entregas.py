"""Servicio de Entregas: calendario de entregas de proyectos y su flujo de desarrollo y revisión.

Único lugar que lee y escribe EntregaProyecto, su bitácora EntregaEvento y sus observaciones
(EntregaObservacion / Observacion). No usa procedimientos almacenados.

Flujo de estados (T_EstadosEntrega):
    1 Nueva -> 2 En Desarrollo -> 4 En Revisión -> 3 Correcciones -> 4 En Revisión ... -> 5 Entregado a Cliente
    1 Nueva -> 6 Nula (anulación)
Cada paso queda en EntregaEvento. Los responsables quedan en RutUserDesa1..3 / RutUserRev1..3: la primera vuelta
usa el 1, las siguientes el 2 y el 3; desde la tercera se sigue escribiendo en el 3.
"""
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import CharField, Count, F, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import (Calificacion, EntregaProyecto, Entregaevento, Entregaobservacion, Observacion, Proyecto,
                      TDuracionProyecto, TipoEntrega, Tipoevento, Tipoobservacion, Urgencia, tusuario)

ESTADO_NUEVA = 1
ESTADO_DESARROLLO = 2
ESTADO_CORRECCIONES = 3
ESTADO_REVISION = 4
ESTADO_ENTREGADO = 5
ESTADO_NULA = 6
HORA_POR_DEFECTO = '06:00'
COLOR_ENTREGADA = '#b3ad9f'
COLOR_POR_DEFECTO = '#6c757d'


class ErrorValidacion(ValueError):
    pass


class NoEncontrado(LookupError):
    pass


def ahora():
    return timezone.localtime(timezone.now()).replace(tzinfo=None)


def _usuarios():
    return get_user_model().objects


# ---------------------------------------------------------------------------------------------------------------
# Catálogos
# ---------------------------------------------------------------------------------------------------------------

def proyectos_para_calendario():
    return Proyecto.objects.select_related('idcotizacion', 'idtamano').order_by('idproyecto')


def tipos_entrega():
    return TipoEntrega.objects.order_by('descripcion')


def urgencias():
    return Urgencia.objects.order_by('descrip')


def tamanos():
    return TDuracionProyecto.objects.order_by('descripcion')


def tipos_observacion():
    return Tipoobservacion.objects.order_by('nombre')


def calificaciones():
    return Calificacion.objects.order_by('nombre')


def observaciones_catalogo():
    return [{
        'id': o.id,
        'tipo': o.tipoobservacion.nombre if o.tipoobservacion else '',
        'descripcion': o.nombre or '',
        'calificacion': o.calificacion.nombre if o.calificacion else '',
    } for o in Observacion.objects.select_related('tipoobservacion', 'calificacion').order_by('tipoobservacion__nombre', 'nombre')]


def usuarios_activos():
    """Usuarios que se pueden asignar a desarrollo o revisión (activos, sin superusuarios ni 'admin')."""
    return [{'rut': u.username, 'nombrecompleto': u.get_full_name().strip() or u.username}
            for u in _usuarios().filter(is_active=True, is_superuser=False).exclude(username__iexact='admin')
            .order_by('first_name', 'last_name', 'username')]


# ---------------------------------------------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------------------------------------------

def desarrollador_actual(entrega):
    return entrega.rutuserdesa3 or entrega.rutuserdesa2 or entrega.rutuserdesa1 or ''


def fecha_asignacion_actual(entrega):
    return entrega.fechaasigdesa3 or entrega.fechaasigdesa2 or entrega.fechaasigdesa1


def nombres_usuarios(codigos):
    """{username: nombre completo (o username)}."""
    codigos = [c for c in set(codigos) if c]
    if not codigos:
        return {}
    return {u.username: (u.get_full_name().strip() or u.username) for u in _usuarios().filter(username__in=codigos)}


def eventos_calendario(desde=None, hasta=None):
    """Entregas no anuladas con fecha de calendario entre desde y hasta, en formato del calendario."""
    qs = (EntregaProyecto.objects
          .select_related('idproyecto', 'idproyecto__idcotizacion', 'idproyecto__idtamano', 'idtipoentrega',
                          'idurgencia', 'idestadoentrega')
          .filter(fechacalendario__isnull=False).exclude(idestadoentrega_id=ESTADO_NULA))
    if desde:
        qs = qs.filter(fechacalendario__gte=desde)
    if hasta:
        qs = qs.filter(fechacalendario__lt=hasta)
    entregas = list(qs)
    nombres = nombres_usuarios(desarrollador_actual(e) for e in entregas)
    eventos = []
    for e in entregas:
        codigo, nombre_proyecto = '', ''
        if e.idproyecto:
            codigo = str(e.idproyecto.idproyecto)
            if e.idproyecto.idcotizacion:
                nombre_proyecto = e.idproyecto.idcotizacion.nombreproyecto or ''
        color = COLOR_POR_DEFECTO
        if e.idestadoentrega_id == ESTADO_ENTREGADO:
            color = COLOR_ENTREGADA
        elif e.idtipoentrega and e.idtipoentrega.color:
            color = e.idtipoentrega.color
        rut_desarrollador = desarrollador_actual(e)
        eventos.append({
            'id': e.identrega,
            'title': f"{codigo} - {nombre_proyecto}".strip(),
            'start': e.fechacalendario.strftime('%Y-%m-%dT%H:%M:%S') if e.fechacalendario else None,
            'allDay': False,
            'display': 'block',
            'backgroundColor': color,
            'borderColor': color,
            'textColor': '#ffffff',
            'extendedProps': {
                'identrega': e.identrega,
                'idproyecto': codigo,
                'nombreproyecto': nombre_proyecto,
                'tipoentrega': e.idtipoentrega.descripcion if e.idtipoentrega else '',
                'horaentrega': e.horaentrega or '',
                'fechaentrega': e.fechaentrega.strftime('%d-%m-%Y') if e.fechaentrega else '',
                'plazo': e.plazoestdesarrollo or '',
                'urgencia_id': e.idurgencia_id,
                'urgencia': e.idurgencia.descrip if e.idurgencia else '',
                'estadoentrega_id': e.idestadoentrega_id,
                'estadoentrega': e.idestadoentrega.descrip if e.idestadoentrega else '',
                'tamano': e.idproyecto.idtamano.descripcion if e.idproyecto and e.idproyecto.idtamano else '',
                'asignado_a': nombres.get(rut_desarrollador, rut_desarrollador or ''),
            }
        })
    return eventos


def listado(estados=None):
    """Entregas para los listados (sin estados: todas menos las anuladas), de la más nueva a la más antigua, con
    desarrollador actual, fecha de asignación, creador y N° de observaciones."""
    observaciones = (Entregaobservacion.objects.filter(entrega_id=OuterRef('pk'), estado=1)
                     .values('entrega_id').annotate(total=Count('id')).values('total')[:1])
    creador = tusuario.objects.filter(idusuario=OuterRef('rutusercreador')).values('nombreusuario')[:1]
    qs = EntregaProyecto.objects.filter(idestadoentrega_id__in=estados) if estados else \
        EntregaProyecto.objects.exclude(idestadoentrega_id=ESTADO_NULA)
    entregas = list(
        qs.select_related('idproyecto', 'idproyecto__idcotizacion', 'idproyecto__idcliente', 'idproyecto__idtamano',
                          'idtipoentrega', 'idurgencia', 'idestadoentrega')
        .annotate(
            rut_cliente=F('idproyecto__idcliente__rut'),
            fecha_adjudicacion=F('idproyecto__fechaadjudicacion'),
            descripcion_urgencia=F('idurgencia__descrip'),
            simbolo_urgencia=F('idurgencia__simbolo'),
            nombre_usuario_creador=Subquery(creador, output_field=CharField()),
            nombre_proyecto=F('idproyecto__idcotizacion__nombreproyecto'),
            descripcion_tipo_entrega=F('idtipoentrega__descripcion'),
            descripcion_estado_entrega=F('idestadoentrega__descrip'),
            estado_proyecto=F('idproyecto__estado'),
            color_tipo_entrega=F('idtipoentrega__color'),
            descripcion_tamanio_proyecto=F('idproyecto__idtamano__descripcion'),
            observaciones=Coalesce(Subquery(observaciones, output_field=IntegerField()), Value(0)),
        )
        .order_by('-fechacalendario', '-identrega'))
    nombres = nombres_usuarios(desarrollador_actual(e) for e in entregas)
    for e in entregas:
        rut = desarrollador_actual(e)
        e.nombre_desarrollador_actual = nombres.get(rut, rut or '')
        e.fecha_asignacion = fecha_asignacion_actual(e)
        e.nombre_usuario_creador = e.nombre_usuario_creador or e.rutusercreador or ''
    return entregas


def de_proyecto(proyecto):
    """Entregas de un proyecto por fecha de entrega (API)."""
    return list(EntregaProyecto.objects.filter(idproyecto=proyecto).select_related('idtipoentrega', 'idestadoentrega')
                .order_by('fechaentrega', 'identrega'))


def _fecha_hora_local(fecha):
    if not fecha:
        return ''
    if timezone.is_aware(fecha):
        fecha = timezone.localtime(fecha)
    return fecha.strftime('%d-%m-%Y %H:%M')


def _eventos_desde_columnas(entrega, nombres):
    """Historial armado con las columnas de asignación, para entregas antiguas sin registros en EntregaEvento."""
    eventos = []
    pasos = [
        ('A Desarrollo', entrega.rutusercreador, entrega.rutuserdesa1, entrega.fechaasigdesa1),
        ('A Revisión', entrega.rutuserdesa1, entrega.rutuserrev1, entrega.fechaasigrev1),
        ('A Desarrollo', entrega.rutuserrev1, entrega.rutuserdesa2, entrega.fechaasigdesa2),
        ('A Revisión', entrega.rutuserdesa2, entrega.rutuserrev2, entrega.fechaasigrev2),
        ('A Desarrollo', entrega.rutuserrev2, entrega.rutuserdesa3, entrega.fechaasigdesa3),
        ('A Revisión', entrega.rutuserdesa3, entrega.rutuserrev3, entrega.fechaasigrev3),
    ]
    for nombre, origen, destino, fecha in pasos:
        if fecha:
            eventos.append({'evento': nombre, 'origen': nombres.get(origen, origen) if origen else '',
                            'destino': nombres.get(destino, destino) if destino else '',
                            'fecha': _fecha_hora_local(fecha), '_orden': fecha})
    eventos.sort(key=lambda x: x['_orden'])
    for e in eventos:
        e.pop('_orden', None)
    return eventos


def visor(identrega):
    """Ficha de la entrega: datos, observaciones vigentes e historial de eventos."""
    entrega = EntregaProyecto.objects.select_related(
        'idproyecto', 'idproyecto__idcotizacion', 'idtipoentrega', 'idestadoentrega').filter(pk=identrega).first()
    if entrega is None:
        raise NoEncontrado('Entrega no encontrada.')
    observaciones = (Entregaobservacion.objects.filter(entrega_id=identrega, estado=1)
                     .select_related('observacion', 'observacion__tipoobservacion', 'observacion__calificacion').order_by('id'))
    eventos = list(Entregaevento.objects.filter(entrega_id=identrega).select_related('tipoevento')
                   .order_by('fechahora', 'identregaevento'))
    codigos = [entrega.rutusercreador, entrega.rutuserdesa1, entrega.rutuserdesa2, entrega.rutuserdesa3,
               entrega.rutuserrev1, entrega.rutuserrev2, entrega.rutuserrev3, entrega.rutuserupdate, entrega.rutuseranula]
    for ev in eventos:
        codigos += [ev.rutorigen, ev.rutdestino]
    nombres = nombres_usuarios(codigos)
    visible = lambda codigo: nombres.get(codigo, codigo) if codigo else ''
    data = {
        'ok': True,
        'identrega': entrega.identrega,
        'estadoentrega_id': entrega.idestadoentrega_id or 0,
        'estadoentrega': entrega.idestadoentrega.descrip if entrega.idestadoentrega else '',
        'idproyecto': str(entrega.idproyecto_id or ''),
        'nombreproyecto': (entrega.idproyecto.idcotizacion.nombreproyecto or '') if entrega.idproyecto and entrega.idproyecto.idcotizacion else '',
        'tipoentrega': (entrega.idtipoentrega.descripcion or '') if entrega.idtipoentrega else '',
        'fechaentrega': entrega.fechaentrega.strftime('%d-%m-%Y') if entrega.fechaentrega else '',
        'observaciones': [],
        'eventos': [],
    }
    for eo in observaciones:
        obs = eo.observacion
        data['observaciones'].append({
            'nro': obs.id if obs else '',
            'tipo': obs.tipoobservacion.nombre if obs and obs.tipoobservacion else '',
            'descripcion': obs.nombre if obs else '',
            'calificacion': obs.calificacion.nombre if obs and obs.calificacion else '',
            'estado': 'CORREGIDA',
        })
    if eventos:
        data['eventos'] = [{'evento': ev.tipoevento.nombre if ev.tipoevento else '', 'origen': visible(ev.rutorigen),
                            'destino': visible(ev.rutdestino), 'fecha': _fecha_hora_local(ev.fechahora)} for ev in eventos]
    else:
        data['eventos'] = _eventos_desde_columnas(entrega, nombres)
    return data


# ---------------------------------------------------------------------------------------------------------------
# Crear, anular, mover
# ---------------------------------------------------------------------------------------------------------------

def crear(usuario, datos):
    """Nueva entrega desde el calendario. 'datos': fecha_calendario y fecha_entrega (AAAA-MM-DD), hora_entrega
    (HH:MM, 06:00 si no viene), idproyecto, idtipoentrega, idurgencia, idtamano (se guarda en el proyecto) y plazo."""
    if not usuario:
        raise ErrorValidacion('No fue posible determinar el usuario creador.')
    fecha_calendario = datos.get('fecha_calendario')
    idproyecto = datos.get('idproyecto')
    idtipoentrega = datos.get('idtipoentrega')
    idurgencia = datos.get('idurgencia')
    fecha_entrega = datos.get('fecha_entrega')
    hora_entrega = datos.get('hora_entrega') or HORA_POR_DEFECTO
    if not fecha_calendario:
        raise ErrorValidacion('Falta la fecha del calendario.')
    if not idproyecto:
        raise ErrorValidacion('Debes seleccionar un proyecto.')
    if not idtipoentrega:
        raise ErrorValidacion('Debes seleccionar un tipo de entrega.')
    if not idurgencia:
        raise ErrorValidacion('Debes seleccionar un tipo de urgencia.')
    if not fecha_entrega:
        raise ErrorValidacion('Debes indicar la fecha de entrega al cliente.')
    try:
        datetime.strptime(fecha_calendario, '%Y-%m-%d')
    except ValueError:
        raise ErrorValidacion('Fecha de calendario inválida.')
    try:
        fecha_ent = datetime.strptime(fecha_entrega, '%Y-%m-%d').date()
    except ValueError:
        raise ErrorValidacion('Fecha de entrega inválida.')
    try:  # FechaCalendario = día elegido en el calendario + hora de entrega
        dt_cal = datetime.strptime(f'{fecha_calendario} {hora_entrega}', '%Y-%m-%d %H:%M')
    except ValueError:
        raise ErrorValidacion('Hora de entrega inválida.')
    if timezone.is_naive(dt_cal):
        dt_cal = timezone.make_aware(dt_cal, timezone.get_current_timezone())
    idtamano = datos.get('idtamano')
    if not idtamano:
        raise ErrorValidacion('Debes seleccionar el tamaño del proyecto.')

    proyecto = Proyecto.objects.filter(pk=idproyecto).first()
    if proyecto is None or not TDuracionProyecto.objects.filter(pk=idtamano).exists():
        raise NoEncontrado('Proyecto o tamaño no encontrado.')
    # el tamaño se guarda en el proyecto aunque luego falle otra validación (así funcionaba)
    proyecto.idtamano_id = idtamano
    proyecto.save(update_fields=['idtamano'])
    if not TipoEntrega.objects.filter(pk=idtipoentrega).exists() or not Urgencia.objects.filter(pk=idurgencia).exists():
        raise NoEncontrado('Tipo de entrega o urgencia no encontrado.')

    entrega = EntregaProyecto(
        rutusercreador=usuario,
        fechacreacion=ahora(),
        fechacalendario=dt_cal,
        idproyecto_id=idproyecto,
        idtipoentrega_id=idtipoentrega,
        idurgencia_id=idurgencia,
        fechaentrega=fecha_ent,
        horaentrega=hora_entrega,
        plazoestdesarrollo=datos.get('plazo') or '',
        idestadoentrega_id=ESTADO_NUEVA,
    )
    entrega.save()
    return entrega


def _bloquear(identrega):
    entrega = EntregaProyecto.objects.select_for_update().filter(pk=identrega).first()
    if entrega is None:
        raise NoEncontrado('Entrega no encontrada.')
    return entrega


def anular(identrega, usuario):
    """Solo una entrega Nueva se puede anular."""
    if not usuario:
        raise ErrorValidacion('No fue posible determinar el usuario que anula.')
    with transaction.atomic():
        entrega = _bloquear(identrega)
        if entrega.idestadoentrega_id != ESTADO_NUEVA:
            raise ErrorValidacion('Solo se puede anular una entrega con estado 1.')
        entrega.idestadoentrega_id = ESTADO_NULA
        entrega.rutuseranula = usuario
        entrega.fechaanulacion = ahora()
        entrega.rutuserupdate = usuario
        entrega.fechaupdate = ahora()
        entrega.save(update_fields=['idestadoentrega', 'rutuseranula', 'fechaanulacion', 'rutuserupdate', 'fechaupdate'])


def mover(identrega, usuario, nueva_fecha_texto):
    """Cambia el día en el calendario (conserva la hora). Una entrega ya entregada no se mueve."""
    if not usuario:
        raise ErrorValidacion('No fue posible determinar el usuario.')
    if not nueva_fecha_texto:
        raise ErrorValidacion('Falta la nueva fecha.')
    try:
        fecha_nueva = datetime.strptime(nueva_fecha_texto, '%Y-%m-%d').date()
    except ValueError:
        raise ErrorValidacion('Formato de fecha inválido.')
    with transaction.atomic():
        entrega = _bloquear(identrega)
        if entrega.idestadoentrega_id == ESTADO_ENTREGADO:
            raise ErrorValidacion('No se puede mover una entrega con estado 5.')
        if not entrega.fechacalendario:
            raise ErrorValidacion('La entrega no tiene fecha calendario.')
        entrega.fechacalendario = entrega.fechacalendario.replace(year=fecha_nueva.year, month=fecha_nueva.month, day=fecha_nueva.day)
        entrega.rutuserupdate = usuario
        entrega.fechaupdate = ahora()
        entrega.save()


# ---------------------------------------------------------------------------------------------------------------
# Flujo desarrollo / revisión
# ---------------------------------------------------------------------------------------------------------------

def _tipo_evento(*alternativas):
    for nombre in alternativas:
        te = Tipoevento.objects.filter(nombre__iexact=nombre).first()
        if te:
            return te
    for nombre in alternativas:
        te = Tipoevento.objects.filter(nombre__icontains=nombre).first()
        if te:
            return te
    return None


def _registrar_evento(entrega, alternativas, origen='', destino=''):
    tipo = _tipo_evento(*alternativas)
    if not tipo:
        raise ValueError(f"No existe Tipoevento para ninguna de estas opciones: {alternativas}")
    return Entregaevento.objects.create(entrega=entrega, tipoevento=tipo, rutorigen=origen or '', rutdestino=destino or '')


def _asignar_desarrollo(entrega, rut, fecha):
    """Nueva -> Desa1; desde Revisión: Desa2, luego Desa3, y desde ahí se sigue en Desa3."""
    if entrega.idestadoentrega_id == ESTADO_NUEVA:
        entrega.rutuserdesa1, entrega.fechaasigdesa1 = rut, fecha
        return ['rutuserdesa1', 'fechaasigdesa1']
    if entrega.idestadoentrega_id == ESTADO_REVISION:
        if not entrega.rutuserdesa2:
            entrega.rutuserdesa2, entrega.fechaasigdesa2 = rut, fecha
            return ['rutuserdesa2', 'fechaasigdesa2']
        entrega.rutuserdesa3, entrega.fechaasigdesa3 = rut, fecha
        return ['rutuserdesa3', 'fechaasigdesa3']
    raise ValueError('Flujo no válido para asignación a desarrollo.')


def _asignar_revision(entrega, rut, fecha):
    """Desarrollo -> Rev1; desde Correcciones: Rev2, luego Rev3, y desde ahí se sigue en Rev3."""
    if entrega.idestadoentrega_id == ESTADO_DESARROLLO:
        entrega.rutuserrev1, entrega.fechaasigrev1 = rut, fecha
        return ['rutuserrev1', 'fechaasigrev1']
    if entrega.idestadoentrega_id == ESTADO_CORRECCIONES:
        if not entrega.rutuserrev2:
            entrega.rutuserrev2, entrega.fechaasigrev2 = rut, fecha
            return ['rutuserrev2', 'fechaasigrev2']
        entrega.rutuserrev3, entrega.fechaasigrev3 = rut, fecha
        return ['rutuserrev3', 'fechaasigrev3']
    raise ValueError('Flujo no válido para asignación a revisión.')


def _usuario_activo(rut):
    return _usuarios().filter(username=rut, is_active=True).exists()


def _pasar(entrega, usuario, nuevo_estado, evento, campos):
    entrega.idestadoentrega_id = nuevo_estado
    entrega.rutuserupdate = usuario
    entrega.fechaupdate = evento.fechahora
    entrega.save(update_fields=['idestadoentrega', 'rutuserupdate', 'fechaupdate', *campos])


def enviar_a_desarrollo(identrega, usuario, rut_desarrollador):
    """Nueva -> En Desarrollo, asignada a rut_desarrollador."""
    if not rut_desarrollador:
        raise ErrorValidacion('Debes seleccionar un usuario.')
    if not _usuario_activo(rut_desarrollador):
        raise ErrorValidacion('El usuario seleccionado no existe o está inactivo.')
    with transaction.atomic():
        entrega = _bloquear(identrega)
        if entrega.idestadoentrega_id != ESTADO_NUEVA:
            raise ErrorValidacion('Solo se puede enviar a desarrollo una entrega con estado 1.')
        evento = _registrar_evento(entrega, ['A Desarrollo', 'Enviar a Desarrollo'], origen=usuario, destino=rut_desarrollador)
        _pasar(entrega, usuario, ESTADO_DESARROLLO, evento, _asignar_desarrollo(entrega, rut_desarrollador, evento.fechahora))


def enviar_a_revision(identrega, usuario, rut_revisor):
    """En Desarrollo o Correcciones -> En Revisión, asignada a rut_revisor."""
    if not rut_revisor:
        raise ErrorValidacion('Debes seleccionar un usuario.')
    if not _usuario_activo(rut_revisor):
        raise ErrorValidacion('El usuario seleccionado no existe o está inactivo.')
    with transaction.atomic():
        entrega = _bloquear(identrega)
        if entrega.idestadoentrega_id not in (ESTADO_DESARROLLO, ESTADO_CORRECCIONES):
            raise ErrorValidacion('Solo se puede enviar a revisión una entrega en desarrollo o correcciones.')
        evento = _registrar_evento(entrega, ['A Revisión', 'Enviar a Revisión'], origen=usuario, destino=rut_revisor)
        _pasar(entrega, usuario, ESTADO_REVISION, evento, _asignar_revision(entrega, rut_revisor, evento.fechahora))


def devolver_a_desarrollo(identrega, usuario):
    """En Revisión -> Correcciones, de vuelta al último desarrollador asignado."""
    with transaction.atomic():
        entrega = _bloquear(identrega)
        if entrega.idestadoentrega_id != ESTADO_REVISION:
            raise ErrorValidacion('Solo se puede enviar a desarrollo una entrega en revisión.')
        rut_destino = desarrollador_actual(entrega)
        if not rut_destino:
            raise ErrorValidacion('No existe desarrollador previo para reenviar la entrega.')
        if not _usuario_activo(rut_destino):
            raise ErrorValidacion('El desarrollador asociado no existe o está inactivo.')
        evento = _registrar_evento(entrega, ['A Desarrollo', 'Enviar a Desarrollo'], origen=usuario, destino=rut_destino)
        _pasar(entrega, usuario, ESTADO_CORRECCIONES, evento, _asignar_desarrollo(entrega, rut_destino, evento.fechahora))


def marcar_entregada(identrega, usuario):
    """En Revisión -> Entregado a Cliente; la fecha de calendario pasa a ser la de este momento."""
    with transaction.atomic():
        entrega = _bloquear(identrega)
        if entrega.idestadoentrega_id != ESTADO_REVISION:
            raise ErrorValidacion('Solo se puede marcar OK una entrega en revisión.')
        evento = _registrar_evento(entrega, ['Entrega OK', 'OK'], origen=usuario, destino='')
        entrega.fechacalendario = evento.fechahora
        _pasar(entrega, usuario, ESTADO_ENTREGADO, evento, ['fechacalendario'])


# ---------------------------------------------------------------------------------------------------------------
# Observaciones
# ---------------------------------------------------------------------------------------------------------------

def agregar_observacion(identrega, idobservacion, user):
    """Asigna una observación del catálogo. Devuelve False si ya estaba asignada."""
    if not idobservacion:
        raise ErrorValidacion('Falta la observación.')
    entrega = EntregaProyecto.objects.filter(pk=identrega).first()
    observacion = Observacion.objects.filter(pk=idobservacion).first()
    if entrega is None or observacion is None:
        raise NoEncontrado('Entrega u observación no encontrada.')
    if Entregaobservacion.objects.filter(entrega=entrega, observacion=observacion, estado=1).exists():
        return False
    Entregaobservacion.objects.create(entrega=entrega, observacion=observacion, username=user, estado=1)
    return True


def crear_observacion(identrega, idtipo, idcalificacion, descripcion, user):
    """Agrega una observación nueva al catálogo y la asigna a la entrega."""
    if not idtipo:
        raise ErrorValidacion('Debes seleccionar el tipo.')
    if not idcalificacion:
        raise ErrorValidacion('Debes seleccionar la calificación.')
    if not descripcion:
        raise ErrorValidacion('Debes ingresar la descripción.')
    entrega = EntregaProyecto.objects.filter(pk=identrega).first()
    tipo = Tipoobservacion.objects.filter(pk=idtipo).first()
    calificacion = Calificacion.objects.filter(pk=idcalificacion).first()
    if entrega is None or tipo is None or calificacion is None:
        raise NoEncontrado('Entrega, tipo o calificación no encontrada.')
    with transaction.atomic():
        obs = Observacion.objects.create(tipoobservacion=tipo, nombre=descripcion, calificacion=calificacion)
        Entregaobservacion.objects.create(entrega=entrega, observacion=obs, username=user, estado=1)
    return obs
