# Generated for cotizacion origin tracking

from django.db import migrations


def set_legacy_origin(apps, schema_editor):
    schema_editor.execute(
        "UPDATE Cotizacion SET Origen = %s WHERE Origen IS NULL OR LTRIM(RTRIM(Origen)) = ''",
        params=['LEGACY'],
    )


class Migration(migrations.Migration):

    dependencies = [
        ('seguimiento', '0014_estadocotizacion_estadofactura_alter_tfpago_options'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                IF COL_LENGTH('Cotizacion', 'Origen') IS NULL
                BEGIN
                    ALTER TABLE Cotizacion ADD Origen VARCHAR(10) NULL;
                END;
            """,
            reverse_sql="""
                IF COL_LENGTH('Cotizacion', 'Origen') IS NOT NULL
                BEGIN
                    ALTER TABLE Cotizacion DROP COLUMN Origen;
                END;
            """,
        ),
        migrations.RunPython(set_legacy_origin, reverse_code=migrations.RunPython.noop),
    ]
