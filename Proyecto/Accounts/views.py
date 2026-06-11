from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group, User
from django.db import transaction, IntegrityError
from django.db.models import Max
from django.db import connection
from django.shortcuts import get_object_or_404, redirect, render

from Vacation.models import Persona


def _es_administrador(user):
    return user.is_authenticated and user.groups.filter(name='Director').exists()


def _crear_persona_si_falta(usuario):
    _asegurar_usuario_ducto(usuario)
    if Persona.objects.filter(user_per=usuario).exists():
        return

    siguiente_id = (Persona.objects.aggregate(mx=Max('id'))['mx'] or 0) + 1
    Persona.objects.create(
        id=siguiente_id,
        user_per=usuario,
        feccon=date.today(),
        suma_dias_vacaciones=0,
    )


def _asegurar_usuario_ducto(usuario):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM ducto.auth_user WHERE id = %s", [usuario.id])
        existe = cursor.fetchone()[0]
        if existe:
            return

        cursor.execute("SET IDENTITY_INSERT ducto.auth_user ON")
        cursor.execute(
            """
            INSERT INTO ducto.auth_user
            (id, password, last_login, is_superuser, username, first_name, last_name, email, is_staff, is_active, date_joined)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                usuario.id,
                usuario.password,
                usuario.last_login,
                int(usuario.is_superuser),
                usuario.username,
                usuario.first_name or '',
                usuario.last_name or '',
                usuario.email or '',
                int(usuario.is_staff),
                int(usuario.is_active),
                usuario.date_joined,
            ],
        )
        cursor.execute("SET IDENTITY_INSERT ducto.auth_user OFF")


@login_required
@user_passes_test(_es_administrador)
def usuario_list(request):
    usuarios = User.objects.filter(is_active=True).order_by('username')
    return render(request, 'accounts/usuario_list.html', {
        'titulo': 'Usuarios',
        'encabezado': 'Usuarios de la aplicación',
        'usuarios': usuarios,
    })


@login_required
@user_passes_test(_es_administrador)
@transaction.atomic
def usuario_create(request):
    grupos = Group.objects.all().order_by('name')
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        email = (request.POST.get('email') or '').strip()
        first_name = (request.POST.get('first_name') or '').strip()
        last_name = (request.POST.get('last_name') or '').strip()
        password = request.POST.get('password') or ''
        grupo_id = request.POST.get('group_id') or ''

        if not username or not password:
            messages.error(request, 'Usuario y contraseña son obligatorios.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'El nombre de usuario ya existe.')
        else:
            usuario = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            usuario.is_staff = True
            usuario.save(update_fields=['is_staff'])
            if grupo_id:
                usuario.groups.add(Group.objects.get(pk=grupo_id))
            _asegurar_usuario_ducto(usuario)
            _crear_persona_si_falta(usuario)
            messages.success(request, 'Usuario creado correctamente.')
            return redirect('usuario_list')

    return render(request, 'accounts/usuario_form.html', {
        'titulo': 'Crear usuario',
        'encabezado': 'Crear usuario',
        'grupos': grupos,
        'modo': 'crear',
    })


@login_required
@user_passes_test(_es_administrador)
def usuario_delete(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        usuario.delete()
        messages.success(request, 'Usuario eliminado correctamente.')
        return redirect('usuario_list')

    return render(request, 'accounts/usuario_confirm_delete.html', {
        'titulo': 'Eliminar usuario',
        'encabezado': 'Eliminar usuario',
        'usuario': usuario,
    })


@login_required
@user_passes_test(_es_administrador)
@transaction.atomic
def usuario_crear_persona(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    if Persona.objects.filter(user_per=usuario).exists():
        messages.info(request, f'La ficha de vacaciones ya existía para {usuario.username}.')
        return redirect('usuario_list')

    try:
        _asegurar_usuario_ducto(usuario)
        siguiente_id = (Persona.objects.aggregate(mx=Max('id'))['mx'] or 0) + 1
        Persona.objects.create(
            id=siguiente_id,
            user_per=usuario,
            feccon=date.today(),
            suma_dias_vacaciones=0,
        )
        messages.success(request, f'Se creó la ficha de vacaciones para {usuario.username}.')
    except IntegrityError:
        messages.error(request, 'La base de datos rechazó la creación de la ficha de vacaciones. Revise la restricción asociada al usuario.')

    return redirect('usuario_list')


@login_required
@user_passes_test(_es_administrador)
@transaction.atomic
def usuario_quitar_persona(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    persona = Persona.objects.filter(user_per=usuario).first()

    if not persona:
        messages.info(request, f'El usuario {usuario.username} no tiene ficha de vacaciones.')
        return redirect('usuario_list')

    if request.method == 'POST':
        persona.delete()
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM ducto.auth_user WHERE id = %s', [usuario.id])
        messages.success(request, f'Se quitó la ficha de vacaciones de {usuario.username}.')
        return redirect('usuario_list')

    return render(request, 'accounts/usuario_quitar_persona.html', {
        'titulo': 'Quitar ficha vacaciones',
        'encabezado': 'Quitar ficha vacaciones',
        'usuario': usuario,
        'persona': persona,
    })
