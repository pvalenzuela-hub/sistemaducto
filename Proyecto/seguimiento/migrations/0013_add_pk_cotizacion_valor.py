from django.db import migrations


FORWARD_SQL = """
IF COL_LENGTH('Cotizacion_Valor', 'IdCotizacionValor') IS NULL
BEGIN
    ALTER TABLE Cotizacion_Valor
    ADD IdCotizacionValor INT IDENTITY(1,1) NOT NULL;
END

IF NOT EXISTS (
    SELECT 1
    FROM sys.key_constraints
    WHERE [type] = 'PK' AND [parent_object_id] = OBJECT_ID('Cotizacion_Valor')
)
BEGIN
    ALTER TABLE Cotizacion_Valor
    ADD CONSTRAINT PK_Cotizacion_Valor PRIMARY KEY (IdCotizacionValor);
END
"""


REVERSE_SQL = """
IF EXISTS (
    SELECT 1
    FROM sys.key_constraints
    WHERE [type] = 'PK' AND [parent_object_id] = OBJECT_ID('Cotizacion_Valor')
)
BEGIN
    ALTER TABLE Cotizacion_Valor DROP CONSTRAINT PK_Cotizacion_Valor;
END

IF COL_LENGTH('Cotizacion_Valor', 'IdCotizacionValor') IS NOT NULL
BEGIN
    ALTER TABLE Cotizacion_Valor DROP COLUMN IdCotizacionValor;
END
"""


class Migration(migrations.Migration):

    dependencies = [
        ('seguimiento', '0012_cotizacionfpago_cotizacionnota_cotizacionvalor_and_more'),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
