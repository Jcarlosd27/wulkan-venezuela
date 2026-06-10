# Wulkan Venezuela

Plataforma ecommerce B2B para Wulkan Venezuela. El sistema permite administrar catalogo, categorias, stock, fotos, PDFs, anuncios moviles, clientes ferreteros, vendedores, credito B2B, ordenes, comisiones, servicios tecnicos, usuarios admin y auditoria.

## Arquitectura Actual

- `backend/api`: admin web Flask, API movil, modelos SQL, migraciones Alembic, storage S3 compatible y scripts operativos.
- `apps/mobile`: app Android Flutter para clientes ferreteros y vendedores, conectada al backend Flask.
- `.do/app.yaml`: spec de DigitalOcean App Platform para desplegar el backend.
- `infra/digitalocean`: guia y variables de produccion para App Platform, PostgreSQL y Spaces.
- `infra/docker`: archivos opcionales para operacion con Docker.
- `docs`: documentacion comercial, operativa y de avance.

## Stack Productivo

- Flask + Bootstrap 5.3 + UIX + Graphify.
- PostgreSQL en DigitalOcean Managed Database.
- DigitalOcean Spaces para fotos, banners y PDFs.
- Flutter Android consumiendo `https://crmwulky.com.ve/api/mobile`.

El proyecto ya no usa Next.js, Firebase, Firestore, Cloud Functions ni monorepo Node/pnpm.

## Comandos Principales

Backend:

```powershell
cd backend/api
python -m compileall .
python scripts/readiness_check.py --strict
python scripts/smoke_production.py --base-url https://crmwulky.com.ve
```

App movil:

```powershell
cd apps/mobile
flutter pub get
flutter analyze
flutter test
flutter build apk --release --dart-define-from-file=dart_defines.digitalocean.example.json
```

## Produccion DigitalOcean

La guia de despliegue esta en `infra/digitalocean/README.md`.

La app movil debe compilarse con:

- `WULKAN_MOBILE_DATA_SOURCE=api`
- `WULKAN_MOBILE_AUTH_MODE=api`
- `WULKAN_ADMIN_API_URL=https://crmwulky.com.ve/api/mobile`
- `WULKAN_MOBILE_ORDER_API_URL=https://crmwulky.com.ve/api/mobile/orders`
