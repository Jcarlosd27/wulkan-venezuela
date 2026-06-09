# Wulkan Flask Admin

Admin panel y API movil para Wulkan Venezuela.

## Stack

- Flask
- Bootstrap 5.3
- UIX local en `static/css/uix.css`
- Graphify local en `graphify.py` y `static/js/graphify.js`
- SQLAlchemy y Alembic para base productiva
- Gunicorn para runtime WSGI productivo
- Storage local en desarrollo y S3-compatible en produccion

## Ejecutar

Instalar dependencias:

```bash
python -m pip install -r backend/api/requirements.txt
```

Desde la raiz:

```bash
npm run dev:admin:flask
```

Admin:

```text
http://localhost:5000
```

API movil:

```text
http://localhost:5000/api/mobile/products
http://localhost:5000/api/mobile/announcements
http://localhost:5000/api/mobile/auth/login
```

Salud del servicio:

```text
http://localhost:5000/healthz
http://localhost:5000/readyz
```

## Base de datos

Archivo de variables sugerido:

```text
backend/api/.env.example
```

Fuente de datos:

```text
WULKAN_DATA_BACKEND=json
```

Para operar contra SQL:

```powershell
$env:WULKAN_DATA_BACKEND="sql"
$env:WULKAN_SQL_FALLBACK_TO_JSON="0"
```

Migrar base:

```bash
cd backend/api
python -m alembic upgrade head
```

Cargar datos actuales desde JSON en desarrollo local:

```bash
cd backend/api
python scripts/seed_database.py --reset
```

El seed local crea tablas si faltan y marca la base en Alembic `head`.

En staging o produccion:

```bash
cd backend/api
python -m alembic upgrade head
python scripts/seed_database.py
```

Variables recomendadas para produccion:

```bash
WULKAN_ENV=production
WULKAN_SECRET_KEY=<secreto-real-largo>
WULKAN_DATA_BACKEND=sql
WULKAN_SQL_FALLBACK_TO_JSON=0
WULKAN_REQUIRE_MOBILE_TOKEN=1
WULKAN_DATABASE_URL=postgresql+psycopg://user:password@host:5432/wulkan
WULKAN_LOGIN_MAX_ATTEMPTS=5
WULKAN_LOGIN_WINDOW_SECONDS=300
WULKAN_MAX_UPLOAD_MB=16
WULKAN_STORAGE_BACKEND=s3
WULKAN_STORAGE_PUBLIC_BASE_URL=https://cdn.example.com
WULKAN_S3_BUCKET=wulkan-assets
WULKAN_S3_REGION=us-east-1
WULKAN_S3_ENDPOINT_URL=
WULKAN_S3_PREFIX=production
```

En `production`, Flask falla al arrancar si intenta usar secreto de desarrollo, backend JSON, SQLite, fallback a JSON o storage local.

## Produccion con Docker

Desde `infra/docker`:

```bash
cp .env.production.example .env.production
docker compose -f docker-compose.production.yml --env-file .env.production up -d --build
```

Crear admin inicial:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production exec api \
  python scripts/create_admin.py --email admin@wulkan.com --name "Admin Wulkan" --role super_admin
```

Smoke test:

```bash
python scripts/smoke_production.py --base-url https://wulkan.example.com
```

Backup:

```bash
python scripts/backup_database.py --output-dir backups
```

## Produccion en DigitalOcean

El proyecto incluye una spec para App Platform en `.do/app.yaml` y una guia operativa en `infra/digitalocean/README.md`.

Arquitectura recomendada:

- App Platform ejecuta este backend con Docker.
- Managed PostgreSQL usa `WULKAN_DATABASE_URL` o `DATABASE_URL`.
- DigitalOcean Spaces usa `WULKAN_STORAGE_BACKEND=s3`.
- La app movil se compila con `apps/mobile/dart_defines.digitalocean.example.json`.

El contenedor usa `scripts/start_web.sh`, ejecuta `python -m alembic upgrade head` al iniciar y luego levanta Gunicorn con el puerto entregado por DigitalOcean.

## Seguridad admin

- Los formularios del admin usan CSRF con `csrf_field()`.
- La API movil queda fuera de CSRF y usa autenticacion JSON/token.
- Roles disponibles: `super_admin`, `operator`, `sales`, `inventory`, `readonly`.
- Auditoria disponible en `/audit` para `super_admin`.
- Usuarios admin y clientes nuevos quedan con contrasena temporal y `mustChangePassword`.
- El admin cambia su clave en `/account/password`.
- El ferretero cambia su clave con `POST /api/mobile/auth/change-password`.
- Login admin y movil tienen bloqueo temporal por intentos fallidos.
