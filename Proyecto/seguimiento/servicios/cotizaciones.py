"""Servicio de Cotizaciones: acceso a datos y reglas del módulo de cotizaciones.

Único lugar que lee y escribe Cotizacion y sus tablas de detalle: Cotizacion_Valor (ítems), Cotizacion_Fpago
(forma de pago), Cotizacion_Nota (notas), Cotizacion_Seg (seguimiento). Las cotizaciones no usan procedimientos
almacenados. Al aprobarse ("Aprobada, Es Proyecto") se crea el proyecto con servicios.proyectos.
"""
import json
from collections import defaultdict

from django.db import transaction
from django.db.models import (CharField, DecimalField, Exists, Max, OuterRef, Q, Subquery, Sum, Value)
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone

from ..models import (Cliente, Clientecontacto, Cotizacion, CotizacionFpago, CotizacionNota, CotizacionSeg,
                      CotizacionValor, Estadocotizacion, ItemCotizacion, NotaCotizacion, Proyecto, TFpago, Tregion)
from . import proyectos

ESTADOS_COTIZACION = {0: 'Borrador', 1: 'Activa', 2: 'Cerrada', 3: 'Anulada'}  # Cotizacion.Estado
ESTADO_EN_ESPERA = 'En Espera'  # única en que se puede editar
ESTADO_APROBADA = 'Aprobada, Es Proyecto'  # al pasar a este estado se crea el proyecto
ID_ESTADO_EN_ESPERA = 1


def ahora():
    return timezone.localtime(timezone.now()).replace(tzinfo=None)


# ---------------------------------------------------------------------------------------------------------------
# Catálogos
# ---------------------------------------------------------------------------------------------------------------

def estados():
    return list(Estadocotizacion.objects.order_by('orden', 'nombre'))


def estados_por_id():
    return Estadocotizacion.objects.order_by('pk')


def estado_en_espera():
    return (Estadocotizacion.objects.filter(pk=ID_ESTADO_EN_ESPERA).first()
            or Estadocotizacion.objects.filter(nombre__iexact=ESTADO_EN_ESPERA).first())


def id_estado_en_espera():
    return Estadocotizacion.objects.filter(nombre__iexact=ESTADO_EN_ESPERA).values_list('pk', flat=True).first()


def nombre_region(codregion):
    if not codregion:
        return ''
    region = Tregion.objects.filter(codregion=codregion).only('descrip').first()
    return region.descrip if region else ''


def formas_pago_catalogo():
    """Formas de pago que se ofrecen en el formulario (TFpago, regionrm = 0)."""
    return TFpago.objects.filter(regionrm=0).order_by('idfpago')


def items_catalogo():
    return ItemCotizacion.objects.all().order_by('iditem')


def notas_catalogo():
    return NotaCotizacion.objects.all().order_by('idnota')


def buscar_mandantes(term, limite=20):
    qs = Cliente.objects.order_by('razonsocial')
    if term:
        qs = qs.filter(razonsocial__icontains=term)
    return list(qs[:limite])


def mandante(pk):
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


# ---------------------------------------------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------------------------------------------

def todas():
    return Cotizacion.objects.all()


def con_relaciones():
    return Cotizacion.objects.select_related('idcliente', 'idcontacto', 'estadocotizacion')


def obtener(pk):
    return con_relaciones().filter(pk=pk).first()


def puede_editar(cotizacion):
    return (cotizacion.estadocotizacion.nombre if cotizacion.estadocotizacion_id else '') == ESTADO_EN_ESPERA


def _con_proyecto_y_ultimo_seguimiento(qs):
    ultimo_seguimiento = CotizacionSeg.objects.filter(idcotizacion=OuterRef('pk')).order_by('-idreg')
    proyecto = Proyecto.objects.filter(idcotizacion=OuterRef('pk')).order_by('idproyecto')
    return qs.annotate(
        tiene_proyecto=Exists(Proyecto.objects.filter(idcotizacion=OuterRef('pk'))),
        num_proyecto=Subquery(proyecto.values('idproyecto')[:1]),
        valor_proyecto=Subquery(proyecto.values('valor')[:1]),
        fpago_proyecto=Subquery(proyecto.values('fpago')[:1]),
        fecha_ultimo_seg=Subquery(ultimo_seguimiento.values('fecharevision')[:1]),
        comentario_ultimo_seg=Subquery(ultimo_seguimiento.values('comentario')[:1]),
    )


def buscar(numero='', proyecto='', mandante='', fecha_desde='', fecha_hasta=''):
    """Búsqueda de Cotizaciones. 'numero' busca en N° de cotización, id y versión."""
    qs = _con_proyecto_y_ultimo_seguimiento(con_relaciones())
    qs = qs.annotate(proyecto_id=Subquery(
        Proyecto.objects.filter(idcotizacion=OuterRef('pk')).order_by('idproyecto').values('idproyecto')[:1]))
    qs = qs.order_by('-numcotizacion', '-numcorr', '-fecha')
    if numero:
        if numero.isdigit():
            numero_int = int(numero)
            qs = qs.filter(Q(idcotizacion=numero_int) | Q(numcotizacion=numero_int) | Q(numcorr=numero_int)
                           | Q(numcotizacion__icontains=numero) | Q(idcotizacion__icontains=numero))
        else:
            qs = qs.annotate(
                numcotizacion_texto=Cast('numcotizacion', CharField()),
                idcotizacion_texto=Cast('idcotizacion', CharField()),
            ).filter(Q(numcorr__icontains=numero) | Q(numcotizacion_texto__icontains=numero)
                     | Q(idcotizacion_texto__icontains=numero))
    if proyecto:
        qs = qs.filter(nombreproyecto__icontains=proyecto)
    if mandante:
        qs = qs.filter(idcliente__razonsocial__icontains=mandante)
    if fecha_desde:
        qs = qs.filter(fecha__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha__lte=fecha_hasta)
    return list(qs)


def buscar_seguimiento(numero='', proyecto='', mandante='', estados_sel=None, fecha_desde='', fecha_hasta='',
                       usar_fechas=True):
    """Seguimiento de Cotizaciones, con el valor de los ítems opcionales (valor_opcional)."""
    qs = _con_proyecto_y_ultimo_seguimiento(con_relaciones()).annotate(
        valor_opcional=Coalesce(
            Sum('cotizacionvalor__valor', filter=Q(cotizacionvalor__opcional='S')),
            Value(0),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        ),
    ).order_by('-fecha', '-numcotizacion', '-numcorr')
    if numero:
        qs = qs.filter(Q(numcotizacion__icontains=numero) | Q(idcotizacion__icontains=numero))
    if proyecto:
        qs = qs.filter(nombreproyecto__icontains=proyecto)
    if mandante:
        qs = qs.filter(idcliente__razonsocial__icontains=mandante)
    if estados_sel:
        qs = qs.filter(estadocotizacion_id__in=estados_sel)
    if usar_fechas:
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)
    return list(qs)


def detalle(cotizacion):
    """Tablas de detalle de una cotización, en el orden en que se muestran."""
    return {
        'proyectos': list(Proyecto.objects.filter(idcotizacion=cotizacion).order_by('idproyecto')),
        'valores': valores(cotizacion),
        'formas_pago': list(CotizacionFpago.objects.filter(idcotizacion=cotizacion).order_by('linea')),
        'notas': list(CotizacionNota.objects.select_related('idnota').filter(idcotizacion=cotizacion).order_by('idcotizacionnota')),
    }


def valores(cotizacion):
    return list(CotizacionValor.objects.filter(idcotizacion=cotizacion).order_by('item'))


def valores_por_cotizacion(ids):
    por_cot = defaultdict(list)
    for v in CotizacionValor.objects.filter(idcotizacion_id__in=list(ids)).order_by('item'):
        por_cot[v.idcotizacion_id].append(v)
    return por_cot


def conceptos_forma_pago(cotizacion):
    return list(CotizacionFpago.objects.filter(idcotizacion=cotizacion).order_by('linea').values_list('concepto', flat=True))


def textos_notas(cotizacion):
    return list(CotizacionNota.objects.filter(idcotizacion=cotizacion).order_by('idcotizacionnota')
                .values_list('idnota__nota', flat=True))


def totales(valores_cotizacion):
    """(total sin opcionales, total con opcionales)."""
    return (sum(float(v.valor or 0) for v in valores_cotizacion if (v.opcional or 'N') != 'S'),
            sum(float(v.valor or 0) for v in valores_cotizacion))


def seguimientos(cotizacion):
    return list(CotizacionSeg.objects.filter(idcotizacion=cotizacion).order_by('-idreg'))


def historial(idcotizacion):
    return list(CotizacionSeg.objects.select_related('usuario').filter(idcotizacion_id=idcotizacion)
                .order_by('-fecharevision', '-idreg'))


def datos_para_formulario(cotizacion):
    """Notas marcadas, forma de pago e ítems para cargar el formulario (editar o copiar)."""
    return {
        'notas_seleccionadas': list(CotizacionNota.objects.filter(idcotizacion=cotizacion).values_list('idnota_id', flat=True)),
        'formapago_items': list(CotizacionFpago.objects.filter(idcotizacion=cotizacion).values('linea', 'concepto').order_by('linea')),
        'items_guardados': list(CotizacionValor.objects.filter(idcotizacion=cotizacion).values('item', 'glosa', 'valor', 'opcional').order_by('item')),
    }


def para_api():
    return Cotizacion.objects.select_related('idcliente', 'idcontacto', 'estadocotizacion')


def buscar_api(*, estados_filtro=None, idcliente=None, rut=None, desde=None, hasta=None, q=''):
    """Listado de la API: q busca en el nombre del proyecto o el N° de cotización (acepta '9321-000')."""
    qs = para_api()
    if estados_filtro:
        qs = qs.filter(estadocotizacion_id__in=estados_filtro)
    if idcliente:
        qs = qs.filter(idcliente_id=idcliente)
    if rut:
        qs = qs.filter(idcliente__rut=rut)
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)
    if q:
        cond = Q(nombreproyecto__icontains=q)
        numero = q.split('-')[0]
        if numero.isdigit():
            cond |= Q(numcotizacion=int(numero))
        qs = qs.filter(cond)
    return qs.order_by('-fecha', '-idcotizacion')


# ---------------------------------------------------------------------------------------------------------------
# Detalle: ítems, forma de pago y notas (llegan del formulario como JSON)
# ---------------------------------------------------------------------------------------------------------------

def _cargar(texto):
    try:
        return json.loads(texto or '[]')
    except json.JSONDecodeError:
        return []


def guardar_items(cotizacion, items_json):
    """Reemplaza los ítems. Item = número de línea (1, 2, 3...), como en el sistema anterior: la llave de
    Cotizacion_Valor es (IdCotizacion, Item), así se pueden repetir glosas y no hay límite de líneas."""
    items = []
    for dato in _cargar(items_json):
        if not isinstance(dato, dict):
            continue
        glosa = (dato.get('glosa') or '').strip()
        if not glosa:
            continue
        try:
            valor = float(dato.get('valor') or 0)
        except (TypeError, ValueError):
            valor = 0
        items.append((len(items) + 1, glosa, valor, 'S' if dato.get('opcional') == 'S' else 'N'))
    CotizacionValor.objects.filter(idcotizacion=cotizacion).delete()
    for item_num, glosa, valor, opcional in items:
        CotizacionValor.objects.create(idcotizacion=cotizacion, item=item_num, glosa=glosa, valor=valor, opcional=opcional)


def guardar_forma_pago(cotizacion, formapago_json):
    conceptos = [(d.get('concepto') or '').strip() for d in _cargar(formapago_json) if isinstance(d, dict)]
    CotizacionFpago.objects.filter(idcotizacion=cotizacion).delete()
    for idx, concepto in enumerate([c for c in conceptos if c], start=1):
        CotizacionFpago.objects.create(idcotizacion=cotizacion, linea=idx, concepto=concepto)


def guardar_notas(cotizacion, notas_json):
    ids_notas = []
    for dato in _cargar(notas_json):
        if dato.get('selected'):
            try:
                ids_notas.append(int(dato.get('id')))
            except (TypeError, ValueError):
                continue
    CotizacionNota.objects.filter(idcotizacion=cotizacion).delete()
    if not ids_notas:
        return
    for nota in NotaCotizacion.objects.filter(idnota__in=ids_notas):
        CotizacionNota.objects.create(idcotizacion=cotizacion, idnota=nota)


def actualizar_valor_total(cotizacion):
    """ValorTotal = suma de todos los ítems (incluidos los opcionales), como el escritorio."""
    total = CotizacionValor.objects.filter(idcotizacion=cotizacion).aggregate(total=Sum('valor'))['total'] or 0
    Cotizacion.objects.filter(pk=cotizacion.pk).update(valortotal=total)


def _guardar_detalle(cotizacion, items_json, formapago_json, notas_json):
    guardar_items(cotizacion, items_json)
    guardar_forma_pago(cotizacion, formapago_json)
    guardar_notas(cotizacion, notas_json)
    actualizar_valor_total(cotizacion)


def copiar_detalle(origen, destino):
    for nota in CotizacionNota.objects.filter(idcotizacion=origen).select_related('idnota').order_by('idcotizacionnota'):
        CotizacionNota.objects.create(idcotizacion=destino, idnota=nota.idnota)
    for fp in CotizacionFpago.objects.filter(idcotizacion=origen).order_by('linea'):
        CotizacionFpago.objects.create(idcotizacion=destino, linea=fp.linea, concepto=fp.concepto)
    for valor in CotizacionValor.objects.filter(idcotizacion=origen).order_by('item'):
        CotizacionValor.objects.create(idcotizacion=destino, item=valor.item, glosa=valor.glosa, valor=valor.valor,
                                       opcional=valor.opcional)


# ---------------------------------------------------------------------------------------------------------------
# Crear, modificar, versionar
# ---------------------------------------------------------------------------------------------------------------

def crear(cotizacion, usuario, *, fecha=None, items_json='', formapago_json='', notas_json=''):
    """Graba una cotización nueva (instancia sin guardar, con los datos del formulario): N° = máximo + 1 (salvo
    que venga uno), versión 0, En Espera, activa, origen WEB; luego su detalle."""
    with transaction.atomic():
        cotizacion.fecha = fecha or timezone.localdate()
        cotizacion.estadocotizacion = estado_en_espera()
        siguiente = (Cotizacion.objects.aggregate(mx=Max('numcotizacion'))['mx'] or 0) + 1
        cotizacion.numcotizacion = cotizacion.numcotizacion or siguiente
        cotizacion.numcorr = 0
        cotizacion.estado = 0
        cotizacion.esactiva = True
        cotizacion.idusuario = (usuario or '')[:15]
        cotizacion.origen = 'WEB'
        cotizacion.fecharegistro = cotizacion.fechaact = ahora()
        cotizacion.save()
        _guardar_detalle(cotizacion, items_json, formapago_json, notas_json)
    return cotizacion


def modificar(cotizacion, *, fecha=None, items_json='', formapago_json='', notas_json=''):
    """Graba los cambios del formulario (instancia ya modificada) y reemplaza su detalle."""
    with transaction.atomic():
        cotizacion.fecha = fecha or cotizacion.fecha
        cotizacion.fechaact = ahora()
        cotizacion.origen = cotizacion.origen or 'WEB'
        cotizacion.save()
        _guardar_detalle(cotizacion, items_json, formapago_json, notas_json)
    return cotizacion


def versionar(base, usuario):
    """Nueva versión (mismo N°, versión + 1) con los datos y el detalle de la cotización base."""
    with transaction.atomic():
        nueva = Cotizacion(
            numcotizacion=base.numcotizacion,
            numcorr=(base.numcorr or 0) + 1,
            fecha=timezone.localdate(),
            idcliente=base.idcliente,
            idcontacto=base.idcontacto,
            nombreproyecto=base.nombreproyecto,
            dirproyecto=base.dirproyecto,
            codregion=base.codregion,
            destino=base.destino,
            pisos=base.pisos,
            edificios=base.edificios,
            valortotal=base.valortotal,
            moneda=base.moneda,
            estado=0,
            estadocotizacion=estado_en_espera(),
            idusuario=(usuario or '')[:15],
            origen='WEB',
            fechaact=ahora(),
            esactiva=True,
            mt2=base.mt2,
            fecharegistro=ahora(),
        )
        nueva.save()
        copiar_detalle(base, nueva)
        actualizar_valor_total(nueva)
    return nueva


# ---------------------------------------------------------------------------------------------------------------
# Seguimiento
# ---------------------------------------------------------------------------------------------------------------

def validar_seguimiento(*, comentario, cambia_estado, nuevo_estado, es_recordatorio, fecha_recordatorio,
                        quien_adjudica, email_adjudicacion, fecha_adjudicacion):
    """Errores por campo ({campo: mensaje}) del seguimiento, con las reglas del escritorio."""
    errores = {}
    if not comentario:
        errores['comentario'] = 'Debe ingresar comentario del seguimiento.'
    if cambia_estado and not nuevo_estado:
        errores['nuevo_estado'] = 'Debe seleccionar el nuevo estado.'  # antes dejaba la cotización sin estado
    if cambia_estado and nuevo_estado and nuevo_estado.nombre == ESTADO_APROBADA:
        if not fecha_adjudicacion:
            errores['fecha_adjudicacion'] = 'Debe ingresar fecha de adjudicación.'
        if not quien_adjudica:
            errores['quien_adjudica'] = 'Debe ingresar quién adjudica.'
        if not email_adjudicacion:
            errores['email_adjudicacion'] = 'Debe ingresar eMail quien adjudica.'
    if es_recordatorio and fecha_recordatorio and fecha_recordatorio <= timezone.localdate():
        errores['fecha_recordatorio'] = 'Ingrese fecha de recordatorio mayor a hoy.'
    return errores


def registrar_seguimiento(cotizacion, user, *, comentario, es_recordatorio=False, fecha_recordatorio=None,
                          nuevo_estado=None, quien_adjudica='', email_adjudicacion='', fecha_adjudicacion=None):
    """Agrega el seguimiento y, si viene nuevo_estado, cambia el estado. Al aprobarse se crea el proyecto
    (servicios.proyectos.crear_desde_cotizacion). 'user' es el usuario de Django (Cotizacion_Seg.Usuario)."""
    with transaction.atomic():
        ultimo_idreg = CotizacionSeg.objects.filter(idcotizacion=cotizacion).aggregate(mx=Max('idreg'))['mx'] or 0
        CotizacionSeg(
            idcotizacion=cotizacion,
            idreg=ultimo_idreg + 1,
            usuario=user,
            fecharevision=ahora(),
            comentario=comentario,
            esrecordatorio=es_recordatorio,
            fecharecordatorio=fecha_recordatorio,
        ).save(force_insert=True)
        if nuevo_estado is not None:
            cotizacion.estadocotizacion = nuevo_estado
            if nuevo_estado.nombre == ESTADO_APROBADA:
                cotizacion.estado = 1
                proyectos.crear_desde_cotizacion(cotizacion, quien_adjudica=quien_adjudica,
                                                 email_adjudicacion=email_adjudicacion,
                                                 fecha_adjudicacion=fecha_adjudicacion)
            cotizacion.fechaact = ahora()
            cotizacion.save(update_fields=['estadocotizacion', 'estado', 'fechaact'])
