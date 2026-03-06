from django import forms
from django.forms import ModelForm, widgets

from .models import *

    
class UserForm(forms.ModelForm):
    class Meta:
        model = Registrovac
        fields = "__all__"
        widgets = {
            'user_vac_id': forms.TextInput(attrs={'class':'form-control',}),
            'fecini': forms.DateInput(attrs={'class': 'form-control','type':"date"}),
            'fecfin': forms.DateInput(attrs={'class': 'form-control','type':"date"}),
            'dias_vacaciones': forms.NumberInput(attrs={'class': 'form-control'}),
        }


    
