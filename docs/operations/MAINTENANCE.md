# Mantenimiento Productivo Wulkan

Este documento resume las tareas operativas para mantener estable el Admin Panel, la API movil y la base B2B.

## Entornos

- `development`: uso local con JSON o SQLite.
- `staging`: pruebas con SQL y token movil obligatorio.
- `production`: operacion real con PostgreSQL, DigitalOcean Spaces y token movil obligatorio.

Variables minimas de produccion:

```text
WULKAN_ENV=production
WULKAN_SECRET_KEY=<secreto-real>
WULKAN_DATA_BACKEND=sql
WULKAN_SQL_FALLBACK_TO_JSON=0
WULKAN_REQUIRE_MOBILE_TOKEN=1
WULKAN_DATABASE_URL=<postgresql-url>
WULKAN_STORAGE_BACKEND=s3
WULKAN_S3_BUCKET=wulkan-assets
WULKAN_S3_REGION=atl1
WULKAN_S3_ENDPOINT_URL=https://atl1.digitaloceanspaces.com
WULKAN_STORAGE_PUBLIC_BASE_URL=https://wulkan-assets.atl1.cdn.digitaloceanspaces.com
```

## Migraciones

El contenedor ejecuta Alembic al iniciar cuando `WULKAN_RUN_MIGRATIONS=1`.

```bash
cd backend/api
python -m alembic upgrade head
```

Antes de subir cambios productivos, validar:

```bash
python -m compileall backend/api
python backend/api/scripts/smoke_production.py --base-url https://crmwulky.com.ve
```

## Backups

El backup usa `pg_dump` en formato custom.

```bash
cd backend/api
python scripts/backup_database.py --output-dir backups
```

Restauracion:

```bash
cd backend/api
python scripts/restore_database.py --backup-file backups/wulkan-YYYYMMDD-HHMMSS.dump
```

Recomendacion para produccion:

- Backup diario automatico.
- Retencion minima de 14 dias.
- Prueba de restauracion mensual en staging.
- Descargar respaldo antes de importaciones masivas grandes.

## Logs

- Errores: logs de Runtime en DigitalOcean App Platform.
- Actividad: modulo `Auditoria` del Admin Panel.
- Alertas internas: modulo `Notificaciones`.
- Readiness tecnico: modulo `Sistema > Mantenimiento`.

## Readiness

Ejecutar cuando se cambien variables, dominio, APK o datos base:

```bash
cd backend/api
python scripts/readiness_check.py --strict
```

El modulo `Mantenimiento` muestra:

- Entorno efectivo.
- Version y build.
- Backend de datos.
- Storage.
- Token movil.
- Migracion Alembic vigente.
- Estado de backups, logs, documentacion y paginacion.

## Versionado

Configurar en despliegue:

```text
WULKAN_APP_VERSION=1.0.0
WULKAN_BUILD_SHA=<commit-git>
```

La API movil publica estos datos en `/api/v1/mobile/meta`, `healthz` y `readyz`.
