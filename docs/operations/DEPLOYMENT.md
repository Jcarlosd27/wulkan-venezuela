# Guia de despliegue productivo

## Objetivo

Publicar Wulkan como plataforma comercial B2B real:

- Admin Flask por HTTPS.
- API movil por HTTPS.
- PostgreSQL como base productiva.
- Storage externo para imagenes y PDFs.
- Backups reproducibles.
- App Flutter apuntando al dominio productivo.

## Stack productivo

- Flask + Gunicorn.
- PostgreSQL.
- SQLAlchemy + Alembic.
- Caddy como reverse proxy con HTTPS automatico.
- S3 compatible para media comercial.
- Flutter Android en modo API.

## Variables obligatorias

Usar `infra/docker/.env.production.example` como base y crear:

```text
infra/docker/.env.production
```

Valores minimos:

```bash
WULKAN_DOMAIN=wulkan.example.com
WULKAN_ENV=production
WULKAN_SECRET_KEY=<secreto-real-largo>
WULKAN_REQUIRE_MOBILE_TOKEN=1
POSTGRES_DB=wulkan
POSTGRES_USER=wulkan
POSTGRES_PASSWORD=<password-fuerte>
WULKAN_STORAGE_BACKEND=s3
WULKAN_STORAGE_PUBLIC_BASE_URL=https://cdn.example.com
WULKAN_S3_BUCKET=wulkan-assets
WULKAN_S3_REGION=us-east-1
WULKAN_S3_PREFIX=production
```

En produccion el backend no arranca si detecta:

- `WULKAN_SECRET_KEY=wulkan-dev`.
- `WULKAN_DATA_BACKEND=json`.
- SQLite.
- Fallback SQL a JSON.
- Storage local.

## Despliegue con Docker

Desde `infra/docker`:

```bash
cp .env.production.example .env.production
docker compose -f docker-compose.production.yml --env-file .env.production up -d --build
```

El servicio `api` ejecuta:

```bash
python -m alembic upgrade head
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 60 wsgi:application
```

Para contenedores pequenos, partir con `WULKAN_WEB_WORKERS=1` evita duplicar memoria en procesos Python. Los threads mantienen concurrencia suficiente para el panel, API movil y cargas operativas iniciales. Si el trafico crece y la RAM queda estable bajo 70%, se puede aumentar workers o subir el tamano del contenedor.

Caddy publica el dominio definido en `WULKAN_DOMAIN` y solicita certificado HTTPS automaticamente. El DNS del dominio debe apuntar al servidor antes de levantar el stack.

## Primer administrador

Crear o restablecer un admin inicial:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production exec api \
  python scripts/create_admin.py \
  --email admin@wulkan.com \
  --name "Admin Wulkan" \
  --role super_admin
```

El usuario queda con `mustChangePassword=true`, por lo que debera cambiar la clave al ingresar.

## Smoke test

Luego de levantar:

```bash
python backend/api/scripts/smoke_production.py --base-url https://wulkan.example.com
python backend/api/scripts/smoke_security.py
```

Tambien se puede ejecutar con npm desde la raiz para entorno local:

```bash
npm run prod:smoke -- --base-url http://localhost:5000
```

Debe validar:

- `/healthz`.
- `/readyz`.
- `/api/v1/mobile/products`.
- `/api/v1/mobile/categories`.
- `/api/v1/mobile/announcements`.

Si `WULKAN_REQUIRE_MOBILE_TOKEN=1`, el smoke sin credenciales valida que esas rutas moviles
respondan `401 token requerido`. Para validar lectura real con token:

```bash
set WULKAN_SMOKE_MOBILE_EMAIL=cliente@empresa.com
set WULKAN_SMOKE_MOBILE_PASSWORD=clave-temporal-o-real
python backend/api/scripts/smoke_production.py --base-url https://crmwulky.com.ve
```

## Backups

Crear backup:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production exec api \
  python scripts/backup_database.py --output-dir /app/backups
```

Restaurar backup:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production exec api \
  python scripts/restore_database.py /app/backups/wulkan-YYYYMMDD-HHMMSS.dump --yes
```

Recomendacion operativa:

- Backup diario.
- Retencion minima 30 dias.
- Copiar backups fuera del servidor.
- Probar restauracion en staging al menos una vez al mes.

## Storage externo

Produccion exige:

```bash
WULKAN_STORAGE_BACKEND=s3
```

Compatible con:

- AWS S3.
- Cloudflare R2.
- DigitalOcean Spaces.
- MinIO administrado.

Si se usa R2/Spaces/MinIO, configurar `WULKAN_S3_ENDPOINT_URL`.

Los uploads admitidos son:

- `jpg`
- `jpeg`
- `png`
- `webp`
- `gif`
- `pdf`

## App movil en produccion

Editar:

```text
apps/mobile/dart_defines.production.example.json
```

Configurar:

```json
{
  "WULKAN_MOBILE_DATA_SOURCE": "api",
  "WULKAN_MOBILE_AUTH_MODE": "api",
  "WULKAN_ADMIN_API_URL": "https://wulkan.example.com/api/v1/mobile",
  "WULKAN_MOBILE_ORDER_API_URL": "https://wulkan.example.com/api/v1/mobile/orders"
}
```

Compilar APK:

```bash
npm run mobile:build:apk:prod
```

## Checklist de salida a produccion

- Dominio apuntando al servidor.
- HTTPS activo.
- `WULKAN_ENV=production`.
- `WULKAN_SECRET_KEY` real.
- PostgreSQL activo.
- Alembic en `head`.
- Storage externo activo.
- Admin inicial creado.
- Login admin probado.
- Cliente ferretero creado.
- Login movil probado.
- Cambio de contrasena temporal probado.
- Producto publicado desde admin.
- Producto visible en app.
- Orden creada desde app.
- Orden visible en admin.
- Credito del ferretero recalculado.
- Stock reservado/descontado segun estado.
- Backup creado.
- Restore probado en staging.
- Smoke test pasando.
