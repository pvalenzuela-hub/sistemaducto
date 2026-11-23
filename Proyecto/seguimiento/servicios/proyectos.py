"""Servicio de Proyectos: acceso a datos y reglas del módulo de proyectos.

Es el único lugar que lee y escribe Proyecto y su bitácora Proyecto_Seg, y que llama a los procedimientos de
proyectos que comparte el sistema de escritorio (VB.NET):

    SEG_ConsultaProyecto_WEB   listados antiguos (terminados, visto bueno, en desarrollo)
    EL_Proyecto_SEG            eliminar comentario de seguimiento
    REP_Adjudicacion           reporte de adjudicaciones
    Consulta_AgnoAdjudicacion  años con adjudicaciones

Estado del proyecto: el escritorio usa Proyecto.Estado con los códigos de tEstado (0 a 17) y la web usa
estadoproyecto_id, que es el mismo código + 1. Toda escritura de estado pasa por cambiar_estado(), que
actualiza ambos.

SEREMI (datos del trámite y su bitácora) está en servicios.seremi.
"""
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal

from django.db import connection, transaction
from django.db.models import Max, Q
from django.utils import timezone

from ..models import Cliente, Clientecontacto, Factura, Proyecto, ProyectoSeg, Tregion, estadoproyecto
from . import bitacora

# Estados marcados por defecto en el filtro de Seguimiento de Proyectos (estadoproyecto_id): Nuevo, Con Datos de
# Facturación, Entrega Versión Revisión, Con Observaciones, Con VB para Ingreso a SEREMI, A Espera de VB y EN PAUSA.
# Quedan fuera los estados SEREMI avanzados, terminados y anulados (pedido de Paulo, 2026-11-20).
ESTADOS_PROYECTO_ACTIVOS = [1, 2, 3, 4, 5, 9, 11]
ESTADO_NUEVO = 1
ESTADO_CON_DATOS_FACTURACION = 2
ESTADO_PROYECTO_ANULADO = 8  # no se facturan proyectos anulados

MEDIOS_CONF = ['Orden de Compra', 'Contrato', 'eMail', 'Orden de Trabajo', 'Carta Adjudicación', '........']

# (código tEstado del nuevo estado, campo del formulario, campo del modelo, nombre, obligatoria)
# Igual que SEG_EditaProyecto / GR_Proyecto_SEG del escritorio: según el nuevo estado se pide y guarda una fecha.
FECHAS_POR_ESTADO_PROYECTO = [
    (2, 'fecha_primer_envio', 'fechaprimereenvio', 'la Fecha de Primera Entrega', True),     # Entrega Versión Revisión
    (5, 'fecha_ingreso_seremi', 'fechaingresoseremi', 'la Fecha de Ingreso a SEREMI', True),  # Proyecto Ingresado a SEREMI
    (6, 'fecha_aprob_seremi', 'fechaaprobseremi', 'la Fecha de Aprobación SEREMI', False),   # Terminado y Aprobado en SEREMI
]


class ErrorValidacion(ValueError):
    pass


def ahora():
    """Hora local de Chile sin zona, como se guardan las fechas-hora en la base."""
    return timezone.localtime(timezone.now()).replace(tzinfo=None)


def estado_web(cod_estado):
    """estadoproyecto_id que corresponde a un código de tEstado (Proyecto.Estado)."""
    return None if cod_estado is None else int(cod_estado) + 1


# ---------------------------------------------------------------------------------------------------------------
# Catálogos
# ---------------------------------------------------------------------------------------------------------------

def estados():
    """Estados de proyecto de la web (estadoproyecto), por id."""
    return estadoproyecto.objects.order_by('id')


def estados_por_nombre():
    return estadoproyecto.objects.order_by('nombre')


def ids_estados():
    return list(estadoproyecto.objects.values_list('id', flat=True))


def nombres_estados():
    """{id: nombre} de los estados de proyecto (sin recortar)."""
    return dict(estadoproyecto.objects.values_list('id', 'nombre'))


def regiones():
    return {r.codregion: r.descrip for r in Tregion.objects.all()}


def regiones_de(codigos):
    codigos = {c for c in codigos if c is not None}
    if not codigos:
        return {}
    return dict(Tregion.objects.filter(codregion__in=codigos).values_list('codregion', 'descrip'))


def mandantes():
    """Clientes que son mandantes (cliente de la cotización) de algún proyecto."""
    return Cliente.objects.filter(
        idcliente__in=Proyecto.objects.values('idcotizacion__idcliente_id').distinct()
    ).distinct().order_by('razonsocial')


def clientes():
    """Clientes que aparecen en algún proyecto (como cliente de facturación o secundario)."""
    return Cliente.objects.filter(
        Q(proyectos_principales__isnull=False) | Q(proyectos_secundarios__isnull=False)
    ).distinct().order_by('razonsocial')


def contactos_facturacion():
    return Clientecontacto.objects.select_related('idcliente').order_by('nombrecontacto')


# ---------------------------------------------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------------------------------------------

def todos():
    return Proyecto.objects.all()


def obtener(idproyecto):
    return Proyecto.objects.filter(pk=idproyecto).first()


def para_facturar():
    """Proyecto con lo que necesita Crear Factura."""
    return Proyecto.objects.select_related('idcliente', 'idcontactofacturacion', 'estadoproyecto')


def para_glosa():
    return Proyecto.objects.select_related('idcotizacion__idcliente', 'estadoproyecto')


def buscar_seguimiento(estados_sel, mandante=None, numero=None):
    """Listado de Seguimiento de Proyectos. Buscar por N° de proyecto busca en todos los estados, como el escritorio."""
    qs = Proyecto.objects.select_related(
        'idcotizacion', 'idcotizacion__idcliente', 'idcotizacion__idcontacto', 'idcliente', 'idcontactofacturacion',
        'estadoproyecto',
    )
    if not numero:
        qs = qs.filter(estadoproyecto_id__in=estados_sel)
    if mandante:
        qs = qs.filter(idcotizacion__idcliente_id=mandante)
    if numero:
        qs = qs.filter(idproyecto__icontains=numero)
    return list(qs.order_by('idcotizacion__codregion', 'idproyecto'))


def buscar_reporte(estados_sel=None, mandante=None, cliente=None, numero=None):
    """Reporte de Proyectos. Sin estados elegidos se incluyen todos."""
    qs = Proyecto.objects.select_related('idcotizacion', 'idcotizacion__idcliente', 'idcliente', 'estadoproyecto')
    if estados_sel:
        qs = qs.filter(estadoproyecto_id__in=estados_sel)
    if mandante:
        qs = qs.filter(idcotizacion__idcliente_id=mandante)
    if cliente:
        qs = qs.filter(idcliente_id=cliente)
    if numero:
        qs = qs.filter(idproyecto__icontains=numero)
    return list(qs.order_by('idcotizacion__codregion', 'idproyecto'))


def para_api():
    return Proyecto.objects.select_related('idcliente', 'estadoproyecto', 'idcotizacion__idcliente')


def buscar_api(*, estados_filtro=None, idcliente=None, rut=None, desde=None, hasta=None, q=''):
    """Listado de la API. idcliente y rut buscan como cliente o como mandante; q busca nombre, N° de proyecto o
    N° de cotización. Del más nuevo al más antiguo."""
    qs = para_api()
    if estados_filtro:
        qs = qs.filter(estadoproyecto_id__in=estados_filtro)
    if idcliente:
        qs = qs.filter(Q(idcliente_id=idcliente) | Q(idcotizacion__idcliente_id=idcliente))
    if rut:
        qs = qs.filter(Q(idcliente__rut=rut) | Q(idcotizacion__idcliente__rut=rut))
    if desde:
        qs = qs.filter(fechacreacion__gte=desde)
    if hasta:
        qs = qs.filter(fechacreacion__lte=hasta)
    if q:
        cond = Q(idcotizacion__nombreproyecto__icontains=q)
        if q.isdigit():
            cond |= Q(idproyecto=int(q)) | Q(idcotizacion__numcotizacion=int(q))
        qs = qs.filter(cond)
    return qs.order_by('-idproyecto')


def ids_por_cotizacion(ids_cotizacion):
    """{idcotizacion: [idproyecto, ...]}."""
    por_cot = defaultdict(list)
    for idcot, idproy in Proyecto.objects.filter(idcotizacion_id__in=list(ids_cotizacion)).values_list('idcotizacion_id', 'idproyecto'):
        por_cot[idcot].append(int(idproy))
    return por_cot


def facturacion_completa(proyecto):
    """Datos de facturación completos: requisito para crear facturas."""
    return all([
        proyecto.idcliente_id,
        proyecto.numconf,
        proyecto.medioconf,
        proyecto.fechaconf,
        proyecto.conhes is not None,
        proyecto.coneepp is not None,
        proyecto.conotro is not None,
    ])


def consulta_web(tipo):
    """SEG_ConsultaProyecto_WEB: 1 = terminados, 2 = con visto bueno, 3 = en desarrollo."""
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC [ducto].[SEG_ConsultaProyecto_WEB] %s', [tipo])
        return cursor.fetchall()


def nombre(idproyecto):
    with connection.cursor() as cursor:
        cursor.execute('SELECT b.NombreProyecto FROM Proyecto a JOIN Cotizacion b ON b.IdCotizacion = a.IdCotizacion '
                       'WHERE a.IdProyecto = %s', [idproyecto])
        fila = cursor.fetchone()
    return fila[0] if fila else ''


# ---------------------------------------------------------------------------------------------------------------
# % por facturar: una sola regla para web, glosa y API, la del escritorio (dbo.SaldoPorFacturar).
# Solo descuentan las facturas emitidas (Emitida, Pendiente de Pago, Pago por Retirar, Pagada, Pago Verificado);
# Provisoria, Para Emitir, En Pausa y NULA no. Un proyecto facturado sobre el 100% queda con saldo negativo, a la
# vista para revisarlo (decisión de Paulo, 2026-11-23).
# ---------------------------------------------------------------------------------------------------------------

def saldos_por_facturar(ids_proyecto):
    """{idproyecto (int): % que falta facturar}, calculado por dbo.SaldoPorFacturar."""
    ids = sorted({int(i) for i in ids_proyecto if i is not None})
    saldos = {}
    with connection.cursor() as cursor:
        for i in range(0, len(ids), 1000):  # SQL Server admite hasta 2.100 parámetros por consulta
            tramo = ids[i:i + 1000]
            cursor.execute(f"SELECT IdProyecto, dbo.SaldoPorFacturar(IdProyecto) FROM Proyecto "
                           f"WHERE IdProyecto IN ({','.join(['%s'] * len(tramo))})", tramo)
            saldos.update({int(pid): float(saldo) for pid, saldo in cursor.fetchall()})
    return saldos


def porcentajes_facturados(ids_proyecto):
    """{idproyecto: % facturado} = 100 - saldo por facturar, con 2 decimales."""
    return {pid: round(100 - saldo, 2) for pid, saldo in saldos_por_facturar(ids_proyecto).items()}


# ---------------------------------------------------------------------------------------------------------------
# Bitácora Proyecto_Seg
# ---------------------------------------------------------------------------------------------------------------

def _ids(ids_proyecto):
    return [str(pid) for pid in ids_proyecto if pid is not None]


def textos_seguimiento(ids_proyecto):
    """{'idproyecto': todo el seguimiento como texto, del más antiguo al más nuevo}."""
    ids = _ids(ids_proyecto)
    if not ids:
        return {}
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT IdProyecto, Comentario, Fecha, ISNULL(IdUsuario,'') FROM Proyecto_Seg "
                       f"WHERE IdProyecto IN ({','.join(['%s'] * len(ids))}) ORDER BY IdProyecto, Fecha", ids)
        filas = cursor.fetchall()
    textos = defaultdict(list)
    for idproyecto, comentario, fecha, idusuario in filas:
        fecha_txt = fecha.strftime('%d/%m/%Y %H:%M') if fecha else ''
        textos[str(idproyecto)].append(f"{fecha_txt} : ({idusuario or ''}) {str(comentario).rstrip()}")
    return {k: "\n".join(v) for k, v in textos.items()}


def ultimas_fechas_seguimiento(ids_proyecto):
    """{'idproyecto': fecha del último seguimiento}."""
    ids = _ids(ids_proyecto)
    if not ids:
        return {}
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT IdProyecto, MAX(Fecha) FROM Proyecto_Seg WHERE IdProyecto IN ({','.join(['%s'] * len(ids))}) "
                       "GROUP BY IdProyecto", ids)
        return {str(idproyecto): fecha for idproyecto, fecha in cursor.fetchall()}


def seguimiento_cronologico(idproyecto):
    """(IdProyecto, Comentario, Fecha) del más antiguo al más nuevo (visor de las pantallas antiguas)."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT IdProyecto, Comentario, Fecha FROM Proyecto_Seg WHERE IdProyecto = %s ORDER BY Fecha',
                       [idproyecto])
        return cursor.fetchall()


def comentarios(idproyecto):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT IdReg, Fecha, Comentario, ISNULL(EsRecordatorio, 0), FechaRecordatorio, ISNULL(IdUsuario, '') "
            "FROM Proyecto_Seg WHERE IdProyecto = %s ORDER BY IdReg DESC", [idproyecto])
        return [{
            'idreg': idreg,
            'fecha': fecha.strftime('%d/%m/%Y %H:%M') if fecha else '',
            'fecha_iso': fecha.strftime('%Y-%m-%d') if fecha else '',
            'comentario': (comentario or '').rstrip(),
            'es_recordatorio': bool(es_rec),
            'fecha_recordatorio': fecha_rec.strftime('%Y-%m-%d') if fecha_rec else '',
            'usuario': usuario,
        } for idreg, fecha, comentario, es_rec, fecha_rec, usuario in cursor.fetchall()]


def agregar_comentario(idproyecto, comentario, usuario, estado, fecha_recordatorio=None):
    """Agrega un comentario a Proyecto_Seg (IdReg = máximo + 1). 'estado' es el estado del proyecto que queda
    registrado junto al comentario."""
    ultimo_idreg = ProyectoSeg.objects.filter(idproyecto_id=idproyecto).aggregate(mx=Max('idreg'))['mx'] or 0
    data = {
        'idproyecto_id': idproyecto,
        'idreg': int(ultimo_idreg) + 1,
        'fecha': ahora(),
        'comentario': comentario,
        'idusuario': (usuario or '')[:15],
        'estado': estado,
    }
    if fecha_recordatorio:
        data['esrecordatorio'] = True
        data['fecharecordatorio'] = fecha_recordatorio
    return ProyectoSeg.objects.create(**data)


def editar_comentario(idproyecto, idreg, comentario, dia, usuario, es_recordatorio=False, fecha_recordatorio=None):
    """Como AC_Proyecto_SEG: cambia fecha, texto y recordatorio; el usuario queda como quien editó.
    Si el día no cambia se conserva la hora (el procedimiento recibe solo la fecha y la perdía).
    Devuelve False si el comentario ya no existe."""
    if not comentario:
        raise ErrorValidacion('El comentario no puede quedar vacío.')
    with connection.cursor() as cursor:
        cursor.execute('SELECT Fecha FROM Proyecto_Seg WHERE IdProyecto = %s AND IdReg = %s', [idproyecto, idreg])
        fila = cursor.fetchone()
        if fila is None:
            return False
        fecha = fila[0] if fila[0] and fila[0].date() == dia else datetime.combine(dia, time.min)
        cursor.execute(
            'UPDATE Proyecto_Seg SET Fecha = %s, Comentario = %s, IdUsuario = %s, EsRecordatorio = %s, '
            'FechaRecordatorio = %s WHERE IdProyecto = %s AND IdReg = %s',
            [fecha, comentario, (usuario or '')[:15], int(bool(es_recordatorio)),
             fecha_recordatorio if es_recordatorio else None, idproyecto, idreg])
    return True


def eliminar_comentario(idproyecto, idreg):
    """EL_Proyecto_SEG."""
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC EL_Proyecto_SEG %s, %s', [idproyecto, idreg])


# Bitácora con formato de la API (fecha como datetime, sin recordatorios)
def listar_comentarios_api(idproyecto):
    return bitacora.proyecto.listar(idproyecto)


def ultimos_comentarios(ids):
    return bitacora.proyecto.ultimos(ids)


def comentar_api(idproyecto, comentario, usuario, estado):
    """Comentario desde la API. Debe llamarse dentro de transaction.atomic()."""
    return bitacora.proyecto.agregar(idproyecto, comentario, usuario, estado=estado)


# ---------------------------------------------------------------------------------------------------------------
# Estado y seguimiento
# ---------------------------------------------------------------------------------------------------------------

def cambiar_estado(proyecto, nuevo_estado_id, *, actualiza_fecha=True, **otros_campos):
    """Cambia el estado actualizando estadoproyecto_id (web) y Estado (código tEstado = id - 1, escritorio)."""
    campos = {'estadoproyecto_id': nuevo_estado_id, 'estado': nuevo_estado_id - 1, **otros_campos}
    if actualiza_fecha:
        campos['fechaact'] = timezone.localdate()
    Proyecto.objects.filter(pk=proyecto.pk).update(**campos)


def registrar_seguimiento(proyecto, usuario, *, comentario='', nuevo_estado_id=None, fechas=None,
                          fecha_recordatorio=None):
    """Seguimiento de Proyectos: cambio de estado (con su fecha según FECHAS_POR_ESTADO_PROYECTO) y/o comentario.

    'fechas' son los textos AAAA-MM-DD del formulario por campo (fecha_primer_envio, ...). Valida como el escritorio:
    cambiar de estado o poner recordatorio exige comentario; el recordatorio debe ser posterior a hoy.
    """
    if fecha_recordatorio is not None:
        if fecha_recordatorio <= timezone.localdate():
            raise ErrorValidacion('La fecha de recordatorio debe ser posterior a hoy.')
        if not comentario:
            raise ErrorValidacion('Debe ingresar comentario del seguimiento.')

    cambia_estado = bool(nuevo_estado_id) and int(nuevo_estado_id) != proyecto.estadoproyecto_id
    if cambia_estado and not comentario:
        raise ErrorValidacion('Debe ingresar comentario del seguimiento.')

    fechas_estado = {}
    if cambia_estado:
        codigo_nuevo = int(nuevo_estado_id) - 1
        for codigo, campo_post, campo_modelo, nombre_fecha, obligatoria in FECHAS_POR_ESTADO_PROYECTO:
            if codigo != codigo_nuevo:
                continue
            texto = ((fechas or {}).get(campo_post) or '').strip()
            try:
                valor = date.fromisoformat(texto) if texto else None
            except ValueError:
                raise ErrorValidacion(f'{nombre_fecha}: fecha inválida.')
            if obligatoria and not valor:
                raise ErrorValidacion(f'Debe ingresar {nombre_fecha}.')
            if valor:
                fechas_estado[campo_modelo] = valor

    with transaction.atomic():
        if cambia_estado:
            cambiar_estado(proyecto, int(nuevo_estado_id), **fechas_estado)
            proyecto.refresh_from_db()
        if comentario:
            agregar_comentario(proyecto.pk, comentario, usuario, proyecto.estadoproyecto_id or 0,
                               fecha_recordatorio=fecha_recordatorio)


def cambiar_estado_api(proyecto, nuevo_estado, comentario, usuario):
    """API: cambia el estado (exige comentario, igual que la web) y/o agrega un comentario.

    Devuelve (cambió_estado, comentario creado o None). Debe llamarse dentro de transaction.atomic().
    """
    nombres = nombres_estados()
    estado_actual = proyecto.estadoproyecto_id
    cambia = nuevo_estado != estado_actual
    if cambia and not comentario:
        raise ErrorValidacion("Para cambiar el estado se requiere 'comentario', igual que en la aplicación web")
    if cambia:
        cambiar_estado(proyecto, nuevo_estado, actualiza_fecha=False)
    nuevo = None
    if comentario:
        if cambia:
            comentario = f"[API] Estado: {(nombres.get(estado_actual) or '-').strip()} -> " \
                         f"{nombres[nuevo_estado].strip()}. {comentario}"
        nuevo = comentar_api(proyecto.pk, comentario, usuario, nuevo_estado)
    return cambia, nuevo


# ---------------------------------------------------------------------------------------------------------------
# Datos de facturación
# ---------------------------------------------------------------------------------------------------------------

def guardar_datos_facturacion(proyecto, usuario, *, idcliente, moneda, valor, medioconf, fpago, numconf, fechaconf,
                              conhes, coneepp, conotro, idcontacto, email_contacto, comentario=''):
    """Igual que GR_Proyecto_DatosFactura del escritorio, más el paso de estado de la web.

    El email de facturación es el del contacto elegido (si se escribe otro, se respeta) y se registra cuándo se
    asignó el contacto. Las facturas del proyecto sin cliente quedan con el cliente de facturación.
    El escritorio no cambia el estado; en la web este botón pasa "Proyecto Nuevo" a "Proyecto con Datos de
    Facturación" (un proyecto más avanzado conserva su estado). Devuelve True si avanzó el estado.
    """
    proyecto.idcliente_id = idcliente
    proyecto.moneda = moneda
    proyecto.valor = valor
    proyecto.medioconf = medioconf
    proyecto.fpago = fpago
    proyecto.numconf = numconf
    proyecto.fechaconf = fechaconf
    proyecto.conhes = conhes
    proyecto.coneepp = coneepp
    proyecto.conotro = conotro
    if idcontacto:
        contacto = Clientecontacto.objects.filter(pk=idcontacto).first()
        if contacto and contacto.pk != proyecto.idcontactofacturacion_id:
            proyecto.fecharegistrocontacto = ahora()
        proyecto.idcontactofacturacion_id = idcontacto
        proyecto.emailcontactofacturacion = email_contacto or (contacto.email if contacto else None)
    else:
        proyecto.idcontactofacturacion_id = None
        proyecto.emailcontactofacturacion = email_contacto or None
    proyecto.fechaact = timezone.now().date()
    avanza_estado = proyecto.estadoproyecto_id in (None, ESTADO_NUEVO)
    if avanza_estado:
        proyecto.estadoproyecto_id = ESTADO_CON_DATOS_FACTURACION
        proyecto.estado = ESTADO_CON_DATOS_FACTURACION - 1
    with transaction.atomic():
        proyecto.save()
        if proyecto.idcliente_id:
            Factura.objects.filter(idproyecto=proyecto, idcliente__isnull=True).update(idcliente_id=proyecto.idcliente_id)
        if comentario:
            agregar_comentario(proyecto.idproyecto, comentario, usuario, proyecto.estadoproyecto_id or 0)
    return avanza_estado


# ---------------------------------------------------------------------------------------------------------------
# Creación (al aprobar una cotización)
# ---------------------------------------------------------------------------------------------------------------

def crear_desde_cotizacion(cotizacion, *, quien_adjudica=None, email_adjudicacion=None, fecha_adjudicacion=None):
    """Crea el proyecto de una cotización aprobada (si no tiene uno), con N° = máximo + 1. Devuelve el proyecto
    creado o None si ya existía."""
    if Proyecto.objects.filter(idcotizacion=cotizacion).exists():
        return None
    proyecto_id = (Proyecto.objects.aggregate(mx=Max('idproyecto'))['mx'] or Decimal('0')) + Decimal('1')
    return Proyecto.objects.create(
        idproyecto=proyecto_id,
        fechacreacion=timezone.localdate(),
        idcotizacion=cotizacion,
        fpago='',
        valor=float(cotizacion.valortotal or 0),
        estadoproyecto_id=ESTADO_NUEVO,
        estado=ESTADO_NUEVO - 1,
        idcliente=cotizacion.idcliente,
        fechaact=timezone.localdate(),
        quienadjudica=quien_adjudica or None,
        emailadjudicacion=email_adjudicacion or None,
        fechaadjudicacion=fecha_adjudicacion,
        moneda=cotizacion.moneda,
        fecharegistro=ahora(),
    )


# ---------------------------------------------------------------------------------------------------------------
# Reporte de Adjudicaciones (REP_Adjudicacion / Report4 del escritorio)
# ---------------------------------------------------------------------------------------------------------------

def anios_adjudicacion():
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC Consulta_AgnoAdjudicacion')
        return [int(r[0]) for r in cursor.fetchall()]


def adjudicaciones(desde_anio):
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
