import json
import os
import re
from urllib.parse import urlencode
from datetime import timezone as dt_timezone
from urllib.request import urlopen
from django.shortcuts import render, redirect
from django.urls import reverse
from .models import *
from django.conf import settings
from django.views.generic import TemplateView, ListView, DetailView
from django.views.decorators.http import require_POST, require_GET
from django.http import HttpResponseNotAllowed, HttpResponse
from collections import defaultdict
from datetime import date
import json as _json

from django.db.models import Max, Prefetch, F, OuterRef, Subquery, Count, IntegerField, CharField, Value, Q, Exists, Sum, DecimalField
from django.db.models.functions import Cast
from django.db import transaction, IntegrityError, connection
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from datetime import timedelta, datetime, time
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.contrib import messages
from django.template.loader import render_to_string
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from .forms import ClienteForm, ClienteContactoFormSet, ClienteSeguimientoForm, CotizacionForm, TipoEntregaForm, SeguimientoCotizacionForm, ValorUFForm
from weasyprint import HTML
from django.db import DatabaseError
from .servicios import proyectos as srv_proyectos
from .servicios import uf as srv_uf
from .servicios import cotizaciones as srv_cotizaciones
from .servicios import clientes as srv_clientes
from .servicios import entregas as srv_entregas
from .servicios import tablas as srv_tablas
from django.http import Http404





ESTADO_CLIENTE_ELIMINADO = 5

CATALOGO_COTIZACIONES = [
    {
        'titulo': 'Búsqueda de Cotizaciones',
        'submenu': 'Consulta y selección de cotizaciones',
        'descripcion': 'Listado inicial para buscar, revisar y abrir cotizaciones existentes.',
        'accion_principal': 'Buscar cotizaciones',
        'url_principal_name': 'cotizaciones_busqueda',
    },
    {
        'titulo': 'Ingreso de Cotizaciones',
        'submenu': 'Alta de cotización nueva',
        'descripcion': 'Formulario base para crear una cotización nueva en el sistema.',
        'accion_principal': 'Crear cotización',
        'url_principal_name': 'cotizaciones_ingreso',
    },
]

ESTADOS_COTIZACION = srv_cotizaciones.ESTADOS_COTIZACION


def _cotizacion_estado_visual(cotizacion):
    if not cotizacion.esactiva:
        return {
            'label': 'Cerrada / Inactiva',
            'class': 'cotizacion-badge-cerrada',
        }

    if cotizacion.estado == 0:
        return {
            'label': 'Borrador',
            'class': 'cotizacion-badge-borrador',
        }

    return {
        'label': 'Activa',
        'class': 'cotizacion-badge-activa',
    }


def _facturacion_completa_proyecto(proyecto):
    return srv_proyectos.facturacion_completa(proyecto)


def _valor_uf_por_fecha(fecha):
    """UF de la fecha desde tValorUF; si falta, la busca en internet (mindicador.cl, findic.cl o SII) y la guarda."""
    return srv_uf.valor_por_fecha(fecha)


def _siguiente_num_factura():
    ultima = Factura.objects.order_by('-numfactura').first()
    return (int(ultima.numfactura) + 1) if ultima else 1


def _parse_date_ddmmyyyy(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%d/%m/%Y').date()
    except ValueError:
        return None


@login_required
def api_valor_uf_por_fecha(request):
    fecha_txt = (request.GET.get('fecha') or '').strip()
    fecha = _parse_date_ddmmyyyy(fecha_txt)
    if not fecha:
        return JsonResponse({'ok': False, 'message': 'Fecha inválida.'}, status=400)

    valor = _valor_uf_por_fecha(fecha)
    if valor is None:
        return JsonResponse({'ok': False, 'message': f'No existe UF para esa fecha, ni en el sistema ni en {srv_uf.FUENTES_TEXTO}.'}, status=404)
    return JsonResponse({'ok': True, 'valoruf': round(float(valor), 2)})  # tValorUF es real: sin decimales de más


def _estado_cotizacion_class(nombre):
    texto = (nombre or '').lower()
    if 'aprob' in texto:
        return 'estado-cotizacion-aprobada'
    if 'esper' in texto:
        return 'estado-cotizacion-espera'
    if 'cerr' in texto or 'inact' in texto:
        return 'estado-cotizacion-cerrada'
    return 'estado-cotizacion-pendiente'


def _estado_cotizacion_style(estado):
    if not estado:
        return ''
    estilos = []
    if getattr(estado, 'colorfondo', None):
        estilos.append(f'background-color: {estado.colorfondo};')
    if getattr(estado, 'colortexto', None):
        estilos.append(f'color: {estado.colortexto};')
    return ' '.join(estilos)


def _direccion_mandante(cliente):
    if not cliente:
        return ''
    return cliente.direcfactura or cliente.direccion or ''


User = get_user_model()


def _nombre_visible_usuario_actual(usuario):
    nombre = usuario.get_full_name().strip()
    if nombre:
        return nombre

    username = getattr(usuario, 'username', '') or str(usuario)
    return username.strip()


@login_required
def cotizaciones_home(request):
    return render(request, 'cotizaciones/index.html', {
        'titulo': 'Cotizaciones',
        'encabezado': 'Cotizaciones',
        'submenu': 'Módulo de cotizaciones',
        'secciones': CATALOGO_COTIZACIONES,
    })


@login_required
def cotizaciones_busqueda(request):
    numero = (request.GET.get('numero') or '').strip()
    proyecto = (request.GET.get('proyecto') or '').strip()
    mandante = (request.GET.get('mandante') or '').strip()
    fecha_desde = (request.GET.get('fecha_desde') or '').strip()
    fecha_hasta = (request.GET.get('fecha_hasta') or '').strip()
    busqueda_textual = bool(numero or proyecto or mandante)

    if not any([numero, proyecto, mandante, fecha_desde, fecha_hasta]):
        fecha_desde = (timezone.localdate() - timedelta(days=30)).isoformat()

    if busqueda_textual:
        fecha_desde = ''
        fecha_hasta = ''

    clear_params = {'fecha_desde': fecha_desde}
    qs = srv_cotizaciones.buscar(numero, proyecto, mandante, fecha_desde, fecha_hasta)

    cotizaciones = []
    estado_proyecto_protegido = srv_cotizaciones.ESTADO_APROBADA
    for cotizacion in qs:
        cotizacion.estado_texto = ESTADOS_COTIZACION.get(cotizacion.estado, 'Sin estado')
        cotizacion.estadocotizacion_texto = cotizacion.estadocotizacion.nombre if cotizacion.estadocotizacion_id else 'Sin estado'
        cotizacion.estadocotizacion_class = _estado_cotizacion_class(cotizacion.estadocotizacion_texto)
        cotizacion.mandante_texto = cotizacion.idcliente.razonsocial if cotizacion.idcliente else ''
        cotizacion.contacto_texto = cotizacion.idcontacto.nombrecontacto if cotizacion.idcontacto else ''
        cotizacion.proyecto_texto = cotizacion.nombreproyecto or (str(cotizacion.proyecto_id) if cotizacion.tiene_proyecto and cotizacion.proyecto_id else '')
        cotizacion.valor_total_texto = cotizacion.valortotal or 0
        cotizacion.fecha_ultimo_seg_texto = cotizacion.fecha_ultimo_seg.strftime('%d-%m-%Y %H:%M') if cotizacion.fecha_ultimo_seg else ''
        cotizacion.comentario_ultimo_seg_texto = (cotizacion.comentario_ultimo_seg or '')[:80]
        cotizacion.num_proyecto_texto = str(cotizacion.num_proyecto) if cotizacion.num_proyecto else ''
        cotizacion.valor_proyecto_texto = cotizacion.valor_proyecto or 0
        cotizacion.fpago_proyecto_texto = cotizacion.fpago_proyecto or ''
        cotizacion.es_activa_texto = 'SI' if cotizacion.esactiva else 'NO'
        cotizacion.bloquea_acciones = bool(cotizacion.tiene_proyecto and cotizacion.estadocotizacion_texto == estado_proyecto_protegido)
        cotizaciones.append(cotizacion)

    return render(request, 'cotizaciones/busqueda.html', {
        'titulo': 'Búsqueda de Cotizaciones',
        'encabezado': 'Búsqueda de Cotizaciones',
        'submenu': 'Consulta y selección',
        'volver_url_name': 'cotizaciones_home',
        'accion_nombre': 'Ingreso de Cotizaciones',
        'accion_url_name': 'cotizaciones_ingreso',
        'cotizaciones': cotizaciones,
        'filtros': {
            'numero': numero,
            'proyecto': proyecto,
            'mandante': mandante,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
        },
        'limpiar_url': f"?{urlencode(clear_params)}",
    })


def _formatear_miles(valor):
    try:
        return f"{float(valor or 0):,.0f}".replace(',', '.')
    except (TypeError, ValueError):
        return '0'


@login_required
def cotizaciones_seguimiento(request):
    numero = (request.GET.get('numero') or '').strip()
    proyecto = (request.GET.get('proyecto') or '').strip()
    mandante = (request.GET.get('mandante') or '').strip()
    fecha_desde = (request.GET.get('fecha_desde') or '').strip()
    fecha_hasta = (request.GET.get('fecha_hasta') or '').strip()
    # Estados con selección múltiple. Al abrir (sin filtros) se muestran las "En Espera", como antes.
    estado_espera = srv_cotizaciones.id_estado_en_espera()
    filtrado = 'filtrado' in request.GET or 'estado' in request.GET
    estados_sel = sorted({int(e) for e in request.GET.getlist('estado') if e.strip().isdigit()})
    if not filtrado and not any([numero, proyecto, mandante, fecha_desde, fecha_hasta]) and estado_espera:
        estados_sel = [estado_espera]

    usar_fechas = not any([numero, proyecto, mandante, estados_sel])
    qs = srv_cotizaciones.buscar_seguimiento(numero, proyecto, mandante, estados_sel, fecha_desde, fecha_hasta, usar_fechas)

    cotizaciones = []
    for cotizacion in qs:
        cotizacion.estado_texto = ESTADOS_COTIZACION.get(cotizacion.estado, 'Sin estado')
        cotizacion.estadocotizacion_texto = cotizacion.estadocotizacion.nombre if cotizacion.estadocotizacion_id else 'Sin estado'
        cotizacion.estadocotizacion_class = _estado_cotizacion_class(cotizacion.estadocotizacion_texto)
        cotizacion.estadocotizacion_style = _estado_cotizacion_style(cotizacion.estadocotizacion)
        cotizacion.mandante_texto = cotizacion.idcliente.razonsocial if cotizacion.idcliente else ''
        cotizacion.contacto_texto = cotizacion.idcontacto.nombrecontacto if cotizacion.idcontacto else ''
        cotizacion.email_texto = cotizacion.idcontacto.email if cotizacion.idcontacto else ''
        cotizacion.telefono_texto = cotizacion.idcontacto.telefono if cotizacion.idcontacto else ''
        cotizacion.fpago_texto = cotizacion.fpago_proyecto or ''
        cotizacion.moneda_texto = cotizacion.moneda or ''
        cotizacion.proyecto_texto = cotizacion.nombreproyecto or ''
        valor_total = float(cotizacion.valortotal or 0)
        valor_opcional = float(cotizacion.valor_opcional or 0)
        cotizacion.valor_opcional_texto = _formatear_miles(valor_opcional)
        cotizacion.valor_total_texto = _formatear_miles(max(valor_total - valor_opcional, 0))
        cotizacion.fecha_ultimo_seg_texto = cotizacion.fecha_ultimo_seg.strftime('%d-%m-%Y %H:%M') if cotizacion.fecha_ultimo_seg else ''
        cotizacion.comentario_ultimo_seg_texto = (cotizacion.comentario_ultimo_seg or '')[:80]
        cotizacion.num_proyecto_texto = str(cotizacion.num_proyecto) if cotizacion.num_proyecto else ''
        cotizacion.valor_proyecto_texto = _formatear_miles(cotizacion.valor_proyecto)
        cotizacion.es_activa_texto = 'SI' if cotizacion.esactiva else 'NO'
        cotizacion.puede_editar = cotizacion.estadocotizacion_texto == srv_cotizaciones.ESTADO_EN_ESPERA
        cotizaciones.append(cotizacion)

    return render(request, 'cotizaciones/seguimiento_listado.html', {
        'titulo': 'Seguimiento de Cotizaciones',
        'encabezado': 'Seguimiento de Cotizaciones',
        'submenu': 'Listado principal de seguimiento',
        'volver_url_name': 'cotizaciones_home',
        'cotizaciones': cotizaciones,
        'filtros': {
            'numero': numero,
            'proyecto': proyecto,
            'mandante': mandante,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
        },
        'usar_fechas': usar_fechas,
        'estados_marcados': estados_sel,
        'estados_defecto': [estado_espera] if estado_espera else [],
        'estados': srv_cotizaciones.estados(),
        'limpiar_url': request.path,
    })


@login_required
def cotizacion_seguimiento_historial(request, pk):
    seguimientos = []
    for seg in srv_cotizaciones.historial(pk):
        usuario = seg.usuario
        nombre_usuario = ''
        if usuario:
            nombre_usuario = f"{(usuario.first_name or '').strip()} {(usuario.last_name or '').strip()}".strip() or usuario.username
        seguimientos.append({
            'fecha': seg.fecharevision.strftime('%d-%m-%Y %H:%M') if seg.fecharevision else '',
            'usuario': nombre_usuario,
            'comentario': seg.comentario or '',
            'recordatorio': 'SI' if seg.esrecordatorio else 'NO',
            'fecha_recordatorio': seg.fecharecordatorio.strftime('%d-%m-%Y') if seg.fecharecordatorio else '',
        })
    return JsonResponse({'seguimientos': seguimientos})


@login_required
def cotizaciones_ingreso(request):
    copy_from = (request.GET.get('copy_from') or request.POST.get('copy_from') or '').strip()
    cotizacion_origen = None
    notas_seleccionadas = []
    formapago_items = []
    items_guardados = []

    if copy_from.isdigit():
        cotizacion_origen = get_object_or_404(srv_cotizaciones.con_relaciones(), pk=int(copy_from))
        datos = srv_cotizaciones.datos_para_formulario(cotizacion_origen)
        notas_seleccionadas = datos['notas_seleccionadas']
        formapago_items = datos['formapago_items']
        items_guardados = datos['items_guardados']

    if request.method == 'POST':
        form = CotizacionForm(request.POST)
        if form.is_valid():
            cotizacion = srv_cotizaciones.crear(
                form.save(commit=False), request.user.username, fecha=form.cleaned_data.get('fecha'),
                items_json=request.POST.get('items_json', ''), formapago_json=request.POST.get('formapago_json', ''),
                notas_json=request.POST.get('notas_json', ''))
            messages.success(request, 'Cotización creada correctamente.')
            return redirect('cotizacion_detalle', pk=cotizacion.pk)
    else:
        initial = {'fecha': timezone.localdate()}
        if cotizacion_origen:
            initial.update({
                'idcliente': cotizacion_origen.idcliente_id,
                'idcontacto': cotizacion_origen.idcontacto_id,
                'fecha': timezone.localdate(),
                'nombreproyecto': cotizacion_origen.nombreproyecto,
                'dirproyecto': cotizacion_origen.dirproyecto,
                'codregion': cotizacion_origen.codregion,
                'destino': cotizacion_origen.destino,
                'pisos': cotizacion_origen.pisos,
                'edificios': cotizacion_origen.edificios,
                'mt2': cotizacion_origen.mt2,
                'moneda': cotizacion_origen.moneda,
            })
        form = CotizacionForm(initial=initial)

    formapago_catalogo = list(srv_cotizaciones.formas_pago_catalogo().values('concepto'))

    return render(request, 'cotizaciones/form.html', {
        'titulo': 'Ingreso de Cotizaciones',
        'encabezado': 'Ingreso de Cotizaciones',
        'submenu': 'Alta de cotización nueva' if not cotizacion_origen else 'Copia de cotización',
        'volver_url_name': 'cotizaciones_home',
        'accion_nombre': 'Búsqueda de Cotizaciones',
        'accion_url_name': 'cotizaciones_busqueda',
        'form': form,
        'modo': 'crear',
        'copy_from': copy_from,
        'items_guardados': items_guardados,
        'notas_seleccionadas': notas_seleccionadas,
        'formapago_items': formapago_items,
        'formapago_catalogo': formapago_catalogo,
    })


@login_required
def cotizacion_visor(request, pk):
    cotizacion = get_object_or_404(srv_cotizaciones.con_relaciones(), pk=pk)
    tablas = srv_cotizaciones.detalle(cotizacion)
    proyectos, valores, formas_pago, notas = tablas['proyectos'], tablas['valores'], tablas['formas_pago'], tablas['notas']
    seguimientos = srv_cotizaciones.seguimientos(cotizacion)

    cotizacion.estado_texto = ESTADOS_COTIZACION.get(cotizacion.estado, 'Sin estado')
    cotizacion.estadocotizacion_texto = cotizacion.estadocotizacion.nombre if cotizacion.estadocotizacion_id else 'Sin estado'
    cotizacion.estadocotizacion_class = _estado_cotizacion_class(cotizacion.estadocotizacion_texto)
    cotizacion.mandante_texto = cotizacion.idcliente.razonsocial if cotizacion.idcliente else ''
    cotizacion.mandante_direccion = _direccion_mandante(cotizacion.idcliente)
    cotizacion.contacto_texto = cotizacion.idcontacto.nombrecontacto if cotizacion.idcontacto else ''
    cotizacion.telefono_contacto = cotizacion.idcontacto.telefono if cotizacion.idcontacto else ''
    cotizacion.email_contacto = cotizacion.idcontacto.email if cotizacion.idcontacto else ''
    cotizacion.proyecto_texto = cotizacion.nombreproyecto or ''
    cotizacion.region_texto = srv_cotizaciones.nombre_region(cotizacion.codregion)
    cotizacion.estado_visual = _cotizacion_estado_visual(cotizacion)
    cotizacion.cotizacion_pdf_url = request.build_absolute_uri(reverse('cotizacion_reporte_pdf', args=[cotizacion.pk]))
    cotizacion.mt2_texto = cotizacion.mt2 if cotizacion.mt2 is not None else 'No informado'
    cotizacion.total_proyecto, cotizacion.total_con_opcional = srv_cotizaciones.totales(valores)
    cotizacion.puede_editar = srv_cotizaciones.puede_editar(cotizacion)

    return render(request, 'cotizaciones/detalle.html', {
        'titulo': f'Cotización {cotizacion.numcotizacion or cotizacion.idcotizacion}',
        'encabezado': 'Visor de Cotización',
        'submenu': 'Consulta completa de cotización',
        'cotizacion': cotizacion,
        'proyectos': proyectos,
        'valores': valores,
        'formas_pago': formas_pago,
        'notas': notas,
        'seguimientos': seguimientos,
        'volver_url_name': 'cotizaciones_busqueda',
        'editar_url_name': 'cotizacion_editar',
    })


@login_required
@transaction.atomic
def cotizacion_seguimiento(request, pk):
    cotizacion = get_object_or_404(srv_cotizaciones.con_relaciones(), pk=pk)
    return_to = (request.GET.get('return_to') or request.POST.get('return_to') or '').strip()
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    if request.method == 'POST':
        form = SeguimientoCotizacionForm(request.POST)
        if form.is_valid():
            comentario = (form.cleaned_data.get('comentario') or '').replace("'", '')
            es_recordatorio = form.cleaned_data.get('es_recordatorio', False)
            cambia_estado = form.cleaned_data.get('cambia_estado', False)
            nuevo_estado = form.cleaned_data.get('nuevo_estado')
            quien_adjudica = (form.cleaned_data.get('quien_adjudica') or '').strip()
            email_adjudicacion = (form.cleaned_data.get('email_adjudicacion') or '').strip()
            fecha_adjudicacion = form.cleaned_data.get('fecha_adjudicacion')
            fecha_recordatorio = form.cleaned_data.get('fecha_recordatorio')

            errores = srv_cotizaciones.validar_seguimiento(
                comentario=comentario, cambia_estado=cambia_estado, nuevo_estado=nuevo_estado,
                es_recordatorio=es_recordatorio, fecha_recordatorio=fecha_recordatorio, quien_adjudica=quien_adjudica,
                email_adjudicacion=email_adjudicacion, fecha_adjudicacion=fecha_adjudicacion)
            for campo, mensaje in errores.items():
                form.add_error(campo, mensaje)

            if not form.errors:
                srv_cotizaciones.registrar_seguimiento(
                    cotizacion, request.user, comentario=comentario, es_recordatorio=es_recordatorio,
                    fecha_recordatorio=fecha_recordatorio, nuevo_estado=nuevo_estado if cambia_estado else None,
                    quien_adjudica=quien_adjudica, email_adjudicacion=email_adjudicacion,
                    fecha_adjudicacion=fecha_adjudicacion)
                messages.success(request, 'Seguimiento registrado correctamente.')
                if is_ajax:
                    return JsonResponse({'ok': True})
                if return_to == 'seguimiento':
                    return redirect('cotizaciones_seguimiento')
                return redirect('cotizacion_visor', pk=cotizacion.pk)
    else:
        form = SeguimientoCotizacionForm(initial={'comentario': ''})

    if is_ajax:
        return JsonResponse({
            'html': render_to_string('cotizaciones/seguimiento_form_body.html', {
                'cotizacion': cotizacion,
                'form': form,
                'return_to': return_to,
            }, request=request)
        })

    return render(request, 'cotizaciones/seguimiento_form.html', {
        'titulo': f'Seguimiento Cotización {cotizacion.numcotizacion or cotizacion.idcotizacion}',
        'encabezado': 'Seguimiento de Cotización',
        'submenu': 'Registrar comentario y cambio de estado',
        'cotizacion': cotizacion,
        'form': form,
        'volver_url_name': 'cotizaciones_seguimiento',
        'return_to': return_to,
    })


@login_required
def cotizacion_editar(request, pk):
    cotizacion = get_object_or_404(srv_cotizaciones.con_relaciones(), pk=pk)
    return_to = (request.GET.get('return_to') or request.POST.get('return_to') or '').strip()
    volver_url_name = 'cotizaciones_seguimiento' if return_to == 'seguimiento' else 'cotizacion_detalle'
    if not srv_cotizaciones.puede_editar(cotizacion):
        messages.info(request, 'Esta cotización no se puede editar en su estado actual.')
        return redirect('cotizacion_visor', pk=cotizacion.pk)
    datos = srv_cotizaciones.datos_para_formulario(cotizacion)
    notas_seleccionadas = datos['notas_seleccionadas']
    formapago_items = datos['formapago_items']
    items_guardados = datos['items_guardados']
    if request.method == 'POST':
        form = CotizacionForm(request.POST, instance=cotizacion)
        if form.is_valid():
            cotizacion = srv_cotizaciones.modificar(
                form.save(commit=False), fecha=form.cleaned_data.get('fecha'),
                items_json=request.POST.get('items_json', ''), formapago_json=request.POST.get('formapago_json', ''),
                notas_json=request.POST.get('notas_json', ''))
            messages.success(request, 'Cotización actualizada correctamente.')
            if volver_url_name == 'cotizaciones_seguimiento':
                return redirect(volver_url_name)
            return redirect(volver_url_name, pk=cotizacion.pk)
    else:
        form = CotizacionForm(instance=cotizacion, initial={'fecha': cotizacion.fecha})

    formapago_catalogo = list(srv_cotizaciones.formas_pago_catalogo().values('concepto'))

    return render(request, 'cotizaciones/form.html', {
        'titulo': 'Editar Cotización',
        'encabezado': 'Editar Cotización',
        'submenu': 'Modificación de cotización',
        'volver_url_name': 'cotizacion_detalle',
        'volver_pk': cotizacion.pk,
        'accion_url_name': 'cotizaciones_busqueda',
        'accion_nombre': 'Búsqueda de Cotizaciones',
        'form': form,
        'cotizacion': cotizacion,
        'modo': 'editar',
        'volver_url_name': volver_url_name,
        'return_to': return_to,
        'notas_seleccionadas': notas_seleccionadas,
        'formapago_items': formapago_items,
        'items_guardados': items_guardados,
        'formapago_catalogo': formapago_catalogo,
    })


@login_required
@transaction.atomic
def cotizacion_versionar(request, pk):
    base = get_object_or_404(srv_cotizaciones.todas(), pk=pk)
    nueva = srv_cotizaciones.versionar(base, request.user.username)

    messages.success(request, 'Nueva versión creada correctamente.')
    return redirect('cotizacion_detalle', pk=nueva.pk)


@login_required
def cotizacion_detalle(request, pk):
    cotizacion = get_object_or_404(srv_cotizaciones.con_relaciones(), pk=pk)
    tablas = srv_cotizaciones.detalle(cotizacion)
    proyectos, valores, formas_pago, notas = tablas['proyectos'], tablas['valores'], tablas['formas_pago'], tablas['notas']

    cotizacion.estado_texto = ESTADOS_COTIZACION.get(cotizacion.estado, 'Sin estado')
    cotizacion.estadocotizacion_texto = cotizacion.estadocotizacion.nombre if cotizacion.estadocotizacion_id else 'Sin estado'
    cotizacion.estadocotizacion_class = _estado_cotizacion_class(cotizacion.estadocotizacion_texto)
    cotizacion.mandante_texto = cotizacion.idcliente.razonsocial if cotizacion.idcliente else ''
    cotizacion.mandante_direccion = _direccion_mandante(cotizacion.idcliente)
    cotizacion.contacto_texto = cotizacion.idcontacto.nombrecontacto if cotizacion.idcontacto else ''
    cotizacion.telefono_contacto = cotizacion.idcontacto.telefono if cotizacion.idcontacto else ''
    cotizacion.email_contacto = cotizacion.idcontacto.email if cotizacion.idcontacto else ''
    cotizacion.region_texto = srv_cotizaciones.nombre_region(cotizacion.codregion)
    cotizacion.estado_visual = _cotizacion_estado_visual(cotizacion)
    cotizacion.cotizacion_pdf_url = request.build_absolute_uri(reverse('cotizacion_reporte_pdf', args=[cotizacion.pk]))
    cotizacion.mt2_texto = cotizacion.mt2 if cotizacion.mt2 is not None else 'No informado'
    cotizacion.total_proyecto, cotizacion.total_con_opcional = srv_cotizaciones.totales(valores)
    cotizacion.puede_editar = srv_cotizaciones.puede_editar(cotizacion)

    return render(request, 'cotizaciones/detalle.html', {
        'titulo': f'Cotización {cotizacion.numcotizacion or cotizacion.idcotizacion}',
        'encabezado': 'Detalle de Cotización',
        'submenu': 'Ficha de cotización',
        'cotizacion': cotizacion,
        'proyectos': proyectos,
        'valores': valores,
        'formas_pago': formas_pago,
        'notas': notas,
        'volver_url_name': 'cotizaciones_busqueda',
        'editar_url_name': 'cotizacion_editar',
    })


def _cotizacion_html_para_pdf(request, context):
    return render_to_string('cotizaciones/reporte_pdf.html', context, request=request)


def _render_pdf_con_weasyprint(html, base_url):
    return HTML(string=html, base_url=base_url).write_pdf()


@login_required
def cotizacion_reporte_pdf(request, pk):
    cotizacion = get_object_or_404(srv_cotizaciones.con_relaciones(), pk=pk)
    tablas = srv_cotizaciones.detalle(cotizacion)
    proyectos, valores, formas_pago, notas = tablas['proyectos'], tablas['valores'], tablas['formas_pago'], tablas['notas']

    cotizacion.estado_texto = ESTADOS_COTIZACION.get(cotizacion.estado, 'Sin estado')
    cotizacion.estadocotizacion_texto = cotizacion.estadocotizacion.nombre if cotizacion.estadocotizacion_id else 'Sin estado'
    cotizacion.estadocotizacion_class = _estado_cotizacion_class(cotizacion.estadocotizacion_texto)
    cotizacion.mandante_texto = cotizacion.idcliente.razonsocial if cotizacion.idcliente else ''
    cotizacion.mandante_direccion = _direccion_mandante(cotizacion.idcliente)
    cotizacion.contacto_texto = cotizacion.idcontacto.nombrecontacto if cotizacion.idcontacto else ''
    cotizacion.telefono_contacto = cotizacion.idcontacto.telefono if cotizacion.idcontacto else ''
    cotizacion.email_contacto = cotizacion.idcontacto.email if cotizacion.idcontacto else ''
    cotizacion.region_texto = srv_cotizaciones.nombre_region(cotizacion.codregion)
    cotizacion.estado_visual = _cotizacion_estado_visual(cotizacion)
    cotizacion.mt2_texto = cotizacion.mt2 if cotizacion.mt2 is not None else 'No informado'
    cotizacion.total_proyecto, cotizacion.total_con_opcional = srv_cotizaciones.totales(valores)

    context = {
        'titulo': f'Reporte Cotización {cotizacion.numcotizacion or cotizacion.idcotizacion}',
        'cotizacion': cotizacion,
        'proyectos': proyectos,
        'valores': valores,
        'formas_pago': formas_pago,
        'notas': notas,
    }
    html = _cotizacion_html_para_pdf(request, context)
    try:
        pdf_bytes = _render_pdf_con_weasyprint(html, request.build_absolute_uri('/'))
    except Exception as exc:
        return HttpResponse(f'No se pudo generar el PDF: {exc}', content_type='text/plain', status=500)

    if not pdf_bytes or not isinstance(pdf_bytes, (bytes, bytearray)):
        return HttpResponse('No se pudo generar el PDF.', content_type='text/plain', status=500)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Reporte_Cotizacion_{cotizacion.numcotizacion or cotizacion.idcotizacion}.pdf"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_GET
def api_cotizaciones_mandantes(request):
    term = (request.GET.get('term') or '').strip()
    data = [
        {
            'id': c.idcliente,
            'text': c.razonsocial or f'Cliente {c.idcliente}',
            'direccion': c.direccion or '',
            'telefono': c.telefono or '',
        }
        for c in srv_cotizaciones.buscar_mandantes(term)
    ]
    return JsonResponse({'results': data})


@login_required
@require_GET
def api_cotizaciones_mandante_detalle(request, pk):
    cliente = srv_cotizaciones.mandante(pk)
    if not cliente:
        return JsonResponse({'ok': False, 'detail': {}}, status=404)
    return JsonResponse({
        'ok': True,
        'detail': {
            'id': cliente.idcliente,
            'text': cliente.razonsocial or f'Cliente {cliente.idcliente}',
            'direccion': cliente.direccion or '',
            'telefono': cliente.telefono or '',
        },
    })


@login_required
@require_GET
def api_cotizaciones_contactos(request):
    cliente_id = (request.GET.get('cliente_id') or '').strip()
    term = (request.GET.get('term') or '').strip()

    qs = srv_cotizaciones.buscar_contactos(int(cliente_id) if cliente_id.isdigit() else None, term)

    data = [
        {
            'id': contacto.idcontacto,
            'text': contacto.nombrecontacto or f'Contacto {contacto.idcontacto}',
            'cliente_id': contacto.idcliente_id,
            'cargo': contacto.cargo or '',
            'telefono': contacto.telefono or '',
            'email': contacto.email or '',
        }
        for contacto in qs
    ]
    return JsonResponse({'results': data})


@login_required
@require_GET
def api_cotizaciones_contacto_detalle(request, pk):
    contacto = srv_cotizaciones.contacto(pk)
    if not contacto:
        return JsonResponse({'ok': False, 'detail': {}}, status=404)
    return JsonResponse({
        'ok': True,
        'detail': {
            'id': contacto.idcontacto,
            'text': contacto.nombrecontacto or f'Contacto {contacto.idcontacto}',
            'cliente_id': contacto.idcliente_id,
            'cargo': contacto.cargo or '',
            'telefono': contacto.telefono or '',
            'email': contacto.email or '',
        },
    })


@login_required
@require_GET
def api_cotizaciones_items(request):
    qs = srv_cotizaciones.items_catalogo()
    data = [{'id': item.iditem, 'text': item.nombre} for item in qs]
    return JsonResponse({'results': data})


@login_required
@require_GET
def api_cotizaciones_notas(request):
    qs = srv_cotizaciones.notas_catalogo()
    data = [{'id': nota.idnota, 'text': nota.nota} for nota in qs]
    return JsonResponse({'results': data})


@login_required
@require_GET
def api_cotizaciones_formapago(request):
    qs = srv_cotizaciones.formas_pago_catalogo()
    data = [{'id': fp.idfpago, 'text': fp.concepto} for fp in qs]
    return JsonResponse({'results': data})


def _ahora_santiago_naive():
    return timezone.localtime(timezone.now()).replace(tzinfo=None)


def _notas_pendientes_desde_post(post_data, usuario):
    usuario_nombre = _nombre_visible_usuario_actual(usuario)
    notas = []

    for texto in post_data.getlist('notas_agregadas'):
        texto_limpio = (texto or '').strip()
        if texto_limpio:
            notas.append({
                'nota': texto_limpio,
                'usuario_nombre': usuario_nombre,
            })

    return notas


# Create your views here.

class HomeView(LoginRequiredMixin,TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "titulo": "Inicio",
            "encabezado": "Ducto Proyectos",
        })
        return context
    
 
class ListaCategoria(LoginRequiredMixin,ListView):
    model = T_Categoria
    template_name = 'listacategoria.html'

    def get_queryset(self):
        return srv_tablas.categorias()

    def get(self, request, *args, **kwargs):
        contexto = {
            'categorias': self.get_queryset(),
            'encabezado': 'Listado de Categorías',
            'submenu': 'Categorías',
            'titulo': 'Listado Categorías'
            }

        return render(request, self.template_name, contexto)
    

class Vista1(LoginRequiredMixin,TemplateView):
    template_name = "proyterminados.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)

        try:
            contexto["proyecto"] = srv_proyectos.consulta_web(1)
        except DatabaseError as e:
            print("Error SQL:", e)
            contexto["proyecto"] = []
            contexto["error_sql"] = "No se pudo consultar la base de datos."

        contexto.update({
            "encabezado": "DUCTO",
            "titulo": "PROYECTOS TERMINADOS",
            "menu": "Proyectos",
            "submenu": "Listado de Proyectos Terminados",
        })
        return contexto


# Estados marcados por defecto en el filtro de Seguimiento de Proyectos (estadoproyecto_id): Nuevo, Con Datos de
# Facturación, Entrega Versión Revisión, Con Observaciones, Con VB para Ingreso a SEREMI, A Espera de VB y EN PAUSA.
# Quedan fuera los estados SEREMI avanzados, terminados y anulados (pedido de Paulo, 2026-11-20).
ESTADOS_PROYECTO_ACTIVOS = srv_proyectos.ESTADOS_PROYECTO_ACTIVOS
# No se facturan proyectos anulados (estadoproyecto_id de 'Proyecto ANULADO')
ESTADO_PROYECTO_ANULADO = srv_proyectos.ESTADO_PROYECTO_ANULADO
# Crear factura y datos de facturación: perfil 0 del escritorio = grupo Director + grupo Facturación
GRUPOS_FACTURACION = ('Director', 'Facturación')


def _url_seguimiento_con_filtros(filtros):
    """URL del listado con los filtros que tenía el usuario; 'estado' viene como ids separados por coma."""
    params = [('filtrado', '1')]
    params += [('estado', e) for e in (filtros.get('estado') or '').split(',') if e.strip()]
    params += [(k, v) for k, v in filtros.items() if k != 'estado' and v]
    return f"{reverse('seguimiento_proyectos')}?{urlencode(params)}"


def _estados_factura_catalogo():
    from .servicios import facturas as srv_facturas
    return srv_facturas.estados()


def puede_facturar(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name__in=GRUPOS_FACTURACION).exists())


def _sin_permiso_facturar(request):
    msg = 'No tiene permiso para facturar ni modificar datos de facturación.'
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'message': msg}, status=403)
    messages.error(request, msg)
    return redirect('seguimiento_proyectos')


class VistaSeguimiento(LoginRequiredMixin,TemplateView):
    template_name = "proyectos_seguimiento.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)

        # Filtro de estados con selección múltiple; al abrir se marcan los estados por defecto
        filtrado = 'filtrado' in self.request.GET or 'estado' in self.request.GET
        valores_estado = [e.strip() for e in self.request.GET.getlist('estado') if e.strip()]
        todos_ids = srv_proyectos.ids_estados()
        if 'todos' in valores_estado:
            estados_sel = todos_ids
        elif filtrado:
            estados_sel = sorted({int(e) for e in valores_estado if e.isdigit()} & set(todos_ids))
        else:
            estados_sel = list(ESTADOS_PROYECTO_ACTIVOS)
        estado_id = ','.join(str(e) for e in estados_sel)
        mandante_id = (self.request.GET.get('mandante') or '').strip()
        numero_proyecto = (self.request.GET.get('numero_proyecto') or '').strip()

        proyectos = srv_proyectos.buscar_seguimiento(estados_sel, mandante_id, numero_proyecto)

        estados_proyecto = srv_proyectos.estados()
        monedas = MonedaCotizacion.objects.order_by('nombre')
        formas_pago = TFpago.objects.all().order_by('idfpago')
        medios_conf = srv_proyectos.MEDIOS_CONF
        booleanos_si_no = ['NO', 'SI']
        valores_uf = tValorUF.objects.order_by('-Fecha')
        mandantes = srv_proyectos.mandantes()
        clientes_proyecto = srv_proyectos.clientes()
        contactos_facturacion = srv_proyectos.contactos_facturacion()

        regiones = srv_proyectos.regiones()
        seguimientos = srv_proyectos.textos_seguimiento([pro.idproyecto for pro in proyectos])
        ultimas_fechas_seg = srv_proyectos.ultimas_fechas_seguimiento([pro.idproyecto for pro in proyectos])
        saldos_por_facturar = srv_proyectos.saldos_por_facturar(pro.idproyecto for pro in proyectos)

        for pro in proyectos:
            cot = pro.idcotizacion
            pro.nombreproyecto = cot.nombreproyecto if cot else ''
            pro.fecha_cot_texto = cot.fecha.strftime('%d/%m/%Y') if cot and cot.fecha else ''
            pro.cotizacion_texto = ''
            if cot and cot.numcotizacion is not None:
                pro.cotizacion_texto = f"{int(cot.numcotizacion)}-{int(cot.numcorr or 0):03d}"
            pro.moneda_texto = pro.moneda or ''
            pro.dirproyecto_texto = cot.dirproyecto or '' if cot else ''
            pro.destino_texto = cot.destino or '' if cot else ''
            pro.fpago_texto = pro.fpago or ''
            pro.numconf_texto = (pro.numconf or '').strip()  # el escritorio lo guarda con largo fijo (nchar)
            pro.medioconf_texto = (pro.medioconf or '').strip()
            pro.fechaconf_texto = pro.fechaconf.strftime('%d/%m/%Y') if pro.fechaconf else ''
            pro.mandante_texto = cot.idcliente.razonsocial if cot and cot.idcliente else ''
            pro.mandante_comentario_texto = cot.idcliente.comentario if cot and cot.idcliente and cot.idcliente.comentario else ''
            pro.contacto_mandante_texto = cot.idcontacto.nombrecontacto if cot and cot.idcontacto else ''
            pro.email_mandante_texto = cot.idcontacto.email if cot and cot.idcontacto else ''
            pro.telefono_mandante_texto = cot.idcontacto.telefono if cot and cot.idcontacto else ''
            pro.cliente_texto = pro.idcliente.razonsocial if pro.idcliente else ''
            pro.rut_texto = ''
            if pro.idcliente and pro.idcliente.rut is not None and pro.idcliente.dvrut:
                pro.rut_texto = f"{int(pro.idcliente.rut)}-{pro.idcliente.dvrut}"
            pro.comentario_cliente_texto = pro.idcliente.comentario if pro.idcliente else ''
            pro.cliente_factura_texto = pro.idcontactofacturacion.nombrecontacto if pro.idcontactofacturacion else ''
            pro.cargo_factura_texto = pro.idcontactofacturacion.cargo if pro.idcontactofacturacion else ''
            pro.email_factura_texto = pro.idcontactofacturacion.email if pro.idcontactofacturacion else ''
            pro.telefono_factura_texto = pro.idcontactofacturacion.telefono if pro.idcontactofacturacion else ''
            pro.estado_texto = pro.estadoproyecto.nombre if pro.estadoproyecto else ''
            pro.estado_color = pro.estadoproyecto.color if pro.estadoproyecto else ''
            pro.estado_forcolor = pro.estadoproyecto.forcolor if pro.estadoproyecto else ''
            pro.region_texto = regiones.get(cot.codregion, '') if cot else ''
            fecha_ult_seg = ultimas_fechas_seg.get(str(pro.idproyecto))
            if fecha_ult_seg:
                pro.ultimoseg_texto = fecha_ult_seg.strftime('%d/%m/%Y')
            elif pro.fechaultseg:
                pro.ultimoseg_texto = pro.fechaultseg.strftime('%d/%m/%Y')
            elif pro.fecharegistro:
                pro.ultimoseg_texto = pro.fecharegistro.strftime('%d/%m/%Y')
            else:
                pro.ultimoseg_texto = ''
            pro.valor_texto = formatear_numero_cl(pro.valor)
            pro.valor_raw = pro.valor or 0
            pro.x_facturar_texto = format(saldos_por_facturar.get(int(pro.idproyecto), 100), '.2f')
            pro.conhes_texto = pro.conhes or ''
            pro.coneepp_texto = pro.coneepp or ''
            pro.conotro_texto = pro.conotro or ''
            pro.seg_texto = seguimientos.get(str(pro.idproyecto), '')
            pro.facturacion_lista = _facturacion_completa_proyecto(pro)

        contexto["proyecto"] = proyectos
        contexto["estados_proyecto"] = estados_proyecto
        contexto["mandantes"] = mandantes
        contexto["clientes"] = clientes_proyecto
        contexto["contactos_facturacion"] = contactos_facturacion
        contexto["monedas"] = monedas
        contexto["formas_pago"] = formas_pago
        contexto["medios_conf"] = medios_conf
        contexto["booleanos_si_no"] = booleanos_si_no
        contexto["valores_uf"] = valores_uf
        contexto["detalles_factura"] = DetalleFactura.objects.all().order_by('nombre')
        contexto["siguiente_num_factura"] = _siguiente_num_factura()
        contexto["mostrar_crear_factura"] = False
        contexto["filtro_estado"] = estado_id
        contexto["estados_marcados"] = estados_sel
        contexto["estados_defecto"] = ESTADOS_PROYECTO_ACTIVOS
        contexto["estado_anulado"] = ESTADO_PROYECTO_ANULADO
        contexto["estados_factura"] = _estados_factura_catalogo()
        contexto["puede_facturar"] = puede_facturar(self.request.user)
        contexto["filtro_mandante"] = mandante_id
        contexto["filtro_numero_proyecto"] = numero_proyecto

        contexto.update({
            "encabezado": "DUCTO",
            "titulo": "PROYECTOS SEGUIMIENTO",
            "menu": "Proyectos",
            "submenu": "Seguimiento de Proyectos",
        })
        return contexto


FECHAS_POR_ESTADO_PROYECTO = srv_proyectos.FECHAS_POR_ESTADO_PROYECTO


@login_required
@require_POST
def guardar_seguimiento_proyecto(request):
    idproyecto = request.POST.get('idproyecto')
    nuevo_estado_id = request.POST.get('nuevo_estado')
    comentario = (request.POST.get('comentario') or '').strip()
    filtros = {
        'estado': (request.POST.get('filtro_estado') or '').strip(),
        'mandante': (request.POST.get('filtro_mandante') or '').strip(),
        'numero_proyecto': (request.POST.get('filtro_numero_proyecto') or '').strip(),
    }

    def _redirigir_con_filtros(mensaje=None, nivel='success'):
        if mensaje:
            getattr(messages, nivel)(request, mensaje)
        return redirect(_url_seguimiento_con_filtros(filtros))

    if not idproyecto:
        return _redirigir_con_filtros('No se recibió el proyecto.', 'error')

    proyecto = get_object_or_404(srv_proyectos.todos(), pk=idproyecto)

    fecha_recordatorio = None
    if request.POST.get('es_recordatorio'):
        try:
            fecha_recordatorio = date.fromisoformat((request.POST.get('fecha_recordatorio') or '').strip())
        except ValueError:
            return _redirigir_con_filtros('Ingrese la fecha de recordatorio.', 'error')

    try:
        srv_proyectos.registrar_seguimiento(
            proyecto, request.user.username, comentario=comentario, nuevo_estado_id=nuevo_estado_id,
            fechas=request.POST, fecha_recordatorio=fecha_recordatorio)
    except srv_proyectos.ErrorValidacion as e:
        return _redirigir_con_filtros(str(e), 'error')

    return _redirigir_con_filtros('Seguimiento guardado correctamente.')


@login_required
@require_GET
def proyecto_comentarios(request, idproyecto):
    get_object_or_404(srv_proyectos.todos(), pk=idproyecto)
    return JsonResponse({'ok': True, 'comentarios': srv_proyectos.comentarios(idproyecto)})


@login_required
@require_POST
def proyecto_comentario_editar(request, idproyecto, idreg):
    """Como AC_Proyecto_SEG: cambia fecha, texto y recordatorio; el usuario queda como quien editó.
    Si el día no cambia se conserva la hora (el procedimiento recibe solo la fecha y la perdía)."""
    get_object_or_404(srv_proyectos.todos(), pk=idproyecto)
    comentario = (request.POST.get('comentario') or '').strip()
    if not comentario:
        return JsonResponse({'ok': False, 'message': 'El comentario no puede quedar vacío.'}, status=400)
    try:
        dia = date.fromisoformat(request.POST.get('fecha') or '')
        es_rec = request.POST.get('es_recordatorio') == '1'
        fecha_rec = date.fromisoformat(request.POST.get('fecha_recordatorio') or '') if es_rec else None
    except ValueError:
        return JsonResponse({'ok': False, 'message': 'Fecha inválida.'}, status=400)
    if not srv_proyectos.editar_comentario(idproyecto, idreg, comentario, dia, request.user.username,
                                           es_recordatorio=es_rec, fecha_recordatorio=fecha_rec):
        return JsonResponse({'ok': False, 'message': 'El comentario ya no existe.'}, status=404)
    return JsonResponse({'ok': True, 'comentarios': srv_proyectos.comentarios(idproyecto)})


@login_required
@require_POST
def proyecto_comentario_eliminar(request, idproyecto, idreg):
    get_object_or_404(srv_proyectos.todos(), pk=idproyecto)
    srv_proyectos.eliminar_comentario(idproyecto, idreg)
    return JsonResponse({'ok': True, 'comentarios': srv_proyectos.comentarios(idproyecto)})


@login_required
@require_POST
def guardar_datos_facturacion_proyecto(request):
    if not puede_facturar(request.user):
        return _sin_permiso_facturar(request)
    proyecto = get_object_or_404(srv_proyectos.todos(), pk=request.POST.get('idproyecto'))
    filtros = {
        'estado': (request.POST.get('filtro_estado') or '').strip(),
        'mandante': (request.POST.get('filtro_mandante') or '').strip(),
        'numero_proyecto': (request.POST.get('filtro_numero_proyecto') or '').strip(),
    }

    valor = request.POST.get('valor')
    fechaconf = request.POST.get('fechaconf')
    avanza_estado = srv_proyectos.guardar_datos_facturacion(
        proyecto, request.user.username,
        idcliente=request.POST.get('idcliente') or None,
        moneda=request.POST.get('moneda') or None,
        valor=float(valor) if valor not in (None, '') else None,
        medioconf=request.POST.get('medioconf') or None,
        fpago=request.POST.get('fpago') or None,
        numconf=request.POST.get('numconf') or None,
        fechaconf=datetime.strptime(fechaconf, '%d/%m/%Y').date() if fechaconf else None,
        conhes=request.POST.get('conhes') or None,
        coneepp=request.POST.get('coneepp') or None,
        conotro=request.POST.get('conotro') or None,
        idcontacto=request.POST.get('idcontactofacturacion') or None,
        email_contacto=(request.POST.get('emailcontactofacturacion') or '').strip(),
        comentario=(request.POST.get('comentario') or '').strip(),
    )

    messages.success(request, 'Datos de facturación guardados correctamente.' if avanza_estado else
                     'Datos de facturación guardados correctamente. El estado del proyecto no cambió.')
    return redirect(_url_seguimiento_con_filtros(filtros))


@login_required
@require_POST
def crear_factura_proyecto(request):
    if not puede_facturar(request.user):
        return _sin_permiso_facturar(request)
    proyecto = get_object_or_404(srv_proyectos.para_facturar(), pk=request.POST.get('idproyecto'))
    if proyecto.estadoproyecto_id == ESTADO_PROYECTO_ANULADO:
        msg = 'No se puede facturar un proyecto anulado.'
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'message': msg}, status=400)
        messages.error(request, msg)
        return redirect('seguimiento_proyectos')
    if not _facturacion_completa_proyecto(proyecto):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'message': 'El proyecto no tiene datos de facturación completos.'}, status=400)
        messages.error(request, 'El proyecto no tiene datos de facturación completos.')
        return redirect('seguimiento_proyectos')

    es_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    def _error(msg):
        if es_ajax:
            return JsonResponse({'ok': False, 'message': msg}, status=400)
        messages.error(request, msg)
        return redirect('seguimiento_proyectos')

    def _fecha_form(valor):
        """Acepta AAAA-MM-DD (campo date) o DD/MM/AAAA."""
        valor = (valor or '').strip()
        if not valor:
            return None
        try:
            return date.fromisoformat(valor)
        except ValueError:
            return _parse_date_ddmmyyyy(valor)

    def _numero(valor):
        texto = str(valor or '').strip()
        if ',' in texto:
            texto = texto.replace('.', '').replace(',', '.')
        try:
            return float(texto)
        except ValueError:
            return None

    # Mismas reglas y mismo procedimiento (GR_CreaFactura) que Creación de Facturas del sistema de escritorio
    from .servicios import facturas as srv_facturas
    from .servicios.facturas import DETALLES_FACTURA

    # idfactura > 0: modificar una factura del proyecto (solo Provisoria o Para Emitir, lo valida el servicio)
    try:
        idfactura = int(request.POST.get('idfactura') or 0)
    except ValueError:
        idfactura = 0
    try:
        numfactura_int = int(str(request.POST.get('numfactura') or '').strip())
    except ValueError:
        numfactura_int = 0
    if numfactura_int <= 0:
        return _error('N° de Factura no válido.')
    try:
        srv_facturas.validar_grabacion(proyecto, numfactura_int, idfactura)
    except srv_facturas.ErrorValidacion as e:
        return _error(str(e))
    if not proyecto.idcliente_id:
        return _error('No es posible crear la factura: falta la identificación del cliente.')

    fecha_emision = _fecha_form(request.POST.get('fechaemision'))
    if not fecha_emision:
        return _error('Debe ingresar la fecha de la factura.')

    porc = _numero(request.POST.get('porcfact'))
    if not porc or porc <= 0:
        return _error('% a Facturar debe ser mayor a cero.')

    detalle = (request.POST.get('detallefactura') or '').strip()
    if detalle.isdigit():  # compatibilidad con el formulario anterior, que enviaba un número
        idx = int(detalle) - 1
        detalle = DETALLES_FACTURA[idx] if 0 <= idx < len(DETALLES_FACTURA) else ''
    if not detalle:
        return _error('Debe ingresar el detalle a facturar.')

    if (proyecto.moneda or '') == 'UF':
        valor_uf = _numero(request.POST.get('valor_uf'))
        if not valor_uf or valor_uf <= 0:
            fecha_uf = _fecha_form(request.POST.get('fecha_uf')) or fecha_emision
            valor_uf = _valor_uf_por_fecha(fecha_uf)
        if not valor_uf or valor_uf <= 0:
            return _error('Valor U.F. debe ser mayor a cero: no hay UF para la fecha indicada.')
    else:
        valor_uf = 1.0

    # Estado con que nace la factura (como el "Cambiar Estado" de Creación de Facturas del escritorio)
    try:
        estado_factura = int(request.POST.get('estado_factura') or 0)
    except ValueError:
        estado_factura = -1
    if estado_factura not in srv_facturas.estados_dict():
        return _error('Estado de la factura no válido.')

    num_hes = (request.POST.get('numhes_eepp') or '').strip()[:srv_facturas.MAX_NUM_HES]
    fecha_hes = _fecha_form(request.POST.get('fechahes_eepp'))
    try:
        vencimiento = int(request.POST.get('vencimiento') or 30)
    except ValueError:
        vencimiento = 30

    try:
        with transaction.atomic():
            guardada = srv_facturas.grabar(
                proyecto, idfactura=idfactura, numfactura=numfactura_int, fecha_emision=fecha_emision,
                idcliente=proyecto.idcliente_id, porc=porc, valor_uf=float(valor_uf),
                detalle=detalle[:srv_facturas.MAX_DETALLE], num_hes=num_hes, fecha_hes=fecha_hes,
                # al crear, Provisoria (0) es el estado con que nace; al modificar se envía siempre el elegido
                nuevo_estado=estado_factura if idfactura else (estado_factura or None), vencimiento=vencimiento)
            if not idfactura:
                # Datos que el formulario web ya guardaba y el procedimiento no recibe
                srv_facturas.completar_datos_web(numfactura_int, proyecto, proyecto.idcontactofacturacion_id,
                                                 _ahora_santiago_naive())
    except srv_facturas.ErrorValidacion as e:
        return _error(str(e))

    mensaje = f'Factura {"modificada" if idfactura else "creada"}: {numfactura_int}'
    if es_ajax:
        return JsonResponse({'ok': True, 'message': mensaje, 'numfactura': str(numfactura_int),
                             'idfactura': guardada.idfactura if guardada else None})
    messages.success(request, mensaje)
    return redirect('seguimiento_proyectos')


class Vista2(LoginRequiredMixin,TemplateView):
    template_name = "proyvistobueno.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)

        try:
            contexto["proyecto"] = srv_proyectos.consulta_web(2)
        except DatabaseError as e:
            print("Error SQL:", e)
            contexto["proyecto"] = []
            contexto["error_sql"] = "No se pudo consultar la base de datos."

        contexto.update({
            "encabezado": "DUCTO",
            "titulo": "PROYECTOS CON VISTO BUENO",
            "menu": "Proyectos",
            "submenu": "Listado de Proyectos Con Visto Bueno",
        })
        return contexto


class Vista3(LoginRequiredMixin,TemplateView):
    template_name = "proydesarrollo.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)

        try:
            contexto["proyecto"] = srv_proyectos.consulta_web(3)
        except DatabaseError as e:
            print("Error SQL:", e)
            contexto["proyecto"] = []
            contexto["error_sql"] = "No se pudo consultar la base de datos."

        contexto.update({
            "encabezado": "DUCTO",
            "titulo": "PROYECTOS EN DESARROLLO",
            "menu": "Proyectos",
            "submenu": "Listado de Proyectos en Desarrollo",
        })
        return contexto


class VisorComentario(LoginRequiredMixin,DetailView):
    template_name = "seguimiento.html"

    def get(self, request, *args, **kwargs):
        pk = self.kwargs.get("pk")
        tabla = self.kwargs.get("tabla")

        nombre = {
            1: "Proyectos Terminados",
            2: "Proyectos con visto bueno",
            3: "Proyectos en Desarrollo",
        }.get(int(tabla), "Seguimiento")

        nompro = srv_proyectos.nombre(pk)
        rows = srv_proyectos.seguimiento_cronologico(pk)

        contexto = {
            "filas": rows,
            "idproyecto": pk,
            "titulo": nombre,
            "proyecto": nompro,
            "tabla": tabla,
        }
        return render(request, self.template_name, contexto)


@login_required
def guardacomentario(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    comentario = request.POST.get("comentario", "")
    idproyecto = request.POST.get("idproyecto")
    tabla = request.POST.get("tabla")

    srv_proyectos.agregar_comentario(idproyecto, comentario, request.user.username, 0)

    return redirect(f"{idproyecto}/{tabla}")


class ListaTipoEntrega(LoginRequiredMixin,ListView):
    model = TipoEntrega
    template_name = 'listatipoentrega.html'
    context_object_name = 'tipos_entrega'

    def get_queryset(self):
        return srv_tablas.tipos_entrega()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'encabezado': 'Tipos de Entrega',
            'menu': 'Parámetros',
            'submenu': 'Tipos de Entrega',
            'titulo': 'Tipos de Entrega',
        })
        return context


class ListaValorUF(LoginRequiredMixin, ListView):
    model = tValorUF
    template_name = 'listavaloruf.html'
    context_object_name = 'valores_uf'

    def get_queryset(self):
        return srv_tablas.valores_uf()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'encabezado': 'Valores UF',
            'menu': 'tablas',
            'submenu': 'Valores UF',
            'titulo': 'Valores UF',
        })
        return context


@login_required
def valor_uf_create(request):
    if request.method == 'POST':
        form = ValorUFForm(request.POST)
        if form.is_valid():
            srv_tablas.guardar(form)
            return redirect('lista-valor-uf')
    else:
        form = ValorUFForm()

    context = {
        'titulo': 'Crear valor UF',
        'encabezado': 'Crear valor UF',
        'submenu': 'Nuevo registro',
        'form': form,
        'texto_boton': 'Guardar registro',
    }
    return render(request, 'valoruf_form.html', context)


@login_required
def valor_uf_update(request, pk):
    valor_uf = srv_tablas.valor_uf(pk)
    if valor_uf is None:
        raise Http404('Valor UF no encontrado.')

    if request.method == 'POST':
        form = ValorUFForm(request.POST, instance=valor_uf)
        if form.is_valid():
            srv_tablas.guardar(form)
            return redirect('lista-valor-uf')
    else:
        form = ValorUFForm(instance=valor_uf)

    context = {
        'titulo': 'Modificar valor UF',
        'encabezado': 'Modificar valor UF',
        'submenu': 'Edicion de registro',
        'form': form,
        'valor_uf': valor_uf,
        'texto_boton': 'Guardar cambios',
    }
    return render(request, 'valoruf_form.html', context)


@login_required
def valor_uf_delete(request, pk):
    valor_uf = srv_tablas.valor_uf(pk)
    if valor_uf is None:
        raise Http404('Valor UF no encontrado.')

    if request.method == 'POST':
        srv_tablas.eliminar_valor_uf(valor_uf)
        return redirect('lista-valor-uf')

    context = {
        'titulo': 'Eliminar valor UF',
        'encabezado': 'Eliminar valor UF',
        'submenu': 'Confirmacion de eliminacion',
        'valor_uf': valor_uf,
    }
    return render(request, 'valoruf_confirm_delete.html', context)


@login_required
def tipo_entrega_create(request):
    if request.method == 'POST':
        form = TipoEntregaForm(request.POST)
        if form.is_valid():
            srv_tablas.guardar(form)
            return redirect('lista-tipo-entrega')
    else:
        form = TipoEntregaForm()

    context = {
        'titulo': 'Crear tipo de entrega',
        'encabezado': 'Crear tipo de entrega',
        'submenu': 'Nuevo registro',
        'form': form,
        'texto_boton': 'Guardar registro',
    }
    return render(request, 'tipoentrega_form.html', context)


@login_required
def tipo_entrega_update(request, pk):
    tipo_entrega = srv_tablas.tipo_entrega(pk)
    if tipo_entrega is None:
        raise Http404('Tipo de entrega no encontrado.')

    if request.method == 'POST':
        form = TipoEntregaForm(request.POST, instance=tipo_entrega)
        if form.is_valid():
            srv_tablas.guardar(form)
            return redirect('lista-tipo-entrega')
    else:
        form = TipoEntregaForm(instance=tipo_entrega)

    context = {
        'titulo': 'Modificar tipo de entrega',
        'encabezado': 'Modificar tipo de entrega',
        'submenu': 'Edicion de registro',
        'form': form,
        'tipo_entrega': tipo_entrega,
        'texto_boton': 'Guardar cambios',
    }
    return render(request, 'tipoentrega_form.html', context)


@login_required
def tipo_entrega_delete(request, pk):
    tipo_entrega = srv_tablas.tipo_entrega(pk)
    if tipo_entrega is None:
        raise Http404('Tipo de entrega no encontrado.')
    entregas_asociadas = srv_tablas.entregas_con_tipo(tipo_entrega)
    error_eliminacion = None

    if request.method == 'POST':
        try:
            srv_tablas.eliminar_tipo_entrega(tipo_entrega)
            return redirect('lista-tipo-entrega')
        except srv_tablas.NoSePuedeEliminar as e:
            error_eliminacion = str(e)

    context = {
        'titulo': 'Eliminar tipo de entrega',
        'encabezado': 'Eliminar tipo de entrega',
        'submenu': 'Confirmacion de eliminacion',
        'tipo_entrega': tipo_entrega,
        'entregas_asociadas': entregas_asociadas,
        'error_eliminacion': error_eliminacion,
    }
    return render(request, 'tipoentrega_confirm_delete.html', context)
    


def _completar_post_data_cliente(post_data, cliente=None, force_esprincipal=None):
    if force_esprincipal is not None:
        post_data['esprincipal'] = 'True' if force_esprincipal else 'False'

    if cliente and not post_data.get('idestadocliente') and cliente.idestadocliente_id:
        post_data['idestadocliente'] = str(cliente.idestadocliente_id)

    if cliente and not post_data.get('idcomppago') and cliente.idcomppago_id:
        post_data['idcomppago'] = str(cliente.idcomppago_id)

    return post_data

@login_required
def reporte_clientes(request):
    clientes = srv_clientes.listado_principales()
    if not clientes:
        return render(request, 'clientes/reporte_clientes.html', {
            'clientes': [],
            'titulo': 'Clientes principales',
            'encabezado': 'Clientes principales',
            'submenu': 'Lista de clientes principales',
            'url_modificar_name': 'cliente_principal_update',
            'mostrar_eliminar': False,
        })

    return render(request, 'clientes/reporte_clientes.html', {
        'clientes': clientes,
        'titulo': 'Clientes principales',
        'encabezado': 'Clientes principales',
        'submenu': 'Lista de clientes principales',
        'url_modificar_name': 'cliente_principal_update',
        'mostrar_eliminar': False,
    })


@login_required
def clientes_totales(request):
    clientes = srv_clientes.listado_total()

    return render(request, 'clientes/reporte_clientes.html', {
        'clientes': clientes,
        'titulo': 'Clientes totales',
        'encabezado': 'Clientes totales',
        'submenu': 'Lista total de clientes',
        'url_modificar_name': 'cliente_update',
        'mostrar_eliminar': True,
    })


@login_required
@transaction.atomic
def cliente_principal_update(request, pk):
    cliente = get_object_or_404(srv_clientes.principales_activos(), pk=pk)

    if request.method == 'POST':
        post_data = _completar_post_data_cliente(
            request.POST.copy(),
            cliente=cliente,
            force_esprincipal=True,
        )
        form = ClienteForm(
            post_data,
            instance=cliente,
            readonly_esprincipal=True,
            hide_parent_client=True,
            hide_categorias=True,
        )

        if form.is_valid():
            form.save()
            messages.success(request, 'Cliente principal modificado correctamente.')
            return redirect('reporte_clientes')

        messages.error(request, 'Corrige los errores del formulario.')
    else:
        form = ClienteForm(
            instance=cliente,
            readonly_esprincipal=True,
            hide_parent_client=True,
            hide_categorias=True,
        )

    context = {
        'titulo': 'Modificar cliente principal',
        'encabezado': 'Modificar cliente principal',
        'submenu': 'Edición de datos del cliente',
        'form': form,
        'mostrar_comentario': 'comentario' in form.fields,
        'volver_url_name': 'reporte_clientes',
    }
    return render(request, 'clientes/cliente_basic_form.html', context)


@login_required
@transaction.atomic
def cliente_create(request):
    if request.method == 'POST':
        form = ClienteForm(
            request.POST,
            hide_categorias=True,
            hide_comentario=True,
        )

        if form.is_valid():
            srv_clientes.crear(form.save(commit=False))
            messages.success(request, 'Cliente creado correctamente.')
            return redirect('clientes_totales')

        messages.error(request, 'Corrige los errores del formulario.')
    else:
        form = ClienteForm(
            hide_categorias=True,
            hide_comentario=True,
        )

    context = {
        'titulo': 'Ingresar cliente',
        'encabezado': 'Ingresar cliente',
        'submenu': 'Nuevo cliente',
        'form': form,
        'mostrar_comentario': 'comentario' in form.fields,
        'volver_url_name': 'clientes_totales',
    }
    return render(request, 'clientes/cliente_basic_form.html', context)


@login_required
@xframe_options_sameorigin
@transaction.atomic
def cliente_update(request, pk):
    cliente = get_object_or_404(srv_clientes.todos(), pk=pk)
    notas_pendientes = []
    # ?popup=1: se abre dentro de una ventana emergente (p. ej. desde Seguimiento Facturas)
    popup = request.GET.get('popup') == '1'

    if request.method == 'POST':
        post_data = _completar_post_data_cliente(request.POST.copy(), cliente=cliente)

        form = ClienteForm(post_data, instance=cliente)
        formset_contactos = ClienteContactoFormSet(
            post_data,
            instance=cliente,
            prefix='contactos'
        )
        form_nota = ClienteSeguimientoForm(post_data, prefix='nota')
        notas_pendientes = _notas_pendientes_desde_post(post_data, request.user)

        if form.is_valid() and formset_contactos.is_valid() and form_nota.is_valid():
            notas_a_guardar = list(post_data.getlist('notas_agregadas'))
            nota_directa = form_nota.cleaned_data.get('nota')
            if nota_directa:
                notas_a_guardar.append(nota_directa)
            cliente = srv_clientes.guardar_ficha(form, formset_contactos, request.user.username or str(request.user),
                                                 notas_a_guardar)

            if popup:
                return render(request, 'clientes/cliente_popup_guardado.html', {'cliente': cliente})
            messages.success(request, 'Cliente modificado correctamente.')
            return redirect('clientes_totales')

        messages.error(request, 'Corrige los errores del formulario.')

    else:
        form = ClienteForm(instance=cliente)
        formset_contactos = ClienteContactoFormSet(
            instance=cliente,
            prefix='contactos'
        )
        form_nota = ClienteSeguimientoForm(prefix='nota')

    notas_cliente = srv_clientes.notas(cliente)
    # Marca de rebote (correo inválido o bloqueado en un comunicado) junto al correo de cada contacto
    rebotes = srv_clientes.rebotes_por_texto(f.initial.get('email') or f['email'].value() for f in formset_contactos.forms)
    for f in formset_contactos.forms:
        f.rebotes = rebotes.get(f.initial.get('email') or f['email'].value(), [])

    context = {
        'titulo': 'Modificar cliente',
        'encabezado': 'Modificar cliente',
        'submenu': 'Edición de cliente',
        'form': form,
        'formset_contactos': formset_contactos,
        'form_nota': form_nota,
        'notas_cliente': notas_cliente,
        'notas_pendientes': notas_pendientes,
        'cliente': cliente,
        'volver_url_name': 'clientes_totales',
        'popup': popup,
    }
    return render(request, 'clientes/cliente_form.html', context)
    
@login_required
def cliente_delete(request, pk):
    cliente = get_object_or_404(srv_clientes.todos(), pk=pk)

    if request.method == 'POST':
        try:
            srv_clientes.eliminar(cliente)
        except srv_clientes.NoEncontrado:
            raise Http404('No existe el estado Eliminado.')

        messages.success(request, 'Cliente marcado como eliminado correctamente.')
        return redirect('clientes_totales')

    context = {
        'titulo': 'Eliminar cliente',
        'encabezado': 'Eliminar cliente',
        'submenu': 'Confirmación de eliminación',
        'cliente': cliente,
        'volver_url_name': 'clientes_totales',
    }
    return render(request, 'clientes/cliente_confirm_delete.html', context)
    
def formatear_numero_cl(valor):
    valor = valor or 0
    return f"{valor:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
@login_required
def proyectos_totales(request):
    # Estados con selección múltiple; sin ninguno marcado se muestran todos
    estados_sel = sorted({int(e) for e in request.GET.getlist('estado') if e.strip().isdigit()})
    estado_id = ','.join(str(e) for e in estados_sel)
    mandante_id = request.GET.get('mandante', '').strip()
    cliente_id = request.GET.get('cliente', '').strip()
    numero_proyecto = request.GET.get('numero_proyecto', '').strip()

    proyectos = srv_proyectos.buscar_reporte(estados_sel, mandante_id, cliente_id, numero_proyecto)

    estados_proyecto = srv_proyectos.estados_por_nombre()
    clientes_proyecto = srv_proyectos.clientes()
    regiones = srv_proyectos.regiones()

    for pro in proyectos:
        cot = pro.idcotizacion

        pro.nombreproyecto = cot.nombreproyecto if cot else ''
        pro.destino_texto = cot.destino or '' if cot else ''
        pro.pisos_texto = cot.pisos or '' if cot else ''
        pro.region_texto = regiones.get(cot.codregion, '') if cot else ''
        if cot:
            numcot = cot.numcotizacion or cot.idcotizacion
            numcorr = f"{int(cot.numcorr or 0):03d}"
            pro.numcotizacion_texto = f"{numcot}-{numcorr}"
        else:
            pro.numcotizacion_texto = ''
        pro.fechacotizacion = cot.fecha if cot else None
        pro.dirproyecto_texto = cot.dirproyecto or '' if cot else ''
        pro.edificios_texto = cot.edificios or 0 if cot else 0
        pro.valortotal_texto = cot.valortotal or 0 if cot else 0
        pro.moneda_cotizacion = cot.moneda or '' if cot else ''
        pro.mt2_texto = cot.mt2 or 0 if cot else 0

        pro.estado_proyecto_texto = pro.estadoproyecto.nombre if pro.estadoproyecto else ''
        pro.estado_proyecto_color = pro.estadoproyecto.color if pro.estadoproyecto else ''
        pro.estado_proyecto_forcolor = pro.estadoproyecto.forcolor if pro.estadoproyecto else ''

        pro.mandante_texto = cot.idcliente.razonsocial if cot and cot.idcliente else ''
        pro.cliente_texto = pro.idcliente.razonsocial if pro.idcliente else ''

        pro.fpago_texto = pro.fpago or ''
        pro.valor_texto = pro.valor or 0
        pro.numconf_texto = pro.numconf or ''
        pro.medioconf_texto = pro.medioconf or ''
        pro.quienadjudica_texto = pro.quienadjudica or ''
        pro.emailadjudicacion_texto = pro.emailadjudicacion or ''
        pro.conhes_texto = pro.conhes or ''
        pro.coneepp_texto = pro.coneepp or ''
        pro.conotro_texto = pro.conotro or ''
        pro.valor_formateado = formatear_numero_cl(pro.valor)

    context = {
        'titulo': 'Reporte de Proyectos',
        'encabezado': 'Reporte de Proyectos',
        'submenu': 'Reporte de Proyectos',
        'proyectos': proyectos,
        'estados_proyecto': estados_proyecto,
        'mandantes': clientes_proyecto,
        'clientes': clientes_proyecto,
        'filtro_estado': estado_id,
        'estados_marcados': estados_sel,
        'filtro_mandante': mandante_id,
        'filtro_cliente': cliente_id,
        'filtro_numero_proyecto': numero_proyecto,
    }
    return render(request, 'project/proyectos_totales.html', context)

# Calendario

def _to_local_naive(dt_str):
    if not dt_str:
        return None

    dt = parse_datetime(dt_str)
    if not dt:
        return None

    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
        dt = timezone.make_naive(dt, timezone.get_current_timezone())

    return dt


def _make_local_aware(dt_value):
    if not dt_value:
        return None

    if timezone.is_aware(dt_value):
        return dt_value

    return timezone.make_aware(dt_value, timezone.get_current_timezone())


@login_required
def agenda_clientes(request):
    clientes = srv_clientes.activos_por_nombre()

    hoy = timezone.localdate()
    hace_30_dias = hoy - timedelta(days=srv_clientes.DIAS_AGENDA_ATRAS)

    context = {
        'titulo': 'Agenda clientes',
        'encabezado': 'Agenda de clientes',
        'submenu': 'Calendario mensual de actividades comerciales',
        'clientes': clientes,
        'hoy_iso': hoy.isoformat(),
        'hace_30_dias_iso': hace_30_dias.isoformat(),
    }
    return render(request, 'clientes/agenda_clientes.html', context)


@login_required
@require_GET
def eventos_agenda_clientes(request):
    eventos = srv_clientes.eventos_agenda(_to_local_naive(request.GET.get('start')), _to_local_naive(request.GET.get('end')))
    return JsonResponse(eventos, safe=False)


@login_required
@require_POST
def crear_agenda_cliente(request):
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Datos inválidos.'
        }, status=400)

    try:
        agenda = srv_clientes.crear_evento(payload.get('fecha'), payload.get('idcliente'),
                                           (payload.get('descrip') or '').strip())
    except srv_clientes.ErrorValidacion as e:
        return JsonResponse({'ok': False, 'mensaje': str(e)}, status=400)
    except srv_clientes.NoEncontrado:
        raise Http404('Cliente no encontrado.')

    return JsonResponse({
        'ok': True,
        'mensaje': 'Evento de agenda creado correctamente.',
        'id': agenda.id,
    })


@login_required
@require_POST
def mover_agenda_cliente(request, agenda_id):
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Datos inválidos.'
        }, status=400)

    try:
        srv_clientes.mover_evento(agenda_id, payload.get('nueva_fecha'))
    except srv_clientes.ErrorValidacion as e:
        return JsonResponse({'ok': False, 'mensaje': str(e)}, status=400)
    except srv_clientes.NoEncontrado:
        raise Http404('Evento no encontrado.')

    return JsonResponse({
        'ok': True,
        'mensaje': 'Evento movido correctamente.'
    })

def _json_payload(request):
    try:
        return json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return None


def _respuesta_entrega(accion, mensaje_ok, **extra):
    """Ejecuta una acción del servicio de Entregas y arma la respuesta JSON de siempre."""
    try:
        resultado = accion()
    except srv_entregas.ErrorValidacion as e:
        return JsonResponse({'ok': False, 'mensaje': str(e)}, status=400)
    except srv_entregas.NoEncontrado as e:
        raise Http404(str(e))
    datos = {'ok': True, 'mensaje': mensaje_ok}
    datos.update({k: f(resultado) for k, f in extra.items()})
    return JsonResponse(datos)


def _datos_invalidos():
    return JsonResponse({'ok': False, 'mensaje': 'Datos inválidos.'}, status=400)


@login_required
def calendario_entregas_proyecto(request):
    context = {
        'titulo': 'Calendario de entregas',
        'encabezado': 'Calendario de entregas de proyectos',
        'submenu': 'Agenda mensual de entregas',
        'proyectos': srv_entregas.proyectos_para_calendario(),
        'tipos_entrega': srv_entregas.tipos_entrega(),
        'urgencias': srv_entregas.urgencias(),
        'tamanos': srv_entregas.tamanos(),
    }
    return render(request, 'calendario_entregas_proyecto.html', context)


@login_required
def eventos_calendario_entregas(request):
    eventos = srv_entregas.eventos_calendario(_to_local_naive(request.GET.get('start')),
                                              _to_local_naive(request.GET.get('end')))
    return JsonResponse(eventos, safe=False)


def obtener_rut_usuario(request):
    return request.user.username if request.user.is_authenticated else None


@login_required
@require_POST
def crear_entrega_proyecto(request):
    if not obtener_rut_usuario(request):
        return JsonResponse({'ok': False, 'mensaje': 'No fue posible determinar el usuario creador.'}, status=400)
    payload = _json_payload(request)
    if payload is None:
        return _datos_invalidos()
    return _respuesta_entrega(lambda: srv_entregas.crear(obtener_rut_usuario(request), payload),
                              'Entrega creada correctamente.', identrega=lambda e: e.identrega)


@login_required
@require_GET
def usuarios_desarrollo_activos(request):
    return JsonResponse(srv_entregas.usuarios_activos(), safe=False)


@login_required
@require_GET
def usuarios_revision_activos(request):
    return JsonResponse({'ok': True, 'usuarios': srv_entregas.usuarios_activos()})


@login_required
@require_POST
def anular_entrega(request, identrega):
    return _respuesta_entrega(lambda: srv_entregas.anular(identrega, obtener_rut_usuario(request)),
                              'Entrega anulada correctamente.')


@login_required
@require_POST
def asignar_entrega_desarrollo(request, identrega):
    payload = _json_payload(request)
    if payload is None:
        return _datos_invalidos()
    return _respuesta_entrega(
        lambda: srv_entregas.enviar_a_desarrollo(identrega, request.user.username, payload.get('rut_usuario')),
        'Entrega enviada a desarrollo correctamente.')


@login_required
@require_POST
def mover_entrega_calendario(request, identrega):
    if not obtener_rut_usuario(request):
        return JsonResponse({'ok': False, 'mensaje': 'No fue posible determinar el usuario.'}, status=400)
    payload = _json_payload(request)
    if payload is None:
        return _datos_invalidos()
    return _respuesta_entrega(
        lambda: srv_entregas.mover(identrega, obtener_rut_usuario(request), payload.get('nueva_fecha')),
        'Fecha de calendario actualizada correctamente.')


def _listado_entregas(request, plantilla, titulo, encabezado, submenu, estados=None, **extra):
    context = {
        'titulo': titulo,
        'encabezado': encabezado,
        'submenu': submenu,
        'entregas': srv_entregas.listado(estados),
        **extra,
    }
    return render(request, plantilla, context)


@login_required
def entregas_general(request):
    return _listado_entregas(request, 'entregas_general.html', 'Entregas General', 'Entregas General',
                             'Listado general de entregas')


@login_required
def entregas_revision(request):
    return _listado_entregas(request, 'entregas_revision.html', 'Entregas Revisión', 'Entregas en Revisión',
                             'Listado entregas en revisión', [srv_entregas.ESTADO_REVISION],
                             tipos_observacion=srv_entregas.tipos_observacion(),
                             calificaciones=srv_entregas.calificaciones())


@login_required
def entregas_desarrollo(request):
    return _listado_entregas(request, 'entregas_desarrollo.html', 'Entregas Desarrollo', 'Entregas en Desarrollo',
                             'Listado entregas en desarrollo',
                             [srv_entregas.ESTADO_DESARROLLO, srv_entregas.ESTADO_CORRECCIONES])


@login_required
@require_POST
def enviar_entrega_revision(request, identrega):
    payload = _json_payload(request)
    if payload is None:
        return _datos_invalidos()
    return _respuesta_entrega(
        lambda: srv_entregas.enviar_a_revision(identrega, request.user.username, payload.get('rut_usuario')),
        'Entrega enviada a revisión correctamente.')


@login_required
def visor_entrega(request, identrega):
    try:
        return JsonResponse(srv_entregas.visor(identrega))
    except srv_entregas.NoEncontrado as e:
        raise Http404(str(e))


@login_required
@require_GET
def listar_observaciones_catalogo(request):
    return JsonResponse({'ok': True, 'observaciones': srv_entregas.observaciones_catalogo()})


@login_required
@require_POST
def agregar_observacion_entrega(request, identrega):
    try:
        agregada = srv_entregas.agregar_observacion(identrega, request.POST.get('idobservacion'), request.user)
    except srv_entregas.ErrorValidacion as e:
        return JsonResponse({'ok': False, 'mensaje': str(e)}, status=400)
    except srv_entregas.NoEncontrado as e:
        raise Http404(str(e))
    return JsonResponse({'ok': True, 'mensaje': 'Observación agregada correctamente.' if agregada
                         else 'La observación ya estaba agregada a esta entrega.'})


@login_required
@require_POST
def crear_observacion_catalogo(request, identrega):
    return _respuesta_entrega(
        lambda: srv_entregas.crear_observacion(identrega, request.POST.get('idtipoobservacion'),
                                               request.POST.get('idcalificacion'),
                                               (request.POST.get('descripcion') or '').strip(), request.user),
        'Nueva observación creada y asignada a la entrega.', idobservacion=lambda o: o.id)


@login_required
@require_POST
def entrega_revision_enviar_desarrollo(request, identrega):
    return _respuesta_entrega(lambda: srv_entregas.devolver_a_desarrollo(identrega, request.user.username),
                              'Entrega enviada a correcciones correctamente.')


@login_required
@require_POST
def entrega_revision_ok(request, identrega):
    return _respuesta_entrega(lambda: srv_entregas.marcar_entregada(identrega, request.user.username),
                              'Entrega marcada como OK correctamente.')
