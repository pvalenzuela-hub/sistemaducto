"""Seguimiento de Facturas: réplica web del módulo frm_SEG_Facturas del sistema VB.NET.

Usa los mismos procedimientos almacenados del sistema anterior para que datos y reglas sean idénticos:
SEG_ConsultaFactura (listado y filtros), GR_Factura_SEG (nuevo seguimiento, cambio de estado y datos del
cliente), AC_Factura_SEG (editar comentario) y EL_Factura_SEG (eliminar comentario).
"""
from datetime import date, datetime

from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Clientecontacto, Factura

TIPO_ESTADO_FACTURA = 3
ESTADO_PAGADA = 5  # el sistema anterior exige fecha de pago solo para este estado
ESTADOS_POR_DEFECTO = [0, 1, 2, 3, 4, 7]  # todo lo que aún no está pagado, verificado ni nulo

TIPOS_FILTRO = [(1, 'Factura'), (2, 'Proyecto'), (3, 'Mandante'), (4, 'Monto')]

# Colores de fila por estado, los mismos del sistema anterior (en tonos legibles con texto oscuro)
COLOR_ESTADO = {
    0: '#ffffff',  # Provisoria: White
    1: '#fff59d',  # Para Emitir: Yellow
    2: '#ffc4a8',  # Emitida: LightSalmon
    3: '#b9f0b9',  # Pendiente de Pago: LightGreen
    4: '#ff9e9e',  # Pago por Retirar: Red
    5: '#b3f5f5',  # Pagada: Cyan
    6: '#d9b38c',  # NULA: SaddleBrown
    7: '#e8c4c4',  # PAUSA: RosyBrown
    8: '#b5dcf5',  # Pago Verificado: SkyBlue
}

# Largo máximo de los parámetros de GR_Factura_SEG
MAX_HORARIO_LLAMADA = 80
MAX_DIREC_RETIRO = 80
MAX_HORARIO_RETIRO = 50


class ErrorValidacion(ValueError):
    pass


def _estados_factura():
    with connection.cursor() as cursor:
        cursor.execute('SELECT CodEstado, Descrip FROM tEstado WHERE TipoEstado = %s ORDER BY CodEstado',
                       [TIPO_ESTADO_FACTURA])
        return [(cod, (descrip or '').strip()) for cod, descrip in cursor.fetchall()]


def _usuario(request):
    return (request.user.username or '')[:15]


def _ahora_local():
    return timezone.localtime(timezone.now()).replace(tzinfo=None)


def _pesos(valor):
    if valor is None:
        return ''
    return f"{float(valor):,.0f}".replace(',', '.')


def _texto(valor):
    return '' if valor is None else str(valor).strip()


def _consultar_facturas(estados, tipo_filtro, texto):
    """Ejecuta SEG_ConsultaFactura. estados=None equivale a 'Todo'."""
    cod_estado = None if estados is None else ';'.join(str(e) for e in estados)
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC SEG_ConsultaFactura %s, %s, %s',
                       [cod_estado, tipo_filtro, texto if tipo_filtro else None])
        return cursor.fetchall()


def _fila(row):
    contacto_a, contacto_b = _texto(row[17]), _texto(row[18])
    email, cargo = (contacto_a, contacto_b) if '@' in contacto_a else (contacto_b, contacto_a)
    estado = row[11]
    return {
        'numfactura': int(row[0]) if row[0] is not None else '',
        'fecha_emision': row[1] or '',
        'idproyecto': int(row[2]) if row[2] is not None else '',
        'nombre_proyecto': row[3] or '',
        'ultimo_seg': row[4] or '',
        'cliente': row[5] or '',
        'mandante': row[6] or '',
        'monto': row[7] or 0,
        'monto_texto': _pesos(row[7]),
        'detalle': row[8] or '',
        'fecha_pago': row[9] or '',
        'seguimiento': (row[10] or '').replace('\r\n', '\n').strip(),
        'estado': estado,
        'estado_nombre': _texto(row[19]),
        'estado_proyecto': _texto(row[20]),
        'idfactura': row[16],
        'idcliente': row[13],
        'contacto': _texto(row[14]),
        'telefono': _texto(row[15]),
        'email': email,
        'cargo': cargo,
        'saldo_por_facturar': _porcentaje(row[32]),  # PorcFact es real: evita 30,15999984741211
        'porc_fact': _porcentaje(row[34]),
        'vencimiento': row[39],
        'color': COLOR_ESTADO.get(estado, '#ffffff'),
    }


@login_required
@require_GET
def facturas_seguimiento(request):
    estados_catalogo = _estados_factura()
    codigos_validos = {cod for cod, _ in estados_catalogo}

    todo = request.GET.get('todo') == '1'
    if 'filtrado' in request.GET or 'estado' in request.GET:
        estados = sorted({int(e) for e in request.GET.getlist('estado') if e.strip().isdigit()} & codigos_validos)
    else:
        estados = list(ESTADOS_POR_DEFECTO)

    try:
        tipo = int(request.GET.get('tipo') or 0)
    except ValueError:
        tipo = 0
    texto = (request.GET.get('texto') or '').strip()
    if tipo not in dict(TIPOS_FILTRO) or not texto:
        tipo = 0

    error = ''
    if tipo == 1 and not texto.isdigit():
        error, tipo = 'El N° de factura debe ser un número.', 0
    if tipo == 4:
        texto = texto.replace('.', '').replace('$', '').replace(',', '.').strip()
        try:
            float(texto)
        except ValueError:
            error, tipo = 'El monto debe ser un número.', 0

    filas = []
    if todo or estados:
        filas = [_fila(r) for r in _consultar_facturas(None if todo else estados, tipo, texto)]

    return render(request, 'facturas_seguimiento.html', {
        'titulo': 'Seguimiento de Facturas',
        'encabezado': 'Seguimiento de Facturas',
        'menu': 'Facturas',
        'submenu': 'Seguimiento Facturas',
        'estados_catalogo': [
            {'codigo': cod, 'nombre': nombre, 'color': COLOR_ESTADO.get(cod, '#ffffff'),
             'marcado': todo or cod in estados}
            for cod, nombre in estados_catalogo
        ],
        'todo': todo,
        'tipos_filtro': TIPOS_FILTRO,
        'filtro_tipo': int(request.GET.get('tipo') or 0) if (request.GET.get('tipo') or '').isdigit() else 0,
        'filtro_texto': request.GET.get('texto') or '',
        'error': error,
        'filas': filas,
        'total_texto': _pesos(sum(float(f['monto'] or 0) for f in filas)),
        'cantidad': len(filas),
        'estado_pagada': ESTADO_PAGADA,
    })


def _comentarios(idfactura):
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


def _contactos(cliente):
    if cliente is None:
        return []
    return [{
        'idcontacto': c.idcontacto,
        'nombre': c.nombrecontacto or '',
        'cargo': c.cargo or '',
        'telefono': c.telefono or '',
        'email': c.email or '',
    } for c in Clientecontacto.objects.filter(idcliente=cliente).order_by('nombrecontacto')]


def _glosa_correo(factura, proyecto, cotizacion):
    """Texto de correo para enviar la factura, igual al del sistema anterior."""
    porc = f"{factura.porcfact:g}" if factura.porcfact is not None else ''
    nombre = cotizacion.nombreproyecto if cotizacion else ''
    return (
        "Estimado \n\n"
        f"Adjunto soporte electrónico correspondiente a Factura N° {int(factura.numfactura)}:\n\n"
        f"Proyecto: {int(proyecto.idproyecto) if proyecto else ''} {nombre or ''}\n"
        f"Fecha de Emisión: {factura.fechaemision.strftime('%d/%m/%Y') if factura.fechaemision else ''}\n"
        f"Concepto: {porc}% {factura.detalle or ''}\n"
        f"Monto Facturado: ${_pesos(factura.valortotalpesos)}\n\n"
        "Agradecemos confirmar recepción e iniciar el procedimiento respectivo\n\n"
        "Saludos"
    )


@login_required
@require_GET
def factura_seguimiento_detalle(request, idfactura):
    factura = get_object_or_404(
        Factura.objects.select_related('idcliente', 'idproyecto__idcotizacion__idcliente',
                                       'idproyecto__idcotizacion__idcontacto'),
        pk=idfactura)
    proyecto = factura.idproyecto
    cotizacion = proyecto.idcotizacion if proyecto else None
    cliente = factura.idcliente
    mandante = cotizacion.idcliente if cotizacion else None
    estados = dict(_estados_factura())

    return JsonResponse({
        'idfactura': factura.idfactura,
        'numfactura': int(factura.numfactura),
        'asunto': f"FACTURA N°{int(factura.numfactura)} {cotizacion.nombreproyecto if cotizacion else ''}".strip(),
        'fecha_emision': factura.fechaemision.strftime('%d/%m/%Y') if factura.fechaemision else '',
        'fecha_pago': factura.fechapago.isoformat() if factura.fechapago else '',
        'estado': factura.estado,
        'estado_nombre': estados.get(factura.estado, ''),
        'monto_texto': _pesos(factura.valortotalpesos),
        'porc_fact': f"{factura.porcfact:.2f}" if factura.porcfact is not None else '',
        'detalle': factura.detalle or '',
        'vencimiento': factura.vencimiento,
        'idproyecto': int(proyecto.idproyecto) if proyecto else None,
        'nombre_proyecto': cotizacion.nombreproyecto if cotizacion else '',
        'crear_factura_url': (f"{reverse('seguimiento_proyectos')}?numero_proyecto={int(proyecto.idproyecto)}"
                              if proyecto else ''),
        'cliente': {
            'idcliente': cliente.idcliente,
            'razonsocial': cliente.razonsocial or '',
            'horario_llamada': cliente.horariollamada or '',
            'direc_factura': cliente.direcfactura or '',
            'direc_retiro_ch': cliente.direcretiroch or '',
            'horario_retiro_ch': cliente.horarioretiroch or '',
            'comentario': cliente.comentario or '',
        } if cliente else None,
        'mandante': {'idcliente': mandante.idcliente, 'razonsocial': mandante.razonsocial or ''} if mandante else None,
        'contactos_cliente': _contactos(cliente),
        'contactos_mandante': _contactos(mandante),
        'contacto_cotizacion': cotizacion.idcontacto_id if cotizacion else None,
        'glosa': _glosa_correo(factura, proyecto, cotizacion),
        'comentarios': _comentarios(factura.idfactura),
    })


def _fecha(valor, nombre):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        raise ErrorValidacion(f'{nombre}: fecha inválida.')


def _opcional(request, campo, largo):
    valor = (request.POST.get(campo) or '').strip()
    if len(valor) > largo:
        raise ErrorValidacion(f'"{campo}" admite hasta {largo} caracteres.')
    return valor or None


@login_required
@require_POST
def factura_seguimiento_guardar(request, idfactura):
    """Nuevo seguimiento: mismas validaciones que SEG_EditaFactura y grabación con GR_Factura_SEG."""
    factura = get_object_or_404(Factura, pk=idfactura)
    try:
        comentario = (request.POST.get('comentario') or '').strip()
        if not comentario:
            raise ErrorValidacion('Debe ingresar el comentario del seguimiento.')

        cambia_estado = request.POST.get('cambia_estado') == '1'
        cod_estado = None
        fecha_pago = None
        if cambia_estado:
            estados = dict(_estados_factura())
            try:
                cod_estado = int(request.POST.get('estado'))
            except (TypeError, ValueError):
                cod_estado = None
            if cod_estado not in estados:
                raise ErrorValidacion('Debe seleccionar el nuevo estado.')
            if cod_estado == ESTADO_PAGADA:
                fecha_pago = _fecha(request.POST.get('fecha_pago'), 'Fecha de pago')

        es_recordatorio = request.POST.get('es_recordatorio') == '1'
        fecha_recordatorio = None
        if es_recordatorio:
            fecha_recordatorio = _fecha(request.POST.get('fecha_recordatorio'), 'Fecha de recordatorio')
            if fecha_recordatorio <= timezone.localdate():
                raise ErrorValidacion('La fecha de recordatorio debe ser posterior a hoy.')

        horario_llamada = _opcional(request, 'horario_llamada', MAX_HORARIO_LLAMADA)
        direc_retiro = _opcional(request, 'direc_retiro_ch', MAX_DIREC_RETIRO)
        horario_retiro = _opcional(request, 'horario_retiro_ch', MAX_HORARIO_RETIRO)
        comentario_cliente = (request.POST.get('comentario_cliente') or '').strip() or None
    except ErrorValidacion as e:
        return JsonResponse({'ok': False, 'message': str(e)}, status=400)

    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            'SET NOCOUNT ON; EXEC GR_Factura_SEG @IdFactura=%s, @ComentarioSEG=%s, @EsRecordatorio=%s, '
            '@CambiaEstado=%s, @CodEstado=%s, @IdContacto=NULL, @HorarioLlamada=%s, @DirecRetiroCH=%s, '
            '@HorarioRetiroCH=%s, @ComentarioCliente=%s, @FechaPago=%s, @IdCliente=%s, @FechaRecordatorio=%s, '
            '@IdUsuario=%s',
            [factura.idfactura, comentario, int(es_recordatorio), int(cambia_estado), cod_estado,
             horario_llamada, direc_retiro, horario_retiro, comentario_cliente, fecha_pago,
             factura.idcliente_id, fecha_recordatorio, _usuario(request)])
    return JsonResponse({'ok': True, 'message': 'Seguimiento guardado.'})


@login_required
@require_POST
def factura_comentario_editar(request, idfactura, idreg):
    """Edita un comentario con AC_Factura_SEG (el usuario queda como quien lo editó, igual que antes)."""
    get_object_or_404(Factura, pk=idfactura)
    try:
        comentario = (request.POST.get('comentario') or '').strip()
        if not comentario:
            raise ErrorValidacion('El comentario no puede quedar vacío.')
        fecha = _fecha(request.POST.get('fecha'), 'Fecha')
        es_recordatorio = request.POST.get('es_recordatorio') == '1'
        fecha_recordatorio = (_fecha(request.POST.get('fecha_recordatorio'), 'Fecha de recordatorio')
                              if es_recordatorio else None)
    except ErrorValidacion as e:
        return JsonResponse({'ok': False, 'message': str(e)}, status=400)

    with connection.cursor() as cursor:
        cursor.execute('SELECT FechaRevision FROM Factura_Seg WHERE IdFactura = %s AND IdReg = %s', [idfactura, idreg])
        row = cursor.fetchone()
        if row is None:
            return JsonResponse({'ok': False, 'message': 'El comentario ya no existe.'}, status=404)
        # Mismo UPDATE que AC_Factura_SEG, pero conservando la hora si no cambia el día
        # (el procedimiento recibe la fecha como date y borraba la hora).
        anterior = row[0]
        fecha_revision = anterior if anterior and anterior.date() == fecha else datetime.combine(fecha, datetime.min.time())
        cursor.execute(
            'UPDATE Factura_Seg SET FechaRevision = %s, Comentario = %s, EsRecordatorio = %s, '
            'FechaRecordatorio = %s, IdUsuario = %s WHERE IdFactura = %s AND IdReg = %s',
            [fecha_revision, comentario, int(es_recordatorio), fecha_recordatorio, _usuario(request), idfactura, idreg])
    return JsonResponse({'ok': True, 'comentarios': _comentarios(idfactura)})


@login_required
@require_POST
def factura_comentario_eliminar(request, idfactura, idreg):
    get_object_or_404(Factura, pk=idfactura)
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC EL_Factura_SEG @IdFactura=%s, @IdReg=%s', [idfactura, idreg])
    return JsonResponse({'ok': True, 'comentarios': _comentarios(idfactura)})


# ---------------------------------------------------------------------------------------------------------------
# Creación de Facturas (formulario CreacionFactura del sistema anterior)
# ---------------------------------------------------------------------------------------------------------------

DETALLES_FACTURA = ['Anticipo', 'Entrega V00', 'Entrega V Final', 'Saldo', 'V Licitación', 'V Construcción']
ESTADOS_EDITABLES = (0, 1)  # GR_CreaFactura solo modifica facturas Provisoria o Para Emitir


def _cl(valor, decimales=0):
    """Número con formato chileno: miles con punto y decimales con coma."""
    if valor is None:
        return ''
    texto = f"{float(valor):,.{decimales}f}"
    return texto.replace(',', 'X').replace('.', ',').replace('X', '.')


def _porcentaje(valor):
    """Como PorcFacturar.ToString() del sistema anterior: sin decimales sobrantes."""
    if valor is None:
        return ''
    valor = round(float(valor), 2)
    return _cl(valor, 0) if valor.is_integer() else _cl(valor, 2).rstrip('0').rstrip(',')


def _fecha_corta(valor):
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


def genera_glosa(p):
    """Port de GeneraGlosa (FUNCIONES.vb): descripción de la factura. Vacía si falta medio o N° de confirmación."""
    if not p.get('medio_conf') or not p.get('num_conf'):
        return ''
    uf = p.get('moneda') == 'UF'
    dec = 2 if uf else 0
    lineas = [
        '',
        f"{p['idproyecto']} {p['nombre_proyecto']}",
        f"Monto Total Proyecto {p['moneda']} {_cl(p['valor_proyecto'], dec)}",
        f"Según Cotización N° {p['num_cot']} ({_fecha_corta(p['fecha_cot'])})",
        f"Según {p['medio_conf']} N° {str(p['num_conf']).strip()} ({_fecha_corta(p['fecha_conf'])})",
    ]
    for marca, nombre in (('con_hes', 'HES'), ('con_eepp', 'EEPP'), ('con_otro', '.......')):
        if p.get(marca) == 'S':
            lineas.append(f"Según {nombre} N° {(p.get('num_hes_eepp') or '').strip()} ({_fecha_corta(p.get('fecha_hes_eepp'))})")
    lineas += ['', '']
    a_facturar = f"A Facturar {_porcentaje(p['porc'])}% {p['detalle']} {p['moneda']} {_cl(p['monto'], dec)}"
    if uf:
        a_facturar += f"(${_cl(p['total_pesos'])})"
    lineas.append(a_facturar)
    if uf:
        lineas += [f"Según UF ${_cl(p['valor_uf'], 2)} ({_fecha_corta(p['fecha_emision'])})", '']
    lineas.append('Proyecto Especialidad Manejo de Residuos')
    saldo = float(p.get('saldo') or 0)
    if saldo > 0:
        valor_saldo = round(float(p['valor_proyecto'] or 0) * saldo / 100, dec)
        lineas.append(f"Saldo por facturar {_porcentaje(saldo)}%" + (f" UF {_cl(valor_saldo, 2)}" if uf else f" $ {_cl(valor_saldo)}"))
    return '\n'.join(lineas)


def _saldo_por_facturar(idproyecto):
    with connection.cursor() as cursor:
        cursor.execute('SELECT dbo.SaldoPorFacturar(%s)', [idproyecto])
        return float(cursor.fetchone()[0] or 0)


def _facturas_del_proyecto(idproyecto, estados):
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC CO_FacturaxProyecto %s', [idproyecto])
        filas = cursor.fetchall()
    return [{
        'idfactura': r[23],
        'numfactura': int(r[0]),
        'fecha_emision': (r[1] or '').strip(),
        'porc': _porcentaje(r[9]),
        'detalle': r[12] or '',
        'total_texto': _pesos(r[8]),
        'estado': r[10],
        'estado_nombre': estados.get(r[10], ''),
        'editable': r[10] in ESTADOS_EDITABLES,
    } for r in filas]


def _datos_factura(idfactura):
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


def _seguimiento_texto(idfactura):
    if not idfactura:
        return ''
    with connection.cursor() as cursor:
        cursor.execute('SELECT dbo.Fx_ObtieneSEGFactura(%s)', [idfactura])
        return (cursor.fetchone()[0] or '').replace('\r\n', '\n').strip()


def _encabezado_proyecto(proyecto, cliente):
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
        'saldo': _saldo_por_facturar(proyecto.idproyecto),
        'cliente': {
            'idcliente': cliente.idcliente,
            'razonsocial': cliente.razonsocial or '',
            'rut': f"{int(cliente.rut)}-{cliente.dvrut or ''}" if cliente.rut is not None else '',
            'notas': cliente.comentario or '',
            'editar_url': reverse('cliente_update', args=[cliente.idcliente]),
        } if cliente else None,
    }


@login_required
@require_GET
def factura_facturacion(request, idfactura):
    """Abre Creación de Facturas desde una factura del listado, como el clic en el N° de factura."""
    from .views import _valor_uf_por_fecha
    factura = get_object_or_404(
        Factura.objects.select_related('idcliente', 'idproyecto__idcotizacion__idcliente', 'idproyecto__estadoproyecto'),
        pk=idfactura)
    if factura.idproyecto is None:
        return JsonResponse({'ok': False, 'message': 'La factura no tiene proyecto.'}, status=400)
    estados = dict(_estados_factura())
    hoy = timezone.localdate()
    uf_dia = _valor_uf_por_fecha(hoy)
    return JsonResponse({
        'ok': True,
        'origen_idfactura': factura.idfactura,
        'origen_numfactura': int(factura.numfactura),
        'proyecto': _encabezado_proyecto(factura.idproyecto, factura.idcliente),
        'facturas': _facturas_del_proyecto(factura.idproyecto_id, estados),
        'seguimiento': _seguimiento_texto(factura.idfactura),
        'uf_dia': uf_dia,
        'fecha_hoy': hoy.isoformat(),
        'detalles': DETALLES_FACTURA,
    })


@login_required
@require_GET
def factura_datos(request, idfactura):
    datos = _datos_factura(idfactura)
    if datos is None:
        return JsonResponse({'ok': False, 'message': 'La factura no existe.'}, status=404)
    return JsonResponse({'ok': True, 'factura': datos, 'seguimiento': _seguimiento_texto(idfactura)})


@login_required
@require_GET
def factura_por_numero(request):
    """CO_FacturaxNumero: al salir del N° de factura, si ya existe se cargan sus datos (como antes)."""
    try:
        numero = int(request.GET.get('numero') or 0)
    except ValueError:
        numero = 0
    if numero <= 0:
        return JsonResponse({'ok': True, 'existe': False})
    with connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC CO_FacturaxNumero %s', [numero])
        r = cursor.fetchone()
    if r is None:
        return JsonResponse({'ok': True, 'existe': False})
    return JsonResponse({'ok': True, 'existe': True, 'idproyecto': int(r[3]) if r[3] is not None else None,
                         'factura': _datos_factura(r[23]), 'seguimiento': _seguimiento_texto(r[23])})


def _decimal(request, campo, nombre):
    texto = (request.POST.get(campo) or '').strip().replace('.', '').replace(',', '.') if ',' in (request.POST.get(campo) or '') \
        else (request.POST.get(campo) or '').strip()
    try:
        return float(texto)
    except ValueError:
        raise ErrorValidacion(f'{nombre} no es un número válido.')


def _calculo_factura(proyecto, porc, valor_uf):
    """Monto a facturar y total en pesos, igual que el formulario anterior."""
    valor_proyecto = float(proyecto.valor or 0)
    if (proyecto.moneda or '') == 'UF':
        monto = round(porc * valor_proyecto / 100 + 1e-9, 2)
        total_pesos = round(valor_uf * monto + 1e-9, 0)
    else:
        monto = round(porc * valor_proyecto / 100 + 1e-9, 0)
        valor_uf = 1.0
        total_pesos = monto
    return monto, valor_uf, total_pesos


@login_required
@require_POST
def factura_glosa(request, idproyecto):
    """Genera la descripción (botón 'Generar descripción', Button3 del formulario anterior)."""
    from .models import Proyecto
    proyecto = get_object_or_404(Proyecto.objects.select_related('idcotizacion__idcliente', 'estadoproyecto'),
                                 pk=idproyecto)
    try:
        porc = _decimal(request, 'porc', '% a facturar')
        valor_uf = _decimal(request, 'valor_uf', 'Valor UF') if (proyecto.moneda or '') == 'UF' else 1.0
        fecha_emision = _fecha(request.POST.get('fecha_emision'), 'Fecha de emisión')
        monto, valor_uf, total_pesos = _calculo_factura(proyecto, porc, valor_uf)
        if total_pesos <= 0:
            raise ErrorValidacion('Debe ingresar el valor UF.')
    except ErrorValidacion as e:
        return JsonResponse({'ok': False, 'message': str(e)}, status=400)
    enc = _encabezado_proyecto(proyecto, None)
    glosa = genera_glosa({
        **enc,
        'num_hes_eepp': request.POST.get('num_hes_eepp') or '',
        'fecha_hes_eepp': request.POST.get('fecha_hes_eepp') or '',
        'porc': porc, 'detalle': (request.POST.get('detalle') or '').strip(), 'monto': monto,
        'total_pesos': total_pesos, 'valor_uf': valor_uf, 'fecha_emision': fecha_emision,
    })
    if not glosa:
        return JsonResponse({'ok': False, 'message': 'El proyecto no tiene medio y N° de confirmación (OC): '
                                                     'la descripción queda vacía, igual que antes.'}, status=400)
    return JsonResponse({'ok': True, 'glosa': glosa})


@login_required
@require_POST
def factura_grabar(request, idproyecto):
    """Crea o modifica una factura con GR_CreaFactura, con las validaciones de CreacionFactura."""
    from .models import Proyecto
    proyecto = get_object_or_404(Proyecto, pk=idproyecto)
    try:
        idfactura = int(request.POST.get('idfactura') or 0)
        idcliente = int(request.POST.get('idcliente') or 0)
        if idcliente <= 0:
            raise ErrorValidacion('No es posible crear la factura: falta la identificación del cliente.')
        try:
            numfactura = int(request.POST.get('numfactura') or 0)
        except ValueError:
            numfactura = 0
        if numfactura <= 0:
            raise ErrorValidacion('N° de factura no válido.')
        existente = Factura.objects.filter(numfactura=numfactura).exclude(pk=idfactura).first()
        if existente:
            raise ErrorValidacion(f'Factura N° {numfactura} existe por un valor ${_pesos(existente.valortotalpesos)}.')
        if idfactura:
            actual = Factura.objects.filter(pk=idfactura, idproyecto_id=proyecto.pk).first()
            if actual is None:
                raise ErrorValidacion('La factura a modificar no pertenece a este proyecto.')
            if actual.estado not in ESTADOS_EDITABLES:
                raise ErrorValidacion('Solo se pueden modificar facturas en estado Provisoria o Para Emitir.')
        fecha_emision = _fecha(request.POST.get('fecha_emision'), 'Fecha de emisión')
        porc = _decimal(request, 'porc', '% a facturar')
        if porc <= 0:
            raise ErrorValidacion('% a facturar debe ser mayor a cero.')
        uf = (proyecto.moneda or '') == 'UF'
        valor_uf = _decimal(request, 'valor_uf', 'Valor UF') if uf else 1.0
        if valor_uf <= 0:
            raise ErrorValidacion('Valor U.F. debe ser mayor a cero.')
        detalle = (request.POST.get('detalle') or '').strip()
        if not detalle:
            raise ErrorValidacion('Debe ingresar el detalle a facturar.')
        if len(detalle) > 100:
            raise ErrorValidacion('El detalle admite hasta 100 caracteres.')
        nuevo_estado = None
        if request.POST.get('cambia_estado') == '1':
            try:
                nuevo_estado = int(request.POST.get('estado'))
            except (TypeError, ValueError):
                nuevo_estado = None
            if nuevo_estado not in dict(_estados_factura()):
                raise ErrorValidacion('Debe seleccionar el estado de la factura.')
        if not (request.POST.get('glosa') or '').strip():
            raise ErrorValidacion('Falta actualizar la descripción de la factura.')
        num_hes = (request.POST.get('num_hes_eepp') or '').strip()
        if len(num_hes) > 50:
            raise ErrorValidacion('El N° HES/EEPP admite hasta 50 caracteres.')
        fecha_hes = _fecha(request.POST.get('fecha_hes_eepp'), 'Fecha HES/EEPP') if request.POST.get('fecha_hes_eepp') else None
        try:
            vencimiento = int(request.POST.get('vencimiento') or 30)
        except ValueError:
            raise ErrorValidacion('Vencimiento no válido.')
        monto, valor_uf, total_pesos = _calculo_factura(proyecto, porc, valor_uf)
    except ErrorValidacion as e:
        return JsonResponse({'ok': False, 'message': str(e)}, status=400)

    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            'SET NOCOUNT ON; EXEC GR_CreaFactura @IdFactura=%s, @NumFactura=%s, @FechaEmision=%s, @IdCliente=%s, '
            '@IdProyecto=%s, @NumHES_EEPP=%s, @FechaHES_EEPP=%s, @ValorTotal=%s, @ValorUF=%s, @ValorTotalPesos=%s, '
            '@PorcFact=%s, @Detalle=%s, @Moneda=%s, @MontoFacturarMonOrig=%s, @NuevoEstado=%s, @Vencimiento=%s',
            [idfactura, numfactura, fecha_emision, idcliente, proyecto.pk, num_hes, fecha_hes,
             float(proyecto.valor or 0), round(valor_uf, 2), total_pesos, porc, detalle, (proyecto.moneda or '')[:2],
             monto, nuevo_estado, vencimiento])
    guardada = Factura.objects.filter(numfactura=numfactura, idproyecto_id=proyecto.pk).order_by('-idfactura').first()
    return JsonResponse({
        'ok': True,
        'message': 'Factura modificada.' if idfactura else 'Factura creada.',
        'idfactura': guardada.idfactura if guardada else None,
        'facturas': _facturas_del_proyecto(proyecto.pk, dict(_estados_factura())),
        'saldo': _saldo_por_facturar(proyecto.pk),
    })


@login_required
@require_POST
def factura_eliminar(request, idfactura):
    """EL_Factura: borra la factura y su seguimiento (igual que antes, pero pidiendo confirmación en pantalla)."""
    factura = get_object_or_404(Factura, pk=idfactura)
    idproyecto = factura.idproyecto_id
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('SET NOCOUNT ON; EXEC EL_Factura %s', [idfactura])
    return JsonResponse({
        'ok': True,
        'facturas': _facturas_del_proyecto(idproyecto, dict(_estados_factura())) if idproyecto else [],
        'saldo': _saldo_por_facturar(idproyecto) if idproyecto else 0,
    })


@login_required
@require_POST
def cliente_notas_guardar(request, idcliente):
    """Guarda las notas del cliente (botón de notas de CreacionFactura). Como antes, no borra si viene vacío."""
    from .models import Cliente
    cliente = get_object_or_404(Cliente, pk=idcliente)
    notas = (request.POST.get('notas') or '').strip()
    if notas:
        Cliente.objects.filter(pk=cliente.pk).update(comentario=notas)
    return JsonResponse({'ok': True, 'message': 'Notas guardadas.' if notas else 'Sin cambios: las notas venían vacías.'})
