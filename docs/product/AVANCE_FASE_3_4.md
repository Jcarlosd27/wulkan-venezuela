# Avance Fase 3 y 4

Fecha: 2026-06-08

## Resumen

Se continuo la conversion del admin Wulkan hacia operacion B2B para ferreteros.

Este corte implementa el control funcional de linea de credito, ordenes con saldo y registro de abonos externos. Todavia sigue pendiente migrar a PostgreSQL, aplicar JWT movil y cerrar permisos reales por rol antes de operar en produccion con clientes reales.

## Fase 3 - Linea de credito B2B

Estado: funcional inicial.

Hecho:

- Nuevo modulo `Credito B2B`.
- Calculo de linea otorgada por cliente.
- Calculo de credito comprometido por ordenes abiertas.
- Calculo de credito disponible:

```text
credito_disponible = limite_credito - deuda_manual - saldo_ordenes_abiertas
```

- Estados de credito por cliente:
  - `available`
  - `in_use`
  - `exhausted`
  - `without_credit`

- La API movil expone saldo de credito:

```text
GET /api/mobile/credit?customerId=client-ferreteria-valencia
```

- El login ferretero retorna limite, exposicion, usado y disponible.
- Las ordenes creadas desde app validan:
  - cliente existente
  - cliente activo
  - credito habilitado
  - saldo suficiente

Resultado de prueba:

```text
Cliente demo:
Credito disponible despues de abono: USD 915.00
Exposicion actual: USD 85.00
```

## Fase 4 - Ordenes B2B y pagos externos

Estado: funcional inicial.

Hecho:

- Vista `Ordenes B2B` reemplazada por una operacion comercial real.
- Metricas de ordenes:
  - total de ordenes
  - venta emitida
  - saldo pendiente
  - ordenes en revision

- Cada orden muestra:
  - numero
  - cliente
  - total
  - monto abonado
  - saldo
  - estado de credito
  - estado operativo
  - estado de pago

- Estados operativos implementados:
  - `credit_review`
  - `approved_with_credit`
  - `preparing`
  - `delivered`
  - `partial_paid`
  - `paid`
  - `cancelled`

- Registro de abonos externos desde el admin:
  - monto USD
  - monto VES
  - tasa referencial
  - metodo
  - referencia
  - observacion
  - usuario admin

- Metodos de abono:
  - efectivo
  - transferencia
  - pago movil
  - otro

- Historial de abonos visible en `Credito B2B`.
- Historial de estado de orden registrado en cada cambio.
- Registrar un abono libera credito disponible.
- Cancelar una orden libera credito reservado.

Prueba comercial ejecutada:

```text
Orden demo inicial: USD 185.00
Abono externo registrado: USD 100.00
Saldo pendiente: USD 85.00
Estado de orden: partial_paid
Credito disponible cliente: USD 915.00
```

## API movil actualizada

Endpoints relevantes:

```text
POST /api/mobile/auth/login
GET /api/mobile/credit?customerId=client-ferreteria-valencia
GET /api/mobile/orders?customerId=client-ferreteria-valencia
POST /api/mobile/orders
```

La app ya puede consultar productos, crear ordenes y recibir informacion de credito desde Flask. El login real dentro de Flutter queda para Fase 6.

## Validaciones realizadas

Backend:

- `/` responde `200`.
- `/clients` responde `200`.
- `/credit` responde `200`.
- `/orders` responde `200`.
- `/products` responde `200`.
- `/stock` responde `200`.
- `/categories` responde `200`.
- `/media-library` responde `200`.
- `/announcements` responde `200`.
- `/admin-users` responde `200`.

API movil:

- Login ferretero responde credito.
- Consulta de credito responde disponible y exposicion.
- Consulta de ordenes responde historial por cliente.
- Abono externo actualiza saldo y credito disponible.

## Pendiente para producto comercial

- Migrar JSON a PostgreSQL.
- Crear modelos SQLAlchemy y migraciones Alembic.
- JWT obligatorio para API movil.
- CSRF para formularios admin.
- Permisos reales por rol.
- Auditoria persistente.
- Stock reservado/descontado por estado de orden.
- Login ferretero real dentro de Flutter.
- Pantalla movil de credito y ordenes.
- Manual operativo para registrar abonos y gestionar mora.

## Siguiente fase recomendada

Continuar con Fase 5: inventario comercial real.

Objetivo del siguiente corte:

1. Reservar stock cuando una orden quede aprobada.
2. Liberar stock cuando se cancele.
3. Descontar stock cuando se entregue.
4. Crear kardex por producto.
5. Mostrar stock comprometido en admin y app movil.
