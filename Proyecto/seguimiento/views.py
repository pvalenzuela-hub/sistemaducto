import json
import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlencode
from datetime import timezone as dt_timezone
from django.shortcuts import render, redirect
from .models import *
import pyodbc
from django.conf import settings
from django.views.generic import TemplateView, ListView, DetailView
from django.views.decorators.http import require_POST, require_GET
from django.http import HttpResponseNotAllowed, HttpResponse
from collections import defaultdict
from datetime import date

from django.db.models import Max, Prefetch, F, OuterRef, Subquery, Count, IntegerField, CharField, Value, Q, Exists, Sum
from django.db import transaction, IntegrityError
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from datetime import timedelta, datetime, time
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.contrib import messages
from django.template.loader import render_to_string
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from .forms import ClienteForm, ClienteContactoFormSet, ClienteSeguimientoForm, CotizacionForm, TipoEntregaForm




ESTADO_ENTREGA_NUEVA = 1
ESTADO_ENTREGA_DESARROLLO = 2
ESTADO_ENTREGA_CORRECCIONES = 3
ESTADO_ENTREGA_REVISION = 4
ESTADO_ENTREGA_ENTREGADO = 5
ESTADO_ENTREGA_NULA = 6

FECHA_MINIMA_COTIZACION = None
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

ESTADOS_COTIZACION = {
    0: 'Borrador',
    1: 'Activa',
    2: 'Cerrada',
    3: 'Anulada',
}


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


def _estado_cotizacion_class(nombre):
    texto = (nombre or '').lower()
    if 'aprob' in texto:
        return 'estado-cotizacion-aprobada'
    if 'esper' in texto:
        return 'estado-cotizacion-espera'
    if 'cerr' in texto or 'inact' in texto:
        return 'estado-cotizacion-cerrada'
    return 'estado-cotizacion-pendiente'

User = get_user_model()


def _nombre_visible_usuario_actual(usuario):
    nombre = usuario.get_full_name().strip()
    if nombre:
        return nombre

    username = getattr(usuario, 'username', '') or str(usuario)
    return username.strip()


def _nombre_visible_usuario_legacy(usuario):
    return (
        (usuario.nombrecompleto or '').strip()
        or (usuario.username or '').strip()
        or (usuario.email or '').strip()
        or (usuario.id or '').strip()
    )


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
    proyecto_principal = Proyecto.objects.filter(idcotizacion=OuterRef('pk')).order_by('idproyecto')

    qs = (
        Cotizacion.objects
        .select_related('idcliente', 'idcontacto')
        .annotate(
            tiene_proyecto=Exists(Proyecto.objects.filter(idcotizacion=OuterRef('pk'))),
            proyecto_id=Subquery(proyecto_principal.values('idproyecto')[:1]),
            estadocotizacion_texto=F('estadocotizacion__nombre'),
        )
        .order_by('-fecha', '-numcotizacion', '-numcorr')
    )

    numero = (request.GET.get('numero') or '').strip()
    proyecto = (request.GET.get('proyecto') or '').strip()
    mandante = (request.GET.get('mandante') or '').strip()
    fecha_desde = (request.GET.get('fecha_desde') or '').strip()
    fecha_hasta = (request.GET.get('fecha_hasta') or '').strip()

    if not any([numero, proyecto, mandante, fecha_desde, fecha_hasta]):
        fecha_desde = (timezone.localdate() - timedelta(days=30)).isoformat()

    clear_params = {'fecha_desde': fecha_desde}

    if numero:
        if numero.isdigit():
            numero_int = int(numero)
            qs = qs.filter(
                Q(idcotizacion=numero_int) |
                Q(numcotizacion=numero_int) |
                Q(numcorr=numero_int)
            )
        else:
            qs = qs.filter(Q(numcorr__icontains=numero))
    if proyecto:
        qs = qs.filter(nombreproyecto__icontains=proyecto)
    if mandante:
        qs = qs.filter(idcliente__razonsocial__icontains=mandante)
    if fecha_desde:
        qs = qs.filter(fecha__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha__lte=fecha_hasta)

    cotizaciones = []
    for cotizacion in qs:
        cotizacion.estado_texto = ESTADOS_COTIZACION.get(cotizacion.estado, 'Sin estado')
        cotizacion.estadocotizacion_texto = cotizacion.estadocotizacion_texto or 'Sin estado'
        cotizacion.estadocotizacion_class = _estado_cotizacion_class(cotizacion.estadocotizacion_texto)
        cotizacion.mandante_texto = cotizacion.idcliente.razonsocial if cotizacion.idcliente else ''
        cotizacion.contacto_texto = cotizacion.idcontacto.nombrecontacto if cotizacion.idcontacto else ''
        cotizacion.proyecto_texto = cotizacion.nombreproyecto or (str(cotizacion.proyecto_id) if cotizacion.tiene_proyecto and cotizacion.proyecto_id else '')
        cotizacion.valor_total_texto = cotizacion.valortotal or 0
        cotizacion.es_activa_texto = 'SI' if cotizacion.esactiva else 'NO'
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


@login_required
def cotizaciones_ingreso(request):
    if request.method == 'POST':
        form = CotizacionForm(request.POST)
        if form.is_valid():
            cotizacion = form.save(commit=False)
            cotizacion.fecha = form.cleaned_data.get('fecha') or timezone.localdate()
            next_num = (Cotizacion.objects.aggregate(mx=Max('numcotizacion'))['mx'] or 0) + 1
            cotizacion.numcotizacion = cotizacion.numcotizacion or next_num
            cotizacion.numcorr = 0
            cotizacion.estado = 0
            cotizacion.esactiva = True
            cotizacion.idusuario = (request.user.username or '')[:15]
            ahora_local = _ahora_santiago_naive()
            cotizacion.fecharegistro = ahora_local
            cotizacion.fechaact = ahora_local
            cotizacion.save()
            _guardar_items_cotizacion(cotizacion, request.POST.get('items_json', ''))
            _guardar_formapago_cotizacion(cotizacion, request.POST.get('formapago_json', ''))
            _guardar_notas_cotizacion(cotizacion, request.POST.get('notas_json', ''))
            _actualizar_valortotal_cotizacion(cotizacion)
            messages.success(request, 'Cotización creada correctamente.')
            return redirect('cotizacion_detalle', pk=cotizacion.pk)
    else:
        form = CotizacionForm(initial={'fecha': timezone.localdate()})

    formapago_catalogo = list(TFpago.objects.filter(regionrm=0).order_by('codfp').values('concepto'))

    return render(request, 'cotizaciones/form.html', {
        'titulo': 'Ingreso de Cotizaciones',
        'encabezado': 'Ingreso de Cotizaciones',
        'submenu': 'Alta de cotización nueva',
        'volver_url_name': 'cotizaciones_home',
        'accion_nombre': 'Búsqueda de Cotizaciones',
        'accion_url_name': 'cotizaciones_busqueda',
        'form': form,
        'modo': 'crear',
        'items_guardados': [],
        'formapago_catalogo': formapago_catalogo,
    })


@login_required
def cotizacion_editar(request, pk):
    cotizacion = get_object_or_404(Cotizacion.objects.select_related('estadocotizacion'), pk=pk)
    notas_seleccionadas = list(
        CotizacionNota.objects.filter(idcotizacion=cotizacion).values_list('idnota_id', flat=True)
    )
    formapago_items = list(
        CotizacionFpago.objects.filter(idcotizacion=cotizacion).values('linea', 'concepto').order_by('linea')
    )
    items_guardados = list(
        CotizacionValor.objects.filter(idcotizacion=cotizacion).values('item', 'glosa', 'valor', 'opcional').order_by('item')
    )
    if request.method == 'POST':
        form = CotizacionForm(request.POST, instance=cotizacion)
        if form.is_valid():
            cotizacion = form.save(commit=False)
            cotizacion.fecha = form.cleaned_data.get('fecha') or cotizacion.fecha
            cotizacion.fechaact = _ahora_santiago_naive()
            cotizacion.save()
            _guardar_items_cotizacion(cotizacion, request.POST.get('items_json', ''))
            _guardar_formapago_cotizacion(cotizacion, request.POST.get('formapago_json', ''))
            _guardar_notas_cotizacion(cotizacion, request.POST.get('notas_json', ''))
            _actualizar_valortotal_cotizacion(cotizacion)
            messages.success(request, 'Cotización actualizada correctamente.')
            return redirect('cotizacion_detalle', pk=cotizacion.pk)
    else:
        form = CotizacionForm(instance=cotizacion, initial={'fecha': cotizacion.fecha})

    formapago_catalogo = list(TFpago.objects.filter(regionrm=0).order_by('codfp').values('concepto'))

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
        'notas_seleccionadas': notas_seleccionadas,
        'formapago_items': formapago_items,
        'items_guardados': items_guardados,
        'formapago_catalogo': formapago_catalogo,
    })


@login_required
@transaction.atomic
def cotizacion_versionar(request, pk):
    base = get_object_or_404(Cotizacion, pk=pk)

    nuevo_corr = (base.numcorr or 0) + 1

    nueva = Cotizacion(
        numcotizacion=base.numcotizacion,
        numcorr=nuevo_corr,
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
        idusuario=(request.user.username or '')[:15],
        fechaact=_ahora_santiago_naive(),
        esactiva=True,
        mt2=base.mt2,
        fecharegistro=_ahora_santiago_naive(),
    )
    nueva.save()
    _copiar_detalle_cotizacion(base, nueva)
    _actualizar_valortotal_cotizacion(nueva)

    messages.success(request, 'Nueva versión creada correctamente.')
    return redirect('cotizacion_detalle', pk=nueva.pk)


@login_required
def cotizacion_detalle(request, pk):
    cotizacion = get_object_or_404(Cotizacion.objects.select_related('idcliente', 'idcontacto', 'estadocotizacion'), pk=pk)
    proyectos = list(Proyecto.objects.filter(idcotizacion=cotizacion).order_by('idproyecto'))
    valores = list(CotizacionValor.objects.filter(idcotizacion=cotizacion).order_by('item'))
    formas_pago = list(CotizacionFpago.objects.filter(idcotizacion=cotizacion).order_by('linea'))
    notas = list(
        CotizacionNota.objects.select_related('idnota').filter(idcotizacion=cotizacion).order_by('idcotizacionnota')
    )

    cotizacion.estado_texto = ESTADOS_COTIZACION.get(cotizacion.estado, 'Sin estado')
    cotizacion.estadocotizacion_texto = cotizacion.estadocotizacion.nombre if cotizacion.estadocotizacion_id else 'Sin estado'
    cotizacion.estadocotizacion_class = _estado_cotizacion_class(cotizacion.estadocotizacion_texto)
    cotizacion.mandante_texto = cotizacion.idcliente.razonsocial if cotizacion.idcliente else ''
    cotizacion.contacto_texto = cotizacion.idcontacto.nombrecontacto if cotizacion.idcontacto else ''
    cotizacion.telefono_contacto = cotizacion.idcontacto.telefono if cotizacion.idcontacto else ''
    cotizacion.email_contacto = cotizacion.idcontacto.email if cotizacion.idcontacto else ''
    cotizacion.region_texto = ''
    if cotizacion.codregion:
        region = Tregion.objects.filter(codregion=cotizacion.codregion).only('descrip').first()
        cotizacion.region_texto = region.descrip if region else ''
    cotizacion.estado_visual = _cotizacion_estado_visual(cotizacion)
    cotizacion.total_proyecto = sum(float(v.valor or 0) for v in valores if (v.opcional or 'N') != 'S')
    cotizacion.total_con_opcional = sum(float(v.valor or 0) for v in valores)

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


@login_required
def cotizacion_reporte(request, pk):
    cotizacion = get_object_or_404(Cotizacion.objects.select_related('idcliente', 'idcontacto', 'estadocotizacion'), pk=pk)
    proyectos = list(Proyecto.objects.filter(idcotizacion=cotizacion).order_by('idproyecto'))
    valores = list(CotizacionValor.objects.filter(idcotizacion=cotizacion).order_by('item'))
    formas_pago = list(CotizacionFpago.objects.filter(idcotizacion=cotizacion).order_by('linea'))
    notas = list(
        CotizacionNota.objects.select_related('idnota').filter(idcotizacion=cotizacion).order_by('idcotizacionnota')
    )

    cotizacion.estado_texto = ESTADOS_COTIZACION.get(cotizacion.estado, 'Sin estado')
    cotizacion.estadocotizacion_texto = cotizacion.estadocotizacion.nombre if cotizacion.estadocotizacion_id else 'Sin estado'
    cotizacion.estadocotizacion_class = _estado_cotizacion_class(cotizacion.estadocotizacion_texto)
    cotizacion.mandante_texto = cotizacion.idcliente.razonsocial if cotizacion.idcliente else ''
    cotizacion.contacto_texto = cotizacion.idcontacto.nombrecontacto if cotizacion.idcontacto else ''
    cotizacion.telefono_contacto = cotizacion.idcontacto.telefono if cotizacion.idcontacto else ''
    cotizacion.email_contacto = cotizacion.idcontacto.email if cotizacion.idcontacto else ''
    cotizacion.region_texto = ''
    if cotizacion.codregion:
        region = Tregion.objects.filter(codregion=cotizacion.codregion).only('descrip').first()
        cotizacion.region_texto = region.descrip if region else ''
    cotizacion.estado_visual = _cotizacion_estado_visual(cotizacion)
    cotizacion.total_proyecto = sum(float(v.valor or 0) for v in valores if (v.opcional or 'N') != 'S')
    cotizacion.total_con_opcional = sum(float(v.valor or 0) for v in valores)

    return render(request, 'cotizaciones/reporte.html', {
        'titulo': f'Reporte Cotización {cotizacion.numcotizacion or cotizacion.idcotizacion}',
        'cotizacion': cotizacion,
        'proyectos': proyectos,
        'valores': valores,
        'formas_pago': formas_pago,
        'notas': notas,
    })


def _cotizacion_pdf_asset_prefix():
    static_dir = settings.BASE_DIR / 'static'
    return static_dir.as_uri().rstrip('/')


def _cotizacion_html_para_pdf(request, context):
    html = render_to_string('cotizaciones/reporte_pdf.html', context, request=request)
    prefix = _cotizacion_pdf_asset_prefix()
    html = html.replace('/static/', f'{prefix}/')
    html = html.replace('href="/static/', f'href="{prefix}/')
    return html


def _render_pdf_con_wkhtmltopdf(html):
    wkhtmltopdf = shutil.which('wkhtmltopdf')
    if not wkhtmltopdf:
        return None
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, 'cotizacion.html')
        pdf_path = os.path.join(tmpdir, 'cotizacion.pdf')
        with open(html_path, 'w', encoding='utf-8') as fh:
            fh.write(html)
        input_url = f'file://{html_path}'
        proc = subprocess.run(
            [
                wkhtmltopdf,
                '--print-media-type',
                '--enable-local-file-access',
                '--margin-top', '8mm',
                '--margin-right', '8mm',
                '--margin-bottom', '8mm',
                '--margin-left', '8mm',
                input_url,
                pdf_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0 or not os.path.exists(pdf_path):
            raise RuntimeError((proc.stderr or proc.stdout or 'wkhtmltopdf failed').strip())
        with open(pdf_path, 'rb') as fh:
            return fh.read()


@login_required
def cotizacion_reporte_pdf(request, pk):
    cotizacion = get_object_or_404(Cotizacion.objects.select_related('idcliente', 'idcontacto'), pk=pk)
    proyectos = list(Proyecto.objects.filter(idcotizacion=cotizacion).order_by('idproyecto'))
    valores = list(CotizacionValor.objects.filter(idcotizacion=cotizacion).order_by('item'))
    formas_pago = list(CotizacionFpago.objects.filter(idcotizacion=cotizacion).order_by('linea'))
    notas = list(CotizacionNota.objects.select_related('idnota').filter(idcotizacion=cotizacion).order_by('idcotizacionnota'))

    cotizacion.estado_texto = ESTADOS_COTIZACION.get(cotizacion.estado, 'Sin estado')
    cotizacion.estadocotizacion_texto = cotizacion.estadocotizacion.nombre if cotizacion.estadocotizacion_id else 'Sin estado'
    cotizacion.estadocotizacion_class = _estado_cotizacion_class(cotizacion.estadocotizacion_texto)
    cotizacion.mandante_texto = cotizacion.idcliente.razonsocial if cotizacion.idcliente else ''
    cotizacion.contacto_texto = cotizacion.idcontacto.nombrecontacto if cotizacion.idcontacto else ''
    cotizacion.telefono_contacto = cotizacion.idcontacto.telefono if cotizacion.idcontacto else ''
    cotizacion.email_contacto = cotizacion.idcontacto.email if cotizacion.idcontacto else ''
    cotizacion.region_texto = ''
    if cotizacion.codregion:
        region = Tregion.objects.filter(codregion=cotizacion.codregion).only('descrip').first()
        cotizacion.region_texto = region.descrip if region else ''
    cotizacion.estado_visual = _cotizacion_estado_visual(cotizacion)
    cotizacion.total_proyecto = sum(float(v.valor or 0) for v in valores if (v.opcional or 'N') != 'S')
    cotizacion.total_con_opcional = sum(float(v.valor or 0) for v in valores)

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
        pdf_bytes = _render_pdf_con_wkhtmltopdf(html)
    except Exception as exc:
        return render(request, 'cotizaciones/reporte.html', {**context, 'pdf_error': str(exc)})

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Reporte_Cotizacion_{cotizacion.numcotizacion or cotizacion.idcotizacion}.pdf"'
    return response


@login_required
@require_GET
def api_cotizaciones_mandantes(request):
    term = (request.GET.get('term') or '').strip()
    qs = Cliente.objects.order_by('razonsocial')
    if term:
        qs = qs.filter(razonsocial__icontains=term)
    data = [
        {
            'id': c.idcliente,
            'text': c.razonsocial or f'Cliente {c.idcliente}',
            'direccion': c.direccion or '',
            'telefono': c.telefono or '',
        }
        for c in qs[:20]
    ]
    return JsonResponse({'results': data})


@login_required
@require_GET
def api_cotizaciones_mandante_detalle(request, pk):
    cliente = Cliente.objects.filter(idcliente=pk).only('idcliente', 'razonsocial', 'direccion', 'telefono').first()
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

    qs = Clientecontacto.objects.select_related('idcliente').order_by('nombrecontacto', 'idcontacto')
    if cliente_id.isdigit():
        qs = qs.filter(idcliente_id=int(cliente_id))
    if term:
        qs = qs.filter(nombrecontacto__icontains=term)

    data = [
        {
            'id': contacto.idcontacto,
            'text': contacto.nombrecontacto or f'Contacto {contacto.idcontacto}',
            'cliente_id': contacto.idcliente_id,
            'cargo': contacto.cargo or '',
            'telefono': contacto.telefono or '',
            'email': contacto.email or '',
        }
        for contacto in qs[:20]
    ]
    return JsonResponse({'results': data})


@login_required
@require_GET
def api_cotizaciones_contacto_detalle(request, pk):
    contacto = Clientecontacto.objects.filter(idcontacto=pk).only(
        'idcontacto', 'nombrecontacto', 'cargo', 'telefono', 'email', 'idcliente_id'
    ).first()
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
    qs = ItemCotizacion.objects.all().order_by('iditem')
    data = [{'id': item.iditem, 'text': item.nombre} for item in qs]
    return JsonResponse({'results': data})


@login_required
@require_GET
def api_cotizaciones_notas(request):
    qs = NotaCotizacion.objects.all().order_by('idnota')
    data = [{'id': nota.idnota, 'text': nota.nota} for nota in qs]
    return JsonResponse({'results': data})


@login_required
@require_GET
def api_cotizaciones_formapago(request):
    qs = TFpago.objects.filter(regionrm=0).order_by('codfp')
    data = [{'id': fp.idfpago, 'text': fp.concepto} for fp in qs]
    return JsonResponse({'results': data})


def _resolver_id_usuario_nota(username):
    identificador = (username or '').strip()
    if not identificador:
        return ''

    usuario_legacy = AspNetUser.objects.filter(username=identificador).only('id').first()
    if usuario_legacy and usuario_legacy.id:
        return usuario_legacy.id

    return identificador


def _fecha_cliente_seg_guardado():
    # Cliente_Seg es una tabla legacy donde la hora se maneja como valor local
    # sin conversión real de zona horaria. Guardamos la hora local con marca UTC
    # para conservar el mismo reloj visible al leerla después.
    return timezone.localtime(timezone.now()).replace(tzinfo=dt_timezone.utc)


def _ahora_santiago_naive():
    return timezone.localtime(timezone.now()).replace(tzinfo=None)


def _guardar_notas_cotizacion(cotizacion, items_json):
    try:
        datos = json.loads(items_json or '[]')
    except json.JSONDecodeError:
        datos = []

    ids_notas = []
    for dato in datos:
        if dato.get('selected'):
            try:
                ids_notas.append(int(dato.get('id')))
            except (TypeError, ValueError):
                continue

    CotizacionNota.objects.filter(idcotizacion=cotizacion).delete()
    if not ids_notas:
        return

    notas = NotaCotizacion.objects.filter(idnota__in=ids_notas)
    for nota in notas:
        CotizacionNota.objects.create(idcotizacion=cotizacion, idnota=nota)


def _guardar_formapago_cotizacion(cotizacion, formapago_json):
    try:
        datos = json.loads(formapago_json or '[]')
    except json.JSONDecodeError:
        datos = []

    conceptos = []
    for dato in datos:
        if not isinstance(dato, dict):
            continue
        concepto = (dato.get('concepto') or '').strip()
        if concepto:
            conceptos.append(concepto)

    CotizacionFpago.objects.filter(idcotizacion=cotizacion).delete()
    for idx, concepto in enumerate(conceptos, start=1):
        CotizacionFpago.objects.create(idcotizacion=cotizacion, linea=idx, concepto=concepto)


def _actualizar_valortotal_cotizacion(cotizacion):
    total = CotizacionValor.objects.filter(idcotizacion=cotizacion).aggregate(total=Sum('valor'))['total'] or 0
    Cotizacion.objects.filter(pk=cotizacion.pk).update(valortotal=total)


def _guardar_items_cotizacion(cotizacion, items_json):
    try:
        datos = json.loads(items_json or '[]')
    except json.JSONDecodeError:
        datos = []

    items = []
    for dato in datos:
        if not isinstance(dato, dict):
            continue
        try:
            item_num = int(dato.get('item'))
        except (TypeError, ValueError):
            continue
        glosa = (dato.get('glosa') or '').strip()
        if not glosa:
            continue
        try:
            valor = float(dato.get('valor') or 0)
        except (TypeError, ValueError):
            valor = 0
        opcional = 'S' if dato.get('opcional') == 'S' else 'N'
        items.append((item_num, glosa, valor, opcional))

    CotizacionValor.objects.filter(idcotizacion=cotizacion).delete()
    for item_num, glosa, valor, opcional in items:
        CotizacionValor.objects.create(
            idcotizacion=cotizacion,
            item=item_num,
            glosa=glosa,
            valor=valor,
            opcional=opcional,
        )


def _copiar_detalle_cotizacion(origen, destino):
    for nota in CotizacionNota.objects.filter(idcotizacion=origen).select_related('idnota').order_by('idcotizacionnota'):
        CotizacionNota.objects.create(idcotizacion=destino, idnota=nota.idnota)

    for fp in CotizacionFpago.objects.filter(idcotizacion=origen).order_by('linea'):
        CotizacionFpago.objects.create(idcotizacion=destino, linea=fp.linea, concepto=fp.concepto)

    for valor in CotizacionValor.objects.filter(idcotizacion=origen).order_by('item'):
        CotizacionValor.objects.create(
            idcotizacion=destino,
            item=valor.item,
            glosa=valor.glosa,
            valor=valor.valor,
            opcional=valor.opcional,
        )


def _fecha_cliente_seg_mostrada(fecha):
    if not fecha:
        return None

    if timezone.is_aware(fecha):
        return fecha.replace(tzinfo=None)

    return fecha


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


def _asignar_nombre_usuario_notas(notas):
    identificadores = {
        (nota.iduser or '').strip()
        for nota in notas
        if (nota.iduser or '').strip()
    }

    usuarios_aspnet = list(
        AspNetUser.objects.filter(
            Q(id__in=identificadores) | Q(username__in=identificadores)
        )
    )
    usuarios_aspnet_por_id = {
        usuario.id: _nombre_visible_usuario_legacy(usuario)
        for usuario in usuarios_aspnet
        if usuario.id
    }
    usuarios_aspnet_por_username = {
        usuario.username: _nombre_visible_usuario_legacy(usuario)
        for usuario in usuarios_aspnet
        if usuario.username
    }

    usuarios_auth = {
        usuario.username: usuario
        for usuario in User.objects.filter(username__in=identificadores)
    }
    usuarios_legacy = {
        usuario.username: (usuario.nombreusuario or '').strip()
        for usuario in tusuario.objects.filter(username__in=identificadores)
        if usuario.username
    }

    for nota in notas:
        identificador = (nota.iduser or '').strip()
        nombre_aspnet = usuarios_aspnet_por_id.get(identificador) or usuarios_aspnet_por_username.get(identificador)
        usuario_auth = usuarios_auth.get(identificador)
        nombre_auth = usuario_auth.get_full_name().strip() if usuario_auth else ''

        if nombre_aspnet:
            nota.usuario_nombre = nombre_aspnet
        elif nombre_auth:
            nota.usuario_nombre = nombre_auth
        elif usuarios_legacy.get(identificador):
            nota.usuario_nombre = usuarios_legacy[identificador]
        elif usuario_auth:
            nota.usuario_nombre = usuario_auth.username
        elif identificador:
            nota.usuario_nombre = 'Usuario no identificado'
        else:
            nota.usuario_nombre = 'Sin usuario'

        nota.fecha_mostrada = _fecha_cliente_seg_mostrada(nota.fecha)

def get_sql_conn() -> pyodbc.Connection:
    # Connection string directo (sin DSN)
    conn_str = (
        f"DRIVER={{{settings.DUCTO_SQL_DRIVER}}};"
        f"SERVER={settings.DUCTO_SQL_SERVER};"
        f"DATABASE={settings.DUCTO_SQL_DB};"
        f"UID={settings.DUCTO_SQL_USER};"
        f"PWD={settings.DUCTO_SQL_PASSWORD};"
        f"Encrypt={settings.DUCTO_SQL_ENCRYPT};"
        f"TrustServerCertificate={settings.DUCTO_SQL_TRUST_CERT};"
        "Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)

def exec_query(sql: str, params: tuple = ()) -> list:
    with get_sql_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()

def exec_non_query(sql: str, params: tuple = ()) -> None:
    with get_sql_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()

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
        return self.model.objects.all().order_by('NombreCat').reverse()

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

        consulta = "exec [ducto].[SEG_ConsultaProyecto_WEB] ?"
        try:
            rows = exec_query(consulta, (1,))
            contexto["proyecto"] = rows
        except pyodbc.Error as e:
            print("Error SQL:", e)
            contexto["proyecto"] = []
            contexto["error_sql"] = "No se pudo consultar la base de datos."

        contexto.update({
            "encabezado": "DUCTO",
            "titulo": "PROYECTOS TERMINADOS",
            "menu": "Proyectos",
            "submenu": "Listado de Proyectos Terminados para Facturar",
        })
        return contexto


class Vista2(LoginRequiredMixin,TemplateView):
    template_name = "proyvistobueno.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)

        consulta = "exec [ducto].[SEG_ConsultaProyecto_WEB] ?"
        try:
            rows = exec_query(consulta, (2,))
            contexto["proyecto"] = rows
        except pyodbc.Error as e:
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

        consulta = "exec [ducto].[SEG_ConsultaProyecto_WEB] ?"
        try:
            rows = exec_query(consulta, (3,))
            contexto["proyecto"] = rows
        except pyodbc.Error as e:
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

        consulta_nom = """
            SELECT b.NombreProyecto
            FROM Proyecto a
            JOIN Cotizacion b ON b.IdCotizacion = a.IdCotizacion
            WHERE a.IdProyecto = ?
        """
        rows_nom = exec_query(consulta_nom, (pk,))
        nompro = rows_nom[0][0] if rows_nom else ""

        consulta_seg = """
            SELECT IdProyecto, Comentario, Fecha
            FROM [ducto].[ProyectoFacturarSeg]
            WHERE IdProyecto = ? AND Tabla = ?
        """
        rows = exec_query(consulta_seg, (pk, tabla))

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

    consulta = """
        INSERT INTO [ducto].[ProyectoFacturarSeg] (IdProyecto, Tabla, Comentario)
        VALUES (?, ?, ?)
    """
    exec_non_query(consulta, (idproyecto, tabla, comentario))

    return redirect(f"{idproyecto}/{tabla}")


class ListaTipoEntrega(LoginRequiredMixin,ListView):
    model = TipoEntrega
    template_name = 'listatipoentrega.html'
    context_object_name = 'tipos_entrega'

    def get_queryset(self):
        return self.model.objects.all().order_by('descripcion')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'encabezado': 'Tipos de Entrega',
            'menu': 'Parámetros',
            'submenu': 'Tipos de Entrega',
            'titulo': 'Tipos de Entrega',
        })
        return context


@login_required
def tipo_entrega_create(request):
    if request.method == 'POST':
        form = TipoEntregaForm(request.POST)
        if form.is_valid():
            form.save()
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
    tipo_entrega = get_object_or_404(TipoEntrega, pk=pk)

    if request.method == 'POST':
        form = TipoEntregaForm(request.POST, instance=tipo_entrega)
        if form.is_valid():
            form.save()
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
    tipo_entrega = get_object_or_404(TipoEntrega, pk=pk)
    entregas_asociadas = EntregaProyecto.objects.filter(idtipoentrega=tipo_entrega).count()
    error_eliminacion = None

    if request.method == 'POST':
        if entregas_asociadas:
            error_eliminacion = 'No se puede eliminar el tipo de entrega porque tiene entregas asociadas.'
        else:
            try:
                tipo_entrega.delete()
                return redirect('lista-tipo-entrega')
            except IntegrityError:
                error_eliminacion = 'No se puede eliminar el tipo de entrega porque esta siendo utilizado por otros registros.'

    context = {
        'titulo': 'Eliminar tipo de entrega',
        'encabezado': 'Eliminar tipo de entrega',
        'submenu': 'Confirmacion de eliminacion',
        'tipo_entrega': tipo_entrega,
        'entregas_asociadas': entregas_asociadas,
        'error_eliminacion': error_eliminacion,
    }
    return render(request, 'tipoentrega_confirm_delete.html', context)
    
FECHA_MINIMA_COTIZACION = date(1900, 1, 1)


def _queryset_clientes_con_relaciones():
    return (
        Cliente.objects
        .exclude(idestadocliente_id=ESTADO_CLIENTE_ELIMINADO)
        .select_related('idestadocliente', 'idcomppago', 'idcliente_p')
        .prefetch_related(
            Prefetch(
                'clientecategoria_set',
                queryset=ClienteCategoria.objects.select_related('idcategoria')
            )
        )
    )


def _anotar_clientes_reporte(clientes, fechas_por_cliente=None):
    fechas_por_cliente = fechas_por_cliente or {}

    for cliente in clientes:
        cliente.fecha_ultima_cotizacion = fechas_por_cliente.get(cliente.idcliente)

        categorias = []
        for cc in cliente.clientecategoria_set.all():
            if cc.idcategoria:
                categorias.append(cc.idcategoria.NombreCat)

        cliente.categorias_texto = ', '.join(dict.fromkeys(categorias))
        cliente.estado_texto = cliente.idestadocliente.descrip if cliente.idestadocliente_id else ''
        cliente.comportamiento_pago_texto = cliente.idcomppago.descrip if cliente.idcomppago_id else ''


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
    clientes = list(
        _queryset_clientes_con_relaciones()
        .filter(esprincipal=True)
        .order_by('razonsocial')
    )

    if not clientes:
        return render(request, 'clientes/reporte_clientes.html', {
            'clientes': [],
            'titulo': 'Clientes principales',
            'encabezado': 'Clientes principales',
            'submenu': 'Lista de clientes principales',
            'url_modificar_name': 'cliente_principal_update',
            'mostrar_eliminar': False,
        })

    ids_principales = [c.idcliente for c in clientes]

    fechas_principal_qs = (
        Cotizacion.objects
        .filter(idcliente__in=ids_principales)
        .values('idcliente')
        .annotate(ultima_fecha=Max('fecha'))
    )
    fechas_principal = {
        row['idcliente']: row['ultima_fecha']
        for row in fechas_principal_qs
    }

    hijos_qs = (
        Cliente.objects
        .filter(idcliente_p__in=ids_principales)
        .exclude(idestadocliente_id=ESTADO_CLIENTE_ELIMINADO)
        .values('idcliente', 'idcliente_p')
    )

    hijo_a_padre = {}
    ids_hijos = []

    for row in hijos_qs:
        hijo_a_padre[row['idcliente']] = row['idcliente_p']
        ids_hijos.append(row['idcliente'])

    fechas_hijos_por_padre = defaultdict(lambda: FECHA_MINIMA_COTIZACION)

    if ids_hijos:
        fechas_hijos_qs = (
            Cotizacion.objects
            .filter(idcliente__in=ids_hijos)
            .values('idcliente')
            .annotate(ultima_fecha=Max('fecha'))
        )

        for row in fechas_hijos_qs:
            id_hijo = row['idcliente']
            fecha_hijo = row['ultima_fecha'] or FECHA_MINIMA_COTIZACION
            id_padre = hijo_a_padre.get(id_hijo)

            fecha_actual_padre = fechas_hijos_por_padre[id_padre]

            if id_padre and (
                fecha_actual_padre is None or
                (fecha_hijo is not None and fecha_hijo > fecha_actual_padre)
            ):
                fechas_hijos_por_padre[id_padre] = fecha_hijo

    fechas_cliente_finales = {}
    for cliente in clientes:
        fecha_cliente = fechas_principal.get(cliente.idcliente) or FECHA_MINIMA_COTIZACION
        fecha_hijos = fechas_hijos_por_padre.get(cliente.idcliente) or FECHA_MINIMA_COTIZACION

        if fecha_cliente and fecha_hijos:
            fechas_cliente_finales[cliente.idcliente] = max(fecha_cliente, fecha_hijos)
        else:
            fechas_cliente_finales[cliente.idcliente] = fecha_cliente or fecha_hijos

    _anotar_clientes_reporte(clientes, fechas_cliente_finales)

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
    clientes = list(
        _queryset_clientes_con_relaciones()
        .order_by('razonsocial')
    )

    ids_clientes = [cliente.idcliente for cliente in clientes]
    fechas_qs = (
        Cotizacion.objects
        .filter(idcliente__in=ids_clientes)
        .values('idcliente')
        .annotate(ultima_fecha=Max('fecha'))
    )
    fechas_por_cliente = {
        row['idcliente']: row['ultima_fecha']
        for row in fechas_qs
    }

    _anotar_clientes_reporte(clientes, fechas_por_cliente)

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
    cliente = get_object_or_404(
        Cliente.objects.exclude(idestadocliente_id=ESTADO_CLIENTE_ELIMINADO),
        pk=pk,
        esprincipal=True,
    )

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
            cliente = form.save(commit=False)
            cliente.insercion = _ahora_santiago_naive()
            cliente.save()
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
@transaction.atomic
def cliente_update(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    notas_pendientes = []

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
            cliente = form.save()

            # Guardar contactos
            contactos = formset_contactos.save(commit=False)

            # Eliminar los marcados como DELETE
            for obj in formset_contactos.deleted_objects:
                obj.delete()

            for contacto in contactos:
                contacto.idcliente = cliente

                if not contacto.fecharegistro:
                    contacto.fecharegistro = _ahora_santiago_naive()

                contacto.save()

            # Guardar categorías
            categorias = list(dict.fromkeys(form.cleaned_data.get('categorias', [])))

            ClienteCategoria.objects.filter(idcliente=cliente).delete()

            nuevas_categorias = [
                ClienteCategoria(idcliente=cliente, idcategoria=categoria)
                for categoria in categorias
            ]

            if nuevas_categorias:
                ClienteCategoria.objects.bulk_create(nuevas_categorias)

            notas_a_guardar = []
            notas_a_guardar.extend(post_data.getlist('notas_agregadas'))

            nota_directa = form_nota.cleaned_data.get('nota')
            if nota_directa:
                notas_a_guardar.append(nota_directa)

            for nota in notas_a_guardar:
                nota = (nota or '').strip()
                if not nota:
                    continue

                usuario_nota = _resolver_id_usuario_nota(request.user.username or str(request.user))[:128]
                ClienteSeg.objects.create(
                    idcliente=cliente,
                    fecha=_fecha_cliente_seg_guardado(),
                    iduser=usuario_nota,
                    nota=nota,
                )

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

    notas_cliente = list(ClienteSeg.objects.filter(idcliente=cliente))
    _asignar_nombre_usuario_notas(notas_cliente)

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
    }
    return render(request, 'clientes/cliente_form.html', context)
    
@login_required
def cliente_delete(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)

    if request.method == 'POST':
        estado_eliminado = get_object_or_404(Testadocliente, pk=5)

        cliente.idestadocliente = estado_eliminado
        cliente.save(update_fields=['idestadocliente'])

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
    proyectos = list(
        Proyecto.objects.select_related(
            'idcotizacion',
            'idcotizacion__idcliente',
            'idcliente',
            'estadoproyecto'
        ).order_by('idcotizacion__codregion', 'idproyecto')
    )

    regiones = {
        r.codregion: r.descrip
        for r in Tregion.objects.all()
    }

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
        pro.numcorr_texto = ''
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
        'titulo': 'Proyectos',
        'encabezado': 'Proyectos totales',
        'submenu': 'Lista total de proyectos',
        'proyectos': proyectos,
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
    clientes = (
        Cliente.objects
        .exclude(idestadocliente_id=ESTADO_CLIENTE_ELIMINADO)
        .order_by('razonsocial')
    )

    hoy = timezone.localdate()
    hace_30_dias = hoy - timedelta(days=30)

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
    start = request.GET.get('start')
    end = request.GET.get('end')

    start_local = _to_local_naive(start)
    end_local = _to_local_naive(end)

    hace_30_dias = datetime.combine(
        timezone.localdate() - timedelta(days=30),
        time.min,
    )
    hace_30_dias = _make_local_aware(hace_30_dias)

    start_local = _make_local_aware(start_local)
    end_local = _make_local_aware(end_local)

    qs = (
        ClienteAgenda.objects
        .select_related('idcliente')
        .prefetch_related(
            Prefetch(
                'idcliente__clientecontacto_set',
                queryset=Clientecontacto.objects.order_by('nombrecontacto', 'idcontacto')
            )
        )
        .filter(fecha__isnull=False)
    )

    filtro_desde = hace_30_dias
    if start_local and start_local > filtro_desde:
        filtro_desde = start_local

    qs = qs.filter(fecha__gte=filtro_desde)

    if end_local:
        qs = qs.filter(fecha__lt=end_local)

    eventos = []
    for agenda in qs:
        if not agenda.fecha:
            continue

        fecha_evento = agenda.fecha.date()
        nombre_cliente = ''

        if agenda.idcliente and agenda.idcliente.razonsocial:
            nombre_cliente = agenda.idcliente.razonsocial
        elif agenda.titulo:
            nombre_cliente = agenda.titulo
        elif agenda.idcliente_id:
            nombre_cliente = f'Cliente {agenda.idcliente_id}'
        else:
            nombre_cliente = 'Cliente sin nombre'

        contactos = []
        if agenda.idcliente:
            for contacto in agenda.idcliente.clientecontacto_set.all():
                if not any([
                    contacto.nombrecontacto,
                    contacto.cargo,
                    contacto.telefono,
                    contacto.email,
                ]):
                    continue

                tipo_contacto = {
                    'N': 'Normal',
                    'F': 'Facturación',
                    'C': 'Comercial',
                }.get((contacto.tipocontacto or '').strip().upper(), '')

                contactos.append({
                    'tipo': tipo_contacto,
                    'nombre': contacto.nombrecontacto or '',
                    'cargo': contacto.cargo or '',
                    'telefono': contacto.telefono or '',
                    'email': contacto.email or '',
                })

        eventos.append({
            'id': agenda.id,
            'title': nombre_cliente,
            'start': fecha_evento.isoformat(),
            'allDay': True,
            'display': 'block',
            'backgroundColor': '#0d6efd',
            'borderColor': '#0d6efd',
            'textColor': '#ffffff',
            'extendedProps': {
                'cliente': nombre_cliente,
                'titulo': agenda.titulo or nombre_cliente,
                'descrip': agenda.descrip or '',
                'fecha': fecha_evento.strftime('%d-%m-%Y'),
                'comentario_cliente': agenda.idcliente.comentario if agenda.idcliente and agenda.idcliente.comentario else '',
                'contactos': contactos,
            }
        })

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

    fecha_str = payload.get('fecha')
    idcliente = payload.get('idcliente')
    descrip = (payload.get('descrip') or '').strip()

    if not fecha_str:
        return JsonResponse({'ok': False, 'mensaje': 'Debes indicar la fecha del evento.'}, status=400)

    if not idcliente:
        return JsonResponse({'ok': False, 'mensaje': 'Debes seleccionar un cliente.'}, status=400)

    if not descrip:
        return JsonResponse({'ok': False, 'mensaje': 'Debes ingresar el detalle del evento.'}, status=400)

    try:
        fecha_evento = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'ok': False, 'mensaje': 'La fecha del evento es inválida.'}, status=400)

    if fecha_evento < timezone.localdate():
        return JsonResponse({
            'ok': False,
            'mensaje': 'Solo puedes registrar eventos desde hoy en adelante.'
        }, status=400)

    cliente = get_object_or_404(Cliente, pk=idcliente)

    if cliente.idestadocliente_id == ESTADO_CLIENTE_ELIMINADO:
        return JsonResponse({
            'ok': False,
            'mensaje': 'No es posible agendar un cliente eliminado.'
        }, status=400)

    fecha_agenda = datetime.combine(fecha_evento, time(hour=9, minute=0))
    if timezone.is_naive(fecha_agenda):
        fecha_agenda = timezone.make_aware(fecha_agenda, timezone.get_current_timezone())

    agenda = ClienteAgenda(
        idcliente=cliente,
        fecha=fecha_agenda,
        titulo=cliente.razonsocial or f'Cliente {cliente.idcliente}',
        descrip=descrip,
        estado=0,
    )
    agenda.save()

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

    nueva_fecha = payload.get('nueva_fecha')
    if not nueva_fecha:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Falta la nueva fecha.'
        }, status=400)

    try:
        fecha_nueva = datetime.strptime(nueva_fecha, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Formato de fecha inválido.'
        }, status=400)

    hace_30_dias = timezone.localdate() - timedelta(days=30)
    if fecha_nueva < hace_30_dias:
        return JsonResponse({
            'ok': False,
            'mensaje': 'No puedes mover el evento a una fecha anterior al rango visible.'
        }, status=400)

    with transaction.atomic():
        agenda = get_object_or_404(
            ClienteAgenda.objects.select_for_update(),
            pk=agenda_id
        )

        if not agenda.fecha:
            return JsonResponse({
                'ok': False,
                'mensaje': 'El evento no tiene fecha registrada.'
            }, status=400)

        fecha_actual = agenda.fecha
        fecha_actualizada = fecha_actual.replace(
            year=fecha_nueva.year,
            month=fecha_nueva.month,
            day=fecha_nueva.day
        )

        agenda.fecha = fecha_actualizada
        agenda.save(update_fields=['fecha'])

    return JsonResponse({
        'ok': True,
        'mensaje': 'Evento movido correctamente.'
    })

@login_required
def calendario_entregas_proyecto(request):
    proyectos = Proyecto.objects.select_related(
        'idcotizacion',
        'idtamano'
    ).order_by('idproyecto')

    tipos_entrega = TipoEntrega.objects.order_by('descripcion')
    urgencias = Urgencia.objects.order_by('descrip')
    tamanos = TDuracionProyecto.objects.order_by('descripcion')

    context = {
        'titulo': 'Calendario de entregas',
        'encabezado': 'Calendario de entregas de proyectos',
        'submenu': 'Agenda mensual de entregas',
        'proyectos': proyectos,
        'tipos_entrega': tipos_entrega,
        'urgencias': urgencias,
        'tamanos': tamanos,
    }
    return render(request, 'calendario_entregas_proyecto.html', context)

@login_required
def eventos_calendario_entregas(request):
    start = request.GET.get('start')
    end = request.GET.get('end')

    start_local = _to_local_naive(start)
    end_local = _to_local_naive(end)

    qs = EntregaProyecto.objects.select_related(
        'idproyecto',
        'idproyecto__idcotizacion',
        'idproyecto__idtamano',
        'idtipoentrega',
        'idurgencia',
        'idestadoentrega',
    ).filter(
        fechacalendario__isnull=False
    ).exclude(
        idestadoentrega_id=ESTADO_ENTREGA_NULA
    )

    if start_local:
        qs = qs.filter(fechacalendario__gte=start_local)

    if end_local:
        qs = qs.filter(fechacalendario__lt=end_local)

    usernames_desarrollo = set()
    for e in qs:
        rut_actual = _rut_desarrollador_actual(e)
        if rut_actual:
            usernames_desarrollo.add(rut_actual)

    mapa_usuarios = {
        u.username: (u.get_full_name().strip() or u.username)
        for u in User.objects.filter(username__in=usernames_desarrollo)
    }

    eventos = []

    for e in qs:
        proyecto_codigo = ''
        proyecto_nombre = ''

        if e.idproyecto:
            proyecto_codigo = str(e.idproyecto.idproyecto)
            if e.idproyecto.idcotizacion:
                proyecto_nombre = e.idproyecto.idcotizacion.nombreproyecto or ''

        color = '#6c757d'
        if e.idestadoentrega_id == ESTADO_ENTREGA_ENTREGADO:
            color = '#b3ad9f'
        elif e.idtipoentrega and e.idtipoentrega.color:
            color = e.idtipoentrega.color

        titulo = f"{proyecto_codigo} - {proyecto_nombre}".strip()

        rut_desarrollador_actual = _rut_desarrollador_actual(e)
        nombre_desarrollador = mapa_usuarios.get(
            rut_desarrollador_actual,
            rut_desarrollador_actual or ''
        )

        eventos.append({
            'id': e.identrega,
            'title': titulo,
            'start': e.fechacalendario.strftime('%Y-%m-%dT%H:%M:%S') if e.fechacalendario else None,
            'allDay': False,
            'display': 'block',
            'backgroundColor': color,
            'borderColor': color,
            'textColor': '#ffffff',
            'extendedProps': {
                'identrega': e.identrega,
                'idproyecto': proyecto_codigo,
                'nombreproyecto': proyecto_nombre,
                'tipoentrega': e.idtipoentrega.descripcion if e.idtipoentrega else '',
                'horaentrega': e.horaentrega or '',
                'fechaentrega': e.fechaentrega.strftime('%d-%m-%Y') if e.fechaentrega else '',
                'plazo': e.plazoestdesarrollo or '',
                'urgencia_id': e.idurgencia_id,
                'urgencia': e.idurgencia.descrip if e.idurgencia else '',
                'estadoentrega_id': e.idestadoentrega_id,
                'estadoentrega': e.idestadoentrega.descrip if e.idestadoentrega else '',
                'tamano': e.idproyecto.idtamano.descripcion if e.idproyecto and e.idproyecto.idtamano else '',
                'asignado_a': nombre_desarrollador,
            }
        })

    return JsonResponse(eventos, safe=False)


def _rut_desarrollador_actual(entrega):
    return (
        entrega.rutuserdesa3
        or entrega.rutuserdesa2
        or entrega.rutuserdesa1
        or ''
    )

def _fecha_desarrollador_actual(entrega):
    return (
        entrega.fechaasigdesa3
        or entrega.fechaasigdesa2
        or entrega.fechaasigdesa1
    )

@login_required
def obtener_rut_usuario(request):
    if request.user.is_authenticated:
        return request.user.username
    return None

@login_required
@require_POST
def crear_entrega_proyecto(request):
    rut_user = obtener_rut_usuario(request)
    if not rut_user:
        return JsonResponse({
            'ok': False,
            'mensaje': 'No fue posible determinar el usuario creador.'
        }, status=400)

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Datos inválidos.'
        }, status=400)

    fecha_calendario = payload.get('fecha_calendario')
    idproyecto = payload.get('idproyecto')
    idtipoentrega = payload.get('idtipoentrega')
    idurgencia = payload.get('idurgencia')
    fecha_entrega = payload.get('fecha_entrega')
    hora_entrega = payload.get('hora_entrega')
    plazo = payload.get('plazo')

    if not fecha_calendario:
        return JsonResponse({'ok': False, 'mensaje': 'Falta la fecha del calendario.'}, status=400)

    if not idproyecto:
        return JsonResponse({'ok': False, 'mensaje': 'Debes seleccionar un proyecto.'}, status=400)

    if not idtipoentrega:
        return JsonResponse({'ok': False, 'mensaje': 'Debes seleccionar un tipo de entrega.'}, status=400)

    if not idurgencia:
        return JsonResponse({'ok': False, 'mensaje': 'Debes seleccionar un tipo de urgencia.'}, status=400)

    if not fecha_entrega:
        return JsonResponse({'ok': False, 'mensaje': 'Debes indicar la fecha de entrega al cliente.'}, status=400)

    if not hora_entrega:
        hora_entrega = '06:00'

    # Validar fecha clickeada: hoy o futuro
    try:
        fecha_cal = datetime.strptime(fecha_calendario, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'ok': False, 'mensaje': 'Fecha de calendario inválida.'}, status=400)

    try:
        fecha_ent = datetime.strptime(fecha_entrega, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'ok': False, 'mensaje': 'Fecha de entrega inválida.'}, status=400)

    # FechaCalendario = fecha clickeada + hora de entrega
    try:
        dt_cal = datetime.strptime(f'{fecha_calendario} {hora_entrega}', '%Y-%m-%d %H:%M')
    except ValueError:
        return JsonResponse({'ok': False, 'mensaje': 'Hora de entrega inválida.'}, status=400)

    if timezone.is_naive(dt_cal):
        dt_cal = timezone.make_aware(dt_cal, timezone.get_current_timezone())

    idtamano = payload.get('idtamano')

    if not idtamano:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Debes seleccionar el tamaño del proyecto.'
        }, status=400)

    proyecto = get_object_or_404(Proyecto, pk=idproyecto)
    get_object_or_404(TDuracionProyecto, pk=idtamano)

    proyecto.idtamano_id = idtamano
    proyecto.save(update_fields=['idtamano'])

    # Validaciones simples de existencia
    get_object_or_404(Proyecto, pk=idproyecto)
    get_object_or_404(TipoEntrega, pk=idtipoentrega)
    get_object_or_404(Urgencia, pk=idurgencia)

    entrega = EntregaProyecto(
        rutusercreador=rut_user,
        fechacreacion=_ahora_santiago_naive(),
        fechacalendario=dt_cal,
        idproyecto_id=idproyecto,
        idtipoentrega_id=idtipoentrega,
        idurgencia_id=idurgencia,
        fechaentrega=fecha_ent,
        horaentrega=hora_entrega,
        plazoestdesarrollo=plazo or '',
        idestadoentrega_id=1,
    )
    entrega.save()

    return JsonResponse({
        'ok': True,
        'mensaje': 'Entrega creada correctamente.',
        'identrega': entrega.identrega
    })
    
User = get_user_model()

@login_required
@require_GET
def usuarios_desarrollo_activos(request):
    usuarios = (
        User.objects
        .filter(is_active=True, is_superuser=False)
        .exclude(username__iexact='admin')
        .order_by('first_name', 'last_name', 'username')
    )

    data = []
    for u in usuarios:
        nombre = u.get_full_name().strip() or u.username
        data.append({
            'rut': u.username,
            'nombrecompleto': nombre,
        })

    return JsonResponse(data, safe=False)

from django.contrib.auth import get_user_model
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

User = get_user_model()


@login_required
@require_GET
def usuarios_revision_activos(request):
    usuarios = (
        User.objects
        .filter(is_active=True, is_superuser=False)
        .exclude(username__iexact='admin')
        .order_by('first_name', 'last_name', 'username')
    )

    data = []
    for u in usuarios:
        data.append({
            'rut': u.username,
            'nombrecompleto': u.get_full_name().strip() or u.username,
        })

    return JsonResponse({
        'ok': True,
        'usuarios': data
    })




@login_required
@require_POST
def anular_entrega(request, identrega):
    rut_user = obtener_rut_usuario(request)
    if not rut_user:
        return JsonResponse({
            'ok': False,
            'mensaje': 'No fue posible determinar el usuario que anula.'
        }, status=400)

    with transaction.atomic():
        entrega = get_object_or_404(
            EntregaProyecto.objects.select_for_update(),
            pk=identrega
        )

        if entrega.idestadoentrega_id != 1:
            return JsonResponse({
                'ok': False,
                'mensaje': 'Solo se puede anular una entrega con estado 1.'
            }, status=400)

        entrega.idestadoentrega_id = 6
        entrega.rutuseranula = rut_user
        entrega.fechaanulacion = _ahora_santiago_naive()
        entrega.rutuserupdate = rut_user
        entrega.fechaupdate = _ahora_santiago_naive()

        entrega.save(update_fields=[
            'idestadoentrega',
            'rutuseranula',
            'fechaanulacion',
            'rutuserupdate',
            'fechaupdate',
        ])

    return JsonResponse({
        'ok': True,
        'mensaje': 'Entrega anulada correctamente.'
    })
    
@login_required
@require_POST
def asignar_entrega_desarrollo(request, identrega):
    rut_user = request.user.username

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Datos inválidos.'
        }, status=400)

    rut_desarrollador = payload.get('rut_usuario')
    if not rut_desarrollador:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Debes seleccionar un usuario.'
        }, status=400)

    usuario_auth = User.objects.filter(
        username=rut_desarrollador,
        is_active=True
    ).first()

    if not usuario_auth:
        return JsonResponse({
            'ok': False,
            'mensaje': 'El usuario seleccionado no existe o está inactivo.'
        }, status=400)

    with transaction.atomic():
        entrega = get_object_or_404(
            EntregaProyecto.objects.select_for_update(),
            pk=identrega
        )

        if entrega.idestadoentrega_id != ESTADO_ENTREGA_NUEVA:
            return JsonResponse({
                'ok': False,
                'mensaje': 'Solo se puede enviar a desarrollo una entrega con estado 1.'
            }, status=400)

        evento = _registrar_evento(
            entrega,
            ['A Desarrollo', 'Enviar a Desarrollo'],
            origen=rut_user,
            destino=rut_desarrollador
        )

        campos_desarrollo = _set_asignacion_desarrollo_por_flujo(
            entrega,
            rut_desarrollador,
            evento.fechahora
        )

        entrega.idestadoentrega_id = ESTADO_ENTREGA_DESARROLLO
        entrega.rutuserupdate = rut_user
        entrega.fechaupdate = evento.fechahora

        entrega.save(update_fields=[
            'idestadoentrega',
            'rutuserupdate',
            'fechaupdate',
            *campos_desarrollo
        ])

    return JsonResponse({
        'ok': True,
        'mensaje': 'Entrega enviada a desarrollo correctamente.'
    })
    
@login_required
@require_POST
def mover_entrega_calendario(request, identrega):
    rut_user = obtener_rut_usuario(request)
    
    if not rut_user:
        return JsonResponse({
            'ok': False,
            'mensaje': 'No fue posible determinar el usuario.'
        }, status=400)

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Datos inválidos.'
        }, status=400)

    nueva_fecha = payload.get('nueva_fecha')
    if not nueva_fecha:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Falta la nueva fecha.'
        }, status=400)

    try:
        fecha_nueva = datetime.strptime(nueva_fecha, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Formato de fecha inválido.'
        }, status=400)

    with transaction.atomic():
        entrega = get_object_or_404(
            EntregaProyecto.objects.select_for_update(),
            pk=identrega
        )

        if entrega.idestadoentrega_id == 5:
            return JsonResponse({
                'ok': False,
                'mensaje': 'No se puede mover una entrega con estado 5.'
            }, status=400)

        if not entrega.fechacalendario:
            return JsonResponse({
                'ok': False,
                'mensaje': 'La entrega no tiene fecha calendario.'
            }, status=400)

        fecha_actual = entrega.fechacalendario

        # conserva hora/minuto/segundo, cambia solo el día
        fecha_actualizada = fecha_actual.replace(
            year=fecha_nueva.year,
            month=fecha_nueva.month,
            day=fecha_nueva.day
        )

        entrega.fechacalendario = fecha_actualizada
        entrega.rutuserupdate = rut_user
        entrega.fechaupdate = _ahora_santiago_naive()
        entrega.save()

    return JsonResponse({
        'ok': True,
        'mensaje': 'Fecha de calendario actualizada correctamente.'
    })    
    
@login_required
def entregas_general(request):
    observaciones_qs = (
        Entregaobservacion.objects
        .filter(entrega_id=OuterRef('pk'), estado=1)
        .values('entrega_id')
        .annotate(total=Count('id'))
        .values('total')[:1]
    )

    creador_qs = (
        tusuario.objects
        .filter(idusuario=OuterRef('rutusercreador'))
        .values('nombreusuario')[:1]
    )

    entregas = (
        EntregaProyecto.objects
        .exclude(idestadoentrega_id=ESTADO_ENTREGA_NULA)
        .select_related(
            'idproyecto',
            'idproyecto__idcotizacion',
            'idproyecto__idcliente',
            'idproyecto__idtamano',
            'idtipoentrega',
            'idurgencia',
            'idestadoentrega',
        )
        .annotate(
            rut_cliente=F('idproyecto__idcliente__rut'),
            fecha_adjudicacion=F('idproyecto__fechaadjudicacion'),
            descripcion_urgencia=F('idurgencia__descrip'),
            simbolo_urgencia=F('idurgencia__simbolo'),
            nombre_usuario_creador=Subquery(
                creador_qs,
                output_field=CharField()
            ),
            nombre_proyecto=F('idproyecto__idcotizacion__nombreproyecto'),
            descripcion_tipo_entrega=F('idtipoentrega__descripcion'),
            descripcion_estado_entrega=F('idestadoentrega__descrip'),
            estado_proyecto=F('idproyecto__estado'),
            color_tipo_entrega=F('idtipoentrega__color'),
            descripcion_tamanio_proyecto=F('idproyecto__idtamano__descripcion'),
            observaciones=Coalesce(
                Subquery(observaciones_qs, output_field=IntegerField()),
                Value(0)
            ),
        )
        .order_by('-fechacalendario', '-identrega')
    )

    usernames = set()
    for e in entregas:
        rut_actual = _rut_desarrollador_actual(e)
        if rut_actual:
            usernames.add(rut_actual)

    mapa_usuarios = {
        u.username: (u.get_full_name().strip() or u.username)
        for u in User.objects.filter(username__in=usernames)
    }

    for e in entregas:
        rut_actual = _rut_desarrollador_actual(e)
        e.nombre_desarrollador_actual = mapa_usuarios.get(rut_actual, rut_actual or '')
        e.fecha_asignacion = _fecha_desarrollador_actual(e)
        e.nombre_usuario_creador = e.nombre_usuario_creador or e.rutusercreador or ''
        
    context = {
        'titulo': 'Entregas General',
        'encabezado': 'Entregas General',
        'submenu': 'Listado general de entregas',
        'entregas': entregas,
    }
    return render(request, 'entregas_general.html', context)

def _nombre_usuario_visible(codigo_usuario, mapa_usuarios):
    if not codigo_usuario:
        return ''
    return mapa_usuarios.get(codigo_usuario, codigo_usuario)


def _formatear_fecha_hora_local(fecha):
    if not fecha:
        return ''

    if timezone.is_aware(fecha):
        fecha = timezone.localtime(fecha)

    return fecha.strftime('%d-%m-%Y %H:%M')


def _mapa_nombres_usuarios(codigos):
    codigos = [c for c in set(codigos) if c]
    if not codigos:
        return {}

    usuarios = User.objects.filter(username__in=codigos)

    return {
        u.username: (u.get_full_name().strip() or u.username)
        for u in usuarios
    }


def _construir_eventos_entrega(entrega, mapa_usuarios):
    eventos = []

    def agregar_evento(nombre_evento, origen, destino, fecha_evento):
        if not fecha_evento:
            return

        eventos.append({
            'evento': nombre_evento,
            'origen': _nombre_usuario_visible(origen, mapa_usuarios),
            'destino': _nombre_usuario_visible(destino, mapa_usuarios),
            'fecha': _formatear_fecha_hora_local(fecha_evento),
            '_orden': fecha_evento,
        })

    agregar_evento('A Desarrollo', entrega.rutusercreador, entrega.rutuserdesa1, entrega.fechaasigdesa1)
    agregar_evento('A Revisión', entrega.rutuserdesa1, entrega.rutuserrev1, entrega.fechaasigrev1)

    agregar_evento('A Desarrollo', entrega.rutuserrev1, entrega.rutuserdesa2, entrega.fechaasigdesa2)
    agregar_evento('A Revisión', entrega.rutuserdesa2, entrega.rutuserrev2, entrega.fechaasigrev2)

    agregar_evento('A Desarrollo', entrega.rutuserrev2, entrega.rutuserdesa3, entrega.fechaasigdesa3)
    agregar_evento('A Revisión', entrega.rutuserdesa3, entrega.rutuserrev3, entrega.fechaasigrev3)

    eventos.sort(key=lambda x: x['_orden'])

    for e in eventos:
        e.pop('_orden', None)

    return eventos

def _resolver_tipoevento(*alternativas):
    for nombre in alternativas:
        te = Tipoevento.objects.filter(nombre__iexact=nombre).first()
        if te:
            return te

    for nombre in alternativas:
        te = Tipoevento.objects.filter(nombre__icontains=nombre).first()
        if te:
            return te

    return None

def _registrar_evento(entrega, alternativas_tipoevento, origen='', destino=''):
    tipoevento = _resolver_tipoevento(*alternativas_tipoevento)
    if not tipoevento:
        raise ValueError(
            f"No existe Tipoevento para ninguna de estas opciones: {alternativas_tipoevento}"
        )

    evento = Entregaevento.objects.create(
        entrega=entrega,
        tipoevento=tipoevento,
        rutorigen=origen or '',
        rutdestino=destino or '',
    )
    return evento

def _ultimo_desarrollador_asignado(entrega):
    return (
        entrega.rutuserdesa3
        or entrega.rutuserdesa2
        or entrega.rutuserdesa1
        or ''
    )

def _set_asignacion_desarrollo_por_flujo(entrega, rut_destino, fecha_evento):
    """
    Flujo:
    1 -> 2  => Desa1
    4 -> 3  => Desa2, luego Desa3, y desde ahí seguir en Desa3
    """
    if entrega.idestadoentrega_id == ESTADO_ENTREGA_NUEVA:
        entrega.rutuserdesa1 = rut_destino
        entrega.fechaasigdesa1 = fecha_evento
        return ['rutuserdesa1', 'fechaasigdesa1']

    if entrega.idestadoentrega_id == ESTADO_ENTREGA_REVISION:
        if not entrega.rutuserdesa2:
            entrega.rutuserdesa2 = rut_destino
            entrega.fechaasigdesa2 = fecha_evento
            return ['rutuserdesa2', 'fechaasigdesa2']

        if not entrega.rutuserdesa3:
            entrega.rutuserdesa3 = rut_destino
            entrega.fechaasigdesa3 = fecha_evento
            return ['rutuserdesa3', 'fechaasigdesa3']

        # Saturación: seguir iterando en Desa3
        entrega.rutuserdesa3 = rut_destino
        entrega.fechaasigdesa3 = fecha_evento
        return ['rutuserdesa3', 'fechaasigdesa3']

    raise ValueError('Flujo no válido para asignación a desarrollo.')


def _set_asignacion_revision_por_flujo(entrega, rut_destino, fecha_evento):
    """
    Flujo:
    2 -> 4  => Rev1
    3 -> 4  => Rev2, luego Rev3, y desde ahí seguir en Rev3
    """
    if entrega.idestadoentrega_id == ESTADO_ENTREGA_DESARROLLO:
        if not entrega.rutuserrev1:
            entrega.rutuserrev1 = rut_destino
            entrega.fechaasigrev1 = fecha_evento
            return ['rutuserrev1', 'fechaasigrev1']

        # si por algún motivo ya existe, lo vuelve a escribir
        entrega.rutuserrev1 = rut_destino
        entrega.fechaasigrev1 = fecha_evento
        return ['rutuserrev1', 'fechaasigrev1']

    if entrega.idestadoentrega_id == ESTADO_ENTREGA_CORRECCIONES:
        if not entrega.rutuserrev2:
            entrega.rutuserrev2 = rut_destino
            entrega.fechaasigrev2 = fecha_evento
            return ['rutuserrev2', 'fechaasigrev2']

        if not entrega.rutuserrev3:
            entrega.rutuserrev3 = rut_destino
            entrega.fechaasigrev3 = fecha_evento
            return ['rutuserrev3', 'fechaasigrev3']

        # Saturación: seguir iterando en Rev3
        entrega.rutuserrev3 = rut_destino
        entrega.fechaasigrev3 = fecha_evento
        return ['rutuserrev3', 'fechaasigrev3']

    raise ValueError('Flujo no válido para asignación a revisión.')

@login_required
@require_POST
def enviar_entrega_revision(request, identrega):
    rut_user = request.user.username

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Datos inválidos.'
        }, status=400)

    rut_revisor = payload.get('rut_usuario')
    if not rut_revisor:
        return JsonResponse({
            'ok': False,
            'mensaje': 'Debes seleccionar un usuario.'
        }, status=400)

    usuario_revisor = User.objects.filter(
        username=rut_revisor,
        is_active=True
    ).first()

    if not usuario_revisor:
        return JsonResponse({
            'ok': False,
            'mensaje': 'El usuario seleccionado no existe o está inactivo.'
        }, status=400)

    with transaction.atomic():
        entrega = get_object_or_404(
            EntregaProyecto.objects.select_for_update(),
            pk=identrega
        )

        if entrega.idestadoentrega_id not in [ESTADO_ENTREGA_DESARROLLO, ESTADO_ENTREGA_CORRECCIONES]:
            return JsonResponse({
                'ok': False,
                'mensaje': 'Solo se puede enviar a revisión una entrega en desarrollo o correcciones.'
            }, status=400)

        evento = _registrar_evento(
            entrega,
            ['A Revisión', 'Enviar a Revisión'],
            origen=rut_user,
            destino=rut_revisor
        )

        campos_revision = _set_asignacion_revision_por_flujo(
            entrega,
            rut_revisor,
            evento.fechahora
        )

        entrega.idestadoentrega_id = ESTADO_ENTREGA_REVISION
        entrega.rutuserupdate = rut_user
        entrega.fechaupdate = evento.fechahora

        entrega.save(update_fields=[
            'idestadoentrega',
            'rutuserupdate',
            'fechaupdate',
            *campos_revision
        ])

    return JsonResponse({
        'ok': True,
        'mensaje': 'Entrega enviada a revisión correctamente.'
    })
    
def _eventos_fallback_desde_entrega(entrega, mapa_usuarios):
    """
    Solo para entregas antiguas que todavía no tienen registros en EntregaEvento.
    """
    eventos = []

    def agregar(nombre_evento, origen, destino, fecha_evento):
        if not fecha_evento:
            return
        eventos.append({
            'evento': nombre_evento,
            'origen': _nombre_usuario_visible(origen, mapa_usuarios),
            'destino': _nombre_usuario_visible(destino, mapa_usuarios),
            'fecha': _formatear_fecha_hora_local(fecha_evento),
            '_orden': fecha_evento,
        })

    agregar('A Desarrollo', entrega.rutusercreador, entrega.rutuserdesa1, entrega.fechaasigdesa1)
    agregar('A Revisión', entrega.rutuserdesa1, entrega.rutuserrev1, entrega.fechaasigrev1)
    agregar('A Desarrollo', entrega.rutuserrev1, entrega.rutuserdesa2, entrega.fechaasigdesa2)
    agregar('A Revisión', entrega.rutuserdesa2, entrega.rutuserrev2, entrega.fechaasigrev2)
    agregar('A Desarrollo', entrega.rutuserrev2, entrega.rutuserdesa3, entrega.fechaasigdesa3)
    agregar('A Revisión', entrega.rutuserdesa3, entrega.rutuserrev3, entrega.fechaasigrev3)

    eventos.sort(key=lambda x: x['_orden'])

    for e in eventos:
        e.pop('_orden', None)

    return eventos

@login_required
def visor_entrega(request, identrega):
    entrega = get_object_or_404(
        EntregaProyecto.objects.select_related(
            'idproyecto',
            'idproyecto__idcotizacion',
            'idtipoentrega',
            'idestadoentrega',
        ),
        pk=identrega
    )

    observaciones_qs = (
        Entregaobservacion.objects
        .filter(entrega_id=identrega, estado=1)
        .select_related(
            'observacion',
            'observacion__tipoobservacion',
            'observacion__calificacion',
        )
        .order_by('id')
    )

    eventos_qs = (
        Entregaevento.objects
        .filter(entrega_id=identrega)
        .select_related('tipoevento')
        .order_by('fechahora', 'identregaevento')
    )

    codigos_usuarios = [
        entrega.rutusercreador,
        entrega.rutuserdesa1,
        entrega.rutuserdesa2,
        entrega.rutuserdesa3,
        entrega.rutuserrev1,
        entrega.rutuserrev2,
        entrega.rutuserrev3,
        entrega.rutuserupdate,
        entrega.rutuseranula,
    ]

    for ev in eventos_qs:
        codigos_usuarios.append(ev.rutorigen)
        codigos_usuarios.append(ev.rutdestino)

    mapa_usuarios = _mapa_nombres_usuarios(codigos_usuarios)

    data = {
        'ok': True,
        'identrega': entrega.identrega,
        'estadoentrega_id': entrega.idestadoentrega_id or 0,
        'estadoentrega': entrega.idestadoentrega.descrip if entrega.idestadoentrega else '',
        'idproyecto': str(entrega.idproyecto_id or ''),
        'nombreproyecto': '',
        'tipoentrega': '',
        'fechaentrega': entrega.fechaentrega.strftime('%d-%m-%Y') if entrega.fechaentrega else '',
        'observaciones': [],
        'eventos': [],
    }

    if entrega.idproyecto and entrega.idproyecto.idcotizacion:
        data['nombreproyecto'] = entrega.idproyecto.idcotizacion.nombreproyecto or ''

    if entrega.idtipoentrega:
        data['tipoentrega'] = entrega.idtipoentrega.descripcion or ''

    for eo in observaciones_qs:
        obs = eo.observacion
        data['observaciones'].append({
            'nro': obs.id if obs else '',
            'tipo': obs.tipoobservacion.nombre if obs and obs.tipoobservacion else '',
            'descripcion': obs.nombre if obs else '',
            'calificacion': obs.calificacion.nombre if obs and obs.calificacion else '',
            'estado': 'CORREGIDA',
        })

    if eventos_qs.exists():
        for ev in eventos_qs:
            data['eventos'].append({
                'evento': ev.tipoevento.nombre if ev.tipoevento else '',
                'origen': _nombre_usuario_visible(ev.rutorigen, mapa_usuarios),
                'destino': _nombre_usuario_visible(ev.rutdestino, mapa_usuarios),
                'fecha': _formatear_fecha_hora_local(ev.fechahora),
            })
    else:
        # compatibilidad con entregas antiguas sin historial cargado
        data['eventos'] = _eventos_fallback_desde_entrega(entrega, mapa_usuarios)

    return JsonResponse(data)

@login_required
def entregas_revision(request):
    observaciones_qs = (
        Entregaobservacion.objects
        .filter(entrega_id=OuterRef('pk'), estado=1)
        .values('entrega_id')
        .annotate(total=Count('id'))
        .values('total')[:1]
    )

    creador_qs = (
        tusuario.objects
        .filter(idusuario=OuterRef('rutusercreador'))
        .values('nombreusuario')[:1]
    )

    entregas = (
        EntregaProyecto.objects
        .filter(idestadoentrega_id=ESTADO_ENTREGA_REVISION)
        .select_related(
            'idproyecto',
            'idproyecto__idcotizacion',
            'idproyecto__idcliente',
            'idproyecto__idtamano',
            'idtipoentrega',
            'idurgencia',
            'idestadoentrega',
        )
        .annotate(
            rut_cliente=F('idproyecto__idcliente__rut'),
            fecha_adjudicacion=F('idproyecto__fechaadjudicacion'),
            descripcion_urgencia=F('idurgencia__descrip'),
            simbolo_urgencia=F('idurgencia__simbolo'),
            nombre_usuario_creador=Subquery(
                creador_qs,
                output_field=CharField()
            ),
            nombre_proyecto=F('idproyecto__idcotizacion__nombreproyecto'),
            descripcion_tipo_entrega=F('idtipoentrega__descripcion'),
            descripcion_estado_entrega=F('idestadoentrega__descrip'),
            estado_proyecto=F('idproyecto__estado'),
            color_tipo_entrega=F('idtipoentrega__color'),
            descripcion_tamanio_proyecto=F('idproyecto__idtamano__descripcion'),
            observaciones=Coalesce(
                Subquery(observaciones_qs, output_field=IntegerField()),
                Value(0)
            ),
        )
        .order_by('-fechacalendario', '-identrega')
    )

    usernames = set()
    for e in entregas:
        rut_actual = _rut_desarrollador_actual(e)
        if rut_actual:
            usernames.add(rut_actual)

    mapa_usuarios = {
        u.username: (u.get_full_name().strip() or u.username)
        for u in User.objects.filter(username__in=usernames)
    }

    for e in entregas:
        rut_actual = _rut_desarrollador_actual(e)
        e.nombre_desarrollador_actual = mapa_usuarios.get(rut_actual, rut_actual or '')
        e.fecha_asignacion = _fecha_desarrollador_actual(e)
        e.nombre_usuario_creador = e.nombre_usuario_creador or e.rutusercreador or ''

    context = {
        'titulo': 'Entregas Revisión',
        'encabezado': 'Entregas en Revisión',
        'submenu': 'Listado entregas en revisión',
        'entregas': entregas,
        'tipos_observacion': Tipoobservacion.objects.order_by('nombre'),
        'calificaciones': Calificacion.objects.order_by('nombre'),
    }
    return render(request, 'entregas_revision.html', context)

@login_required
def entregas_desarrollo(request):
    observaciones_qs = (
        Entregaobservacion.objects
        .filter(entrega_id=OuterRef('pk'), estado=1)
        .values('entrega_id')
        .annotate(total=Count('id'))
        .values('total')[:1]
    )

    creador_qs = (
        tusuario.objects
        .filter(idusuario=OuterRef('rutusercreador'))
        .values('nombreusuario')[:1]
    )

    entregas = (
        EntregaProyecto.objects
        .filter(idestadoentrega_id__in=[ESTADO_ENTREGA_DESARROLLO, ESTADO_ENTREGA_CORRECCIONES])
        .select_related(
            'idproyecto',
            'idproyecto__idcotizacion',
            'idproyecto__idcliente',
            'idproyecto__idtamano',
            'idtipoentrega',
            'idurgencia',
            'idestadoentrega',
        )
        .annotate(
            rut_cliente=F('idproyecto__idcliente__rut'),
            fecha_adjudicacion=F('idproyecto__fechaadjudicacion'),
            descripcion_urgencia=F('idurgencia__descrip'),
            simbolo_urgencia=F('idurgencia__simbolo'),
            nombre_usuario_creador=Subquery(
                creador_qs,
                output_field=CharField()
            ),
            nombre_proyecto=F('idproyecto__idcotizacion__nombreproyecto'),
            descripcion_tipo_entrega=F('idtipoentrega__descripcion'),
            descripcion_estado_entrega=F('idestadoentrega__descrip'),
            estado_proyecto=F('idproyecto__estado'),
            color_tipo_entrega=F('idtipoentrega__color'),
            descripcion_tamanio_proyecto=F('idproyecto__idtamano__descripcion'),
            observaciones=Coalesce(
                Subquery(observaciones_qs, output_field=IntegerField()),
                Value(0)
            ),
        )
        .order_by('-fechacalendario', '-identrega')
    )

    usernames = set()
    for e in entregas:
        rut_actual = _rut_desarrollador_actual(e)
        if rut_actual:
            usernames.add(rut_actual)

    mapa_usuarios = {
        u.username: (u.get_full_name().strip() or u.username)
        for u in User.objects.filter(username__in=usernames)
    }

    for e in entregas:
        rut_actual = _rut_desarrollador_actual(e)
        e.nombre_desarrollador_actual = mapa_usuarios.get(rut_actual, rut_actual or '')
        e.fecha_asignacion = _fecha_desarrollador_actual(e)
        e.nombre_usuario_creador = e.nombre_usuario_creador or e.rutusercreador or ''

    context = {
        'titulo': 'Entregas Desarrollo',
        'encabezado': 'Entregas en Desarrollo',
        'submenu': 'Listado entregas en desarrollo',
        'entregas': entregas,
    }
    return render(request, 'entregas_desarrollo.html', context)

@login_required
@require_GET
def listar_observaciones_catalogo(request):
    observaciones = (
        Observacion.objects
        .select_related('tipoobservacion', 'calificacion')
        .order_by('tipoobservacion__nombre', 'nombre')
    )

    data = []
    for o in observaciones:
        data.append({
            'id': o.id,
            'tipo': o.tipoobservacion.nombre if o.tipoobservacion else '',
            'descripcion': o.nombre or '',
            'calificacion': o.calificacion.nombre if o.calificacion else '',
        })

    return JsonResponse({'ok': True, 'observaciones': data})


@login_required
@require_POST
def agregar_observacion_entrega(request, identrega):
    idobservacion = request.POST.get('idobservacion')

    if not idobservacion:
        return JsonResponse({'ok': False, 'mensaje': 'Falta la observación.'}, status=400)

    entrega = get_object_or_404(EntregaProyecto, pk=identrega)
    observacion = get_object_or_404(Observacion, pk=idobservacion)

    existe = Entregaobservacion.objects.filter(
        entrega=entrega,
        observacion=observacion,
        estado=1
    ).exists()

    if existe:
        return JsonResponse({
            'ok': True,
            'mensaje': 'La observación ya estaba agregada a esta entrega.'
        })

    Entregaobservacion.objects.create(
        entrega=entrega,
        observacion=observacion,
        username=request.user,
        estado=1
    )

    return JsonResponse({
        'ok': True,
        'mensaje': 'Observación agregada correctamente.'
    })


@login_required
@require_POST
def crear_observacion_catalogo(request, identrega):
    idtipoobservacion = request.POST.get('idtipoobservacion')
    idcalificacion = request.POST.get('idcalificacion')
    descripcion = (request.POST.get('descripcion') or '').strip()

    if not idtipoobservacion:
        return JsonResponse({'ok': False, 'mensaje': 'Debes seleccionar el tipo.'}, status=400)

    if not idcalificacion:
        return JsonResponse({'ok': False, 'mensaje': 'Debes seleccionar la calificación.'}, status=400)

    if not descripcion:
        return JsonResponse({'ok': False, 'mensaje': 'Debes ingresar la descripción.'}, status=400)

    entrega = get_object_or_404(EntregaProyecto, pk=identrega)
    tipo = get_object_or_404(Tipoobservacion, pk=idtipoobservacion)
    calificacion = get_object_or_404(Calificacion, pk=idcalificacion)

    with transaction.atomic():
        obs = Observacion.objects.create(
            tipoobservacion=tipo,
            nombre=descripcion,
            calificacion=calificacion
        )

        Entregaobservacion.objects.create(
            entrega=entrega,
            observacion=obs,
            username=request.user,
            estado=1
        )

    return JsonResponse({
        'ok': True,
        'mensaje': 'Nueva observación creada y asignada a la entrega.',
        'idobservacion': obs.id
    })


@login_required
@require_POST
def entrega_revision_enviar_desarrollo(request, identrega):
    rut_user = request.user.username

    with transaction.atomic():
        entrega = get_object_or_404(
            EntregaProyecto.objects.select_for_update(),
            pk=identrega
        )

        if entrega.idestadoentrega_id != ESTADO_ENTREGA_REVISION:
            return JsonResponse({
                'ok': False,
                'mensaje': 'Solo se puede enviar a desarrollo una entrega en revisión.'
            }, status=400)

        rut_destino = _ultimo_desarrollador_asignado(entrega)
        if not rut_destino:
            return JsonResponse({
                'ok': False,
                'mensaje': 'No existe desarrollador previo para reenviar la entrega.'
            }, status=400)

        usuario_destino = User.objects.filter(
            username=rut_destino,
            is_active=True
        ).first()

        if not usuario_destino:
            return JsonResponse({
                'ok': False,
                'mensaje': 'El desarrollador asociado no existe o está inactivo.'
            }, status=400)

        evento = _registrar_evento(
            entrega,
            ['A Desarrollo', 'Enviar a Desarrollo'],
            origen=rut_user,
            destino=rut_destino
        )

        campos_desarrollo = _set_asignacion_desarrollo_por_flujo(
            entrega,
            rut_destino,
            evento.fechahora
        )

        entrega.idestadoentrega_id = ESTADO_ENTREGA_CORRECCIONES
        entrega.rutuserupdate = rut_user
        entrega.fechaupdate = evento.fechahora

        entrega.save(update_fields=[
            'idestadoentrega',
            'rutuserupdate',
            'fechaupdate',
            *campos_desarrollo
        ])

    return JsonResponse({
        'ok': True,
        'mensaje': 'Entrega enviada a correcciones correctamente.'
    })

@login_required
@require_POST
def entrega_revision_ok(request, identrega):
    rut_user = request.user.username

    with transaction.atomic():
        entrega = get_object_or_404(
            EntregaProyecto.objects.select_for_update(),
            pk=identrega
        )

        if entrega.idestadoentrega_id != ESTADO_ENTREGA_REVISION:
            return JsonResponse({
                'ok': False,
                'mensaje': 'Solo se puede marcar OK una entrega en revisión.'
            }, status=400)

        evento = _registrar_evento(
            entrega,
            ['Entrega OK', 'OK'],
            origen=rut_user,
            destino=''
        )

        entrega.idestadoentrega_id = ESTADO_ENTREGA_ENTREGADO
        entrega.fechacalendario = evento.fechahora
        entrega.rutuserupdate = rut_user
        entrega.fechaupdate = evento.fechahora

        entrega.save(update_fields=[
            'idestadoentrega',
            'fechacalendario',
            'rutuserupdate',
            'fechaupdate',
        ])

    return JsonResponse({
        'ok': True,
        'mensaje': 'Entrega marcada como OK correctamente.'
    })
