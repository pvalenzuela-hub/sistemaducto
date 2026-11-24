"""Usuarios de la aplicación (solo Director). Datos y reglas en seguimiento.servicios.usuarios y .vacaciones."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render

from seguimiento.servicios import usuarios as srv
from seguimiento.servicios import vacaciones as srv_vacaciones


def _es_administrador(user):
    return srv.es_administrador(user)


@login_required
@user_passes_test(_es_administrador)
def usuario_list(request):
    return render(request, 'accounts/usuario_list.html', {
        'titulo': 'Usuarios',
        'encabezado': 'Usuarios de la aplicación',
        'usuarios': srv.activos(),
    })


@login_required
@user_passes_test(_es_administrador)
@transaction.atomic
def usuario_create(request):
    if request.method == 'POST':
        try:
            srv.crear(
                username=(request.POST.get('username') or '').strip(),
                password=request.POST.get('password') or '',
                email=(request.POST.get('email') or '').strip(),
                first_name=(request.POST.get('first_name') or '').strip(),
                last_name=(request.POST.get('last_name') or '').strip(),
                grupo_id=request.POST.get('group_id') or None,
            )
        except srv.ErrorValidacion as e:
            messages.error(request, str(e))
        else:
            messages.success(request, 'Usuario creado correctamente.')
            return redirect('usuario_list')

    return render(request, 'accounts/usuario_form.html', {
        'titulo': 'Crear usuario',
        'encabezado': 'Crear usuario',
        'grupos': srv.grupos(),
        'modo': 'crear',
    })


@login_required
@user_passes_test(_es_administrador)
def usuario_delete(request, pk):
    usuario = get_object_or_404(srv.todos(), pk=pk)
    if request.method == 'POST':
        srv.eliminar(usuario)
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
    usuario = get_object_or_404(srv.todos(), pk=pk)
    if srv_vacaciones.ficha_de_usuario(usuario.id):
        messages.info(request, f'La ficha de vacaciones ya existía para {usuario.username}.')
        return redirect('usuario_list')
    try:
        srv.crear_ficha_vacaciones(usuario)
        messages.success(request, f'Se creó la ficha de vacaciones para {usuario.username}.')
    except IntegrityError:
        messages.error(request, 'La base de datos rechazó la creación de la ficha de vacaciones. Revise la restricción asociada al usuario.')
    return redirect('usuario_list')


@login_required
@user_passes_test(_es_administrador)
@transaction.atomic
def usuario_quitar_persona(request, pk):
    usuario = get_object_or_404(srv.todos(), pk=pk)
    persona = srv_vacaciones.ficha_de_usuario(usuario.id)

    if not persona:
        messages.info(request, f'El usuario {usuario.username} no tiene ficha de vacaciones.')
        return redirect('usuario_list')

    if request.method == 'POST':
        srv.quitar_ficha_vacaciones(usuario, persona)
        messages.success(request, f'Se quitó la ficha de vacaciones de {usuario.username}.')
        return redirect('usuario_list')

    return render(request, 'accounts/usuario_quitar_persona.html', {
        'titulo': 'Quitar ficha vacaciones',
        'encabezado': 'Quitar ficha vacaciones',
        'usuario': usuario,
        'persona': persona,
    })


@login_required
@user_passes_test(_es_administrador)
@transaction.atomic
def usuario_editar_persona(request, pk):
    usuario = get_object_or_404(srv.todos(), pk=pk)
    persona = srv_vacaciones.ficha_de_usuario(usuario.id)
    if not persona:
        srv.crear_ficha_vacaciones(usuario)
        persona = srv_vacaciones.ficha_de_usuario(usuario.id)

    if request.method == 'POST':
        feccon = request.POST.get('feccon')
        if not feccon:
            messages.error(request, 'Debe indicar la fecha de contrato.')
        else:
            srv_vacaciones.cambiar_fecha_contrato(persona, date.fromisoformat(feccon))
            messages.success(request, f'Se actualizó la fecha de contrato de {usuario.username}.')
            return redirect('usuario_list')

    return render(request, 'accounts/usuario_editar_persona.html', {
        'titulo': 'Editar fecha de contrato',
        'encabezado': 'Editar fecha de contrato',
        'usuario': usuario,
        'persona': persona,
    })
