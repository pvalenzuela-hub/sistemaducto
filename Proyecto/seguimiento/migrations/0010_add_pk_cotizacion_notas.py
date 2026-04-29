from django.db import migrations


FORWARD_SQL = """
IF COL_LENGTH('Cotizacion_Notas', 'IdCotizacionNota') IS NULL
BEGIN
    ALTER TABLE Cotizacion_Notas
    ADD IdCotizacionNota INT IDENTITY(1,1) NOT NULL;
END

IF NOT EXISTS (
    SELECT 1
    FROM sys.key_constraints
    WHERE [type] = 'PK' AND [parent_object_id] = OBJECT_ID('Cotizacion_Notas')
)
BEGIN
    ALTER TABLE Cotizacion_Notas
    ADD CONSTRAINT PK_Cotizacion_Notas PRIMARY KEY (IdCotizacionNota);
END
"""


REVERSE_SQL = """
IF EXISTS (
    SELECT 1
    FROM sys.key_constraints
    WHERE [type] = 'PK' AND [parent_object_id] = OBJECT_ID('Cotizacion_Notas')
)
BEGIN
    ALTER TABLE Cotizacion_Notas DROP CONSTRAINT PK_Cotizacion_Notas;
END

IF COL_LENGTH('Cotizacion_Notas', 'IdCotizacionNota') IS NOT NULL
BEGIN
    ALTER TABLE Cotizacion_Notas DROP COLUMN IdCotizacionNota;
END
"""


class Migration(migrations.Migration):

    dependencies = [
        ('seguimiento', '0009_itemcotizacion'),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
