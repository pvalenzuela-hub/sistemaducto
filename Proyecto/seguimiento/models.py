from django.db import models

# Create your models here.
class T_Categoria(models.Model):
    IdCategoria = models.AutoField(primary_key=True)
    NombreCat = models.CharField(max_length=100)

    def __str__(self):
        return self.NombreCat

    class Meta:
        ordering = ["NombreCat"]
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'
        db_table = 'T_Categoria'
        
class TipoEntrega(models.Model):
    idtipoentrega = models.AutoField(db_column='IdTipoEntrega', primary_key=True)
    descripcion = models.CharField(db_column='Descripcion', max_length=100, null=True, blank=True)
    color = models.CharField(db_column='Color', max_length=50, null=True, blank=True)
    factorTiempo = models.FloatField(db_column='FactorTiempo')

    class Meta:
        managed = False
        db_table = '[ducto].[T_TipoEntrega]'
        