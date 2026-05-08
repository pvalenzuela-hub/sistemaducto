from django.db import migrations


def forwards(apps, schema_editor):
    schema_editor.execute("""
        UPDATE Estadocotizacion
        SET ColorFondo = '#dc2626', ColorTexto = '#ffffff', Orden = 4
        WHERE Nombre = 'Nula' OR Nombre = 'Anulada';
    """)


class Migration(migrations.Migration):

    dependencies = [
        ('seguimiento', '0016_estadocotizacion_colores_orden'),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
