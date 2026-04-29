from django.db import migrations, models


def seed_items(apps, schema_editor):
    ItemCotizacion = apps.get_model('seguimiento', 'ItemCotizacion')
    valores = [
        (1, 'CONSULTORIA RES. DOMICILIARIOS'),
        (2, 'GASTOS PLOTEOS (MAX FORMATO A1) SOLO PARA SEREMI'),
        (3, 'TRAMITE DIGITAL PARA APROBACION SEREMI SALUD'),
        (4, 'OPCIONAL TRAMITE APROBACION SEREMI DE SALUD'),
        (5, 'ELABORACION DOSSIER SEREMI SALUD'),
        (6, 'TRAMITE PRESENCIAL TIMBRAJE DE PLANOS SEREMI (INCLUYE PLOTEO 2 JUEGOS FORMATO A1)'),
        (7, 'TRAMITE DIGITAL DECLARACION JURADA SEREMI'),
    ]
    for pk, nombre in valores:
        ItemCotizacion.objects.update_or_create(
            iditem=pk,
            defaults={'nombre': nombre},
        )


def unseed_items(apps, schema_editor):
    ItemCotizacion = apps.get_model('seguimiento', 'ItemCotizacion')
    ItemCotizacion.objects.filter(iditem__in=[1, 2, 3, 4, 5, 6, 7]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('seguimiento', '0008_monedacotizacion'),
    ]

    operations = [
        migrations.CreateModel(
            name='ItemCotizacion',
            fields=[
                ('iditem', models.AutoField(primary_key=True, serialize=False)),
                ('nombre', models.CharField(max_length=255)),
            ],
            options={
                'db_table': 'ItemCotizacion',
                'ordering': ['iditem'],
            },
        ),
        migrations.RunPython(seed_items, reverse_code=unseed_items),
    ]
