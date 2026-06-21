# FVENTAS

FVENTAS es una plataforma comercial B2B para Chile y Venezuela, con panel administrativo Flask, app movil Android/iOS en Flutter y configuracion comercial por empresa. En esta version solo se habilitan esos dos mercados: Chile opera con CLP, RUT, regiones y comunas; Venezuela opera con USD, RIF, estados y municipios. Ningun otro pais debe aparecer como opcion de alta, configuracion, mocks, app movil ni panel administrativo.

## Componentes

- `backend/api`: panel administrativo, API movil, base de datos SQL y scripts operativos.
- `apps/mobile`: app movil para vendedores y clientes B2B.
- `docs/architecture`: estructura tecnica y reglas de mantenimiento.
- `docs/product`: documentacion comercial y funcional.
- `docs/operations`: guias operativas, publicacion y escritorio Windows.
- `infra/digitalocean`: guia y variables para DigitalOcean App Platform.
- `store_assets/google_play`: recursos graficos para publicar la app en Google Play.

## Arranque local del admin

```powershell
cd backend/api
$env:FVENTAS_ENV='development'
$env:FVENTAS_DATA_BACKEND='sql'
$env:FVENTAS_DATABASE_URL='sqlite:///data/fventas.db'
$env:FVENTAS_SQL_FALLBACK_TO_JSON='0'
python -m flask --app app run --host 127.0.0.1 --port 5000
```

Luego abre `http://127.0.0.1:5000`.

## Verificacion rapida

```powershell
cd backend/api
python scripts/smoke_production.py --base-url http://127.0.0.1:5000
python scripts/readiness_check.py
```

## Notas de datos

La base limpia queda preparada para carga real. El catalogo base FVENTAS puede poblar categorias y productos iniciales desde los botones del panel, y los clientes, vendedores, ordenes, credito y comisiones deben cargarse desde el admin o la app movil segun el rol.

## Estructura mantenible

La guia tecnica de carpetas y responsabilidades esta en `docs/architecture/PROJECT_STRUCTURE.md`.
