from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.dateformat import DateFormat

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'formatted_date_joined')
    def formatted_date_joined(self, obj):
        return DateFormat(obj.date_joined).format('d/m/Y')

    formatted_date_joined.short_description = 'Fecha de Contrato'  # Cambia el título aquí

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('** CONTRATO **', {'fields': (('date_joined'),), 'classes': ('collapse',)}),
    )

    # Resto del código...

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:
            return fieldsets

        new_fieldsets = []
        for name, data in fieldsets:
            if name == 'Important dates':
                new_fieldsets.append((name, {'fields': data['fields'], 'description': 'Fecha de Contrato:'}))
            else:
                new_fieldsets.append((name, data))
        
        return new_fieldsets

# Registra la clase CustomUserAdmin con el modelo User
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
