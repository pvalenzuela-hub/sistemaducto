from django.urls import path
from . import views
from .views import Vista1, Vista2, Vista3, VisorComentario

urlpatterns = [
    path('cotizaciones/', views.cotizaciones_home, name='cotizaciones_home'),
    path('cotizaciones/busqueda/', views.cotizaciones_busqueda, name='cotizaciones_busqueda'),
    path('cotizaciones/ingreso/', views.cotizaciones_ingreso, name='cotizaciones_ingreso'),
    path('cotizaciones/<int:pk>/', views.cotizacion_detalle, name='cotizacion_detalle'),
    path('cotizaciones/<int:pk>/editar/', views.cotizacion_editar, name='cotizacion_editar'),
    path('cotizaciones/<int:pk>/versionar/', views.cotizacion_versionar, name='cotizacion_versionar'),
    path('cotizaciones/<int:pk>/reporte/', views.cotizacion_reporte, name='cotizacion_reporte'),
    path('cotizaciones/<int:pk>/reporte/pdf/', views.cotizacion_reporte_pdf, name='cotizacion_reporte_pdf'),
    path('cotizaciones/api/mandantes/', views.api_cotizaciones_mandantes, name='api_cotizaciones_mandantes'),
    path('cotizaciones/api/mandantes/<int:pk>/', views.api_cotizaciones_mandante_detalle, name='api_cotizaciones_mandante_detalle'),
    path('cotizaciones/api/contactos/', views.api_cotizaciones_contactos, name='api_cotizaciones_contactos'),
    path('cotizaciones/api/contactos/<int:pk>/', views.api_cotizaciones_contacto_detalle, name='api_cotizaciones_contacto_detalle'),
    path('cotizaciones/api/items/', views.api_cotizaciones_items, name='api_cotizaciones_items'),
    path('cotizaciones/api/notas/', views.api_cotizaciones_notas, name='api_cotizaciones_notas'),
    path('cotizaciones/api/forma-pago/', views.api_cotizaciones_formapago, name='api_cotizaciones_formapago'),

    path('terminados/', Vista1.as_view(), name='vista1'),
    path('vistobueno/', Vista2.as_view(), name='vista2'),
    path('desarrollo/', Vista3.as_view(), name='vista3'),

    path('<int:pk>/<int:tabla>/', VisorComentario.as_view(), name='visor-comentario'),
    path('guardacomentario/', views.guardacomentario, name='graba-comentario'),

    path('listadocategorias/', views.ListaCategoria.as_view(), name='lista-categoria'),
    path('tipoentrega/', views.ListaTipoEntrega.as_view(), name='lista-tipo-entrega'),
    path('tipoentrega/crear/', views.tipo_entrega_create, name='crear-tipo-entrega'),
    path('tipoentrega/modificar/<int:pk>/', views.tipo_entrega_update, name='editar-tipo-entrega'),
    path('tipoentrega/eliminar/<int:pk>/', views.tipo_entrega_delete, name='eliminar-tipo-entrega'),

    path('proyecto/reporte/', views.proyectos_totales, name='reporte_proyectos'),
    path('clientes/reporte/', views.reporte_clientes, name='reporte_clientes'),
    path('clientes/totales/', views.clientes_totales, name='clientes_totales'),
    path('clientes/crear/', views.cliente_create, name='cliente_create'),
    path('clientes/principales/modificar/<int:pk>/', views.cliente_principal_update, name='cliente_principal_update'),
    path('clientes/agenda/', views.agenda_clientes, name='agenda_clientes'),
    path('clientes/agenda/eventos/', views.eventos_agenda_clientes, name='eventos_agenda_clientes'),
    path('clientes/agenda/crear/', views.crear_agenda_cliente, name='crear_agenda_cliente'),
    path('clientes/agenda/<int:agenda_id>/mover/', views.mover_agenda_cliente, name='mover_agenda_cliente'),
    path('clientes/modificar/<int:pk>/', views.cliente_update, name='cliente_update'),
    path('clientes/eliminar/<int:pk>/', views.cliente_delete, name='cliente_delete'),

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
