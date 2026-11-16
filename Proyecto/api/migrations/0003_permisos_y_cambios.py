from django.db import migrations, models
import django.db.models.deletion


def escritura_a_permisos(apps, schema_editor):
    """Las claves que tenían 'escritura' conservan lo que podían hacer: comentar y editar."""
    ApiKey = apps.get_model('api', 'ApiKey')
    ApiKey.objects.filter(escritura=True).update(comentar=True, editar=True)


def permisos_a_escritura(apps, schema_editor):
    ApiKey = apps.get_model('api', 'ApiKey')
    ApiKey.objects.filter(models.Q(comentar=True) | models.Q(editar=True)).update(escritura=True)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_apikey_escritura'),
    ]

    operations = [
        migrations.AddField(
            model_name='apikey',
            name='comentar',
            field=models.BooleanField(default=False, help_text='Permite agregar y editar comentarios de bitácora'),
        ),
        migrations.AddField(
            model_name='apikey',
            name='editar',
            field=models.BooleanField(default=False, help_text='Permite cambiar estado de facturas y proyectos'),
        ),
        migrations.RunPython(escritura_a_permisos, permisos_a_escritura),
        migrations.RemoveField(
            model_name='apikey',
            name='escritura',
        ),
        migrations.CreateModel(
            name='ApiCambio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('usuario', models.CharField(help_text='Clave de API o usuario del sistema que hizo el cambio', max_length=100)),
                ('metodo', models.CharField(blank=True, max_length=10)),
                ('ruta', models.CharField(blank=True, max_length=255)),
                ('entidad', models.CharField(max_length=30)),
                ('entidad_id', models.CharField(max_length=30)),
                ('accion', models.CharField(choices=[('editar', 'Editar'), ('comentar', 'Agregar comentario'), ('editar_comentario', 'Editar comentario'), ('revertir', 'Revertir')], max_length=20)),
                ('antes', models.TextField(blank=True, default='')),
                ('despues', models.TextField(blank=True, default='')),
                ('api_key', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='api.apikey')),
                ('revertido_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revierte', to='api.apicambio')),
            ],
            options={
                'db_table': 'api_cambio',
                'ordering': ['-id'],
                'indexes': [models.Index(fields=['entidad', 'entidad_id'], name='api_cambio_entidad_idx')],
            },
        ),
    ]
