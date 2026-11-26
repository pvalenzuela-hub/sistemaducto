-- Correos de contactos que rebotaron en comunicados masivos.
-- Una fila por dirección (en minúsculas). Estado:
--   invalida   la dirección o el dominio no existe (o error permanente): se excluye de los comunicados
--   bloqueada  el servidor del destinatario rechazó el mensaje, pero la dirección existe: solo se muestra
-- Tabla aparte: no modifica Cliente_Contacto, que usa también el sistema de escritorio.
IF OBJECT_ID('dbo.CorreoRebotado', 'U') IS NULL
CREATE TABLE dbo.CorreoRebotado (
    Id        int IDENTITY(1,1) NOT NULL CONSTRAINT PK_CorreoRebotado PRIMARY KEY,
    Email     nvarchar(254) NOT NULL CONSTRAINT UQ_CorreoRebotado_Email UNIQUE,
    Estado    varchar(20)   NOT NULL CONSTRAINT CK_CorreoRebotado_Estado CHECK (Estado IN ('invalida', 'bloqueada')),
    Tipo      nvarchar(100) NULL,
    Motivo    nvarchar(500) NULL,
    Origen    nvarchar(100) NULL,
    Fecha     datetime      NOT NULL CONSTRAINT DF_CorreoRebotado_Fecha DEFAULT (GETDATE()),
    Usuario   nvarchar(50)  NULL
);
