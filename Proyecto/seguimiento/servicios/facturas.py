"""Servicio de Facturas: acceso a datos y reglas del módulo de facturas.

Es el único lugar que toca las tablas Factura / Factura_Seg y los procedimientos almacenados de facturas que
comparte el sistema de escritorio (VB.NET):

    SEG_ConsultaFactura   listado de Seguimiento de Facturas
    GR_Factura_SEG        nuevo seguimiento, cambio de estado y datos del cliente
    EL_Factura_SEG        eliminar comentario de seguimiento
    GR_CreaFactura        crear / modificar factura (solo Provisoria o Para Emitir)
    EL_Factura            eliminar factura y su seguimiento
    CO_FacturaxProyecto   facturas de un proyecto
    CO_Factura            datos de una factura
    CO_FacturaxNumero     buscar factura por número
    dbo.SaldoPorFacturar  % del proyecto que falta facturar
    dbo.Fx_ObtieneSEGFactura  seguimiento de la factura como texto

Las vistas web (seguimiento.views_facturas, seguimiento.views) y la API (api.views) solo leen la solicitud,
llaman a estas funciones y arman la respuesta.
"""
from datetime import date, datetime

from django.db import connection, transaction
from django.utils import timezone

from ..models import Clientecontacto, Factura
from . import bitacora

TIPO_ESTADO_FACTURA = 3  # tEstado.TipoEstado: 1=cotización, 2=proyecto, 3=factura
ESTADO_PAGADA = 5  # GR_Factura_SEG (escritorio y web) exige fecha de pago solo para este estado
ESTADOS_PAGADA_API = {5, 8}  # la API exige fecha de pago para Pagada y Pago Verificado
ESTADOS_EDITABLES = (0, 1)  # GR_CreaFactura solo modifica facturas Provisoria o Para Emitir
DETALLES_FACTURA = ['Anticipo', 'Entrega V00', 'Entrega V Final', 'Saldo', 'V Licitación', 'V Construcción']

# Largo máximo de los parámetros de GR_Factura_SEG
MAX_HORARIO_LLAMADA = 80
MAX_DIREC_RETIRO = 80
MAX_HORARIO_RETIRO = 50
MAX_DETALLE = 100
MAX_NUM_HES = 50


class ErrorValidacion(ValueError):
    pass


MENSAJE_NO_VUELVE = ('Una factura ya emitida no puede volver a Provisoria o Para Emitir: '
                     'solo esos estados permiten modificar la factura.')


def puede_cambiar_estado(estado_actual, estado_nuevo):
    """Una factura que ya salió de Provisoria / Para Emitir (emitida, pagada, nula...) no puede volver a esos
    estados: así no se puede modificar una factura emitida (decisión de Paulo, 2026-11-23). Solo web y API;
    el escritorio cambia estados con su propio procedimiento."""
    return not (estado_actual not in ESTADOS_EDITABLES and estado_nuevo in ESTADOS_EDITABLES)


def validar_cambio_estado(estado_actual, estado_nuevo):
    if not puede_cambiar_estado(estado_actual, estado_nuevo):
        raise ErrorValidacion(MENSAJE_NO_VUELVE)


# ---------------------------------------------------------------------------------------------------------------
# Formatos (iguales a los del sistema anterior)
# ---------------------------------------------------------------------------------------------------------------

def pesos(valor):
    if valor is None:
        return ''
    return f"{float(valor):,.0f}".replace(',', '.')


def numero_cl(valor, decimales=0):
    """Número con formato chileno: miles con punto y decimales con coma."""
    if valor is None:
        return ''
    texto = f"{float(valor):,.{decimales}f}"
    return texto.replace(',', 'X').replace('.', ',').replace('X', '.')


def porcentaje(valor):
    """Como PorcFacturar.ToString() del sistema anterior: sin decimales sobrantes."""
    if valor is None:
        return ''
    valor = round(float(valor), 2)
    return numero_cl(valor, 0) if valor.is_integer() else numero_cl(valor, 2).rstrip('0').rstrip(',')


def fecha_corta(valor):
    """dd/mm/aa, como las fechas que el sistema anterior pone en la descripción."""
    if not valor:
        return ''
    if isinstance(valor, str):
        try:
            valor = datetime.strptime(valor.strip(), '%d/%m/%Y').date()
        except ValueError:
            try:
                valor = date.fromisoformat(valor.strip())
            except ValueError:
                return valor
    return valor.strftime('%d/%m/%y')


# ---------------------------------------------------------------------------------------------------------------
# Catálogo y consultas
# ---------------------------------------------------------------------------------------------------------------

def estados():
    """[(código, nombre)] de los estados de factura (tEstado, TipoEstado 3), ordenados por código."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT CodEstado, Descrip FROM tEstado WHERE TipoEstado = %s ORDER BY CodEstado',
                       [TIPO_ESTADO_FACTURA])
        return [(cod, (descrip or '').strip()) for cod, descrip in cursor.fetchall()]


def estados_dict():
    return dict(estados())


def consultar_seguimiento(estados_filtro, tipo_filtro, texto):
    """SEG_ConsultaFactura. estados_filtro=None equivale a 'Todo'. Devuelve las filas tal cual."""
    cod_estado = None if estados_filtro is None else ';'.join(str(e) for e in estados_filtro)
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC SEG_ConsultaFactura %s, %s, %s',
                       [cod_estado, tipo_filtro, texto if tipo_filtro else None])
        return cursor.fetchall()


def todas():
    return Factura.objects.all()


def con_relaciones():
    """Facturas con cliente, proyecto, cotización, mandante y contacto ya cargados."""
    return Factura.objects.select_related('idcliente', 'idproyecto__idcotizacion__idcliente',
                                          'idproyecto__idcotizacion__idcontacto', 'idproyecto__estadoproyecto')


def obtener(idfactura):
    return Factura.objects.filter(pk=idfactura).first()


def existe(idfactura):
    return Factura.objects.filter(pk=idfactura).exists()


def por_numero(numfactura, excluir_idfactura=None):
    """Factura con ese número (otra que excluir_idfactura), o None. Regla: el número de factura es único."""
    qs = Factura.objects.filter(numfactura=numfactura)
    if excluir_idfactura:
        qs = qs.exclude(pk=excluir_idfactura)
    return qs.first()


def contactos(cliente):
    if cliente is None:
        return []
    return [{
        'idcontacto': c.idcontacto,
        'nombre': c.nombrecontacto or '',
        'cargo': c.cargo or '',
        'telefono': c.telefono or '',
        'email': c.email or '',
    } for c in Clientecontacto.objects.filter(idcliente=cliente).order_by('nombrecontacto')]


def glosa_correo(factura, proyecto, cotizacion):
    """Texto de correo para enviar la factura, igual al del sistema anterior."""
    porc = f"{factura.porcfact:g}" if factura.porcfact is not None else ''
    nombre = cotizacion.nombreproyecto if cotizacion else ''
    return (
        "Estimado \n\n"
        f"Adjunto soporte electrónico correspondiente a Factura N° {int(factura.numfactura)}:\n\n"
        f"Proyecto: {int(proyecto.idproyecto) if proyecto else ''} {nombre or ''}\n"
        f"Fecha de Emisión: {factura.fechaemision.strftime('%d/%m/%Y') if factura.fechaemision else ''}\n"
        f"Concepto: {porc}% {factura.detalle or ''}\n"
        f"Monto Facturado: ${pesos(factura.valortotalpesos)}\n\n"
        "Agradecemos confirmar recepción e iniciar el procedimiento respectivo\n\n"
        "Saludos"
    )


def saldo_por_facturar(idproyecto):
    """dbo.SaldoPorFacturar: % del proyecto que falta facturar. Es la regla única (ver proyectos.saldos_por_facturar)."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT dbo.SaldoPorFacturar(%s)', [idproyecto])
        return float(cursor.fetchone()[0] or 0)


def facturas_del_proyecto(idproyecto, catalogo=None):
    """CO_FacturaxProyecto."""
    catalogo = catalogo if catalogo is not None else estados_dict()
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC CO_FacturaxProyecto %s', [idproyecto])
        filas = cursor.fetchall()
    return [{
        'idfactura': r[23],
        'numfactura': int(r[0]),
        'fecha_emision': (r[1] or '').strip(),
        'porc': porcentaje(r[9]),
        'detalle': r[12] or '',
        'total_texto': pesos(r[8]),
        'estado': r[10],
        'estado_nombre': catalogo.get(r[10], ''),
        'editable': r[10] in ESTADOS_EDITABLES,
    } for r in filas]


def datos_factura(idfactura):
    """CO_Factura: datos para cargar una factura existente en el formulario."""
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC CO_Factura %s', [idfactura])
        r = cursor.fetchone()
    if r is None:
        return None

    def iso(texto):
        texto = (texto or '').strip()
        return datetime.strptime(texto, '%d/%m/%Y').date().isoformat() if texto else ''

    return {
        'idfactura': r[23],
        'numfactura': int(r[0]),
        'fecha_emision': iso(r[1]),
        'num_hes_eepp': r[4] or '',
        'fecha_hes_eepp': iso(r[5]),
        'valor_uf': float(r[7]) if r[7] is not None else None,
        'total_pesos': r[8],
        'porc': r[9],
        'estado': r[10],
        'detalle': r[12] or '',
        'moneda': r[21] or '',
        'monto': r[22],
        'vencimiento': r[26],
        'editable': r[10] in ESTADOS_EDITABLES,
    }


def buscar_por_numero(numero):
    """CO_FacturaxNumero: (idproyecto, idfactura) de la factura con ese número, o None."""
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC CO_FacturaxNumero %s', [numero])
        r = cursor.fetchone()
    if r is None:
        return None
    return (int(r[3]) if r[3] is not None else None), r[23]


def seguimiento_texto(idfactura):
    """dbo.Fx_ObtieneSEGFactura: el seguimiento de la factura como un solo texto."""
    if not idfactura:
        return ''
    with connection.cursor() as cursor:
        cursor.execute('SELECT dbo.Fx_ObtieneSEGFactura(%s)', [idfactura])
        return (cursor.fetchone()[0] or '').replace('\r\n', '\n').strip()


# ---------------------------------------------------------------------------------------------------------------
# Seguimiento (bitácora Factura_Seg)
# ---------------------------------------------------------------------------------------------------------------

def comentarios(idfactura):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT IdReg, FechaRevision, Comentario, ISNULL(EsRecordatorio, 0), FechaRecordatorio, ISNULL(IdUsuario, \'\') '
            'FROM Factura_Seg WHERE IdFactura = %s ORDER BY IdReg DESC', [idfactura])
        return [{
            'idreg': idreg,
            'fecha': fecha.strftime('%d/%m/%Y %H:%M') if fecha else '',
            'fecha_iso': fecha.strftime('%Y-%m-%d') if fecha else '',
            'comentario': (comentario or '').rstrip(),
            'es_recordatorio': bool(es_rec),
            'fecha_recordatorio': fecha_rec.strftime('%Y-%m-%d') if fecha_rec else '',
            'usuario': usuario,
        } for idreg, fecha, comentario, es_rec, fecha_rec, usuario in cursor.fetchall()]


def registrar_seguimiento(factura, comentario, usuario, *, es_recordatorio=False, fecha_recordatorio=None,
                          cod_estado=None, fecha_pago=None, horario_llamada=None, direc_retiro=None,
                          horario_retiro=None, comentario_cliente=None):
    """GR_Factura_SEG: agrega un seguimiento y, si viene cod_estado, cambia el estado de la factura.

    También actualiza los datos de cobranza del cliente. Las validaciones de forma las hace quien llama;
    aquí se aplican las de negocio.
    """
    if not comentario:
        raise ErrorValidacion('Debe ingresar el comentario del seguimiento.')
    if cod_estado is not None:
        if cod_estado not in estados_dict():
            raise ErrorValidacion('Debe seleccionar el nuevo estado.')
        validar_cambio_estado(factura.estado, cod_estado)
        if cod_estado != ESTADO_PAGADA:
            fecha_pago = None
    if es_recordatorio and fecha_recordatorio <= timezone.localdate():
        raise ErrorValidacion('La fecha de recordatorio debe ser posterior a hoy.')
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            'SET NOCOUNT ON; EXEC GR_Factura_SEG @IdFactura=%s, @ComentarioSEG=%s, @EsRecordatorio=%s, '
            '@CambiaEstado=%s, @CodEstado=%s, @IdContacto=NULL, @HorarioLlamada=%s, @DirecRetiroCH=%s, '
            '@HorarioRetiroCH=%s, @ComentarioCliente=%s, @FechaPago=%s, @IdCliente=%s, @FechaRecordatorio=%s, '
            '@IdUsuario=%s',
            [factura.idfactura, comentario, int(bool(es_recordatorio)), int(cod_estado is not None), cod_estado,
             horario_llamada, direc_retiro, horario_retiro, comentario_cliente, fecha_pago,
             factura.idcliente_id, fecha_recordatorio if es_recordatorio else None, usuario])


def editar_comentario(idfactura, idreg, comentario, fecha, usuario, es_recordatorio=False, fecha_recordatorio=None):
    """Mismo UPDATE que AC_Factura_SEG, pero conservando la hora si no cambia el día (el procedimiento recibe
    la fecha como date y borraba la hora). Devuelve False si el comentario ya no existe."""
    if not comentario:
        raise ErrorValidacion('El comentario no puede quedar vacío.')
    with connection.cursor() as cursor:
        cursor.execute('SELECT FechaRevision FROM Factura_Seg WHERE IdFactura = %s AND IdReg = %s', [idfactura, idreg])
        row = cursor.fetchone()
        if row is None:
            return False
        anterior = row[0]
        fecha_revision = anterior if anterior and anterior.date() == fecha else datetime.combine(fecha, datetime.min.time())
        cursor.execute(
            'UPDATE Factura_Seg SET FechaRevision = %s, Comentario = %s, EsRecordatorio = %s, '
            'FechaRecordatorio = %s, IdUsuario = %s WHERE IdFactura = %s AND IdReg = %s',
            [fecha_revision, comentario, int(bool(es_recordatorio)), fecha_recordatorio if es_recordatorio else None,
             usuario, idfactura, idreg])
    return True


def eliminar_comentario(idfactura, idreg):
    """EL_Factura_SEG."""
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC EL_Factura_SEG @IdFactura=%s, @IdReg=%s', [idfactura, idreg])


# ---------------------------------------------------------------------------------------------------------------
# Creación y modificación de facturas (CreacionFactura del sistema anterior)
# ---------------------------------------------------------------------------------------------------------------

def genera_glosa(p):
    """Port de GeneraGlosa (FUNCIONES.vb): descripción de la factura. Vacía si falta medio o N° de confirmación."""
    if not p.get('medio_conf') or not p.get('num_conf'):
        return ''
    uf = p.get('moneda') == 'UF'
    dec = 2 if uf else 0
    lineas = [
        '',
        f"{p['idproyecto']} {p['nombre_proyecto']}",
        f"Monto Total Proyecto {p['moneda']} {numero_cl(p['valor_proyecto'], dec)}",
        f"Según Cotización N° {p['num_cot']} ({fecha_corta(p['fecha_cot'])})",
        f"Según {p['medio_conf']} N° {str(p['num_conf']).strip()} ({fecha_corta(p['fecha_conf'])})",
    ]
    for marca, nombre in (('con_hes', 'HES'), ('con_eepp', 'EEPP'), ('con_otro', '.......')):
        if p.get(marca) == 'S':
            lineas.append(f"Según {nombre} N° {(p.get('num_hes_eepp') or '').strip()} ({fecha_corta(p.get('fecha_hes_eepp'))})")
    lineas += ['', '']
    a_facturar = f"A Facturar {porcentaje(p['porc'])}% {p['detalle']} {p['moneda']} {numero_cl(p['monto'], dec)}"
    if uf:
        a_facturar += f"(${numero_cl(p['total_pesos'])})"
    lineas.append(a_facturar)
    if uf:
        lineas += [f"Según UF ${numero_cl(p['valor_uf'], 2)} ({fecha_corta(p['fecha_emision'])})", '']
    lineas.append('Proyecto Especialidad Manejo de Residuos')
    saldo = float(p.get('saldo') or 0)
    if saldo > 0:
        valor_saldo = round(float(p['valor_proyecto'] or 0) * saldo / 100, dec)
        lineas.append(f"Saldo por facturar {porcentaje(saldo)}%" + (f" UF {numero_cl(valor_saldo, 2)}" if uf else f" $ {numero_cl(valor_saldo)}"))
    return '\n'.join(lineas)


def encabezado_proyecto(proyecto, cliente):
    """Datos del proyecto que muestra Creación de Facturas (y que usa la glosa)."""
    from django.urls import reverse
    cot = proyecto.idcotizacion
    return {
        'idproyecto': int(proyecto.idproyecto),
        'nombre_proyecto': cot.nombreproyecto or '',
        'estado_proyecto': proyecto.estadoproyecto.nombre if proyecto.estadoproyecto_id else '',
        'moneda': proyecto.moneda or '',
        'valor_proyecto': proyecto.valor or 0,
        'num_cot': f"{int(cot.numcotizacion)}-{int(cot.numcorr or 0):03d}" if cot.numcotizacion is not None else '',
        'fecha_cot': cot.fecha.strftime('%d/%m/%Y') if cot.fecha else '',
        'mandante': cot.idcliente.razonsocial if cot.idcliente_id else '',
        'medio_conf': proyecto.medioconf or '',
        'num_conf': (proyecto.numconf or '').strip(),
        'fecha_conf': proyecto.fechaconf.strftime('%d/%m/%Y') if proyecto.fechaconf else '',
        'con_hes': proyecto.conhes or '',
        'con_eepp': proyecto.coneepp or '',
        'con_otro': proyecto.conotro or '',
        'forma_pago': proyecto.fpago or '',
        'saldo': saldo_por_facturar(proyecto.idproyecto),
        'cliente': {
            'idcliente': cliente.idcliente,
            'razonsocial': cliente.razonsocial or '',
            'rut': f"{int(cliente.rut)}-{cliente.dvrut or ''}" if cliente.rut is not None else '',
            'notas': cliente.comentario or '',
            'editar_url': reverse('cliente_update', args=[cliente.idcliente]),
        } if cliente else None,
    }


def calculo(proyecto, porc, valor_uf):
    """(monto en moneda del proyecto, valor UF, total en pesos), igual que el formulario anterior."""
    valor_proyecto = float(proyecto.valor or 0)
    if (proyecto.moneda or '') == 'UF':
        monto = round(porc * valor_proyecto / 100 + 1e-9, 2)
        total_pesos = round(valor_uf * monto + 1e-9, 0)
    else:
        monto = round(porc * valor_proyecto / 100 + 1e-9, 0)
        valor_uf = 1.0
        total_pesos = monto
    return monto, valor_uf, total_pesos


def validar_grabacion(proyecto, numfactura, idfactura=0):
    """Reglas comunes a Seguimiento de Facturas y Seguimiento de Proyectos: número de factura único, y solo se
    modifican facturas Provisoria o Para Emitir del mismo proyecto."""
    existente = por_numero(numfactura, excluir_idfactura=idfactura)
    if existente:
        raise ErrorValidacion(f'Factura N° {numfactura} existe por un valor ${pesos(existente.valortotalpesos)}.')
    if idfactura:
        actual = Factura.objects.filter(pk=idfactura, idproyecto_id=proyecto.pk).first()
        if actual is None:
            raise ErrorValidacion('La factura a modificar no pertenece a este proyecto.')
        if actual.estado not in ESTADOS_EDITABLES:
            raise ErrorValidacion('Solo se pueden modificar facturas en estado Provisoria o Para Emitir.')


def grabar(proyecto, *, numfactura, fecha_emision, idcliente, porc, valor_uf, detalle, idfactura=0,
           num_hes='', fecha_hes=None, nuevo_estado=None, vencimiento=30):
    """GR_CreaFactura: crea (idfactura=0) o modifica una factura del proyecto.

    Las validaciones de forma (campos vacíos, formatos) y sus mensajes las hace cada pantalla; las de negocio
    (validar_grabacion) se repiten aquí para que ningún camino las salte. Devuelve la factura grabada.
    """
    validar_grabacion(proyecto, numfactura, idfactura)
    if porc <= 0:
        raise ErrorValidacion('% a facturar debe ser mayor a cero.')
    if valor_uf <= 0:
        raise ErrorValidacion('Valor U.F. debe ser mayor a cero.')
    if nuevo_estado is not None and nuevo_estado not in estados_dict():
        raise ErrorValidacion('Estado de la factura no válido.')
    monto, valor_uf, total_pesos = calculo(proyecto, porc, valor_uf)
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            'SET NOCOUNT ON; EXEC GR_CreaFactura @IdFactura=%s, @NumFactura=%s, @FechaEmision=%s, @IdCliente=%s, '
            '@IdProyecto=%s, @NumHES_EEPP=%s, @FechaHES_EEPP=%s, @ValorTotal=%s, @ValorUF=%s, @ValorTotalPesos=%s, '
            '@PorcFact=%s, @Detalle=%s, @Moneda=%s, @MontoFacturarMonOrig=%s, @NuevoEstado=%s, @Vencimiento=%s',
            [idfactura, numfactura, fecha_emision, idcliente, proyecto.pk, num_hes, fecha_hes,
             float(proyecto.valor or 0), round(valor_uf, 2), total_pesos, porc, detalle, (proyecto.moneda or '')[:2],
             monto, nuevo_estado, vencimiento])
    return Factura.objects.filter(numfactura=numfactura, idproyecto_id=proyecto.pk).order_by('-idfactura').first()


def glosa_de_factura(idfactura):
    """Descripción de una factura ya creada, armada con sus datos guardados (como el escritorio al elegirla en
    "Facturas Emitidas": la descripción no se guarda, se vuelve a generar). Devuelve (glosa, factura) o
    (None, mensaje) si no se puede."""
    from ..models import Proyecto
    datos = datos_factura(idfactura)
    if datos is None:
        return None, 'La factura no existe.'
    factura = Factura.objects.filter(pk=idfactura).first()
    proyecto = Proyecto.objects.select_related('idcotizacion__idcliente', 'estadoproyecto').filter(
        pk=factura.idproyecto_id).first() if factura and factura.idproyecto_id else None
    if proyecto is None:
        return None, 'La factura no tiene proyecto.'
    porc = float(datos['porc'] or 0)
    valor_uf = float(datos['valor_uf'] or 0) if (proyecto.moneda or '') == 'UF' else 1.0
    monto, _, total_calculado = calculo(proyecto, porc, valor_uf)
    if datos['monto'] is not None:
        monto = float(datos['monto'])
    total_pesos = float(datos['total_pesos']) if datos['total_pesos'] is not None else total_calculado
    glosa = genera_glosa({
        **encabezado_proyecto(proyecto, None),
        'num_hes_eepp': datos['num_hes_eepp'], 'fecha_hes_eepp': datos['fecha_hes_eepp'],
        'porc': porc, 'detalle': datos['detalle'], 'monto': monto, 'total_pesos': total_pesos,
        'valor_uf': valor_uf, 'fecha_emision': datos['fecha_emision'],
    })
    if not glosa:
        return None, 'El proyecto no tiene medio y N° de confirmación (OC): la descripción queda vacía, igual que antes.'
    return glosa, datos


def completar_datos_web(numfactura, proyecto, idcontacto, fecha_registro):
    """Datos que el formulario web de Seguimiento de Proyectos guarda y GR_CreaFactura no recibe."""
    Factura.objects.filter(numfactura=numfactura, idproyecto=proyecto).update(idcontacto=idcontacto)
    Factura.objects.filter(numfactura=numfactura, idproyecto=proyecto, fecharegistro__isnull=True).update(
        fecharegistro=fecha_registro)


def eliminar(idfactura):
    """EL_Factura: borra la factura y su seguimiento."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC EL_Factura %s', [idfactura])


# ---------------------------------------------------------------------------------------------------------------
# Reporte de Facturas (une Emitidas, Rep_Factura1, y Pagadas, Rep_Factura2, del escritorio)
# ---------------------------------------------------------------------------------------------------------------

ESTADOS_EMITIDAS = [2, 3, 4, 5, 8]  # Emitidas: Estado >= 2 y no 6 (NULA) ni 7 (PAUSA), como Rep_Factura1


def reporte(campo_fecha, desde, hasta, estados_filtro, cliente, proyecto):
    """Filas (año, mes, N°, emisión, razón social, rut, dv, proyecto, total $, pago, estado, idproyecto) por
    fecha de emisión o de pago ('pago'), ordenadas por año, mes y N°. cliente: nombre o RUT; proyecto: nombre o N°."""
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
    if estados_filtro:
        sql.append(f"AND a.Estado IN ({', '.join(['%s'] * len(estados_filtro))})")
        params += estados_filtro
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


def del_proyecto(idproyecto):
    """Facturas de un proyecto por fecha de emisión."""
    return list(Factura.objects.filter(idproyecto_id=idproyecto).order_by('fechaemision', 'idfactura'))


# ---------------------------------------------------------------------------------------------------------------
# Búsqueda (API)
# ---------------------------------------------------------------------------------------------------------------

def para_api():
    """Facturas con lo que serializa la API (cliente, contacto, proyecto y cotización)."""
    return Factura.objects.select_related('idcliente', 'idcontacto', 'idproyecto__idcotizacion')


def buscar(*, desde=None, hasta=None, modificado_desde=None, idcliente=None, rut=None, idproyecto=None,
           folio=None, estados_filtro=None, monto_min=None, monto_max=None, monto=None, tolerancia=0):
    """Facturas filtradas. Con 'monto' se buscan las de ese total en pesos ± tolerancia, la más cercana primero;
    si no, de la más reciente a la más antigua."""
    from django.db.models import F, Func
    qs = para_api()
    if desde:
        qs = qs.filter(fechaemision__gte=desde)
    if hasta:
        qs = qs.filter(fechaemision__lte=hasta)
    if modificado_desde:
        qs = qs.filter(fechaact__gte=modificado_desde)
    if idcliente:
        qs = qs.filter(idcliente_id=idcliente)
    if rut:
        qs = qs.filter(idcliente__rut=rut)
    if idproyecto:
        qs = qs.filter(idproyecto_id=idproyecto)
    if folio:
        qs = qs.filter(numfactura=folio)
    if estados_filtro:
        qs = qs.filter(estado__in=estados_filtro)
    if monto_min is not None:
        qs = qs.filter(valortotalpesos__gte=monto_min)
    if monto_max is not None:
        qs = qs.filter(valortotalpesos__lte=monto_max)
    if monto is not None:
        # ±0,5 cubre el redondeo a pesos enteros
        qs = qs.filter(valortotalpesos__gte=monto - tolerancia - 0.5, valortotalpesos__lt=monto + tolerancia + 0.5)
        return qs.annotate(dif=Func(F('valortotalpesos') - monto, function='ABS')).order_by('dif', '-fechaemision')
    return qs.order_by('-fechaemision', '-idfactura')


def ultimos_comentarios(ids):
    """{idfactura: último comentario} para varias facturas."""
    return bitacora.factura.ultimos(ids)


def listar_comentarios_api(idfactura):
    return bitacora.factura.listar(idfactura)


def obtener_comentario(idfactura, idreg):
    return bitacora.factura.obtener(idfactura, idreg)


def comentar(idfactura, comentario, usuario):
    """Agrega un comentario y marca la factura como actualizada. Debe llamarse dentro de transaction.atomic()."""
    nuevo = bitacora.factura.agregar(idfactura, comentario, usuario)
    marcar_actualizada(idfactura)
    return nuevo


def reemplazar_comentario(idfactura, idreg, comentario):
    """Cambia el texto de un comentario (API) y marca la factura como actualizada."""
    actual = bitacora.factura.editar(idfactura, idreg, comentario)
    marcar_actualizada(idfactura)
    return actual


# ---------------------------------------------------------------------------------------------------------------
# Estado y pago desde la API
# ---------------------------------------------------------------------------------------------------------------

def cambiar_estado_pago(factura, nuevo_estado, nueva_fecha_pago, usuario):
    """Cambia estado y/o fecha de pago (API) y deja la traza "[API] ..." en Factura_Seg.

    Devuelve la lista de cambios en texto (vacía si no hubo cambios). Debe llamarse dentro de transaction.atomic().
    """
    catalogo = estados_dict()
    validar_cambio_estado(factura.estado, nuevo_estado)
    cambios = []
    if nuevo_estado != factura.estado:
        cambios.append(f"estado: {catalogo.get(factura.estado, factura.estado)} -> {catalogo[nuevo_estado]}")
    if nueva_fecha_pago != factura.fechapago:
        cambios.append(f"fecha de pago: {factura.fechapago or '-'} -> {nueva_fecha_pago or '-'}")
    if cambios:
        Factura.objects.filter(pk=factura.pk).update(
            estado=nuevo_estado, fechapago=nueva_fecha_pago, fechaact=timezone.now())
        bitacora.factura.agregar(factura.pk, f"[API] {'; '.join(cambios)}", usuario)
    return cambios


def marcar_actualizada(idfactura):
    Factura.objects.filter(pk=idfactura).update(fechaact=timezone.now())


# ---------------------------------------------------------------------------------------------------------------
# Cliente (datos que se editan desde facturación)
# ---------------------------------------------------------------------------------------------------------------

def guardar_notas_cliente(idcliente, notas):
    """Notas del cliente (servicio de Clientes). Como antes, no borra si viene vacío. Devuelve True si guardó."""
    from . import clientes
    return clientes.guardar_comentario(idcliente, notas)
