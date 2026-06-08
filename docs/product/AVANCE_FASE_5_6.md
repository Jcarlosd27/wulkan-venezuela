# Avance Fase 5 y arranque Fase 6

Fecha: 2026-06-08

## Resumen

Se implemento inventario comercial real para que el catalogo movil no venda unidades ya comprometidas por ordenes B2B.

Tambien se inicio Fase 6 agregando contrato movil para credito y ordenes del ferretero, manteniendo Graphify como resumen visual ligero en el admin para rotacion e inventario.

## Fase 5 - Inventario comercial real

Estado: funcional inicial.

Hecho:

- Stock fisico separado de stock disponible.
- Stock comprometido calculado desde ordenes con inventario reservado.
- Stock disponible real enviado a la app movil:

```text
stock_disponible = stock_fisico - stock_comprometido
```

- Orden aprobada con credito reserva stock automaticamente.
- Orden cancelada libera stock reservado.
- Orden entregada descuenta stock fisico.
- Movimientos de stock ahora guardan:
  - producto
  - SKU
  - tipo
  - cantidad
  - orden asociada
  - nota
  - usuario
  - fecha

- Modulo `Stock masivo` actualizado:
  - stock fisico
  - comprometido
  - disponible real
  - stock bajo
  - movimientos recientes
  - Graphify para rotacion

- Carga masiva respeta reservas activas.
- Ajuste manual puede definir stock fisico final.
- Productos y API movil muestran stock vendible, no solo stock bruto.

Prueba ejecutada:

```text
Orden creada desde API movil: approved_with_credit
Producto WUL-REP-CAD18 despues de reserva: reservado 1, disponible 3
Orden cancelada desde admin
Producto WUL-REP-CAD18 despues de cancelar: reservado 0, disponible 4
```

## Fase 6 - App movil ferretera

Estado: iniciada.

Hecho:

- La app usa el cliente demo B2B:

```text
client-ferreteria-valencia
```

- Se agregaron modelos moviles:
  - `MobileCreditSnapshot`
  - `MobileOrderSummary`

- El repositorio movil puede consultar:

```text
GET /api/mobile/credit?customerId=client-ferreteria-valencia
GET /api/mobile/orders?customerId=client-ferreteria-valencia
```

- Perfil movil ahora muestra:
  - linea de credito
  - limite
  - comprometido
  - disponible
  - dias de credito
  - ordenes recientes
  - saldo pendiente
  - estado de inventario

- Catalogo movil sigue bloqueando agregar productos sin stock disponible.
- En modo API, `availableStock` ya viene calculado por el admin Flask.

## Validaciones realizadas

Backend:

- `python -m py_compile`: OK
- `/` responde `200`
- `/stock` responde `200`
- `/orders` responde `200`
- `/credit` responde `200`
- `/products` responde `200`
- `/clients` responde `200`

API movil:

- Productos devuelven `stock`, `reservedStock`, `availableStock` y `stockStatus`.
- Credito devuelve disponible y exposicion.
- Crear orden reserva inventario si hay credito y stock.
- Cancelar orden libera inventario.

Mobile:

```text
flutter analyze: OK
flutter test: OK
17 tests passed
```

## Pendiente para cerrar Fase 6

- Login real de ferretero con formulario en Flutter.
- Guardar sesion movil.
- Usar token/JWT en todas las llamadas API.
- Pantalla dedicada de ordenes.
- Pantalla dedicada de credito.
- Estados visuales mas claros para despacho, pago parcial y entrega.
- Soporte de cierre de sesion.

## Siguiente fase recomendada

Continuar con cierre de Fase 6 y preparar Fase 7:

1. Login ferretero real en la app.
2. JWT para proteger API movil.
3. Pantalla `Mis ordenes`.
4. Pantalla `Credito`.
5. Preparar migracion a PostgreSQL antes de vender a clientes reales.
