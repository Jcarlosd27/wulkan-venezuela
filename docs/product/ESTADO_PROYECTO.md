# Estado del proyecto Wulkan

Fecha: 2026-06-08

## Lectura ejecutiva

Wulkan ya no esta en etapa de maqueta. El proyecto se encuentra en nivel **preparado para produccion final, pendiente de activacion externa**.

Estimacion actual:

- **95%** para piloto comercial controlado con Wulkan y ferreteros seleccionados.
- **88%** para produccion final vendible sin acompanar manualmente la operacion.

La diferencia existe porque el repositorio ya trae kit productivo, pero la activacion final depende de elementos externos: dominio, DNS, servidor, credenciales S3/PostgreSQL y QA con ferretero real.

## Stack actual

- Backend: Flask.
- Admin: Bootstrap 5.3, UIX local y Graphify local.
- Persistencia: SQLAlchemy/Alembic con runtime SQL activable y JSON solo para desarrollo.
- Base recomendada: PostgreSQL.
- App movil: Flutter, con repositorio API Flask y modo mock para desarrollo.
- API movil: Flask JSON con token bearer opcional/obligatorio en staging y produccion.

## Modulos admin actuales

| Modulo | Estado | Comentario |
| --- | --- | --- |
| Dashboard | Operativo | Metricas, rotacion e inventario. |
| Productos | Operativo | SKU, precios USD/VES, descuento, stock, variantes, imagenes y PDFs. |
| Biblioteca tecnica | Operativo | Imagenes, fichas PDF y recursos asociados a productos. |
| Categorias | Operativo | CRUD con imagen para app movil. |
| Stock masivo | Operativo | Movimiento individual, carga masiva y reserva por orden. |
| Anuncios app | Operativo | Banners para carrusel movil. |
| Ordenes | Operativo | Ordenes B2B, credito, pagos externos y estados. |
| Clientes ferreteros | Operativo | Usuario, contrasena, credito, estado y acceso movil. |
| Credito | Operativo | Limite, usado, disponible, movimientos y abonos. |
| Usuarios admin | Operativo | Roles, estados y contrasena temporal. |
| Auditoria | Operativo | Eventos de cambios, login y seguridad. |

## Conexion admin-movil

Ya esta conectado:

- Productos creados en admin salen por `/api/mobile/products`.
- Categorias creadas en admin salen por `/api/mobile/categories`.
- Anuncios creados en admin salen por `/api/mobile/announcements`.
- Clientes ferreteros pueden iniciar sesion con `/api/mobile/auth/login`.
- La app puede consultar credito con `/api/mobile/client/credit`.
- Ordenes creadas desde app entran al admin por `/api/mobile/orders`.
- Ordenes afectan credito y stock segun reglas del backend.
- Clientes con contrasena temporal no pueden crear ordenes hasta cambiarla.

## Seguridad y operacion

Entregado:

- Login admin.
- CSRF para formularios admin.
- Roles por modulo.
- Auditoria.
- Login movil con token.
- Rate limit basico de login.
- Cambio obligatorio de contrasena temporal.
- Health check `/healthz`.
- Readiness check `/readyz`.
- Migraciones reproducibles con Alembic.
- Produccion bloqueada si usa configuracion insegura.
- Docker productivo con Caddy, PostgreSQL y Gunicorn.
- Storage externo S3-compatible configurable.
- Scripts de backup, restore, admin inicial y smoke test.

## Que falta para venderlo como producto final

Prioridad alta externa:

- Desplegar en servidor real con HTTPS.
- Configurar PostgreSQL administrado o Postgres del compose productivo.
- Configurar bucket S3/R2/Spaces para imagenes y PDFs.
- Automatizar backup diario y probar restauracion.
- QA end-to-end con telefono fisico apuntando a backend HTTPS.
- Prueba comercial con ferretero real:
  - Login.
  - Cambio de contrasena.
  - Consulta de credito.
  - Compra.
  - Orden en admin.
  - Reserva/descuento de stock.
  - Registro de abono externo.
  - Recalculo de credito disponible.

Prioridad media:

- Recuperacion/restablecimiento seguro de contrasenas.
- Rate limit persistente con Redis o equivalente.
- Exportables CSV/PDF para ordenes, clientes y creditos.
- Observabilidad: logs, metricas y alertas.

## Conclusion comercial

Wulkan esta listo a nivel de codigo para **despliegue productivo controlado** y demostraciones serias con flujo real admin-app.

Para venderlo como producto final sin riesgo operativo, el siguiente bloque es activacion externa: dominio, HTTPS, credenciales, backup probado y QA real.
