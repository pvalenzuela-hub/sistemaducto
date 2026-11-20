"""Permisos por grupo para vistas de la web.

Director = Camila, Robinson, Paulo (equivale al perfil 0 del escritorio en lo administrativo).
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

GRUPO_DIRECTOR = 'Director'


def es_director(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name=GRUPO_DIRECTOR).exists())


def solo_director(vista):
    """Exige sesión iniciada (si no, lleva al login) y grupo Director (si no, 403).
    Sirve para funciones y para Class.as_view(), envolviéndolas en urls.py."""
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not es_director(request.user):
            raise PermissionDenied('Solo para el perfil Director.')
        return vista(request, *args, **kwargs)
    return envoltura
