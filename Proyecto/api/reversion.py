"""Revertir cambios hechos por la API, a partir del registro ApiCambio."""
from datetime import date

from django.db import transaction
from django.utils import timezone

from seguimiento.models import Factura, Proyecto

from . import seg
from .models import ApiCambio

USUARIO_REVERSION = 'sistema'


class NoReversible(Exception):
    pass


def _bitacora(entidad):
    return {'factura_comentario': seg.factura, 'proyecto_comentario': seg.proyecto}[entidad]


def describir(cambio):
    """Texto con lo que haría revertir el cambio."""
    antes, despues = cambio.antes_data, cambio.despues_data
    if cambio.accion == 'editar':
        return f"{cambio.entidad} {cambio.entidad_id}: volver de {despues} a {antes}"
    if cambio.accion == 'comentar':
        return f"{cambio.entidad} {cambio.entidad_id}: eliminar el comentario {despues['comentario']!r}"
    if cambio.accion == 'editar_comentario':
        return f"{cambio.entidad} {cambio.entidad_id}: restaurar el texto {antes['comentario']!r}"
    raise NoReversible(f"La acción '{cambio.accion}' no se puede revertir")


def revertir(cambio, motivo=''):
    """Deshace el cambio si el registro sigue como lo dejó la API. Devuelve el ApiCambio de la reversión."""
    if cambio.revertido_por_id:
        raise NoReversible(f"El cambio #{cambio.pk} ya fue revertido por #{cambio.revertido_por_id}")
    antes, despues = cambio.antes_data, cambio.despues_data
    describir(cambio)  # valida la acción

    with transaction.atomic():
        if cambio.entidad == 'factura' and cambio.accion == 'editar':
            f = Factura.objects.select_for_update().filter(pk=int(cambio.entidad_id)).first()
            if f is None:
                raise NoReversible('La factura ya no existe')
            fecha_despues = date.fromisoformat(despues['fecha_pago']) if despues['fecha_pago'] else None
            if f.estado != despues['estado'] or f.fechapago != fecha_despues:
                raise NoReversible(f"La factura cambió después (estado={f.estado}, fecha_pago={f.fechapago}); "
                                   "revise y corrija a mano")
            fecha_antes = date.fromisoformat(antes['fecha_pago']) if antes['fecha_pago'] else None
            Factura.objects.filter(pk=f.pk).update(estado=antes['estado'], fechapago=fecha_antes,
                                                   fechaact=timezone.now())
            seg.factura.agregar(f.pk, f"[API] Revertido cambio #{cambio.pk}. {motivo}".strip(), USUARIO_REVERSION)

        elif cambio.entidad == 'proyecto' and cambio.accion == 'editar':
            p = Proyecto.objects.select_for_update().filter(pk=int(cambio.entidad_id)).first()
            if p is None:
                raise NoReversible('El proyecto ya no existe')
            if p.estadoproyecto_id != despues['estado']:
                raise NoReversible(f"El proyecto cambió después (estado={p.estadoproyecto_id}); revise y corrija a mano")
            Proyecto.objects.filter(pk=p.pk).update(estadoproyecto_id=antes['estado'], estado=antes['estado'])
            seg.proyecto.agregar(p.pk, f"[API] Revertido cambio #{cambio.pk}. {motivo}".strip(), USUARIO_REVERSION,
                                 estado=antes['estado'])

        elif cambio.entidad in ('factura_comentario', 'proyecto_comentario'):
            id_, idreg = (int(x) for x in cambio.entidad_id.split('/'))
            bitacora = _bitacora(cambio.entidad)
            actual = bitacora.obtener(id_, idreg)
            if actual is None:
                raise NoReversible('El comentario ya no existe')
            if actual['comentario'] != despues['comentario']:
                raise NoReversible('El comentario cambió después; revise y corrija a mano')
            if cambio.accion == 'comentar':
                bitacora.eliminar(id_, idreg)
            else:
                bitacora.editar(id_, idreg, antes['comentario'])
        else:
            raise NoReversible(f"No se sabe revertir '{cambio.accion}' sobre '{cambio.entidad}'")

        reversion = ApiCambio.objects.create(
            usuario=USUARIO_REVERSION, entidad=cambio.entidad, entidad_id=cambio.entidad_id, accion='revertir',
            antes=cambio.despues, despues=cambio.antes or ApiCambio._dump({'cambio': cambio.pk, 'motivo': motivo}),
        )
        ApiCambio.objects.filter(pk=cambio.pk).update(revertido_por=reversion)
    return reversion
