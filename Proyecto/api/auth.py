from functools import wraps

from django.http import JsonResponse
from django.utils import timezone

from .models import ApiKey, hash_key

PERMISOS = ('comentar', 'editar')


def api_key_required(permisos=None):
    """Exige el header 'X-API-Key' con una clave activa. Toda clave activa puede leer.

    `permisos` asocia métodos HTTP al permiso que exigen, p. ej. {'POST': 'comentar', 'PATCH': 'editar'}.
    """
    permisos = permisos or {}
    assert set(permisos.values()) <= set(PERMISOS), permisos

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            raw_key = request.headers.get('X-API-Key', '').strip()
            if not raw_key:
                return JsonResponse({'error': 'Falta el header X-API-Key'}, status=401)

            api_key = ApiKey.objects.filter(key_hash=hash_key(raw_key), activa=True).first()
            if api_key is None:
                return JsonResponse({'error': 'API Key inválida o revocada'}, status=401)
            permiso = permisos.get(request.method)
            if permiso and not getattr(api_key, permiso):
                return JsonResponse({'error': f"Esta API Key no tiene permiso para {permiso}"}, status=403)

            ApiKey.objects.filter(pk=api_key.pk).update(ultimo_uso=timezone.now())
            request.api_key = api_key
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
