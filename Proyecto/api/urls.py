from django.urls import path

from . import views

app_name = 'api'

urlpatterns = [
    path('v1/facturas/', views.facturas_list, name='facturas_list'),
    path('v1/facturas/<int:idfactura>/', views.factura_detail, name='factura_detail'),
]
