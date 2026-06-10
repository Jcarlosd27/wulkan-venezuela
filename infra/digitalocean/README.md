# DigitalOcean para Wulkan Venezuela

Esta carpeta deja el proyecto listo para operar el admin Flask y la API movil en DigitalOcean.

## Componentes

- **App Platform**: ejecuta `backend/api` con Docker, Gunicorn y Flask.
- **Managed PostgreSQL**: almacena productos, categorias, clientes, credito, ordenes, auditoria y usuarios admin.
- **Spaces**: almacena fotos de productos, imagenes de categorias, banners y PDFs.
- **App movil Flutter**: consume el dominio publico del admin/API, no el computador local.

## Archivos preparados

- `.do/app.yaml`: spec de App Platform conectada a GitHub `Jcarlosd27/wulkan-venezuela`.
- `backend/api/Dockerfile`: contenedor productivo.
- `backend/api/scripts/start_web.sh`: ejecuta migraciones Alembic y levanta Gunicorn usando `$PORT`.
- `infra/digitalocean/.env.digitalocean.example`: variables para revisar o copiar en App Platform.
- `apps/mobile/dart_defines.digitalocean.example.json`: configuracion movil apuntando al dominio publico.

## Crear la app en DigitalOcean

1. Crear un Space, por ejemplo `wulkan-assets`, en la region elegida. Para la configuracion actual se usa `atl1`.
2. Crear una llave de Spaces y guardarla como `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY`.
3. Crear la App Platform desde el repositorio de GitHub o importando `.do/app.yaml`.
4. Reemplazar estos valores antes del primer deploy:
   - `WULKAN_SECRET_KEY`
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `WULKAN_STORAGE_PUBLIC_BASE_URL`
   - `WULKAN_S3_BUCKET`
   - `WULKAN_S3_REGION`
   - `WULKAN_S3_ENDPOINT_URL`
5. Confirmar que la base `wulkan-db` quede enlazada y que `WULKAN_DATABASE_URL` use `${wulkan-db.DATABASE_URL}`.

El backend falla al arrancar en produccion si intenta usar JSON, SQLite, storage local o secreto de desarrollo. Con `WULKAN_HARDEN_DEFAULT_ACCOUNTS=1`, el arranque tambien deshabilita cuentas, clientes, productos, categorias, anuncios y servicios tecnicos demo para que la app solo muestre datos creados o cargados por Wulkan.

## Crear el primer super admin

Despues del primer deploy, abrir la consola del componente `wulkan-admin` en DigitalOcean y ejecutar:

```bash
python scripts/create_admin.py \
  --email admin@wulkanvenezuela.com \
  --name "Admin Wulkan" \
  --role super_admin
```

El script pide una contrasena temporal segura y obliga a cambiarla al iniciar sesion.

## Validar produccion

```bash
cd backend/api
python scripts/readiness_check.py --strict
python scripts/smoke_production.py --base-url https://crmwulky.com.ve
```

`readiness_check.py --strict` debe pasar antes de venta comercial: exige super admin real, sin demos activos, catalogo/categorias reales y configuracion SQL/S3/token movil. Si todavia no hay productos reales cargados, el smoke puede fallar en catalogo aunque el servicio este sano.

Endpoints importantes:

- `/healthz`: salud del servicio.
- `/readyz`: valida lectura de datos.
- `/api/mobile/products`: catalogo movil.
- `/api/mobile/categories`: categorias movil.
- `/api/mobile/announcements`: carrusel movil.

## Compilar la app movil contra DigitalOcean

Editar `apps/mobile/dart_defines.digitalocean.example.json` con el dominio real:

```json
{
  "WULKAN_ADMIN_API_URL": "https://crmwulky.com.ve/api/mobile",
  "WULKAN_MOBILE_ORDER_API_URL": "https://crmwulky.com.ve/api/mobile/orders"
}
```

Luego compilar:

```bash
npm run mobile:build:apk:do
```

Para instalar en el telefono conectado:

```bash
adb install -r apps/mobile/build/app/outputs/flutter-apk/app-release.apk
```

Con este modo ya no se usa `adb reverse`; la app consulta el backend publico de DigitalOcean.
