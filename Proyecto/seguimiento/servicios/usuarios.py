"""Servicio de Usuarios: usuarios de la aplicación web, sus grupos y su ficha de vacaciones.

La ficha de vacaciones (ducto.Persona) apunta a ducto.auth_user, una copia de la tabla de usuarios en el esquema
ducto; por eso al crear la ficha se copia el usuario allí (y se borra al quitarla).
"""
from django.contrib.auth.models import Group, User
from django.db import connection, transaction

from . import vacaciones

GRUPO_DIRECTOR = 'Director'


class ErrorValidacion(ValueError):
    pass


def es_administrador(user):
    return user.is_authenticated and user.groups.filter(name=GRUPO_DIRECTOR).exists()


def activos():
    return User.objects.filter(is_active=True).order_by('username')


def grupos():
    return Group.objects.all().order_by('name')


def todos():
    return User.objects.all()


def _copiar_a_ducto(usuario):
    """Copia el usuario a ducto.auth_user (con el mismo Id) si aún no está."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM ducto.auth_user WHERE id = %s", [usuario.id])
        if cursor.fetchone()[0]:
            return
        cursor.execute("SET IDENTITY_INSERT ducto.auth_user ON")
        cursor.execute(
            """
            INSERT INTO ducto.auth_user
            (id, password, last_login, is_superuser, username, first_name, last_name, email, is_staff, is_active, date_joined)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [usuario.id, usuario.password, usuario.last_login, int(usuario.is_superuser), usuario.username,
             usuario.first_name or '', usuario.last_name or '', usuario.email or '', int(usuario.is_staff),
             int(usuario.is_active), usuario.date_joined],
        )
        cursor.execute("SET IDENTITY_INSERT ducto.auth_user OFF")


def crear(*, username, password, email='', first_name='', last_name='', grupo_id=None):
    """Usuario nuevo (staff), en su grupo, con su ficha de vacaciones."""
    if not username or not password:
        raise ErrorValidacion('Usuario y contraseña son obligatorios.')
    if User.objects.filter(username=username).exists():
        raise ErrorValidacion('El nombre de usuario ya existe.')
    with transaction.atomic():
        usuario = User.objects.create_user(username=username, email=email, password=password,
                                           first_name=first_name, last_name=last_name)
        usuario.is_staff = True
        usuario.save(update_fields=['is_staff'])
        if grupo_id:
            usuario.groups.add(Group.objects.get(pk=grupo_id))
        crear_ficha_vacaciones(usuario)
    return usuario


def eliminar(usuario):
    usuario.delete()


def crear_ficha_vacaciones(usuario):
    """Ficha de vacaciones del usuario. Devuelve False si ya existía."""
    _copiar_a_ducto(usuario)
    return vacaciones.crear_ficha(usuario)


def quitar_ficha_vacaciones(usuario, persona):
    with transaction.atomic():
        persona.delete()
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM ducto.auth_user WHERE id = %s', [usuario.id])
