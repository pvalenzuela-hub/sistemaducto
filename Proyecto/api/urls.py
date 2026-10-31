from django.urls import path

from . import views

app_name = 'api'

urlpatterns = [
    path('v1/facturas/', views.facturas_list, name='facturas_list'),
    path('v1/facturas/<int:idfactura>/', views.factura_detail, name='factura_detail'),
    path('v1/facturas/<int:idfactura>/comentarios/', views.factura_comentarios, name='factura_comentarios'),
    path('v1/facturas/<int:idfactura>/comentarios/<int:idreg>/', views.factura_comentario_detail,
         name='factura_comentario_detail'),
    path('v1/clientes/', views.clientes_list, name='clientes_list'),
]
