from django.urls import path

from . import views, views_proyectos

app_name = 'api'

urlpatterns = [
    path('v1/facturas/', views.facturas_list, name='facturas_list'),
    path('v1/facturas/<int:idfactura>/', views.factura_detail, name='factura_detail'),
    path('v1/facturas/<int:idfactura>/comentarios/', views.factura_comentarios, name='factura_comentarios'),
    path('v1/facturas/<int:idfactura>/comentarios/<int:idreg>/', views.factura_comentario_detail,
         name='factura_comentario_detail'),
    path('v1/clientes/', views.clientes_list, name='clientes_list'),
    path('v1/proyectos/', views_proyectos.proyectos_list, name='proyectos_list'),
    path('v1/proyectos/estados/', views_proyectos.proyecto_estados, name='proyecto_estados'),
    path('v1/proyectos/<int:idproyecto>/', views_proyectos.proyecto_detail, name='proyecto_detail'),
    path('v1/proyectos/<int:idproyecto>/comentarios/', views_proyectos.proyecto_comentarios,
         name='proyecto_comentarios'),
    path('v1/cotizaciones/', views_proyectos.cotizaciones_list, name='cotizaciones_list'),
    path('v1/cotizaciones/estados/', views_proyectos.cotizacion_estados, name='cotizacion_estados'),
    path('v1/cotizaciones/<int:idcotizacion>/', views_proyectos.cotizacion_detail, name='cotizacion_detail'),
]
