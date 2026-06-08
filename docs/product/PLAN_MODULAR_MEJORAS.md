# Plan modular de mejoras Wulkan

## Principio

Wulkan se mejora por modulos de negocio, no por pantallas aisladas.

Cada modulo debe respetar:

- Dominio compartido en `packages/domain`.
- Admin como fuente operativa.
- App movil como experiencia de compra/consulta.
- Reglas criticas fuera del frontend.
- Datos auditables en Firestore o backend.

## Modulo 1: Catalogo, categorias y productos

Objetivo:

- Crear productos desde admin.
- Asociar categoria, vertical, precio, stock, imagenes, ficha tecnica y garantia.
- Publicar productos activos hacia la app movil.
- Mostrar catalogo movil con busqueda, filtros, imagenes y detalle.

Estado:

- Producto ecommerce completo desde admin: avanzado.
- App movil consume productos mock o Firestore: avanzado.
- Pendiente: carga real de imagenes a Firebase Storage.
- Pendiente: CRUD formal de categorias.
- Pendiente: variantes avanzadas y compatibilidades editables.

## Modulo 2: Ventas y ordenes

Objetivo:

- Gestionar ventas B2C.
- Gestionar ordenes B2B de ferreteros.
- Unificar pagos, cobros y estados comerciales.
- Mantener trazabilidad de cada venta.

Estado:

- Ordenes B2C: base operativa.
- Ordenes B2B: base operativa.
- Pagos: validacion manual base.
- Vista comercial `/ventas`: inicial.

Pendiente:

- Crear orden B2C desde app contra backend.
- Crear intento de pago seguro.
- Cambiar estados con auditoria.
- Reservar stock al crear orden.
- Reporte de ventas por empresa.

## Modulo 3: Checkout y pagos

Objetivo:

- Carrito movil.
- Checkout seguro.
- Pago movil, transferencia y Mercado Pago.
- Confirmacion por operador o webhook.

Pendiente:

- Cloud Function `createSecureOrder`.
- Cloud Function `confirmPayment`.
- Evidencia de pago.
- Auditoria de validacion.

## Modulo 4: B2B completo

Objetivo:

- Condiciones comerciales por ferretero.
- Ordenes de compra multi-item.
- Solicitudes de reposicion.
- Aprobacion comercial.

Pendiente:

- OC multi-producto.
- Descuentos por empresa.
- Minimos de compra.
- Estados con responsable y fecha.

## Modulo 5: Servicios tecnicos

Objetivo:

- Casos tecnicos.
- Diagnostico.
- Repuestos usados.
- Evidencias.
- Cierre de caso.

Se trabajara despues de estabilizar catalogo, ventas y checkout.
