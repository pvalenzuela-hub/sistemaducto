from django.urls import path
from . import views
from Vacation.views import PersonalListView, DetalleVacaciones,Registrovacaciones


# urlpatterns = [
#     #path('', views.home),
#     #path('', ProyectoListView.as_view(), name='gestion_proyectos')
#     #path('segProyecto/<idproyecto>', views.segProyecto)
#     path('', ProyectListView.as_view(template_name="listadoProyectos.html")),


# ]

urlpatterns = [
    path('listado/', views.PersonalListView.as_view() , name='listado-vacaciones'),
    # path('detalle/<int:id', views.PersonalListView.as_view() , name='personal'),
    path('detalle/<int:pk>',DetalleVacaciones.as_view(), name='detalle-vacaciones'),
    path('detalle/<int:pk>/eliminar/<int:reg_id>/', views.eliminar_registro_vacaciones, name='eliminar-registro-vacaciones'),
    path('eliminar/<int:pk>/', views.eliminar_persona_vacaciones, name='eliminar-persona-vacaciones'),
    path('registro/', views.Registrovacaciones,  name='registro-vacaciones'),
]
