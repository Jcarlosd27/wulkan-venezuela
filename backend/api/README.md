# Wulkan Flask Admin

Admin panel y API movil para Wulkan Venezuela.

## Stack

- Flask
- Bootstrap 5.3
- UIX local en `static/css/uix.css`
- Graphify local en `graphify.py` y `static/js/graphify.js`
- SQLAlchemy y Alembic para base productiva

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
```

En `production`, Flask falla al arrancar si intenta usar secreto de desarrollo, backend JSON, SQLite o fallback a JSON.

## Seguridad admin

- Los formularios del admin usan CSRF con `csrf_field()`.
- La API movil queda fuera de CSRF y usa autenticacion JSON/token.
- Roles disponibles: `super_admin`, `operator`, `sales`, `inventory`, `readonly`.
- Auditoria disponible en `/audit` para `super_admin`.
- Usuarios admin y clientes nuevos quedan con contrasena temporal y `mustChangePassword`.
- El admin cambia su clave en `/account/password`.
- El ferretero cambia su clave con `POST /api/mobile/auth/change-password`.
- Login admin y movil tienen bloqueo temporal por intentos fallidos.
