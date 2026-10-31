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

## API externa (solo lectura)
App `Proyecto/api/`. Autenticación con header `X-API-Key`.

```bash
python manage.py migrate api                # crea la tabla api_apikey
python manage.py apikey crear "Sistema ERP"  # muestra la clave una sola vez
python manage.py apikey listar
python manage.py apikey revocar "Sistema ERP"
```

Endpoints:
- `GET /api/v1/facturas/` — filtros: `desde`, `hasta` (fecha emisión), `modificado_desde` (FechaACT), `idcliente`, `rut`, `idproyecto`, `numfactura`, `estado`, `page`, `page_size` (máx. 500)
- `GET /api/v1/facturas/<idfactura>/`

```bash
curl -H "X-API-Key: <clave>" "https://<host>/api/v1/facturas/?desde=2026-01-01"
```
