from django.db import migrations


def forwards(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "UPDATE Estadocotizacion SET ColorFondo = %s, ColorTexto = %s WHERE nombre = %s",
            ['#dc2626', '#ffffff', 'No Adjudicado'],
        )
        cursor.execute(
            "UPDATE Estadocotizacion SET ColorFondo = NULL, ColorTexto = NULL WHERE nombre = %s",
            ['Nula'],
        )


def backwards(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "UPDATE Estadocotizacion SET ColorFondo = NULL, ColorTexto = NULL WHERE nombre = %s",
            ['No Adjudicado'],
        )
        cursor.execute(
            "UPDATE Estadocotizacion SET ColorFondo = %s, ColorTexto = %s WHERE nombre = %s",
            ['#dc2626', '#ffffff', 'Nula'],
        )


class Migration(migrations.Migration):

    dependencies = [
        ('seguimiento', '0017_estadocotizacion_nula_color'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
