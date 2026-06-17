# Estructura mantenible FVENTAS

Este proyecto queda ordenado para crecer como plataforma SaaS B2B con panel administrativo, backend API y apps moviles Android/iOS.

## Raiz del repositorio

- `backend/api`: backend Flask, panel administrativo, API movil, base SQL, migraciones y scripts operativos.
- `apps/mobile`: aplicacion Flutter compartida para Android e iOS.
- `docs`: documentacion funcional, tecnica, comercial y operativa.
- `infra`: guias y archivos de despliegue.
- `store_assets`: recursos de publicacion para tiendas moviles.
- `artifacts`: carpeta local para entregables generados. No debe usarse como codigo fuente.

## Backend

- `backend/api/app.py`: composicion principal Flask y rutas actuales. Es el punto legado que se ira dividiendo por dominio.
- `backend/api/core`: infraestructura reutilizable.
  - `config.py`: variables de entorno y configuracion por ambiente.
  - `db.py`: conexion SQLAlchemy y ciclo de vida de base de datos.
  - `storage.py`: storage local/S3-compatible.
  - `uix.py`: helpers visuales y formato monetario.
  - `insights.py`: indicadores compactos de negocio para el panel.
  - `chile_locations.py`: normalizacion territorial y telefonica de Chile.
- `backend/api/models.py`: modelos SQLAlchemy.
- `backend/api/store.py`: interfaz de persistencia historica JSON/SQL.
- `backend/api/sql_store.py`: implementacion SQL de persistencia.
- `backend/api/templates`: vistas Jinja del admin.
- `backend/api/static`: CSS, JS e imagenes del admin.
- `backend/api/migrations`: migraciones Alembic.
- `backend/api/scripts`: comandos de mantenimiento, smoke tests, seeds y administracion.

Los archivos `config.py`, `db.py`, `storage.py`, `uix.py`, `insights.py` y `chile_locations.py` en la raiz de `backend/api` quedan como wrappers de compatibilidad. Codigo nuevo debe importar desde `core`.

## App movil

- `apps/mobile/lib/src/config`: configuracion de API y ambiente.
- `apps/mobile/lib/src/data`: clientes HTTP, repositorios y modelos de datos externos.
- `apps/mobile/lib/src/domain`: logica comercial compartida.
- `apps/mobile/lib/src/features`: pantallas por flujo, rol o modulo.
- `apps/mobile/android`: empaquetado Android.
- `apps/mobile/ios`: empaquetado iOS.

La app movil debe consumir exclusivamente la API publicada del backend. No debe depender del telefono conectado a la computadora para sincronizar productos, clientes, ordenes o comisiones.

## Evolucion recomendada del backend

Para mantener el sistema en el tiempo, las nuevas funcionalidades deben entrar por dominios:

- `auth`: sesiones, tokens, cambio de clave y recuperacion.
- `companies`: empresas SaaS, suscripciones, pais y moneda.
- `catalog`: categorias, productos, media, precios y stock.
- `commercial`: vendedores, clientes B2B, CRM, credito y condiciones.
- `orders`: ordenes, despacho, cotizaciones, abonos y comisiones.
- `system`: auditoria, reglas, mantenimiento, plantillas y notificaciones.
- `mobile_api`: endpoints consumidos por Android/iOS.

Cada dominio deberia tener rutas, servicios, validadores y pruebas. Esto evita que el archivo principal crezca indefinidamente.

## Regla de mantenimiento

- Las pantallas del admin deben reflejar la misma logica que la app movil.
- Toda accion sensible debe dejar evento de auditoria.
- Los datos creados desde mobile y web deben usar la misma capa de persistencia.
- Las importaciones masivas deben validar antes de guardar.
- Las monedas, paises, documentos fiscales, telefonos y ciudades deben depender de la configuracion de la empresa.
