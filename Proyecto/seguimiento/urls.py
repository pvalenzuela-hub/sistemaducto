from django.urls import path
from . import views
from . views import Vista1, Vista2, Vista3, VisorComentario, guardacomentario, ListaCategoria, HomeView



urlpatterns = [
    path('terminados/', Vista1.as_view(),name='vista1'),
    path('vistobueno/', Vista2.as_view(),name='vista2'),
    path('desarrollo/', Vista3.as_view(),name='vista3'),
    path("<int:pk>/<int:tabla>/", VisorComentario.as_view(), name="visor-comentario"),
    path('guardacomentario/', views.guardacomentario,name="graba-comentario"),
    path('listadocategorias/', views.ListaCategoria.as_view(),name="lista-categoria"),
    path('tipoentrega/', views.ListaTipoEntrega.as_view(), name='lista-tipo-entrega'),
    
    path('clientes/reporte/', views.reporte_clientes, name='reporte_clientes'),
    
    path('proyecto/reporte/', views.proyectos_totales, name='reporte_proyectos'),
    
    path('proyecto/calendario/', views.calendario_entregas_proyecto, name='calendario_entregas_proyecto'),
    path('proyecto/calendario/eventos/', views.eventos_calendario_entregas, name='eventos_calendario_entregas'),
    path('proyecto/calendario/entrega/crear/', views.crear_entrega_proyecto, name='crear_entrega_proyecto'),
    path('proyecto/calendario/usuarios-desarrollo/', views.usuarios_desarrollo_activos, name='usuarios_desarrollo_activos'),
    path('proyecto/calendario/entrega/<int:identrega>/anular/', views.anular_entrega, name='anular_entrega'),
    path('proyecto/calendario/entrega/<int:identrega>/asignar-desarrollo/', views.asignar_entrega_desarrollo, name='asignar_entrega_desarrollo'),

]