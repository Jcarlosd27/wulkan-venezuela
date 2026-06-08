# Avance Fase 7 - Base productiva de datos

## Objetivo

Preparar el backend Flask para operar con base de datos real, migraciones reproducibles y configuracion por entorno, sin romper el admin actual ni la app movil.

## Entregado

- Configuracion centralizada en `backend/api/config.py`.
- Variables por entorno para `development`, `staging` y `production`.
- Dependencias productivas en `backend/api/requirements.txt`:
  - Flask.
  - SQLAlchemy.
  - Alembic.
  - python-dotenv.
  - psycopg para PostgreSQL.
- Modelos SQLAlchemy para:
  - Usuarios admin.
  - Clientes ferreteros.
  - Categorias.
  - Productos.
  - Biblioteca tecnica.
  - Anuncios.
  - Stock.
  - Ordenes.
  - Movimientos de credito.
- Migracion inicial Alembic en `backend/api/migrations/versions/20260608_0001_initial_schema.py`.
- Seed desde el store JSON actual hacia SQL en `backend/api/scripts/seed_database.py`.
- El seed local marca automaticamente la base en Alembic `head`.
- Base SQLite local generada en `backend/api/data/wulkan.db`.
- Archivos `.db` locales agregados a `.gitignore`.

## Comandos operativos

Instalar dependencias:

```bash
cd backend/api
python -m pip install -r requirements.txt
```

Crear o migrar base:

```bash
cd backend/api
python -m alembic upgrade head
```

Cargar datos actuales desde JSON en desarrollo local:

```bash
cd backend/api
python scripts/seed_database.py --reset
```

En staging o produccion, usar primero Alembic y luego sembrar sin `--reset`:

```bash
cd backend/api
python -m alembic upgrade head
python scripts/seed_database.py
```

Ejecutar admin:

```bash
npm run dev:admin:flask
```

## Variables de entorno

Archivo de referencia:

```text
backend/api/.env.example
```

Variables principales:

```text
WULKAN_ENV=development
WULKAN_SECRET_KEY=change-me-in-production
WULKAN_DATABASE_URL=sqlite:///data/wulkan.db
WULKAN_REQUIRE_MOBILE_TOKEN=0
```

Para staging o produccion:

```text
WULKAN_ENV=production
WULKAN_SECRET_KEY=<secreto-real>
WULKAN_DATABASE_URL=postgresql+psycopg://user:password@host:5432/wulkan
WULKAN_REQUIRE_MOBILE_TOKEN=1
```

## Validacion realizada

- Compilacion Python de `app.py`, `store.py`, `config.py`, `db.py`, `models.py`, `seed_database.py` y migraciones.
- `python scripts/seed_database.py --reset` ejecutado correctamente.
- Seed local autoestampado con Alembic `head`.
- Alembic `upgrade head` probado sobre una base SQLite de verificacion.
- Conteo SQL luego del seed:
  - 3 productos.
  - 1 cliente ferretero.
  - 2 ordenes.
  - 1 movimiento de credito.
- Rutas admin con sesion validada:
  - `/`
  - `/products`
  - `/products/new`
  - `/categories`
  - `/media-library`
  - `/stock`
  - `/announcements`
  - `/orders`
  - `/clients`
  - `/admin-users`
  - `/credit`
- API movil validada:
  - `/api/mobile/products`
  - `/api/mobile/auth/login`

## Estado comercial

Esta fase deja la plataforma lista para migrar a persistencia productiva, pero el admin aun usa el store JSON como fuente runtime para mantener estabilidad mientras se prepara el repositorio SQL.

Siguiente fase recomendada:

- Reemplazar progresivamente `store.py` por repositorios SQL.
- Activar PostgreSQL en staging.
- Usar Alembic como fuente oficial de cambios de esquema.
- Mantener Graphify para tableros y resumentes operativos sin inflar respuestas ni vistas.
