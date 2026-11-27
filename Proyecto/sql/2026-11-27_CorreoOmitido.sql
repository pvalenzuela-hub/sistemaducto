-- Registro de las direcciones a las que los avisos automáticos (cron del VPS: cobranza 1 y 2, aviso de pago,
-- EEPP, entrega V00) no llegaron. Lo escribe /srv/ducto/jobs/correos_omitidos.py y lo muestra la web en
-- Clientes > Correos por corregir. Una fila por aviso (Proceso + factura o proyecto) y dirección; si el aviso se
-- repite, se suma en Veces y se actualiza UltimaFecha. Motivo:
--   invalida   la dirección está marcada como inválida en CorreoRebotado: no se le escribió
--   rechazada  el servidor de correo la rechazó al enviar
-- Enviado = 1: el aviso salió igual a otra dirección del cliente. Enviado = 0: el aviso no se envió.
IF OBJECT_ID('dbo.CorreoOmitido', 'U') IS NULL
CREATE TABLE dbo.CorreoOmitido (
    Id          int IDENTITY(1,1) NOT NULL CONSTRAINT PK_CorreoOmitido PRIMARY KEY,
    Proceso     varchar(30)   NOT NULL,
    Email       nvarchar(254) NOT NULL,
    Motivo      varchar(20)   NOT NULL CONSTRAINT CK_CorreoOmitido_Motivo CHECK (Motivo IN ('invalida', 'rechazada')),
    Detalle     nvarchar(500) NULL,
    IdFactura   int           NULL,
    IdProyecto  numeric(10,0) NULL,
    Enviado     bit           NOT NULL,
    Fecha       datetime      NOT NULL,
    UltimaFecha datetime      NOT NULL,
    Veces       int           NOT NULL CONSTRAINT DF_CorreoOmitido_Veces DEFAULT (1)
);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CorreoOmitido_Email' AND object_id = OBJECT_ID('dbo.CorreoOmitido'))
CREATE INDEX IX_CorreoOmitido_Email ON dbo.CorreoOmitido (Email);
