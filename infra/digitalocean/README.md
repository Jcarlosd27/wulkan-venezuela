# DigitalOcean para FVENTAS

Esta carpeta deja el proyecto listo para operar el admin Flask y la API movil de FVENTAS en DigitalOcean.

## Componentes

- **App Platform o Droplet**: ejecuta `backend/api` con Docker, Gunicorn y Flask.
- **Managed PostgreSQL**: almacena productos, categorias, clientes, credito, ordenes, auditoria y usuarios admin.
- **Spaces**: almacena fotos de productos, imagenes de categorias, banners y PDFs.
- **App movil Flutter**: consume el dominio publico del admin/API, no el computador local.

## Archivos preparados

- `.do/app.yaml`: spec de App Platform conectada a GitHub.
- `backend/api/Dockerfile`: contenedor productivo.
- `backend/api/scripts/start_web.sh`: ejecuta migraciones Alembic y levanta Gunicorn usando `$PORT`.
- `infra/digitalocean/.env.digitalocean.example`: variables para revisar o copiar en App Platform.
- `apps/mobile/dart_defines.digitalocean.example.json`: configuracion movil apuntando al dominio publico.

## Uso de RAM en App Platform

En el plan pequeno de App Platform se recomienda partir con:

```bash
FVENTAS_WEB_WORKERS=1
FVENTAS_WEB_THREADS=4
FVENTAS_DB_POOL_SIZE=2
FVENTAS_DB_MAX_OVERFLOW=2
```

Esto evita levantar copias innecesarias de Flask/Gunicorn y mantiene un pool SQL acotado. Si la RAM se mantiene bajo 70% y el trafico crece, se puede escalar subiendo el tamano del contenedor antes de aumentar workers.

## Ruta recomendada: App Platform

1. Crear un Space, por ejemplo `fventas-assets`, en la region elegida.
2. Crear una llave de Spaces y guardarla como `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY`.
3. Crear la App Platform desde el repositorio de GitHub `Jcarlosd27/wulkan-venezuela` o importando `.do/app.yaml`.
4. Reemplazar estos valores antes del primer deploy:
   - `FVENTAS_SECRET_KEY`
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `FVENTAS_STORAGE_PUBLIC_BASE_URL`
   - `FVENTAS_S3_BUCKET`
   - `FVENTAS_S3_REGION`
   - `FVENTAS_S3_ENDPOINT_URL`
   - `FVENTAS_SIGNUP_WINDOW_SECONDS` y `FVENTAS_SIGNUP_MAX_EVENTS`
   - `FVENTAS_ACCOUNT_DELETION_WINDOW_SECONDS` y `FVENTAS_ACCOUNT_DELETION_MAX_EVENTS`
5. Confirmar que la base de datos quede enlazada y que `FVENTAS_DATABASE_URL` use la variable interna entregada por App Platform.

`FVENTAS_S3_ACL=public-read` solo debe aplicar a recursos publicos como imagenes de producto/categoria/anuncios. Los documentos internos quedan protegidos por visibilidad, ruta firmada y auditoria desde el panel.

## Ruta alternativa: Droplet con Docker Compose

Usar esta ruta si Oceancloud se administrara como VPS.

```bash
cd infra/docker
cp .env.production.example .env.production
# Editar .env.production con dominio, Managed PostgreSQL, Spaces y secretos reales.
docker compose -f docker-compose.production.yml --env-file .env.production build
docker compose -f docker-compose.production.yml --env-file .env.production up -d
```

Si se necesita un ambiente autocontenido con PostgreSQL dentro del VPS:

```bash
cd infra/docker
cp .env.production.localdb.example .env.production
# Editar secretos, dominio y storage antes de levantar.
docker compose \
  -f docker-compose.production.yml \
  -f docker-compose.production.localdb.yml \
  --env-file .env.production \
  up -d --build
```

El backend falla al arrancar en produccion si intenta usar JSON, SQLite, storage local o secreto de desarrollo. Con `FVENTAS_HARDEN_DEFAULT_ACCOUNTS=1`, el arranque tambien deshabilita cuentas, clientes, productos, categorias, anuncios y servicios tecnicos demo para que la app solo muestre datos creados o cargados por la empresa suscrita.

## Crear el primer super admin

Despues del primer deploy, abrir la consola del componente web en DigitalOcean y ejecutar:

```bash
python scripts/create_admin.py \
  --email admin@empresa.com \
  --name "Admin FVENTAS" \
  --role super_admin
```

El script pide una contrasena temporal segura y obliga a cambiarla al iniciar sesion.

## Validar produccion

```bash
python scripts/readiness_check.py --strict
python scripts/smoke_production.py --base-url https://app.example.com
```

`readiness_check.py --strict` debe pasar antes de venta comercial: exige super admin real, sin demos activos, catalogo/categorias reales y configuracion SQL/S3/token movil. Si todavia no hay productos reales cargados, el smoke puede fallar en catalogo aunque el servicio este sano.

Endpoints importantes:

- `/healthz`: salud del servicio.
- `/readyz`: valida lectura de datos.
- `/api/v1/mobile/products`: catalogo movil.
- `/api/v1/mobile/categories`: categorias movil.
- `/api/v1/mobile/announcements`: carrusel movil.

## Compilar la app movil contra DigitalOcean

Editar `apps/mobile/dart_defines.digitalocean.example.json` con el dominio real:

```json
{
  "FVENTAS_ADMIN_API_URL": "https://app.example.com/api/v1/mobile",
  "FVENTAS_MOBILE_ORDER_API_URL": "https://app.example.com/api/v1/mobile/orders"
}
```

Luego compilar:

```bash
cd apps/mobile
flutter build apk --release --dart-define-from-file=dart_defines.digitalocean.example.json
```

Para instalar en el telefono conectado:

```bash
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

Con este modo ya no se usa `adb reverse`; la app consulta el backend publico de DigitalOcean.
