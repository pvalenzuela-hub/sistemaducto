from django.db import migrations


FORWARD_SQL = """
IF COL_LENGTH('Cotizacion_FPago', 'IdCotizacionFpago') IS NULL
BEGIN
    ALTER TABLE Cotizacion_FPago
    ADD IdCotizacionFpago INT IDENTITY(1,1) NOT NULL;
END

IF NOT EXISTS (
    SELECT 1
    FROM sys.key_constraints
    WHERE [type] = 'PK' AND [parent_object_id] = OBJECT_ID('Cotizacion_FPago')
)
BEGIN
    ALTER TABLE Cotizacion_FPago
    ADD CONSTRAINT PK_Cotizacion_FPago PRIMARY KEY (IdCotizacionFpago);
END
"""


REVERSE_SQL = """
IF EXISTS (
    SELECT 1
    FROM sys.key_constraints
    WHERE [type] = 'PK' AND [parent_object_id] = OBJECT_ID('Cotizacion_FPago')
)
BEGIN
    ALTER TABLE Cotizacion_FPago DROP CONSTRAINT PK_Cotizacion_FPago;
END

IF COL_LENGTH('Cotizacion_FPago', 'IdCotizacionFpago') IS NOT NULL
BEGIN
    ALTER TABLE Cotizacion_FPago DROP COLUMN IdCotizacionFpago;
END
"""


class Migration(migrations.Migration):

    dependencies = [
        ('seguimiento', '0010_add_pk_cotizacion_notas'),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
