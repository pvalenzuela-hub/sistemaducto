from django.urls import path

from . import views

urlpatterns = [
    path('usuarios/', views.usuario_list, name='usuario_list'),
    path('usuarios/crear/', views.usuario_create, name='usuario_create'),
    path('usuarios/<int:pk>/crear-persona/', views.usuario_crear_persona, name='usuario_crear_persona'),
    path('usuarios/<int:pk>/eliminar/', views.usuario_delete, name='usuario_delete'),
]
