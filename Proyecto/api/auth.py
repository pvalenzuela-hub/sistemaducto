from functools import wraps

from django.http import JsonResponse
from django.utils import timezone

from .models import ApiKey, hash_key

WRITE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')


def api_key_required(view_func):
    """Exige el header 'X-API-Key' con una clave activa; los métodos de escritura exigen permiso de escritura."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        raw_key = request.headers.get('X-API-Key', '').strip()
        if not raw_key:
            return JsonResponse({'error': 'Falta el header X-API-Key'}, status=401)

        api_key = ApiKey.objects.filter(key_hash=hash_key(raw_key), activa=True).first()
        if api_key is None:
            return JsonResponse({'error': 'API Key inválida o revocada'}, status=401)
        if request.method in WRITE_METHODS and not api_key.escritura:
            return JsonResponse({'error': 'Esta API Key no tiene permiso de escritura'}, status=403)

        ApiKey.objects.filter(pk=api_key.pk).update(ultimo_uso=timezone.now())
        request.api_key = api_key
        return view_func(request, *args, **kwargs)
    return wrapper
