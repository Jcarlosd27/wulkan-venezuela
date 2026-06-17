# DigitalOcean para FVENTAS

Esta carpeta deja el proyecto listo para operar el admin Flask y la API movil de FVENTAS en DigitalOcean.

## Componentes

- **App Platform**: ejecuta `backend/api` con Docker, Gunicorn y Flask.
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

## Crear la app en DigitalOcean

1. Crear un Space, por ejemplo `fventas-assets`, en la region elegida.
2. Crear una llave de Spaces y guardarla como `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY`.
3. Crear la App Platform desde el repositorio de GitHub o importando `.do/app.yaml`.
4. Reemplazar estos valores antes del primer deploy:
   - `FVENTAS_SECRET_KEY`
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `FVENTAS_STORAGE_PUBLIC_BASE_URL`
   - `FVENTAS_S3_BUCKET`
   - `FVENTAS_S3_REGION`
   - `FVENTAS_S3_ENDPOINT_URL`
5. Confirmar que la base de datos quede enlazada y que `FVENTAS_DATABASE_URL` use la variable interna entregada por App Platform.

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
cd backend/api
python scripts/readiness_check.py --strict
python scripts/smoke_production.py --base-url https://app.fventas.cl
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
  "FVENTAS_ADMIN_API_URL": "https://app.fventas.cl/api/mobile",
  "FVENTAS_MOBILE_ORDER_API_URL": "https://app.fventas.cl/api/mobile/orders"
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
