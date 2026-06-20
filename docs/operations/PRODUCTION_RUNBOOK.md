# FVENTAS Production Runbook

Fecha base: 2026-06-18

Este runbook deja el flujo minimo para pasar FVENTAS a produccion sin exponer datos demo, sin saltar controles de seguridad y con la app movil apuntando al backend real.

## Alcance comercial de lanzamiento

El panel entregado a empresas suscriptoras debe concentrarse solo en los modulos necesarios para operar la app movil:

- Dashboard.
- Vendedores.
- Clientes B2B.
- Credito B2B.
- Ordenes.
- Comisiones.
- Productos.
- Categorias.
- Biblioteca tecnica.
- Stock.
- Anuncios app.
- Servicios tecnicos/puntos.
- Notificaciones.
- Reglas de negocio.
- Configuracion.
- Usuarios admin.
- Documentos.
- Plantillas.
- Auditoria.

Los modulos CRM, cotizaciones web, cobranza dedicada, despacho dedicado, reportes avanzados, mantenimiento y permisos granulares quedan archivados para empresas en esta version. Si un rol de empresa intenta abrirlos por URL, debe recibir 403. `Mantenimiento` queda reservado para `platform_admin`.

El alcance geografico comercial de esta version queda limitado a Chile y Venezuela:

- Chile: RUT, regiones/comunas, precios visibles en CLP con simbolo `$`.
- Venezuela: RIF, estados/municipios, precios visibles en USD con simbolo `$`.
- Otros paises no deben aparecer en landing, signup, configuracion, panel plataforma ni app movil hasta que se active un nuevo mercado con su biblioteca territorial, moneda, textos legales y smokes.

## Estado actual

No subir trafico real hasta que `scripts/readiness_check.py --strict` finalice sin errores.

El ultimo readiness local marco bloqueos que requieren datos o credenciales productivas:

- Configurar PostgreSQL real; SQLite no es valido para produccion.
- Configurar storage S3/Spaces y `FVENTAS_STORAGE_PUBLIC_BASE_URL`.
- Crear al menos un super administrador real activo.
- Ejecutar bootstrap productivo para empresa base, aceptacion legal y catalogo inicial.
- Cargar vendedores y clientes B2B reales antes del smoke comercial.

## Variables obligatorias

Crear `infra/docker/.env.production` desde `infra/docker/.env.production.example` y reemplazar todos los placeholders.

- `FVENTAS_DOMAIN`: dominio publico del panel/API.
- `FVENTAS_SECRET_KEY`: secreto largo generado para produccion.
- `POSTGRES_PASSWORD`: password fuerte de PostgreSQL.
- `FVENTAS_STORAGE_BACKEND=s3`.
- `FVENTAS_S3_BUCKET`, `FVENTAS_S3_REGION`, `FVENTAS_STORAGE_PUBLIC_BASE_URL`.
- `FVENTAS_CSP_REPORT_ONLY=0`.
- `FVENTAS_REQUIRE_MOBILE_TOKEN=1`.
- `FVENTAS_REJECT_LEGACY_MOBILE_TOKENS=1`.
- `FVENTAS_REQUIRE_MOBILE_DEVICE_HEADER=1`.
- `FVENTAS_ALLOW_LEGACY_MOBILE_API=0`.
- `FVENTAS_TRUST_PROXY_HEADERS=1` si el backend esta detras de DigitalOcean App Platform, Caddy u otro proxy que sanee `X-Forwarded-For`.
- `FVENTAS_LANDING_ACCESS_PREFERENCE_WINDOW_SECONDS` y `FVENTAS_LANDING_ACCESS_PREFERENCE_MAX_EVENTS` para limitar eventos anonimos desde la landing.
- `FVENTAS_ACCOUNT_DELETION_WINDOW_SECONDS` y `FVENTAS_ACCOUNT_DELETION_MAX_EVENTS` para limitar solicitudes publicas repetidas de eliminacion de cuenta.
- `FVENTAS_MOBILE_PASSWORD_RECOVERY_WINDOW_SECONDS` y `FVENTAS_MOBILE_PASSWORD_RECOVERY_MAX_EVENTS` para limitar recuperaciones moviles repetidas sin enumerar cuentas.
- `FVENTAS_HARDEN_DEFAULT_ACCOUNTS=1`.

Generar secretos:

```bash
openssl rand -base64 48
```

## Despliegue backend/admin con base administrada

```bash
cd infra/docker
cp .env.production.example .env.production
# Editar .env.production con dominio, secretos, Managed PostgreSQL y S3/Spaces reales.
docker compose -f docker-compose.production.yml --env-file .env.production build
docker compose -f docker-compose.production.yml --env-file .env.production up -d
docker compose -f docker-compose.production.yml --env-file .env.production ps
```

El contenedor `api` ejecuta `scripts/start_web.sh`, que corre migraciones, endurece cuentas/demo y levanta Gunicorn.

Si se publica con Caddy o DigitalOcean App Platform, mantener `FVENTAS_TRUST_PROXY_HEADERS=1` para que auditoria, bloqueo de login y logs comerciales usen la IP real del cliente. Si se expone Flask/Gunicorn directamente sin proxy confiable, dejarlo en `0`.

Para S3/Spaces, `FVENTAS_S3_ACL=public-read` puede usarse solo para imagenes y recursos publicos. Los documentos internos subidos desde Biblioteca/Documentos no heredan ACL publica y deben abrirse mediante la ruta firmada del panel.

## Bootstrap inicial sin datos demo

Antes de publicar trafico real, crear el super admin y sembrar datos base usando valores reales en `.env.production`.

Variables minimas:

```bash
FVENTAS_BOOTSTRAP_ON_START=0
FVENTAS_BOOTSTRAP_RESET_PASSWORDS=0
FVENTAS_BOOTSTRAP_OWNER_NAME="Nombre responsable"
FVENTAS_BOOTSTRAP_OWNER_EMAIL="responsable@empresa.com"
FVENTAS_BOOTSTRAP_ADMIN_NAME="Christian Super Admin"
FVENTAS_BOOTSTRAP_ADMIN_EMAIL="admin@empresa.com"
FVENTAS_BOOTSTRAP_ADMIN_PASSWORD="password-temporal-fuerte"
```

Variables opcionales para dejar el flujo vendedor/cliente listo:

```bash
FVENTAS_BOOTSTRAP_SELLER_NAME="Vendedor inicial"
FVENTAS_BOOTSTRAP_SELLER_EMAIL="vendedor@empresa.com"
FVENTAS_BOOTSTRAP_SELLER_PASSWORD="password-temporal-fuerte"
FVENTAS_BOOTSTRAP_CLIENT_BUSINESS_NAME="Cliente B2B inicial"
FVENTAS_BOOTSTRAP_CLIENT_EMAIL="cliente@empresa.com"
FVENTAS_BOOTSTRAP_CLIENT_PASSWORD="password-temporal-fuerte"
```

Ejecutar:

```bash
cd infra/docker
docker compose -f docker-compose.production.yml --env-file .env.production exec api python scripts/bootstrap_production.py
```

El bootstrap es idempotente: actualiza la empresa base, registra aceptacion legal vigente, crea/actualiza el super admin real, crea vendedor/cliente solo si entregaste variables y siembra categorias/productos base con imagen para que la app movil no quede vacia.

Por seguridad, si el usuario, vendedor o cliente ya existe, el bootstrap no resetea su password salvo que ejecutes con `--reset-passwords` o configures `FVENTAS_BOOTSTRAP_RESET_PASSWORDS=1`. Para correrlo automaticamente durante el arranque del contenedor, configura `FVENTAS_BOOTSTRAP_ON_START=1`; el arranque usa modo no interactivo y fallara si falta una password necesaria para crear una cuenta nueva.

## Despliegue alternativo con PostgreSQL local en Docker

Solo usar esta ruta si no se contratara una base administrada.

```bash
cd infra/docker
cp .env.production.localdb.example .env.production
# Editar secretos, dominio y storage reales.
docker compose \
  -f docker-compose.production.yml \
  -f docker-compose.production.localdb.yml \
  --env-file .env.production \
  up -d --build
```

## Validacion antes de trafico real

```bash
cd infra/docker
docker compose -f docker-compose.production.yml --env-file .env.production exec api python scripts/readiness_check.py --strict
docker compose -f docker-compose.production.yml --env-file .env.production exec api python scripts/smoke_production.py --base-url https://TU_DOMINIO
```

Antes de enviar a App Store o TestFlight externo, confirmar:

- Backend/API productivo accesible por HTTPS publico.
- Cuenta demo de cliente B2B activa con catalogo, carrito, pedido e historial visibles.
- Cuenta demo de vendedor activa con catalogo, creacion de cliente, pedido asistido y comisiones visibles.
- Notas de revision con credenciales demo, pais/moneda configurada y explicacion de que es una app B2B privada para empresas suscriptoras.
- Politica de privacidad, terminos y eliminacion publicados desde URLs publicas.
- La app no contiene datos demo sensibles ni permite navegar datos de otra empresa.

Para probar endpoints protegidos de la app movil:

```bash
export FVENTAS_SMOKE_MOBILE_EMAIL="cliente-real@empresa.com"
export FVENTAS_SMOKE_MOBILE_PASSWORD="password-temporal"
docker compose -f docker-compose.production.yml --env-file .env.production exec api python scripts/smoke_production.py --base-url https://TU_DOMINIO
```

## Build movil

Actualizar `apps/mobile/dart_defines.production.example.json` con el dominio real y generar builds sin mocks.

```bash
cd apps/mobile
flutter test
flutter build ipa --dart-define-from-file=dart_defines.production.json
flutter build appbundle --dart-define-from-file=dart_defines.production.json
```

Condiciones obligatorias para publicar:

- `FVENTAS_ALLOW_MOCK=false`.
- `FVENTAS_MOBILE_DATA_SOURCE=api`.
- `FVENTAS_MOBILE_AUTH_MODE=api`.
- URLs bajo `/api/v1/mobile`.
- La moneda visible debe provenir del mercado/empresa suscriptora retornada por el backend.

## Checklist go-live

- DNS del dominio apuntando al servidor.
- HTTPS valido desde Caddy.
- `/healthz`, `/readyz` y `/api/v1/mobile/meta` responden 200.
- Readiness estricto sin errores.
- Smoke movil con cliente real sin 401 inesperado.
- Super admin real creado y cuentas demo desactivadas.
- Empresas suscriptoras tienen pais, moneda, condiciones de compra y aceptacion legal.
- Productos, categorias, vendedores y clientes estan asociados a su empresa.
- Backups de PostgreSQL y bucket S3 configurados.
- Politica de privacidad, terminos y eliminacion de cuenta accesibles desde landing y app.
