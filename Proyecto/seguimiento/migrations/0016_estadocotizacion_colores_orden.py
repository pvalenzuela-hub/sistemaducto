from django.db import migrations


def forwards(apps, schema_editor):
    if schema_editor.connection.introspection.table_names().__contains__('Estadocotizacion'):
        schema_editor.execute("IF COL_LENGTH('Estadocotizacion', 'ColorFondo') IS NULL ALTER TABLE Estadocotizacion ADD ColorFondo VARCHAR(20) NULL;")
        schema_editor.execute("IF COL_LENGTH('Estadocotizacion', 'ColorTexto') IS NULL ALTER TABLE Estadocotizacion ADD ColorTexto VARCHAR(20) NULL;")
        schema_editor.execute("IF COL_LENGTH('Estadocotizacion', 'Orden') IS NULL ALTER TABLE Estadocotizacion ADD Orden INT NULL;")
        schema_editor.execute("UPDATE Estadocotizacion SET ColorFondo = '#fef3c7', ColorTexto = '#92400e', Orden = 1 WHERE Nombre = 'En Espera' OR Nombre = 'Espera';")
        schema_editor.execute("UPDATE Estadocotizacion SET ColorFondo = '#dcfce7', ColorTexto = '#166534', Orden = 2 WHERE Nombre = 'Aprobada, Es Proyecto';")
        schema_editor.execute("UPDATE Estadocotizacion SET ColorFondo = '#e5e7eb', ColorTexto = '#475569', Orden = 3 WHERE Nombre = 'Cerrada';")
        schema_editor.execute("UPDATE Estadocotizacion SET ColorFondo = '#dbeafe', ColorTexto = '#1d4ed8', Orden = 4 WHERE Nombre = 'Pendiente';")


class Migration(migrations.Migration):

    dependencies = [
        ('seguimiento', '0015_cotizacion_origen_web'),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
