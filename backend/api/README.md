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
