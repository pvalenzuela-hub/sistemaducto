from django.db import migrations, models


def seed_monedas(apps, schema_editor):
    MonedaCotizacion = apps.get_model('seguimiento', 'MonedaCotizacion')
    valores = [
        (1, '$'),
        (2, 'UF'),
    ]
    for pk, nombre in valores:
        MonedaCotizacion.objects.update_or_create(
            idmoneda=pk,
            defaults={'nombre': nombre},
        )


def unseed_monedas(apps, schema_editor):
    MonedaCotizacion = apps.get_model('seguimiento', 'MonedaCotizacion')
    MonedaCotizacion.objects.filter(idmoneda__in=[1, 2]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('seguimiento', '0007_aspnetuser_clienteagenda_clienteseg_entregaevento_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='MonedaCotizacion',
            fields=[
                ('idmoneda', models.AutoField(primary_key=True, serialize=False)),
                ('nombre', models.CharField(max_length=10)),
            ],
            options={
                'db_table': 'MonedaCotizacion',
                'ordering': ['idmoneda'],
            },
        ),
        migrations.RunPython(seed_monedas, reverse_code=unseed_monedas),
    ]
