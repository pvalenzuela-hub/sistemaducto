from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group, User
from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from Vacation.models import Persona


def _es_administrador(user):
    return user.is_authenticated and user.groups.filter(name='Director').exists()


def _crear_persona_si_falta(usuario):
    Persona.objects.get_or_create(
        user_per=usuario,
        defaults={'feccon': date.today()},
    )


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
