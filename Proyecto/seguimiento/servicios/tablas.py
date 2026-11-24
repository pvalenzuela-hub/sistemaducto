"""Servicio de Tablas: catálogos que mantiene el Director (categorías, tipos de entrega y valores UF).

Los formularios de Django (seguimiento.forms) validan; aquí se leen y graban los registros.
"""
from datetime import date

from django.db import IntegrityError

from ..models import EntregaProyecto, T_Categoria, TipoEntrega, tValorUF
from . import uf


class NoSePuedeEliminar(ValueError):
    pass


def guardar(form):
    """Graba un formulario de catálogo ya validado."""
    return form.save()


# Categorías
def categorias():
    return T_Categoria.objects.all().order_by('NombreCat').reverse()


# Tipos de entrega
def tipos_entrega():
    return TipoEntrega.objects.all().order_by('descripcion')


def tipo_entrega(pk):
    return TipoEntrega.objects.filter(pk=pk).first()


def entregas_con_tipo(tipo):
    return EntregaProyecto.objects.filter(idtipoentrega=tipo).count()


def eliminar_tipo_entrega(tipo):
    """No se elimina un tipo con entregas asociadas ni uno usado por otros registros."""
    if entregas_con_tipo(tipo):
        raise NoSePuedeEliminar('No se puede eliminar el tipo de entrega porque tiene entregas asociadas.')
    try:
        tipo.delete()
    except IntegrityError:
        raise NoSePuedeEliminar('No se puede eliminar el tipo de entrega porque esta siendo utilizado por otros registros.')


# Valores UF
def valores_uf():
    """Valores UF del más reciente al más antiguo; antes completa las fechas que falten (servicios.uf)."""
    uf.sincronizar_faltantes()
    return tValorUF.objects.all().order_by('-Fecha')


def valor_uf(fecha_texto):
    """Registro de UF por fecha AAAA-MM-DD (ValueError si la fecha no es válida)."""
    return tValorUF.objects.filter(pk=date.fromisoformat(fecha_texto)).first()


def eliminar_valor_uf(registro):
    registro.delete()
