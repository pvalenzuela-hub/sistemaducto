from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import (
    Cliente,
    Clientecontacto,
    ClienteCategoria,
    T_Categoria,
    Testadocliente,
    Tcomppago,
    TipoEntrega,
)


def calcular_dv_rut(rut: int) -> str:
    rut_reverso = map(int, reversed(str(rut)))
    factores = [2, 3, 4, 5, 6, 7]

    suma = 0
    for i, digito in enumerate(rut_reverso):
        suma += digito * factores[i % len(factores)]

    resto = 11 - (suma % 11)

    if resto == 11:
        return '0'
    if resto == 10:
        return 'K'
    return str(resto)


class DescripModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.descrip or str(obj.pk)


class ClienteRelacionadoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.razonsocial or f"Cliente {obj.pk}"


class CategoriaModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.NombreCat or str(obj.pk)


class TipoEntregaForm(forms.ModelForm):
    class Meta:
        model = TipoEntrega
        fields = ['descripcion', 'color', 'factorTiempo']
        widgets = {
            'factorTiempo': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for _, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'

        self.fields['descripcion'].label = 'Descripcion'
        self.fields['color'].label = 'Color'
        self.fields['factorTiempo'].label = 'Factor de tiempo'

        self.fields['descripcion'].required = True
        self.fields['color'].required = False

        self.fields['descripcion'].widget.attrs.update({
            'placeholder': 'Ingrese la descripcion del tipo de entrega',
        })
        self.fields['color'].widget.attrs.update({
            'placeholder': 'Ejemplo: #0d6efd',
        })
        self.fields['factorTiempo'].widget.attrs.update({
            'placeholder': '0.00',
        })

    def clean_descripcion(self):
        valor = (self.cleaned_data.get('descripcion') or '').strip()
        if not valor:
            raise ValidationError('La descripcion es obligatoria.')
        return valor

    def clean_color(self):
        valor = (self.cleaned_data.get('color') or '').strip()
        return valor or None


class ClienteForm(forms.ModelForm):
    esprincipal = forms.TypedChoiceField(
        label='Es principal',
        choices=(
            ('True', 'Sí'),
            ('False', 'No'),
        ),
        coerce=lambda x: True if x == 'True' else False if x == 'False' else None,
        empty_value=None,
        required=True,
        widget=forms.Select()
    )

    idcliente_p = ClienteRelacionadoChoiceField(
        queryset=Cliente.objects.all().order_by('razonsocial'),
        required=False,
        label='Cliente Principal',
        empty_label='---------'
    )

    idestadocliente = DescripModelChoiceField(
        queryset=Testadocliente.objects.all().order_by('descrip'),
        required=True,
        label='Estado cliente',
        empty_label='Seleccione estado cliente'
    )

    idcomppago = DescripModelChoiceField(
        queryset=Tcomppago.objects.all().order_by('descrip'),
        required=True,
        label='Comportamiento pago',
        empty_label='Seleccione comportamiento pago'
    )

    categorias = CategoriaModelMultipleChoiceField(
        queryset=T_Categoria.objects.all().order_by('NombreCat'),
        required=False,
        label='Categorías',
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': 8})
    )

    class Meta:
        model = Cliente
        exclude = ['insercion', 'estado']
        widgets = {
            'comentario': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for _, field in self.fields.items():
            if isinstance(field.widget, forms.SelectMultiple):
                existing = field.widget.attrs.get('class', '')
                field.widget.attrs['class'] = (existing + ' form-select').strip()
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs['class'] = 'form-control'
            else:
                field.widget.attrs['class'] = 'form-control'

        self.fields['rut'].required = False
        self.fields['dvrut'].required = False
        self.fields['razonsocial'].required = True
        self.fields['esprincipal'].required = True
        self.fields['idestadocliente'].required = True
        self.fields['idcomppago'].required = True

        self.fields['rut'].label = 'RUT Cliente'
        self.fields['dvrut'].label = ''
        self.fields['razonsocial'].label = 'Razón Social'
        self.fields['direccion'].label = 'Dirección'
        self.fields['telefono'].label = 'Teléfono'
        self.fields['horariollamada'].label = 'Horario Llamada'
        self.fields['direcfactura'].label = 'Dirección Facturación'
        self.fields['horariorecep'].label = 'Horario de Recepción'
        self.fields['direcretiroch'].label = 'Dirección de Retiro'
        self.fields['horarioretiroch'].label = 'Horario de Retiro CH'
        self.fields['idcliente_p'].label = 'Cliente Principal'
        self.fields['idestadocliente'].label = 'Estado cliente'
        self.fields['idcomppago'].label = 'Comportamiento pago'
        self.fields['comentario'].label = 'Notas'
        self.fields['categorias'].label = 'Categorías'

        self.fields['rut'].widget.attrs.update({
            'placeholder': 'Ingrese RUT sin puntos ni guión',
            'step': '1',
        })
        self.fields['dvrut'].widget.attrs.update({
            'maxlength': '1',
            'placeholder': 'DV',
            'style': 'text-transform: uppercase;',
        })

        if self.instance and self.instance.pk:
            self.fields['idcliente_p'].queryset = Cliente.objects.exclude(
                pk=self.instance.pk
            ).order_by('razonsocial')

            categorias_ids = ClienteCategoria.objects.filter(
                idcliente=self.instance
            ).values_list('idcategoria_id', flat=True)
            self.fields['categorias'].initial = list(categorias_ids)

        esprincipal_actual = None

        if self.is_bound:
            valor_post = self.data.get(self.add_prefix('esprincipal'))
            if valor_post == 'True':
                esprincipal_actual = True
            elif valor_post == 'False':
                esprincipal_actual = False
        elif self.instance and self.instance.pk is not None:
            esprincipal_actual = self.instance.esprincipal

        if esprincipal_actual is True:
            self.fields['idcliente_p'].widget.attrs['disabled'] = 'disabled'

    def clean_razonsocial(self):
        valor = (self.cleaned_data.get('razonsocial') or '').strip()
        if not valor:
            raise ValidationError('La Razón Social no puede estar vacía.')
        return valor

    def clean_dvrut(self):
        valor = self.cleaned_data.get('dvrut')
        if valor:
            return valor.strip().upper()
        return valor

    def clean(self):
        cleaned_data = super().clean()

        rut = cleaned_data.get('rut')
        dvrut = cleaned_data.get('dvrut')
        esprincipal = cleaned_data.get('esprincipal')
        idcliente_p = cleaned_data.get('idcliente_p')

        if rut not in (None, ''):
            try:
                rut_int = int(rut)
            except (ValueError, TypeError):
                self.add_error('rut', 'El RUT debe ser numérico.')
            else:
                if not dvrut:
                    self.add_error('dvrut', 'Debe ingresar el dígito verificador.')
                else:
                    dv_esperado = calcular_dv_rut(rut_int)
                    if dvrut.upper() != dv_esperado:
                        self.add_error(
                            'dvrut',
                            f'El dígito verificador no corresponde al RUT ingresado. Debe ser {dv_esperado}.'
                        )

        if dvrut and rut in (None, ''):
            self.add_error('rut', 'Debe ingresar el RUT Cliente si informa dígito verificador.')

        if esprincipal not in (True, False):
            self.add_error('esprincipal', 'Debe indicar si el cliente es principal.')

        if esprincipal is False and not idcliente_p:
            self.add_error(
                'idcliente_p',
                'Debe seleccionar un Cliente Principal cuando "Es principal" es "No".'
            )

        if esprincipal is True:
            cleaned_data['idcliente_p'] = None

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        if instance.esprincipal is True:
            instance.idcliente_p = None

        if commit:
            instance.save()
            self.save_m2m()

        return instance


TIPO_CONTACTO_CHOICES = (
    ('', 'Seleccione'),
    ('N', 'N - Normal'),
    ('F', 'F - Facturación'),
    ('C', 'C - Comercial'),
)


class ClienteContactoForm(forms.ModelForm):
    tipocontacto = forms.ChoiceField(
        choices=TIPO_CONTACTO_CHOICES,
        required=False,
        label='Tipo',
        widget=forms.Select()
    )

    class Meta:
        model = Clientecontacto
        exclude = ['idcliente', 'fecharegistro']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for _, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs['class'] = 'form-control'

        self.fields['tipocontacto'].label = 'Tipo'
        self.fields['nombrecontacto'].label = 'Contacto'
        self.fields['cargo'].label = 'Cargo'
        self.fields['telefono'].label = 'Teléfonos'
        self.fields['email'].label = 'eMail'

        self.fields['tipocontacto'].required = False
        self.fields['nombrecontacto'].required = False
        self.fields['cargo'].required = False
        self.fields['telefono'].required = False
        self.fields['email'].required = False

    def clean_tipocontacto(self):
        valor = (self.cleaned_data.get('tipocontacto') or '').strip().upper()

        if valor and valor not in {'N', 'F', 'C'}:
            raise ValidationError('El tipo de contacto solo permite N, F o C.')

        return valor

    def clean(self):
        cleaned_data = super().clean()

        tipocontacto = (cleaned_data.get('tipocontacto') or '').strip()
        nombrecontacto = (cleaned_data.get('nombrecontacto') or '').strip()
        cargo = (cleaned_data.get('cargo') or '').strip()
        telefono = (cleaned_data.get('telefono') or '').strip()
        email = (cleaned_data.get('email') or '').strip()
        marcado_delete = cleaned_data.get('DELETE', False)

        fila_vacia = not any([tipocontacto, nombrecontacto, cargo, telefono, email])

        if not marcado_delete and not fila_vacia:
            if not tipocontacto:
                self.add_error('tipocontacto', 'Debe seleccionar el tipo.')
            if not nombrecontacto:
                self.add_error('nombrecontacto', 'Debe ingresar el nombre del contacto.')

        return cleaned_data


ClienteContactoFormSet = inlineformset_factory(
    Cliente,
    Clientecontacto,
    form=ClienteContactoForm,
    extra=1,
    can_delete=True
)
