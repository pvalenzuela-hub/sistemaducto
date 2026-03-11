from django.shortcuts import render, redirect
from .models import *
import pyodbc
from django.conf import settings
from django.views.generic import TemplateView, ListView, DetailView
from django.http import HttpResponseNotAllowed
from collections import defaultdict
from datetime import date

from django.db.models import Max, Prefetch
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from datetime import timedelta

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
class HomeView(TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "titulo": "Inicio",
            "encabezado": "Ducto Proyectos",
        })
        return context
    
class ListaCategoria(ListView):
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
    
class Vista1(TemplateView):
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


class Vista2(TemplateView):
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


class Vista3(TemplateView):
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

class VisorComentario(DetailView):
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

class ListaTipoEntrega(ListView):
    model = TipoEntrega
    template_name = 'listatipoentrega.html'
    context_object_name = 'tipos_entrega'

    def get_queryset(self):
        return self.model.objects.all().order_by('descripcion')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'encabezado': 'Listado de Tipos de Entrega',
            'menu': 'Parámetros',
            'submenu': 'Tipos de Entrega',
            'titulo': 'Listado',
        })
        return context
    
FECHA_MINIMA_COTIZACION = date(1900, 1, 1)

def reporte_clientes(request):
    # 1. Clientes principales activos
    clientes = list(
        Cliente.objects.filter(
            estado='A',
            esprincipal=True
        )
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
        return render(request, 'clientes/reporte_clientes.html', {'clientes': []})

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

    # 3. Obtener hijos de esos clientes principales
    hijos_qs = (
        Cliente.objects
        .filter(idcliente_p__in=ids_principales)
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

            if id_padre and fecha_hijo > fechas_hijos_por_padre[id_padre]:
                fechas_hijos_por_padre[id_padre] = fecha_hijo

    # 5. Armar datos finales del reporte
    for cliente in clientes:
        fecha_cliente = fechas_principal.get(cliente.idcliente) or FECHA_MINIMA_COTIZACION
        fecha_hijos = fechas_hijos_por_padre.get(cliente.idcliente) or FECHA_MINIMA_COTIZACION

        cliente.fecha_ultima_cotizacion = max(fecha_cliente, fecha_hijos)

        categorias = []
        for cc in cliente.clientecategoria_set.all():
            if cc.idcategoria:
                categorias.append(cc.idcategoria.NombreCat)

        # evita repetir categorías y conserva orden
        cliente.categorias_texto = ', '.join(dict.fromkeys(categorias))

        # textos para mostrar en la tabla
        cliente.estado_texto = cliente.idestadocliente.descrip if cliente.idestadocliente_id else ''
        cliente.comportamiento_pago_texto = cliente.idcomppago.descrip if cliente.idcomppago_id else ''

    return render(request, 'clientes/reporte_clientes.html', {
        'clientes': clientes,
        'encabezado': 'Clientes totales',
        'submenu': 'Lista total de clientes'
    })
    
    
def formatear_numero_cl(valor):
    valor = valor or 0
    return f"{valor:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
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

def calendario_entregas_proyecto(request):
    context = {
        'titulo': 'Calendario de entregas',
        'encabezado': 'Calendario de entregas de proyectos',
        'submenu': 'Agenda mensual de entregas',
    }
    return render(request, 'calendario_entregas_proyecto.html', context)


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
        idestadoentrega_id=6
    )

    if start_local:
        qs = qs.filter(fechacalendario__gte=start_local)

    if end_local:
        qs = qs.filter(fechacalendario__lt=end_local)

    eventos = []

    for e in qs:
        proyecto_codigo = ''
        proyecto_nombre = ''

        if e.idproyecto:
            proyecto_codigo = str(e.idproyecto.idproyecto)
            if e.idproyecto.idcotizacion:
                proyecto_nombre = e.idproyecto.idcotizacion.nombreproyecto or ''

        color = '#6c757d'
        if e.idestadoentrega_id == 5:
            color = '#b3ad9f'
        elif e.idtipoentrega and e.idtipoentrega.color:
            color = e.idtipoentrega.color

        hora_txt = e.fechacalendario.strftime('%H:%M') if e.fechacalendario else ''
        titulo = f"{hora_txt} {proyecto_codigo} - {proyecto_nombre}".strip()

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
            }
        })

    return JsonResponse(eventos, safe=False)