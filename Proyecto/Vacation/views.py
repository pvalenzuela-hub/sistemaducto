
from django.views.generic import ListView, View, DetailView
#from django.views.generic import ListView
#from django.views.generic import TemplateView
from .models import Persona, Registrovac
from django.contrib.auth.models import User
from .form import *
from django.shortcuts import render, redirect,get_object_or_404
from django.contrib import messages
from django.http import Http404

from seguimiento.servicios import vacaciones as srv_vacaciones

# Create your views here.

##########################
# VISTA BASADA EN CLASES #
##########################
class PersonalListView(ListView):
    # nombre de la plantilla que va a ser renderizada
    model = Persona
    template_name = 'listadopersonal.html'
    context_object_name = 'personas'
    
    def get_queryset(self):
        return srv_vacaciones.personas()  # recalcula los días de cada persona a hoy

    def get(self,request,*args,**kwargs):
        contexto = {
            'personas':self.get_queryset(),
            'titulo': 'Personal',
            'encabezado': 'Vacaciones'
        }
        return render(request,self.template_name,contexto)

class DetalleVacaciones(DetailView):
    # nombre de la plantilla que va a ser renderizada
    model = Registrovac
    
    template_name = 'consultaVacaciones.html'
    def get(self, request, *args, **kwargs):
        pk = self.kwargs.get('pk')
        usuario = srv_vacaciones.persona(pk)
        if usuario is None:
            raise Persona.DoesNotExist
        persona = usuario.user_per
        contexto = {
            'registro': srv_vacaciones.registros(pk),
            'encabezado': 'Detalle Vacaciones : '+persona.first_name+' '+persona.last_name,
        }
        return render(request, self.template_name, contexto)


def eliminar_registro_vacaciones(request, pk, reg_id):
    persona = srv_vacaciones.persona(pk)
    registro = srv_vacaciones.registro(pk, reg_id) if persona else None
    if registro is None:
        raise Http404('Registro no encontrado.')

    if request.method == 'POST':
        srv_vacaciones.eliminar_registro(persona, registro)
        messages.success(request, 'El registro de vacaciones fue eliminado correctamente.')
        return redirect('detalle-vacaciones', pk=pk)

    return redirect('detalle-vacaciones', pk=pk)


def eliminar_persona_vacaciones(request, pk):
    persona = srv_vacaciones.persona(pk)
    if persona is None:
        raise Http404('Persona no encontrada.')

    if request.method == 'POST':
        srv_vacaciones.eliminar_persona(persona)
        messages.success(request, 'La persona fue eliminada del módulo de vacaciones.')
        return redirect('listado-vacaciones')

    return redirect('listado-vacaciones')

def Registrovacaciones(request):
    form = UserForm
    mydict = {
        'form': form
    }
    if request.method == 'POST':
        formulario = form(data=request.POST)
        if formulario.is_valid():
            formulario.save()
            # messages.success(request,'Usuario creado exitosamente!')
            return redirect('listado-vacaciones')
        mydict["form"] = formulario
    return render(request,'vacaciones.html', context=mydict)
