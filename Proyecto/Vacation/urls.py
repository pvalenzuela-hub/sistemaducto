from django.urls import path
from . import views
from seguimiento.permisos import solo_director  # todas las pantallas de vacaciones: solo Director
from Vacation.views import PersonalListView, DetalleVacaciones,Registrovacaciones


# urlpatterns = [
#     #path('', views.home),
#     #path('', ProyectoListView.as_view(), name='gestion_proyectos')
#     #path('segProyecto/<idproyecto>', views.segProyecto)
#     path('', ProyectListView.as_view(template_name="listadoProyectos.html")),


# ]

urlpatterns = [
    path('listado/', solo_director(views.PersonalListView.as_view()) , name='listado-vacaciones'),
    # path('detalle/<int:id', views.PersonalListView.as_view() , name='personal'),
    path('detalle/<int:pk>',solo_director(DetalleVacaciones.as_view()), name='detalle-vacaciones'),
    path('detalle/<int:pk>/eliminar/<int:reg_id>/', solo_director(views.eliminar_registro_vacaciones), name='eliminar-registro-vacaciones'),
    path('eliminar/<int:pk>/', solo_director(views.eliminar_persona_vacaciones), name='eliminar-persona-vacaciones'),
    path('registro/', solo_director(views.Registrovacaciones),  name='registro-vacaciones'),
]
