from django.urls import path
from . import views
from .views import Vista1, Vista2, Vista3, VisorComentario

urlpatterns = [
    path('terminados/', Vista1.as_view(), name='vista1'),
    path('vistobueno/', Vista2.as_view(), name='vista2'),
    path('desarrollo/', Vista3.as_view(), name='vista3'),

    path('<int:pk>/<int:tabla>/', VisorComentario.as_view(), name='visor-comentario'),
    path('guardacomentario/', views.guardacomentario, name='graba-comentario'),

    path('listadocategorias/', views.ListaCategoria.as_view(), name='lista-categoria'),
    path('tipoentrega/', views.ListaTipoEntrega.as_view(), name='lista-tipo-entrega'),

    path('clientes/reporte/', views.reporte_clientes, name='reporte_clientes'),
    path('proyecto/reporte/', views.proyectos_totales, name='reporte_proyectos'),

    # Calendario entregas
    path('proyecto/calendario/', views.calendario_entregas_proyecto, name='calendario_entregas_proyecto'),
    path('proyecto/calendario/eventos/', views.eventos_calendario_entregas, name='eventos_calendario_entregas'),
    path('proyecto/calendario/entrega/crear/', views.crear_entrega_proyecto, name='crear_entrega_proyecto'),
    path('proyecto/calendario/usuarios-desarrollo/', views.usuarios_desarrollo_activos, name='usuarios_desarrollo_activos'),
    path('proyecto/calendario/entrega/<int:identrega>/anular/', views.anular_entrega, name='anular_entrega'),
    path('proyecto/calendario/entrega/<int:identrega>/asignar-desarrollo/', views.asignar_entrega_desarrollo, name='asignar_entrega_desarrollo'),
    path('proyecto/calendario/entrega/<int:identrega>/mover/', views.mover_entrega_calendario, name='mover_entrega_calendario'),

    # Listados
    path('proyecto/entregas-general/', views.entregas_general, name='entregas_general'),
    path('proyecto/entregas-revision/', views.entregas_revision, name='entregas_revision'),
    path('proyecto/entregas-desa/', views.entregas_desarrollo, name='entregas_desarrollo'),

    # Visor entrega
    path('entregas/visor/<int:identrega>/', views.visor_entrega, name='visor_entrega'),

    # Observaciones
    path('entregas/observaciones/catalogo/', views.listar_observaciones_catalogo, name='listar_observaciones_catalogo'),
    path('entregas/<int:identrega>/observaciones/agregar/', views.agregar_observacion_entrega, name='agregar_observacion_entrega'),
    path('entregas/<int:identrega>/observaciones/crear/', views.crear_observacion_catalogo, name='crear_observacion_catalogo'),

    # Flujo revisión / desarrollo
    path('entregas/<int:identrega>/revision/enviar-desarrollo/', views.entrega_revision_enviar_desarrollo, name='entrega_revision_enviar_desarrollo'),
    path('entregas/<int:identrega>/revision/entrega-ok/', views.entrega_revision_ok, name='entrega_revision_ok'),
    path('usuarios/revision/activos/', views.usuarios_revision_activos, name='usuarios_revision_activos'),
    path('entregas/<int:identrega>/desarrollo/enviar-revision/', views.enviar_entrega_revision, name='enviar_entrega_revision'),
]