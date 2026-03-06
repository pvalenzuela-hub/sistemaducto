from django.urls import path
from . import views
from . views import Vista1, Vista2, Vista3, VisorComentario, guardacomentario, ListaCategoria



urlpatterns = [
    # path('', views.index,name="index"),
    path('terminados/', Vista1.as_view(),name='vista1'),
    path('vistobueno/', Vista2.as_view(),name='vista2'),
    path('desarrollo/', Vista3.as_view(),name='vista3'),
    path("<int:pk>/<int:tabla>/", VisorComentario.as_view(), name="visor-comentario"),
    path('guardacomentario/', views.guardacomentario,name="graba-comentario"),
    path('listadocategorias/', views.ListaCategoria.as_view(),name="lista-categoria"),
    path('tipoentrega/', views.ListaTipoEntrega.as_view(), name='lista-tipo-entrega'),


]