from django.contrib import admin

from .models import ApiKey


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'prefijo', 'activa', 'creada', 'ultimo_uso')
    readonly_fields = ('prefijo', 'key_hash', 'creada', 'ultimo_uso')
