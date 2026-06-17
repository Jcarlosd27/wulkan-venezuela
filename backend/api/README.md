# FVENTAS Flask Admin

Admin panel y API movil para FVENTAS multiempresa y multipais.

## Stack

- Flask
- Bootstrap 5.3
- UIX local en `static/css/uix.css`
- Motor local de FVENTAS Insights en `core/insights.py` y `static/js/insights.js`
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

Mantenimiento operativo:

```text
http://localhost:5000/maintenance
```

## Base de datos

Archivo de variables sugerido:

```text
backend/api/.env.example
```

Fuente de datos:

```text
FVENTAS_DATA_BACKEND=json
```

Para operar contra SQL:

```powershell
$env:FVENTAS_DATA_BACKEND="sql"
$env:FVENTAS_SQL_FALLBACK_TO_JSON="0"
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
FVENTAS_ENV=production
FVENTAS_APP_VERSION=1.0.0
FVENTAS_BUILD_SHA=<commit-git>
FVENTAS_SECRET_KEY=<secreto-real-largo>
FVENTAS_DATA_BACKEND=sql
FVENTAS_SQL_FALLBACK_TO_JSON=0
FVENTAS_REQUIRE_MOBILE_TOKEN=1
FVENTAS_DATABASE_URL=postgresql+psycopg://user:password@host:5432/FVENTAS
FVENTAS_LOGIN_MAX_ATTEMPTS=5
FVENTAS_LOGIN_WINDOW_SECONDS=300
FVENTAS_MAX_UPLOAD_MB=16
FVENTAS_BACKUP_DIR=backups
FVENTAS_LOG_LEVEL=INFO
FVENTAS_RUN_MIGRATIONS=1
FVENTAS_HARDEN_DEFAULT_ACCOUNTS=1
FVENTAS_STORAGE_BACKEND=s3
FVENTAS_STORAGE_PUBLIC_BASE_URL=https://FVENTAS-assets.atl1.cdn.digitaloceanspaces.com
FVENTAS_S3_BUCKET=FVENTAS-assets
FVENTAS_S3_REGION=atl1
FVENTAS_S3_ENDPOINT_URL=https://atl1.digitaloceanspaces.com
FVENTAS_S3_PREFIX=production
```

En `production`, Flask falla al arrancar si intenta usar secreto de desarrollo, backend JSON, SQLite, fallback a JSON o storage local. Con `FVENTAS_HARDEN_DEFAULT_ACCOUNTS=1`, el arranque productivo deshabilita cuentas demo y oculta el catalogo demo inicial.

## Produccion con Docker

Desde `infra/docker`:

```bash
cp .env.production.example .env.production
docker compose -f docker-compose.production.yml --env-file .env.production up -d --build
```

Crear admin inicial:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production exec api \
  python scripts/create_admin.py --email admin@FVENTAS.com --name "Admin FVENTAS" --role super_admin
```

Smoke test:

```bash
python scripts/readiness_check.py --strict
python scripts/smoke_production.py --base-url https://FVENTAS.example.com
```

Backup:

```bash
python scripts/backup_database.py --output-dir backups
```

## Produccion en DigitalOcean

El proyecto incluye una spec para App Platform en `.do/app.yaml` y una guia operativa en `infra/digitalocean/README.md`.

Arquitectura recomendada:

- App Platform ejecuta este backend con Docker.
- Managed PostgreSQL usa `FVENTAS_DATABASE_URL` o `DATABASE_URL`.
- DigitalOcean Spaces usa `FVENTAS_STORAGE_BACKEND=s3`.
- La app movil se compila con `apps/mobile/dart_defines.digitalocean.example.json`.

El contenedor usa `scripts/start_web.sh`, ejecuta `python -m alembic upgrade head` al iniciar, deshabilita seeds demo en produccion y luego levanta Gunicorn con el puerto entregado por DigitalOcean.

## Estructura backend

Los modulos de infraestructura viven en `core/`. Los archivos historicos `config.py`, `db.py`, `storage.py`, `uix.py`, `insights.py` y `chile_locations.py` quedan solo como compatibilidad para scripts antiguos. Codigo nuevo debe importar desde `core`.

Guia completa: `../../docs/architecture/PROJECT_STRUCTURE.md`.

## Seguridad admin

- Los formularios del admin usan CSRF con `csrf_field()`.
- La API movil queda fuera de CSRF y usa autenticacion JSON/token.
- Roles disponibles: `super_admin`, `commercial_manager`, `operator`, `sales`, `inventory`, `readonly`.
- El rol `sales` es para vendedores en app movil; el panel web queda restringido a roles administrativos.
- Auditoria disponible en `/audit` para `super_admin`.
- Usuarios admin y clientes nuevos quedan con contrasena temporal y `mustChangePassword`.
- El admin cambia su clave en `/account/password`.
- El cliente B2B cambia su clave con `POST /api/mobile/auth/change-password`.
- Login admin y movil tienen bloqueo temporal por intentos fallidos.
