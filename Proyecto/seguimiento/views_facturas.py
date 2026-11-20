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
        'contacto': _texto(row[14]),
        'telefono': _texto(row[15]),
        'email': email,
        'cargo': cargo,
        'saldo_por_facturar': row[32],
        'porc_fact': row[34],
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
        'menu': 'Cobranza',
        'submenu': 'Seguimiento de Facturas',
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
