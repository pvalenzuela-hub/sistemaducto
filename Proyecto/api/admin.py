from django.contrib import admin

from .models import ApiCambio, ApiKey


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'prefijo', 'activa', 'comentar', 'editar', 'creada', 'ultimo_uso')
    readonly_fields = ('prefijo', 'key_hash', 'creada', 'ultimo_uso')


@admin.register(ApiCambio)
class ApiCambioAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'usuario', 'accion', 'entidad', 'entidad_id', 'revertido_por')
    list_filter = ('accion', 'entidad', 'usuario')
    search_fields = ('entidad_id', 'antes', 'despues')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
