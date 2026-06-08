# Avance Fase 8 - Runtime SQL conectado

## Objetivo

Conectar el admin Flask y la API movil con la base SQL preparada en Fase 7, manteniendo fallback JSON para desarrollo y seguridad operativa.

## Entregado

- Nuevo adapter `backend/api/sql_store.py`.
- `store.py` ahora soporta dos fuentes de datos:
  - `json`: modo actual por defecto.
  - `sql`: modo productivo con SQLAlchemy.
- Variable `WULKAN_DATA_BACKEND` agregada a configuracion.
- Variable `WULKAN_SQL_FALLBACK_TO_JSON` agregada para controlar fallback.
- Lectura SQL para:
  - Usuarios admin.
  - Clientes ferreteros.
  - Categorias.
  - Productos.
  - Biblioteca tecnica.
  - Anuncios app.
  - Stock y movimientos.
  - Ordenes.
  - Movimientos de credito.
- Escritura SQL mediante `save_store()` para las mismas entidades.
- Soft delete SQL para productos, categorias, anuncios, clientes, usuarios y media, evitando romper historiales de ordenes o stock.

## Graphify operativo

```text
Fuente actual       JSON por defecto / SQL activable
Admin panel         Conectado a load_store/save_store
API movil           Conectada a load_store/save_store
Orden movil SQL     Validada
Credito B2B SQL     Validado por orden movil aprobada
Fallback JSON       Disponible para desarrollo
```

## Como activar SQL

Desarrollo local:

```bash
cd backend/api
python -m pip install -r requirements.txt
python scripts/seed_database.py --reset
$env:WULKAN_DATA_BACKEND="sql"
$env:WULKAN_SQL_FALLBACK_TO_JSON="0"
python app.py
```

Produccion o staging:

```bash
WULKAN_ENV=production
WULKAN_DATA_BACKEND=sql
WULKAN_SQL_FALLBACK_TO_JSON=0
WULKAN_DATABASE_URL=postgresql+psycopg://user:password@host:5432/wulkan
WULKAN_SECRET_KEY=<secreto-real>
WULKAN_REQUIRE_MOBILE_TOKEN=1
```

## Validacion realizada

- Compilacion Python:
  - `app.py`
  - `store.py`
  - `sql_store.py`
  - `config.py`
  - `db.py`
  - `models.py`
  - `scripts/seed_database.py`
- Seed SQL local ejecutado correctamente.
- Rutas admin probadas en modo JSON:
  - `/`
  - `/products`
  - `/categories`
  - `/stock`
  - `/orders`
  - `/clients`
  - `/admin-users`
  - `/credit`
  - `/announcements`
  - `/media-library`
- Rutas admin probadas en modo SQL estricto:
  - Mismas rutas anteriores con `WULKAN_SQL_FALLBACK_TO_JSON=0`.
- API movil probada en modo JSON y SQL:
  - `/api/mobile/auth/login`
  - `/api/mobile/products`
  - `/api/mobile/categories`
  - `/api/mobile/announcements`
  - `/api/mobile/orders`
- Prueba SQL de escritura:
  - Orden creada desde API movil.
  - Orden aprobada con credito.
  - Orden visible para el cliente ferretero.
  - Movimiento de stock registrado.
- Base local reseteada luego de la prueba para no dejar ordenes temporales.

## Estado comercial

El panel ya puede operar conectado a SQL, pero la recomendacion para produccion es usar PostgreSQL y activar `WULKAN_SQL_FALLBACK_TO_JSON=0` para detectar errores reales.

Todavia falta para cierre comercial completo:

- CSRF en formularios admin.
- Auditoria por accion de usuario.
- Permisos reales por rol en cada modulo.
- Repositorios SQL especificos por modulo para reemplazar el adapter generico.
- Backups automaticos PostgreSQL.
- Despliegue HTTPS con secretos reales.
