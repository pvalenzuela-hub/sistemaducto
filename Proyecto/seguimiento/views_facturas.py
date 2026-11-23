"""Seguimiento de Facturas: réplica web del módulo frm_SEG_Facturas del sistema VB.NET.

Las vistas leen la solicitud, validan el formulario y arman la respuesta. El acceso a datos, los
procedimientos almacenados y las reglas de negocio están en seguimiento.servicios.facturas.
"""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Cliente, Proyecto
from .servicios import facturas as srv
from .servicios.facturas import (DETALLES_FACTURA, ESTADO_PAGADA, ErrorValidacion,
                                 MAX_DIREC_RETIRO, MAX_HORARIO_LLAMADA, MAX_HORARIO_RETIRO, genera_glosa)

ESTADOS_POR_DEFECTO = [0, 1, 7]  # Provisoria, Para Emitir y En Pausa

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

def _usuario(request):
    return (request.user.username or '')[:15]


def _texto(valor):
    return '' if valor is None else str(valor).strip()


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
        'monto_texto': srv.pesos(row[7]),
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
        'saldo_por_facturar': srv.porcentaje(row[32]),  # PorcFact es real: evita 30,15999984741211
        'porc_fact': srv.porcentaje(row[34]),
        'vencimiento': row[39],
        'color': COLOR_ESTADO.get(estado, '#ffffff'),
    }


@login_required
@require_GET
def facturas_seguimiento(request):
    estados_catalogo = srv.estados()
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
        filas = [_fila(r) for r in srv.consultar_seguimiento(None if todo else estados, tipo, texto)]

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
        'estados_defecto': ESTADOS_POR_DEFECTO,
        'tipos_filtro': TIPOS_FILTRO,
        'filtro_tipo': int(request.GET.get('tipo') or 0) if (request.GET.get('tipo') or '').isdigit() else 0,
        'filtro_texto': request.GET.get('texto') or '',
        'error': error,
        'filas': filas,
        'total_texto': srv.pesos(sum(float(f['monto'] or 0) for f in filas)),
        'cantidad': len(filas),
        'estado_pagada': ESTADO_PAGADA,
    })


@login_required
@require_GET
def factura_seguimiento_detalle(request, idfactura):
    factura = get_object_or_404(srv.con_relaciones(), pk=idfactura)
    proyecto = factura.idproyecto
    cotizacion = proyecto.idcotizacion if proyecto else None
    cliente = factura.idcliente
    mandante = cotizacion.idcliente if cotizacion else None
    estados = srv.estados_dict()

    return JsonResponse({
        'idfactura': factura.idfactura,
        'numfactura': int(factura.numfactura),
        'asunto': f"FACTURA N°{int(factura.numfactura)} {cotizacion.nombreproyecto if cotizacion else ''}".strip(),
        'fecha_emision': factura.fechaemision.strftime('%d/%m/%Y') if factura.fechaemision else '',
        'fecha_pago': factura.fechapago.isoformat() if factura.fechapago else '',
        'estado': factura.estado,
        'estado_nombre': estados.get(factura.estado, ''),
        'monto_texto': srv.pesos(factura.valortotalpesos),
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
        'contactos_cliente': srv.contactos(cliente),
        'contactos_mandante': srv.contactos(mandante),
        'contacto_cotizacion': cotizacion.idcontacto_id if cotizacion else None,
        'glosa': srv.glosa_correo(factura, proyecto, cotizacion),
        'comentarios': srv.comentarios(factura.idfactura),
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
    factura = get_object_or_404(srv.todas(), pk=idfactura)
    try:
        comentario = (request.POST.get('comentario') or '').strip()
        if not comentario:
            raise ErrorValidacion('Debe ingresar el comentario del seguimiento.')

        cambia_estado = request.POST.get('cambia_estado') == '1'
        cod_estado = None
        fecha_pago = None
        if cambia_estado:
            estados = srv.estados_dict()
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

        srv.registrar_seguimiento(
            factura, comentario, _usuario(request), es_recordatorio=es_recordatorio,
            fecha_recordatorio=fecha_recordatorio, cod_estado=cod_estado, fecha_pago=fecha_pago,
            horario_llamada=horario_llamada, direc_retiro=direc_retiro, horario_retiro=horario_retiro,
            comentario_cliente=comentario_cliente)
    except ErrorValidacion as e:
        return JsonResponse({'ok': False, 'message': str(e)}, status=400)
    return JsonResponse({'ok': True, 'message': 'Seguimiento guardado.'})


@login_required
@require_POST
def factura_comentario_editar(request, idfactura, idreg):
    """Edita un comentario con AC_Factura_SEG (el usuario queda como quien lo editó, igual que antes)."""
    get_object_or_404(srv.todas(), pk=idfactura)
    try:
        comentario = (request.POST.get('comentario') or '').strip()
        if not comentario:
            raise ErrorValidacion('El comentario no puede quedar vacío.')
        fecha = _fecha(request.POST.get('fecha'), 'Fecha')
        es_recordatorio = request.POST.get('es_recordatorio') == '1'
        fecha_recordatorio = (_fecha(request.POST.get('fecha_recordatorio'), 'Fecha de recordatorio')
                              if es_recordatorio else None)
        existe = srv.editar_comentario(idfactura, idreg, comentario, fecha, _usuario(request),
                                       es_recordatorio=es_recordatorio, fecha_recordatorio=fecha_recordatorio)
    except ErrorValidacion as e:
        return JsonResponse({'ok': False, 'message': str(e)}, status=400)
    if not existe:
        return JsonResponse({'ok': False, 'message': 'El comentario ya no existe.'}, status=404)
    return JsonResponse({'ok': True, 'comentarios': srv.comentarios(idfactura)})


@login_required
@require_POST
def factura_comentario_eliminar(request, idfactura, idreg):
    get_object_or_404(srv.todas(), pk=idfactura)
    srv.eliminar_comentario(idfactura, idreg)
    return JsonResponse({'ok': True, 'comentarios': srv.comentarios(idfactura)})


@login_required
@require_GET
def factura_facturacion(request, idfactura):
    """Abre Creación de Facturas desde una factura del listado, como el clic en el N° de factura."""
    from .views import _valor_uf_por_fecha
    factura = get_object_or_404(srv.con_relaciones(), pk=idfactura)
    if factura.idproyecto is None:
        return JsonResponse({'ok': False, 'message': 'La factura no tiene proyecto.'}, status=400)
    estados = srv.estados_dict()
    hoy = timezone.localdate()
    uf_dia = _valor_uf_por_fecha(hoy)
    return JsonResponse({
        'ok': True,
        'origen_idfactura': factura.idfactura,
        'origen_numfactura': int(factura.numfactura),
        'proyecto': srv.encabezado_proyecto(factura.idproyecto, factura.idcliente),
        'facturas': srv.facturas_del_proyecto(factura.idproyecto_id, estados),
        'seguimiento': srv.seguimiento_texto(factura.idfactura),
        'uf_dia': uf_dia,
        'fecha_hoy': hoy.isoformat(),
        'detalles': DETALLES_FACTURA,
    })


@login_required
@require_GET
def factura_datos(request, idfactura):
    datos = srv.datos_factura(idfactura)
    if datos is None:
        return JsonResponse({'ok': False, 'message': 'La factura no existe.'}, status=404)
    return JsonResponse({'ok': True, 'factura': datos, 'seguimiento': srv.seguimiento_texto(idfactura)})


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
    encontrada = srv.buscar_por_numero(numero)
    if encontrada is None:
        return JsonResponse({'ok': True, 'existe': False})
    idproyecto, idfactura = encontrada
    return JsonResponse({'ok': True, 'existe': True, 'idproyecto': idproyecto,
                         'factura': srv.datos_factura(idfactura), 'seguimiento': srv.seguimiento_texto(idfactura)})


def _decimal(request, campo, nombre):
    texto = (request.POST.get(campo) or '').strip().replace('.', '').replace(',', '.') if ',' in (request.POST.get(campo) or '') \
        else (request.POST.get(campo) or '').strip()
    try:
        return float(texto)
    except ValueError:
        raise ErrorValidacion(f'{nombre} no es un número válido.')


@login_required
@require_POST
def factura_glosa(request, idproyecto):
    """Genera la descripción (botón 'Generar descripción', Button3 del formulario anterior)."""
    proyecto = get_object_or_404(Proyecto.objects.select_related('idcotizacion__idcliente', 'estadoproyecto'),
                                 pk=idproyecto)
    try:
        fecha_emision = _fecha(request.POST.get('fecha_emision'), 'Fecha de emisión')
        porc = _decimal(request, 'porc', '% a facturar')
        valor_uf = 1.0
        if (proyecto.moneda or '') == 'UF':
            if (request.POST.get('valor_uf') or '').strip():
                valor_uf = _decimal(request, 'valor_uf', 'Valor UF')
            else:  # la pantalla aún no tenía la UF: se usa la de la fecha de la factura (tValorUF o internet)
                from .views import _valor_uf_por_fecha
                valor_uf = round(float(_valor_uf_por_fecha(fecha_emision) or 0), 2)
                if valor_uf <= 0:
                    raise ErrorValidacion('No hay valor UF para la fecha de la factura (no está en el sistema ni en mindicador.cl, findic.cl o SII). '
                                          'Elija la UF con la opción "Manual" o cambie la fecha.')
        monto, valor_uf, total_pesos = srv.calculo(proyecto, porc, valor_uf)
        if total_pesos <= 0:
            raise ErrorValidacion('Debe ingresar el valor UF.')
    except ErrorValidacion as e:
        return JsonResponse({'ok': False, 'message': str(e)}, status=400)
    enc = srv.encabezado_proyecto(proyecto, None)
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
        srv.validar_grabacion(proyecto, numfactura, idfactura)
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
        if len(detalle) > srv.MAX_DETALLE:
            raise ErrorValidacion(f'El detalle admite hasta {srv.MAX_DETALLE} caracteres.')
        nuevo_estado = None
        if request.POST.get('cambia_estado') == '1':
            try:
                nuevo_estado = int(request.POST.get('estado'))
            except (TypeError, ValueError):
                nuevo_estado = None
            if nuevo_estado not in srv.estados_dict():
                raise ErrorValidacion('Debe seleccionar el estado de la factura.')
        if not (request.POST.get('glosa') or '').strip():
            raise ErrorValidacion('Falta actualizar la descripción de la factura.')
        num_hes = (request.POST.get('num_hes_eepp') or '').strip()
        if len(num_hes) > srv.MAX_NUM_HES:
            raise ErrorValidacion(f'El N° HES/EEPP admite hasta {srv.MAX_NUM_HES} caracteres.')
        fecha_hes = _fecha(request.POST.get('fecha_hes_eepp'), 'Fecha HES/EEPP') if request.POST.get('fecha_hes_eepp') else None
        try:
            vencimiento = int(request.POST.get('vencimiento') or 30)
        except ValueError:
            raise ErrorValidacion('Vencimiento no válido.')
        guardada = srv.grabar(
            proyecto, idfactura=idfactura, numfactura=numfactura, fecha_emision=fecha_emision, idcliente=idcliente,
            porc=porc, valor_uf=valor_uf, detalle=detalle, num_hes=num_hes, fecha_hes=fecha_hes,
            nuevo_estado=nuevo_estado, vencimiento=vencimiento)
    except ErrorValidacion as e:
        return JsonResponse({'ok': False, 'message': str(e)}, status=400)
    return JsonResponse({
        'ok': True,
        'message': 'Factura modificada.' if idfactura else 'Factura creada.',
        'idfactura': guardada.idfactura if guardada else None,
        'facturas': srv.facturas_del_proyecto(proyecto.pk, srv.estados_dict()),
        'saldo': srv.saldo_por_facturar(proyecto.pk),
    })


@login_required
@require_POST
def factura_eliminar(request, idfactura):
    """EL_Factura: borra la factura y su seguimiento (igual que antes, pero pidiendo confirmación en pantalla)."""
    factura = get_object_or_404(srv.todas(), pk=idfactura)
    idproyecto = factura.idproyecto_id
    srv.eliminar(idfactura)
    return JsonResponse({
        'ok': True,
        'facturas': srv.facturas_del_proyecto(idproyecto, srv.estados_dict()) if idproyecto else [],
        'saldo': srv.saldo_por_facturar(idproyecto) if idproyecto else 0,
    })


@login_required
@require_POST
def cliente_notas_guardar(request, idcliente):
    """Guarda las notas del cliente (botón de notas de CreacionFactura). Como antes, no borra si viene vacío."""
    cliente = get_object_or_404(Cliente, pk=idcliente)
    guardadas = srv.guardar_notas_cliente(cliente.pk, (request.POST.get('notas') or '').strip())
    return JsonResponse({'ok': True, 'message': 'Notas guardadas.' if guardadas else 'Sin cambios: las notas venían vacías.'})
