from django import forms
from django.forms import ModelForm, widgets

from .models import *

class PersonaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        nombre = obj.user_per.get_full_name().strip()
        return nombre if nombre else obj.user_per.username
        
class UserForm(forms.ModelForm):
    user_vac = PersonaChoiceField(
        queryset=Persona.objects.select_related('user_per').all(),
        widget=forms.Select(attrs={'class': 'form-control select2'}),
        label='Usuario'
    )
    
    class Meta:
        model = Registrovac
        fields = "__all__"
        widgets = {
            'fecini': forms.DateInput(attrs={'class': 'form-control','type':"date"}),
            'fecfin': forms.DateInput(attrs={'class': 'form-control','type':"date"}),
            'dias_vacaciones': forms.NumberInput(attrs={'class': 'form-control'}),
        }


    
