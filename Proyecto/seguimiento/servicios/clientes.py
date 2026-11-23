"""Servicio de Clientes: acceso a datos y reglas del módulo de clientes.

Único lugar que lee y escribe Cliente y sus tablas: Cliente_Contacto (contactos), Cliente_Categoria (categorías),
Cliente_Seg (notas) y Cliente_Agenda (agenda comercial). No usa procedimientos almacenados.
Los formularios de Django (seguimiento.forms) validan los datos; aquí se graban.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Prefetch, Q
from django.utils import timezone

from ..models import (AspNetUser, Cliente, ClienteAgenda, ClienteCategoria, Clientecontacto, ClienteSeg,
                      Cotizacion, Testadocliente, tusuario)

ESTADO_CLIENTE_ELIMINADO = 5  # tEstadoCliente: la eliminación es lógica
FECHA_MINIMA = date(1900, 1, 1)
DIAS_AGENDA_ATRAS = 30  # la agenda muestra desde hace 30 días
HORA_AGENDA = time(hour=9, minute=0)
TIPOS_CONTACTO = {'N': 'Normal', 'F': 'Facturación', 'C': 'Comercial'}


class ErrorValidacion(ValueError):
    pass


class NoEncontrado(LookupError):
    pass


def ahora():
    return timezone.localtime(timezone.now()).replace(tzinfo=None)


# ---------------------------------------------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------------------------------------------

def todos():
    return Cliente.objects.all()


def activos():
    """Clientes no eliminados."""
    return Cliente.objects.exclude(idestadocliente_id=ESTADO_CLIENTE_ELIMINADO)


def activos_por_nombre():
    return activos().order_by('razonsocial')


def principales_activos():
    return activos().filter(esprincipal=True)


def _con_relaciones():
    return (
        activos()
        .select_related('idestadocliente', 'idcomppago', 'idcliente_p')
        .prefetch_related(Prefetch('clientecategoria_set', queryset=ClienteCategoria.objects.select_related('idcategoria')))
    )


def _ultima_cotizacion(ids_clientes):
    """{idcliente: fecha de su última cotización}."""
    return {row['idcliente']: row['ultima_fecha']
            for row in Cotizacion.objects.filter(idcliente__in=ids_clientes).values('idcliente').annotate(ultima_fecha=Max('fecha'))}


def _anotar(clientes, fechas_por_cliente):
    for cliente in clientes:
        cliente.fecha_ultima_cotizacion = fechas_por_cliente.get(cliente.idcliente)
        categorias = [cc.idcategoria.NombreCat for cc in cliente.clientecategoria_set.all() if cc.idcategoria]
        cliente.categorias_texto = ', '.join(dict.fromkeys(categorias))
        cliente.estado_texto = cliente.idestadocliente.descrip if cliente.idestadocliente_id else ''
        cliente.comportamiento_pago_texto = cliente.idcomppago.descrip if cliente.idcomppago_id else ''


def listado_total():
    """Todos los clientes no eliminados, con categorías, estado, comportamiento de pago y última cotización."""
    clientes = list(_con_relaciones().order_by('razonsocial'))
    _anotar(clientes, _ultima_cotizacion([c.idcliente for c in clientes]))
    return clientes


def listado_principales():
    """Clientes principales. Su última cotización es la más reciente entre la suya y la de sus clientes hijos."""
    clientes = list(_con_relaciones().filter(esprincipal=True).order_by('razonsocial'))
    if not clientes:
        return []
    ids_principales = [c.idcliente for c in clientes]
    fechas_principal = _ultima_cotizacion(ids_principales)

    hijo_a_padre = {}
    for row in activos().filter(idcliente_p__in=ids_principales).values('idcliente', 'idcliente_p'):
        hijo_a_padre[row['idcliente']] = row['idcliente_p']
    fechas_hijos_por_padre = defaultdict(lambda: FECHA_MINIMA)
    if hijo_a_padre:
        for id_hijo, fecha in _ultima_cotizacion(list(hijo_a_padre)).items():
            fecha_hijo = fecha or FECHA_MINIMA
            id_padre = hijo_a_padre.get(id_hijo)
            fecha_actual_padre = fechas_hijos_por_padre[id_padre]
            if id_padre and (fecha_actual_padre is None or (fecha_hijo is not None and fecha_hijo > fecha_actual_padre)):
                fechas_hijos_por_padre[id_padre] = fecha_hijo

    fechas = {}
    for cliente in clientes:
        fecha_cliente = fechas_principal.get(cliente.idcliente) or FECHA_MINIMA
        fecha_hijos = fechas_hijos_por_padre.get(cliente.idcliente) or FECHA_MINIMA
        fechas[cliente.idcliente] = max(fecha_cliente, fecha_hijos) if fecha_cliente and fecha_hijos else (fecha_cliente or fecha_hijos)
    _anotar(clientes, fechas)
    return clientes


def buscar_por_nombre(term, limite=20):
    qs = Cliente.objects.order_by('razonsocial')
    if term:
        qs = qs.filter(razonsocial__icontains=term)
    return list(qs[:limite])


def resumen(pk):
    return Cliente.objects.filter(idcliente=pk).only('idcliente', 'razonsocial', 'direccion', 'telefono').first()


def buscar_contactos(cliente_id=None, term='', limite=20):
    qs = Clientecontacto.objects.select_related('idcliente').order_by('nombrecontacto', 'idcontacto')
    if cliente_id:
        qs = qs.filter(idcliente_id=cliente_id)
    if term:
        qs = qs.filter(nombrecontacto__icontains=term)
    return list(qs[:limite])


def contacto(pk):
    return Clientecontacto.objects.filter(idcontacto=pk).only(
        'idcontacto', 'nombrecontacto', 'cargo', 'telefono', 'email', 'idcliente_id').first()


def buscar_api(*, rut=None, q=''):
    """Listado de la API: q busca en la razón social o en el RUT (acepta 76.357.050-9)."""
    qs = Cliente.objects.all()
    if rut:
        qs = qs.filter(rut=rut)
    if q:
        cond = Q(razonsocial__icontains=q)
        digitos = q.split('-')[0].replace('.', '').strip()
        if digitos.isdigit():
            cond |= Q(rut=int(digitos))
        qs = qs.filter(cond)
    return qs.order_by('razonsocial', 'idcliente')


# ---------------------------------------------------------------------------------------------------------------
# Notas (Cliente_Seg)
# ---------------------------------------------------------------------------------------------------------------

def _id_usuario_nota(username):
    """Cliente_Seg guarda el Id de AspNetUsers (el escritorio); si el usuario no existe allí, su nombre de usuario."""
    identificador = (username or '').strip()
    if not identificador:
        return ''
    usuario_legacy = AspNetUser.objects.filter(username=identificador).only('id').first()
    if usuario_legacy and usuario_legacy.id:
        return usuario_legacy.id
    return identificador


def _fecha_nota():
    # Cliente_Seg es una tabla legacy donde la hora se maneja como valor local sin conversión real de zona horaria.
    # Se guarda la hora local con marca UTC para conservar el mismo reloj visible al leerla después.
    return timezone.localtime(timezone.now()).replace(tzinfo=dt_timezone.utc)


def _nombre_legacy(usuario):
    return ((usuario.nombrecompleto or '').strip() or (usuario.username or '').strip()
            or (usuario.email or '').strip() or (usuario.id or '').strip())


def notas(cliente):
    """Notas del cliente con el nombre de quien las escribió (AspNetUsers, usuario web o tUsuario)."""
    lista = list(ClienteSeg.objects.filter(idcliente=cliente))
    identificadores = {(n.iduser or '').strip() for n in lista if (n.iduser or '').strip()}
    aspnet = list(AspNetUser.objects.filter(Q(id__in=identificadores) | Q(username__in=identificadores)))
    por_id = {u.id: _nombre_legacy(u) for u in aspnet if u.id}
    por_username = {u.username: _nombre_legacy(u) for u in aspnet if u.username}
    auth = {u.username: u for u in get_user_model().objects.filter(username__in=identificadores)}
    legacy = {u.username: (u.nombreusuario or '').strip() for u in tusuario.objects.filter(username__in=identificadores) if u.username}
    for nota in lista:
        identificador = (nota.iduser or '').strip()
        nombre_aspnet = por_id.get(identificador) or por_username.get(identificador)
        usuario_auth = auth.get(identificador)
        nombre_auth = usuario_auth.get_full_name().strip() if usuario_auth else ''
        if nombre_aspnet:
            nota.usuario_nombre = nombre_aspnet
        elif nombre_auth:
            nota.usuario_nombre = nombre_auth
        elif legacy.get(identificador):
            nota.usuario_nombre = legacy[identificador]
        elif usuario_auth:
            nota.usuario_nombre = usuario_auth.username
        elif identificador:
            nota.usuario_nombre = 'Usuario no identificado'
        else:
            nota.usuario_nombre = 'Sin usuario'
        nota.fecha_mostrada = nota.fecha.replace(tzinfo=None) if nota.fecha and timezone.is_aware(nota.fecha) else nota.fecha
    return lista


def agregar_notas(cliente, textos, usuario):
    """Agrega una nota por cada texto no vacío."""
    for texto in textos:
        texto = (texto or '').strip()
        if texto:
            ClienteSeg.objects.create(idcliente=cliente, fecha=_fecha_nota(), iduser=_id_usuario_nota(usuario)[:128], nota=texto)


def guardar_comentario(idcliente, comentario):
    """Notas del cliente (campo Comentario) desde facturación. Como antes, no borra si viene vacío.
    Devuelve True si guardó."""
    if not comentario:
        return False
    Cliente.objects.filter(pk=idcliente).update(comentario=comentario)
    return True


# ---------------------------------------------------------------------------------------------------------------
# Crear, modificar, eliminar
# ---------------------------------------------------------------------------------------------------------------

def crear(cliente):
    """Graba un cliente nuevo (instancia del formulario, sin guardar)."""
    cliente.insercion = ahora()
    cliente.save()
    return cliente


def guardar_ficha(form, formset_contactos, usuario, notas_nuevas=()):
    """Ficha completa del cliente: datos (form), contactos (formset: agrega, modifica, elimina), categorías del
    formulario y notas nuevas. Los formularios deben venir validados."""
    with transaction.atomic():
        cliente = form.save()
        contactos = formset_contactos.save(commit=False)
        for obj in formset_contactos.deleted_objects:
            obj.delete()
        for c in contactos:
            c.idcliente = cliente
            if not c.fecharegistro:
                c.fecharegistro = ahora()
            c.save()
        categorias = list(dict.fromkeys(form.cleaned_data.get('categorias', [])))
        ClienteCategoria.objects.filter(idcliente=cliente).delete()
        if categorias:
            ClienteCategoria.objects.bulk_create([ClienteCategoria(idcliente=cliente, idcategoria=cat) for cat in categorias])
        agregar_notas(cliente, notas_nuevas, usuario)
    return cliente


def eliminar(cliente):
    """Eliminación lógica: el cliente queda en estado Eliminado."""
    estado = Testadocliente.objects.filter(pk=ESTADO_CLIENTE_ELIMINADO).first()
    if estado is None:
        raise NoEncontrado('No existe el estado Eliminado.')
    cliente.idestadocliente = estado
    cliente.save(update_fields=['idestadocliente'])


# ---------------------------------------------------------------------------------------------------------------
# Agenda comercial (Cliente_Agenda)
# ---------------------------------------------------------------------------------------------------------------

def _local_aware(dt):
    if dt is None:
        return None
    return dt if timezone.is_aware(dt) else timezone.make_aware(dt, timezone.get_current_timezone())


def eventos_agenda(desde=None, hasta=None):
    """Eventos de la agenda entre desde y hasta (hora local), nunca antes de hace 30 días, con los contactos del
    cliente. Formato del calendario (FullCalendar)."""
    limite = _local_aware(datetime.combine(timezone.localdate() - timedelta(days=DIAS_AGENDA_ATRAS), time.min))
    desde, hasta = _local_aware(desde), _local_aware(hasta)
    qs = (ClienteAgenda.objects.select_related('idcliente')
          .prefetch_related(Prefetch('idcliente__clientecontacto_set',
                                     queryset=Clientecontacto.objects.order_by('nombrecontacto', 'idcontacto')))
          .filter(fecha__isnull=False)
          .filter(fecha__gte=desde if desde and desde > limite else limite))
    if hasta:
        qs = qs.filter(fecha__lt=hasta)

    eventos = []
    for agenda in qs:
        if not agenda.fecha:
            continue
        fecha_evento = agenda.fecha.date()
        cliente = agenda.idcliente
        if cliente and cliente.razonsocial:
            nombre = cliente.razonsocial
        elif agenda.titulo:
            nombre = agenda.titulo
        elif agenda.idcliente_id:
            nombre = f'Cliente {agenda.idcliente_id}'
        else:
            nombre = 'Cliente sin nombre'
        contactos = []
        if cliente:
            for c in cliente.clientecontacto_set.all():
                if not any([c.nombrecontacto, c.cargo, c.telefono, c.email]):
                    continue
                contactos.append({
                    'tipo': TIPOS_CONTACTO.get((c.tipocontacto or '').strip().upper(), ''),
                    'nombre': c.nombrecontacto or '', 'cargo': c.cargo or '',
                    'telefono': c.telefono or '', 'email': c.email or '',
                })
        eventos.append({
            'id': agenda.id,
            'title': nombre,
            'start': fecha_evento.isoformat(),
            'allDay': True,
            'display': 'block',
            'backgroundColor': '#0d6efd',
            'borderColor': '#0d6efd',
            'textColor': '#ffffff',
            'extendedProps': {
                'cliente': nombre,
                'titulo': agenda.titulo or nombre,
                'descrip': agenda.descrip or '',
                'fecha': fecha_evento.strftime('%d-%m-%Y'),
                'comentario_cliente': cliente.comentario if cliente and cliente.comentario else '',
                'contactos': contactos,
            }
        })
    return eventos


def crear_evento(fecha_texto, idcliente, descrip):
    """Agenda un evento (9:00 del día elegido, desde hoy en adelante) para un cliente no eliminado."""
    if not fecha_texto:
        raise ErrorValidacion('Debes indicar la fecha del evento.')
    if not idcliente:
        raise ErrorValidacion('Debes seleccionar un cliente.')
    if not descrip:
        raise ErrorValidacion('Debes ingresar el detalle del evento.')
    try:
        fecha_evento = datetime.strptime(fecha_texto, '%Y-%m-%d').date()
    except ValueError:
        raise ErrorValidacion('La fecha del evento es inválida.')
    if fecha_evento < timezone.localdate():
        raise ErrorValidacion('Solo puedes registrar eventos desde hoy en adelante.')
    cliente = Cliente.objects.filter(pk=idcliente).first()
    if cliente is None:
        raise NoEncontrado('Cliente no encontrado.')
    if cliente.idestadocliente_id == ESTADO_CLIENTE_ELIMINADO:
        raise ErrorValidacion('No es posible agendar un cliente eliminado.')
    agenda = ClienteAgenda(idcliente=cliente, fecha=_local_aware(datetime.combine(fecha_evento, HORA_AGENDA)),
                           titulo=cliente.razonsocial or f'Cliente {cliente.idcliente}', descrip=descrip, estado=0)
    agenda.save()
    return agenda


def mover_evento(agenda_id, nueva_fecha_texto):
    """Cambia el día de un evento (conserva la hora). No se puede mover antes del rango visible (30 días)."""
    if not nueva_fecha_texto:
        raise ErrorValidacion('Falta la nueva fecha.')
    try:
        fecha_nueva = datetime.strptime(nueva_fecha_texto, '%Y-%m-%d').date()
    except ValueError:
        raise ErrorValidacion('Formato de fecha inválido.')
    if fecha_nueva < timezone.localdate() - timedelta(days=DIAS_AGENDA_ATRAS):
        raise ErrorValidacion('No puedes mover el evento a una fecha anterior al rango visible.')
    with transaction.atomic():
        agenda = ClienteAgenda.objects.select_for_update().filter(pk=agenda_id).first()
        if agenda is None:
            raise NoEncontrado('Evento no encontrado.')
        if not agenda.fecha:
            raise ErrorValidacion('El evento no tiene fecha registrada.')
        agenda.fecha = agenda.fecha.replace(year=fecha_nueva.year, month=fecha_nueva.month, day=fecha_nueva.day)
        agenda.save(update_fields=['fecha'])
    return agenda
