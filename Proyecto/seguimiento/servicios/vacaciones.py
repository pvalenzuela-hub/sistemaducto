"""Servicio de Vacaciones: fichas de personal (Persona) y sus registros de vacaciones (Registrovac).

Regla de días: 1,25 días hábiles por mes trabajado desde la fecha de contrato. En el mes del aniversario se suma
la fracción de días (diferencia de días / 30). Días pendientes = días ganados - días tomados.
"""
from datetime import date

from dateutil.relativedelta import relativedelta
from django.db.models import Max, Sum

DIAS_POR_MES = 1.25


def calculo(feccon, dias_tomados, hoy=None):
    """(meses trabajados, días ganados, días pendientes) a la fecha."""
    hoy = hoy or date.today()
    diferencia = relativedelta(hoy, feccon)
    meses = diferencia.years * 12 + diferencia.months
    if hoy.month == feccon.month:
        meses = meses + ((hoy.day - feccon.day) / 30)
    dias_totales = meses * DIAS_POR_MES
    return meses, dias_totales, dias_totales - (dias_tomados or 0)


def _modelos():
    from Vacation.models import Persona, Registrovac
    return Persona, Registrovac


def dias_tomados(persona):
    return persona.registrovac_set.aggregate(total=Sum('dias_vacaciones'))['total'] or 0


def recalcular(persona):
    """Actualiza los días tomados, ganados y pendientes de la persona (Persona.save aplica calculo())."""
    persona.suma_dias_vacaciones = dias_tomados(persona)
    persona.save()


def personas():
    """Personal con los días recalculados a hoy (el listado los actualiza al abrirse, como antes)."""
    Persona, _ = _modelos()
    for persona in Persona.objects.all():
        recalcular(persona)
    return Persona.objects.order_by('user_per')


def persona(pk):
    Persona, _ = _modelos()
    return Persona.objects.filter(pk=pk).first()


def ficha_de_usuario(usuario_id):
    Persona, _ = _modelos()
    return Persona.objects.filter(user_per_id=usuario_id).first()


def registros(pk_persona):
    _, Registrovac = _modelos()
    return Registrovac.objects.filter(user_vac=pk_persona)


def registro(pk_persona, reg_id):
    _, Registrovac = _modelos()
    return Registrovac.objects.filter(pk=reg_id, user_vac_id=pk_persona).first()


def eliminar_registro(persona_obj, registro_obj):
    registro_obj.delete()
    recalcular(persona_obj)


def eliminar_persona(persona_obj):
    persona_obj.registrovac_set.all().delete()
    persona_obj.delete()


def crear_ficha(usuario):
    """Ficha de vacaciones con Id = máximo + 1 y contrato hoy. Devuelve False si ya existía."""
    Persona, _ = _modelos()
    if Persona.objects.filter(user_per_id=usuario.id).exists():
        return False
    siguiente_id = (Persona.objects.aggregate(mx=Max('id'))['mx'] or 0) + 1
    Persona.objects.create(id=siguiente_id, user_per_id=usuario.id, feccon=date.today(), suma_dias_vacaciones=0)
    return True


def cambiar_fecha_contrato(persona_obj, feccon):
    """Nueva fecha de contrato y días recalculados (sin pasar por Persona.save)."""
    Persona, _ = _modelos()
    tomados = dias_tomados(persona_obj)
    meses, totales, pendientes = calculo(feccon, tomados)
    Persona.objects.filter(pk=persona_obj.pk).update(feccon=feccon, suma_dias_vacaciones=tomados, dias_totales=totales,
                                                    dias_pendientes=pendientes, meses_totales=meses)
