from django.shortcuts import render, redirect
from .models import *
import pyodbc
from django.conf import settings
from django.views.generic import TemplateView, ListView, DetailView
from django.http import HttpResponseNotAllowed


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
def home(request):
    return redirect('vista1')
    


class ListaCategoria(ListView):
    model = T_Categoria
    template_name = 'listacategoria.html'

    def get_queryset(self):
        return self.model.objects.all().order_by('NombreCat').reverse()

    def get(self, request, *args, **kwargs):
        contexto = {
            'categorias': self.get_queryset(),
            'encabezado': 'Listado de Categorías',
            'menu': 'Parámetros',
            'submenu': 'categorías',
            'titulo': 'Listado'
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
            "submenu": "Listado de Proyectos Con Visto Bueno para Facturar",
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
            "submenu": "Listado de Proyectos en Desarrollo para Facturar",
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