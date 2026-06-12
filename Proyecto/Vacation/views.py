
from django.views.generic import ListView, View, DetailView
#from django.views.generic import ListView
#from django.views.generic import TemplateView
from .models import Persona, Registrovac
from django.contrib.auth.models import User
from .form import *
from django.shortcuts import render, redirect,get_object_or_404
from django.contrib import messages

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
        personas = super().get_queryset()
        for persona in personas:
            persona.calcular_dias_vacaciones()
      
        return self.model.objects.order_by('user_per')

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
        usuario = Persona.objects.get(id=pk)
        persona = User.objects.get(id=usuario.user_per_id)
        contexto = {
            'registro': self.model.objects.filter(user_vac=pk),
            'encabezado': 'Detalle Vacaciones : '+persona.first_name+' '+persona.last_name,
        }
        return render(request, self.template_name, contexto)


def eliminar_registro_vacaciones(request, pk, reg_id):
    persona = get_object_or_404(Persona, pk=pk)
    registro = get_object_or_404(Registrovac, pk=reg_id, user_vac=persona)

    if request.method == 'POST':
        registro.delete()
        persona.calcular_dias_vacaciones()
        messages.success(request, 'El registro de vacaciones fue eliminado correctamente.')
        return redirect('detalle-vacaciones', pk=pk)

    return redirect('detalle-vacaciones', pk=pk)


def eliminar_persona_vacaciones(request, pk):
    persona = get_object_or_404(Persona, pk=pk)

    if request.method == 'POST':
        persona.registrovac_set.all().delete()
        persona.delete()
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
