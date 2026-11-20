from django.urls import path
from . import views, views_facturas, views_seremi
from .views import Vista1, Vista2, Vista3, VistaSeguimiento, VisorComentario

urlpatterns = [
    path('cotizaciones/', views.cotizaciones_home, name='cotizaciones_home'),
    path('cotizaciones/busqueda/', views.cotizaciones_busqueda, name='cotizaciones_busqueda'),
    path('cotizaciones/seguimiento/', views.cotizaciones_seguimiento, name='cotizaciones_seguimiento'),
    path('cotizaciones/<int:pk>/seguimiento/historial/', views.cotizacion_seguimiento_historial, name='cotizacion_seguimiento_historial'),
    path('cotizaciones/ingreso/', views.cotizaciones_ingreso, name='cotizaciones_ingreso'),
    path('cotizaciones/<int:pk>/visor/', views.cotizacion_visor, name='cotizacion_visor'),
    path('cotizaciones/<int:pk>/seguimiento/', views.cotizacion_seguimiento, name='cotizacion_seguimiento'),
    path('cotizaciones/<int:pk>/', views.cotizacion_detalle, name='cotizacion_detalle'),
    path('cotizaciones/<int:pk>/editar/', views.cotizacion_editar, name='cotizacion_editar'),
    path('cotizaciones/<int:pk>/versionar/', views.cotizacion_versionar, name='cotizacion_versionar'),
    path('cotizaciones/<int:pk>/reporte/pdf/', views.cotizacion_reporte_pdf, name='cotizacion_reporte_pdf'),
    path('cotizaciones/api/mandantes/', views.api_cotizaciones_mandantes, name='api_cotizaciones_mandantes'),
    path('cotizaciones/api/mandantes/<int:pk>/', views.api_cotizaciones_mandante_detalle, name='api_cotizaciones_mandante_detalle'),
    path('cotizaciones/api/contactos/', views.api_cotizaciones_contactos, name='api_cotizaciones_contactos'),
    path('cotizaciones/api/contactos/<int:pk>/', views.api_cotizaciones_contacto_detalle, name='api_cotizaciones_contacto_detalle'),
    path('cotizaciones/api/items/', views.api_cotizaciones_items, name='api_cotizaciones_items'),
    path('cotizaciones/api/notas/', views.api_cotizaciones_notas, name='api_cotizaciones_notas'),
    path('cotizaciones/api/forma-pago/', views.api_cotizaciones_formapago, name='api_cotizaciones_formapago'),

    path('terminados/', Vista1.as_view(), name='vista1'),
    path('proyectos/seguimiento/', VistaSeguimiento.as_view(), name='seguimiento_proyectos'),
    path('proyectos/seguimiento/guardar/', views.guardar_seguimiento_proyecto, name='guardar_seguimiento_proyecto'),
    path('proyectos/seguimiento/guardar-facturacion/', views.guardar_datos_facturacion_proyecto, name='guardar_datos_facturacion_proyecto'),
    path('proyectos/seguimiento/crear-factura/', views.crear_factura_proyecto, name='crear_factura_proyecto'),
    path('proyectos/seguimiento/api/valor-uf/', views.api_valor_uf_por_fecha, name='api_valor_uf_por_fecha'),
    path('proyectos/seremi/', views_seremi.seremi_seguimiento, name='seremi_seguimiento'),
    path('proyectos/seremi/<int:idproyecto>/', views_seremi.seremi_proyecto, name='seremi_proyecto'),
    path('proyectos/seremi/<int:idproyecto>/datos/', views_seremi.seremi_guardar_datos, name='seremi_guardar_datos'),
    path('proyectos/seremi/<int:idproyecto>/estado/', views_seremi.seremi_cambiar_estado, name='seremi_cambiar_estado'),
    path('proyectos/seremi/<int:idproyecto>/comentarios/', views_seremi.seremi_comentario_agregar, name='seremi_comentario_agregar'),
    path('proyectos/seremi/<int:idproyecto>/comentarios/<int:idcomentario>/eliminar/', views_seremi.seremi_comentario_eliminar, name='seremi_comentario_eliminar'),
    path('facturas/seguimiento/', views_facturas.facturas_seguimiento, name='facturas_seguimiento'),
    path('facturas/<int:idfactura>/seguimiento/', views_facturas.factura_seguimiento_detalle, name='factura_seguimiento_detalle'),
    path('facturas/<int:idfactura>/seguimiento/guardar/', views_facturas.factura_seguimiento_guardar, name='factura_seguimiento_guardar'),
    path('facturas/<int:idfactura>/comentarios/<int:idreg>/editar/', views_facturas.factura_comentario_editar, name='factura_comentario_editar'),
    path('facturas/<int:idfactura>/comentarios/<int:idreg>/eliminar/', views_facturas.factura_comentario_eliminar, name='factura_comentario_eliminar'),
    path('facturas/<int:idfactura>/facturacion/', views_facturas.factura_facturacion, name='factura_facturacion'),
    path('facturas/<int:idfactura>/datos/', views_facturas.factura_datos, name='factura_datos'),
    path('facturas/<int:idfactura>/eliminar/', views_facturas.factura_eliminar, name='factura_eliminar'),
    path('facturas/por-numero/', views_facturas.factura_por_numero, name='factura_por_numero'),
    path('facturas/proyecto/<int:idproyecto>/glosa/', views_facturas.factura_glosa, name='factura_glosa'),
    path('facturas/proyecto/<int:idproyecto>/grabar/', views_facturas.factura_grabar, name='factura_grabar'),
    path('facturas/clientes/<int:idcliente>/notas/', views_facturas.cliente_notas_guardar, name='cliente_notas_guardar'),
    path('vistobueno/', Vista2.as_view(), name='vista2'),
    path('desarrollo/', Vista3.as_view(), name='vista3'),

    path('<int:pk>/<int:tabla>/', VisorComentario.as_view(), name='visor-comentario'),
    path('guardacomentario/', views.guardacomentario, name='graba-comentario'),

    path('listadocategorias/', views.ListaCategoria.as_view(), name='lista-categoria'),
    path('tipoentrega/', views.ListaTipoEntrega.as_view(), name='lista-tipo-entrega'),
    path('tipoentrega/crear/', views.tipo_entrega_create, name='crear-tipo-entrega'),
    path('tipoentrega/modificar/<int:pk>/', views.tipo_entrega_update, name='editar-tipo-entrega'),
    path('tipoentrega/eliminar/<int:pk>/', views.tipo_entrega_delete, name='eliminar-tipo-entrega'),
    path('valor-uf/', views.ListaValorUF.as_view(), name='lista-valor-uf'),
    path('valor-uf/crear/', views.valor_uf_create, name='crear-valor-uf'),
    path('valor-uf/modificar/<str:pk>/', views.valor_uf_update, name='editar-valor-uf'),
    path('valor-uf/eliminar/<str:pk>/', views.valor_uf_delete, name='eliminar-valor-uf'),

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
