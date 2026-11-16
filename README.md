# Sistema Ducto

Sistema de gestion para Ducto (proyectos, cuentas, vacaciones, seguimiento).

## Stack
- Django (ver requirements.txt)
- legacy_vbnet/ - referencia del sistema legacy en VB.NET (NO es codigo activo)

## Estructura
- Proyecto/ - proyecto Django principal
  - Accounts/ - cuentas y usuarios
  - Vacation/ - vacaciones
  - seguimiento/ - seguimiento de proyectos
  - static/, templates/ - frontend
- legacy_vbnet/ - DuctoProyectos (VB.NET), reportes PDF, scripts SQL de referencia
- Bugs_Hot_Fix/ - registro de bugs y hot fixes

## Ejecucion
```bash
cd Proyecto
python manage.py migrate
python manage.py runserver
```

## Git
- Remote: git@github.com:pvalenzuela-hub/sistemaducto.git

## API externa
App `Proyecto/api/`. Autenticación con header `X-API-Key`. Guía de integración para terceros: doc "API de Facturas – Sistema Ducto".

```bash
python manage.py migrate api                                       # tablas api_apikey y api_cambio
python manage.py apikey crear "asistente"                          # solo lectura; muestra la clave una vez
python manage.py apikey crear "Conciliador" --comentar --editar    # lectura, comentarios y cambios de estado
python manage.py apikey permisos "asistente" --comentar si --editar no
python manage.py apikey listar
python manage.py apikey revocar "asistente"
python manage.py apicambios listar [--clave X] [--entidad proyecto] [--id 4141]   # registro de cambios de la API
python manage.py apicambios ver 12
python manage.py apicambios revertir 12 [--motivo "..."] --confirmar             # sin --confirmar solo muestra qué haría
```

Permisos: toda clave activa lee; `comentar` permite POST/PATCH de comentarios; `editar` permite PATCH de facturas y proyectos. Cada cambio queda en `api_cambio` (quién, cuándo, antes y después) y se ve en el admin.

Endpoints (`/api/v1/`):
- `GET facturas/` — filtros: `estado` (lista con comas), `desde`, `hasta`, `rut`, `idcliente`, `idproyecto`, `folio`, `monto_min`, `monto_max`, `monto` + `tolerancia` / `tolerancia_pct`, `modificado_desde`, `page`, `page_size` (máx. 500)
- `GET|PATCH facturas/<idfactura>/` — PATCH acepta `estado`, `fecha_pago`, `comentario`; estados 5 y 8 exigen `fecha_pago`
- `GET|POST facturas/<idfactura>/comentarios/` y `PATCH .../comentarios/<idreg>/` — sobre `Factura_Seg`, usuario `api:<nombre>`
- `GET clientes/` — filtros `q`, `rut`
- `GET proyectos/` — filtros `estado`, `idcliente`, `rut` (cliente de facturación o mandante), `desde`, `hasta` (fecha de creación), `q` (nombre o número)
- `GET|PATCH proyectos/<idproyecto>/` — ficha completa; PATCH acepta `estado` (exige `comentario`) y `comentario`
- `GET|POST proyectos/<idproyecto>/comentarios/` — sobre `Proyecto_Seg`
- `GET proyectos/estados/`, `GET cotizaciones/estados/`
- `GET cotizaciones/` — filtros `estado`, `idcliente`, `rut`, `desde`, `hasta`, `q`; `GET cotizaciones/<idcotizacion>/`

Notas: en proyectos, `cliente` es a quién se factura (`Proyecto.IdCliente`) y `mandante` el cliente de la cotización; "incluye trámite SEREMI" se deduce de items cuya glosa dice SEREMI. Facturas exentas de IVA (`neto` = `total` = `ValorTotalPesos`, `iva` = 0). Nombres de estado desde `tEstado` con `TipoEstado = 3`.
