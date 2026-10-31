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
python manage.py migrate api                                   # tabla api_apikey
python manage.py apikey crear "Sistema ERP"                    # solo lectura; muestra la clave una vez
python manage.py apikey crear "Conciliador" --escritura        # lectura y escritura
python manage.py apikey permisos "Sistema ERP" --escritura si
python manage.py apikey listar
python manage.py apikey revocar "Sistema ERP"
```

Endpoints (`/api/v1/`):
- `GET facturas/` — filtros: `estado` (lista con comas), `desde`, `hasta`, `rut`, `idcliente`, `idproyecto`, `folio`, `monto_min`, `monto_max`, `monto` + `tolerancia` / `tolerancia_pct`, `modificado_desde`, `page`, `page_size` (máx. 500)
- `GET|PATCH facturas/<idfactura>/` — PATCH acepta `estado`, `fecha_pago`, `comentario`; estados 5 y 8 exigen `fecha_pago`
- `GET|POST facturas/<idfactura>/comentarios/` y `PATCH .../comentarios/<idreg>/` — sobre `Factura_Seg`, usuario `api:<nombre>`
- `GET clientes/` — filtros `q`, `rut`

Notas: facturas exentas de IVA (`neto` = `total` = `ValorTotalPesos`, `iva` = 0). Nombres de estado desde `tEstado` con `TipoEstado = 3`.
