# Avance Fase 11 - Kit de produccion final

## Objetivo

Convertir el piloto avanzado de Wulkan en un producto listo para desplegarse en un ambiente productivo real, con HTTPS, PostgreSQL, storage externo, backups, smoke checks y app movil compilable contra API.

## Entregado

- Backend Flask preparado para WSGI:
  - `backend/api/wsgi.py`.
  - Gunicorn en requirements.
  - `app.run()` sin debug en produccion.
- Docker productivo:
  - `backend/api/Dockerfile`.
  - `backend/api/.dockerignore`.
  - `infra/docker/docker-compose.production.yml`.
  - `infra/docker/Caddyfile`.
  - `infra/docker/.env.production.example`.
- HTTPS automatico con Caddy usando `WULKAN_DOMAIN`.
- PostgreSQL productivo con healthcheck.
- Alembic ejecutado al arrancar el contenedor `api`.
- Storage externo S3-compatible:
  - `WULKAN_STORAGE_BACKEND=s3`.
  - `WULKAN_STORAGE_PUBLIC_BASE_URL`.
  - `WULKAN_S3_BUCKET`.
  - `WULKAN_S3_REGION`.
  - `WULKAN_S3_ENDPOINT_URL`.
  - `WULKAN_S3_PREFIX`.
- Validacion de archivos subidos:
  - Imagenes: `jpg`, `jpeg`, `png`, `webp`, `gif`.
  - PDFs: `pdf`.
- Produccion bloqueada si intenta usar storage local.
- Scripts operativos:
  - `scripts/create_admin.py`.
  - `scripts/backup_database.py`.
  - `scripts/restore_database.py`.
  - `scripts/smoke_production.py`.
- GitHub Actions:
  - `.github/workflows/production-checks.yml`.
  - Backend Flask, migraciones y smoke local.
  - Flutter analyze y test.
- Defines moviles de produccion:
  - `apps/mobile/dart_defines.production.example.json`.
- Script npm:
  - `mobile:build:apk:prod`.
  - `prod:smoke`.
- Guia productiva actualizada en `docs/operations/DEPLOYMENT.md`.

## Graphify operativo

```text
WSGI/Gunicorn          Listo
Docker backend        Listo
PostgreSQL compose    Listo
HTTPS Caddy           Listo
Storage S3            Configurable
Backups               Script listo
Restore               Script listo
Smoke test            Script listo
APK API prod          Configurable
CI productivo         Activo
```

## Flujo productivo recomendado

1. Crear DNS para `WULKAN_DOMAIN`.
2. Copiar `infra/docker/.env.production.example` a `.env.production`.
3. Configurar secretos, PostgreSQL y S3.
4. Levantar:

```bash
cd infra/docker
docker compose -f docker-compose.production.yml --env-file .env.production up -d --build
```

5. Crear admin inicial:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production exec api \
  python scripts/create_admin.py --email admin@wulkan.com --name "Admin Wulkan" --role super_admin
```

6. Ejecutar smoke:

```bash
python backend/api/scripts/smoke_production.py --base-url https://wulkan.example.com
```

7. Compilar APK productiva:

```bash
npm run mobile:build:apk:prod
```

## Estado comercial

Con esta fase el repositorio queda **preparado para produccion final**.

Lo unico que no puede cerrarse desde codigo local es la activacion externa:

- Dominio real.
- DNS.
- Credenciales S3/R2/Spaces.
- Servidor/VPS o nube.
- Prueba real con ferretero y telefono apuntando al dominio HTTPS.

Cuando esos datos existan, el checklist de `docs/operations/DEPLOYMENT.md` permite llevarlo a operacion comercial real.
