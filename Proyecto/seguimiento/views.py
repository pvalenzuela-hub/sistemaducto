import json
from django.shortcuts import render, redirect
from .models import *
import pyodbc
from django.conf import settings
from django.views.generic import TemplateView, ListView, DetailView
from django.views.decorators.http import require_POST, require_GET
from django.http import HttpResponseNotAllowed
from collections import defaultdict
from datetime import date

from django.db.models import Max, Prefetch, F, OuterRef, Subquery, Count, IntegerField, CharField, Value
from django.db import transaction, IntegrityError
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from datetime import timedelta, datetime
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models.functions import Coalesce
from .forms import ClienteForm, ClienteContactoFormSet, TipoEntregaForm




ESTADO_ENTREGA_NUEVA = 1
ESTADO_ENTREGA_DESARROLLO = 2
ESTADO_ENTREGA_CORRECCIONES = 3
ESTADO_ENTREGA_REVISION = 4
ESTADO_ENTREGA_ENTREGADO = 5
ESTADO_ENTREGA_NULA = 6

FECHA_MINIMA_COTIZACION = None
ESTADO_CLIENTE_ELIMINADO = 5

User = get_user_model()

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

@login_required
def reporte_clientes(request):
    # 1. Clientes principales no eliminados lógicamente
    clientes = list(
        Cliente.objects.filter(
            esprincipal=True
        )
        .exclude(idestadocliente_id=ESTADO_CLIENTE_ELIMINADO)
        .select_related('idestadocliente', 'idcomppago')
        .prefetch_related(
            Prefetch(
                'clientecategoria_set',
                queryset=ClienteCategoria.objects.select_related('idcategoria')
            )
        )
        .order_by('razonsocial')
    )

    if not clientes:
        return render(request, 'clientes/reporte_clientes.html', {
            'clientes': [],
            'encabezado': 'Clientes totales',
            'submenu': 'Lista total de clientes'
        })

    ids_principales = [c.idcliente for c in clientes]

    # 2. Última fecha de cotización del cliente principal
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

    # 3. Obtener hijos de esos clientes principales, excluyendo eliminados
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

    # 4. Última fecha de cotización de los hijos
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

    # 5. Armar datos finales del reporte
    for cliente in clientes:
        fecha_cliente = fechas_principal.get(cliente.idcliente) or FECHA_MINIMA_COTIZACION
        fecha_hijos = fechas_hijos_por_padre.get(cliente.idcliente) or FECHA_MINIMA_COTIZACION

        if fecha_cliente and fecha_hijos:
            cliente.fecha_ultima_cotizacion = max(fecha_cliente, fecha_hijos)
        else:
            cliente.fecha_ultima_cotizacion = fecha_cliente or fecha_hijos

        categorias = []
        for cc in cliente.clientecategoria_set.all():
            if cc.idcategoria:
                categorias.append(cc.idcategoria.NombreCat)

        cliente.categorias_texto = ', '.join(dict.fromkeys(categorias))

        cliente.estado_texto = cliente.idestadocliente.descrip if cliente.idestadocliente_id else ''
        cliente.comportamiento_pago_texto = cliente.idcomppago.descrip if cliente.idcomppago_id else ''

    return render(request, 'clientes/reporte_clientes.html', {
        'clientes': clientes,
        'encabezado': 'Clientes totales',
        'submenu': 'Lista total de clientes'
    })
    
@login_required
@transaction.atomic
def cliente_update(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)

    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente)
        formset_contactos = ClienteContactoFormSet(
            request.POST,
            instance=cliente,
            prefix='contactos'
        )

        if form.is_valid() and formset_contactos.is_valid():
            cliente = form.save()

            # Guardar contactos
            contactos = formset_contactos.save(commit=False)

            # Eliminar los marcados como DELETE
            for obj in formset_contactos.deleted_objects:
                obj.delete()

            for contacto in contactos:
                contacto.idcliente = cliente

                if not contacto.fecharegistro:
                    contacto.fecharegistro = timezone.now()

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

            messages.success(request, 'Cliente modificado correctamente.')
            return redirect('reporte_clientes')

        messages.error(request, 'Corrige los errores del formulario.')

    else:
        form = ClienteForm(instance=cliente)
        formset_contactos = ClienteContactoFormSet(
            instance=cliente,
            prefix='contactos'
        )

    context = {
        'titulo': 'Modificar cliente',
        'encabezado': 'Modificar cliente',
        'submenu': 'Edición de cliente',
        'form': form,
        'formset_contactos': formset_contactos,
        'cliente': cliente,
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
        return redirect('reporte_clientes')

    context = {
        'titulo': 'Eliminar cliente',
        'encabezado': 'Eliminar cliente',
        'submenu': 'Confirmación de eliminación',
        'cliente': cliente,
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
        pro.numcotizacion_texto = cot.numcotizacion if cot else ''
        pro.numcorr_texto = cot.numcorr if cot else ''
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
        fechacreacion=timezone.now(),
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
        entrega.fechaanulacion = timezone.now()
        entrega.rutuserupdate = rut_user
        entrega.fechaupdate = timezone.now()

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
        entrega.fechaupdate = timezone.now()
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
