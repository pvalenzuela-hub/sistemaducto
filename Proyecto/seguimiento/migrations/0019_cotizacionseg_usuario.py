from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('seguimiento', '0018_adjust_estadocotizacion_colors'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE Cotizacion_Seg ADD Usuario INT NULL;"
                "ALTER TABLE Cotizacion_Seg ADD CONSTRAINT FK_Cotizacion_Seg_Usuario "
                "FOREIGN KEY (Usuario) REFERENCES auth_user(id);"
            ),
            reverse_sql=(
                "ALTER TABLE Cotizacion_Seg DROP CONSTRAINT FK_Cotizacion_Seg_Usuario;"
                "ALTER TABLE Cotizacion_Seg DROP COLUMN Usuario;"
            ),
        ),
    ]
