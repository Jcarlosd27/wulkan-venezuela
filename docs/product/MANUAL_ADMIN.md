# Manual Admin Panel Wulkan

El Admin Panel es el centro interno de operacion B2B. Los vendedores trabajan desde la app movil; el panel web queda para administracion, gerencia, inventario, cobranza, despacho y auditoria.

## Ingreso

1. Entrar al dominio productivo.
2. Ingresar correo y contrasena.
3. Si el usuario tiene clave temporal, cambiarla antes de operar.
4. Usar el icono de llave para cambiar contrasena cuando sea necesario.

## Roles Web

- `super_admin`: controla todos los modulos y puede eliminar logicamente datos.
- `general_manager`: revisa gestion, aprueba credito/comisiones y audita.
- `commercial_manager`: administra vendedores, clientes, credito, ordenes, cotizaciones y comisiones.
- `operator`: crea y edita operacion diaria sin aprobar credito sensible.
- `inventory`: gestiona productos, categorias, biblioteca tecnica y stock.
- `collections`: gestiona cobranza, abonos y estados de deuda.
- `dispatch`: gestiona despacho, rutas y evidencias.
- `auditor`: acceso de lectura y auditoria.
- `readonly`: lectura operativa limitada.

## Modulos Principales

- `Dashboard`: KPIs comerciales, credito, cobranza, stock, despacho y comisiones.
- `Vendedores`: usuarios comerciales moviles, zonas, metas y porcentaje de comision.
- `Clientes`: ferreteros, RIF, direcciones, contactos, vendedor asignado y acceso movil.
- `Credito B2B`: lineas, cupos, vencimientos, historial y decisiones gerenciales.
- `Ordenes`: compras B2B, estado comercial, pago, stock, despacho y saldo.
- `Comisiones`: calculo y liberacion segun regla Wulkan.
- `Productos`: catalogo, SKU, precios, descuento, stock inicial, imagenes, PDFs y variantes.
- `Categorias`: familias visibles en app con imagen, icono, orden y jerarquia.
- `Biblioteca tecnica`: fotos, fichas PDF, manuales y recursos por producto.
- `Stock masivo`: movimientos individuales, importacion Excel/CSV y pegado rapido.
- `Anuncios app`: banners del carrusel movil.
- `Servicios tecnicos`: directorio publico para la app.
- `Reportes`: exportables comerciales, financieros, inventario y vendedores.
- `Auditoria`: cambios before/after, login, exportaciones, aprobaciones y eventos sensibles.
- `Plantillas`: formatos oficiales para cargas masivas.
- `Mantenimiento`: salud tecnica, version, migraciones, backups y readiness.

## Carga Masiva

1. Ir a `Plantillas`.
2. Descargar el formato Excel o CSV del modulo correspondiente.
3. Completar solo columnas oficiales.
4. Subir el archivo desde el modulo.
5. Revisar preview: filas a crear, actualizar, omitir y errores.
6. Confirmar solo si el resumen es correcto.

## Trazabilidad

Todas las acciones sensibles deben quedar en `Auditoria`:

- Creacion, edicion y eliminacion logica.
- Aprobacion/rechazo de credito.
- Cambios de estado de orden.
- Abonos externos.
- Cambios de comision.
- Importaciones y exportaciones.
- Login, bloqueo y cambios de clave.

## Operacion Segura

- No usar cuentas compartidas.
- Crear usuarios por persona.
- Asignar solo el rol necesario.
- Usar `Mantenimiento` antes de una carga grande.
- Exportar respaldo antes de importaciones masivas relevantes.
