from django.db import models
from django.db.models import Sum
from django.contrib.auth.models import User
from datetime import date
from django.db.models.signals import post_save
from django.dispatch import receiver
from dateutil.relativedelta import relativedelta

# Create your models here.
class Persona(models.Model):
    user_per = models.OneToOneField(User, on_delete=models.CASCADE)
    feccon = models.DateField()
    suma_dias_vacaciones = models.FloatField(null=True, blank=True)
    dias_pendientes = models.FloatField(null=True, blank=True)
    dias_totales = models.FloatField(null=True, blank=True)
    meses_totales = models.FloatField(null=True, blank=True)

    def calcular_dias_vacaciones(self):
        total = self.registrovac_set.aggregate(total_vacaciones=Sum('dias_vacaciones'))['total_vacaciones']
        self.suma_dias_vacaciones = total or 0
        self.save()

    def save(self, *args, **kwargs):
        fecha = date.today()
        #dias_totales = float(((fecha - self.feccon).days / 365.25) * 15) or 0
        diferencia = relativedelta(fecha, self.feccon)
        meses = diferencia.years * 12 + diferencia.months
        if fecha.month == self.feccon.month:
            meses = meses + ((fecha.day - self.feccon.day)/30)
        
        dias_totales = meses * 1.25

        self.dias_totales = dias_totales
        self.dias_pendientes = dias_totales - self.suma_dias_vacaciones
        self.meses_totales = meses
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["user_per"]
        verbose_name = 'Registro de Persona'
        verbose_name_plural = 'Registros de Personas'
        db_table = '[project].[ducto].[Persona]'
        managed = False

    def __str__(self):
        return str(self.user_per)


class Registrovac(models.Model):
    user_vac = models.ForeignKey(Persona, on_delete=models.CASCADE,verbose_name="Usuario")
    fecini = models.DateField(verbose_name="Fecha inicio")
    fecfin = models.DateField(verbose_name="Fecha fin")
    dias_vacaciones = models.FloatField(verbose_name='Días hábiles de vacaciones')

    class Meta:
        ordering = ["user_vac","fecini"]
        verbose_name = 'Registro de Vacaciones'
        verbose_name_plural = 'Registros de Vacaciones'
        db_table = '[project].[ducto].[Registrovac]'
        managed = False

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.user_vac.calcular_dias_vacaciones()

    def __str__(self):
        texto = "{0} {1} {2} {3}"
        return texto.format(self.user_vac,str(self.fecini),str(self.fecfin),str(self.dias_vacaciones))

@receiver(post_save, sender=Registrovac)
def actualizar_dias_vacaciones(sender, instance, **kwargs):
    instance.user_vac.calcular_dias_vacaciones()        