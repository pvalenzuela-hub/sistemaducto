from django.db import migrations, models


def seed_destinos(apps, schema_editor):
    DestinoCotizacion = apps.get_model('seguimiento', 'DestinoCotizacion')
    valores = [
        (1, 'COMERCIAL'),
        (2, 'HABITACIONAL'),
        (3, 'SALUD'),
        (4, 'INDUSTRIAL'),
        (5, 'OFICINAS'),
    ]
    for pk, nombre in valores:
        DestinoCotizacion.objects.update_or_create(
            iddestino=pk,
            defaults={'nombre': nombre},
        )


def unseed_destinos(apps, schema_editor):
    DestinoCotizacion = apps.get_model('seguimiento', 'DestinoCotizacion')
    DestinoCotizacion.objects.filter(iddestino__in=[1, 2, 3, 4, 5]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('seguimiento', '0005_calificacion_entregaobservacion_observacion_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='DestinoCotizacion',
            fields=[
                ('iddestino', models.AutoField(primary_key=True, serialize=False)),
                ('nombre', models.CharField(max_length=50)),
            ],
            options={
                'db_table': 'DestinoCotizacion',
                'ordering': ['iddestino'],
            },
        ),
        migrations.RunPython(seed_destinos, reverse_code=unseed_destinos),
    ]
