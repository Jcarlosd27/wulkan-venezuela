# Admin MVP

## Rutas actuales

- `/`: dashboard operativo.
- `/verticales`: verticales comerciales.
- `/verticales/nueva`: formulario inicial de vertical.
- `/verticales/[id]`: detalle de vertical y atributos.
- `/productos`: catalogo maestro.
- `/productos/nuevo`: formulario inicial de producto.
- `/productos/[id]`: ficha operativa de producto.
- `/empresas`: empresas, ferreteros y red tecnica.
- `/ordenes`: ordenes B2C.
- `/b2b`: ordenes de compra B2B.
- `/servicios`: casos tecnicos.
- `/cotizaciones`: solicitudes comerciales o tecnicas.
- `/pagos`: pagos y validacion manual.
- `/ubicaciones`: puntos autorizados.

## Estado tecnico

El admin usa `AdminRepository` como punto de acceso a datos. Actualmente lee datos mock, pero la interfaz ya esta aislada para reemplazar esa implementacion por Firestore.

## Siguiente conexion

1. Crear cliente Firebase web.
2. Implementar repositorio Firestore.
3. Conectar formularios a server actions o endpoints protegidos.
4. Registrar auditoria en acciones sensibles.
5. Agregar autenticacion y custom claims.
