# Contrato app movil Wulkan

Este documento define la frontera que la app Android debe consumir para pasar de mock a MVP conectado sin duplicar reglas criticas en Flutter.

## Estado

- Fecha: 2026-05-21.
- Objetivo: preparar la transicion de app mock a app conectada.
- Fuente inicial: Firestore Emulator `127.0.0.1:8085`.
- Proyecto dev: `wulkan-dev`.
- Regla principal: la app puede mostrar, solicitar y adjuntar datos; las decisiones criticas viven en backend.
- Implementacion inicial: `MockMobileRepository` y `FirestoreMobileRepository`.
- Bootstrap: `configureMobileRuntime` inicializa Firebase solo si el entorno usa Auth o Firestore.
- Auth: `MockMobileAuthRepository` y `FirebaseMobileAuthRepository`.
- Checkout: `MobileCartService` calcula preview y `MobileSecureOrderDraft` prepara payload para `createSecureOrder`.

## Configuracion movil

La app usa `--dart-define` para activar mocks o Firebase.

Variables:

- `WULKAN_FIREBASE_PROJECT_ID`: proyecto Firebase.
- `WULKAN_MOBILE_DATA_SOURCE`: `mock` o `firestore`.
- `WULKAN_MOBILE_AUTH_MODE`: `mock` o `firebase`.
- `WULKAN_DEFAULT_COUNTRY`: `VE`.
- `WULKAN_PRIMARY_CURRENCY`: `USD`.
- `WULKAN_SECONDARY_CURRENCY`: `VES`.
- `WULKAN_EXCHANGE_RATE_USD_VES`: tasa referencial para UI.
- `WULKAN_FIRESTORE_EMULATOR_HOST`: host del emulador desde Android.

Para Android Emulator, el host local del equipo se usa como `10.0.2.2:8085`.

## Pantallas MVP y datos

| Pantalla movil | Datos requeridos | Origen MVP |
| --- | --- | --- |
| Inicio | verticales, destacados, tasa | `business_verticals`, `app_settings` |
| Catalogo | productos, precios, stock, compatibilidades | `products`, `product_prices`, `product_stock`, `product_compatibilities` |
| Detalle tecnico | producto, variantes, garantia, compatibilidad | `products`, `product_variants`, `product_compatibilities` |
| Carrito | items locales y resumen | estado local + Cloud Function al confirmar |
| Checkout | total definitivo, pago inicial | `createSecureOrder` |
| Cotizaciones | solicitudes y respuestas | `quotes`, `quote_items` |
| Puntos cercanos | ubicaciones autorizadas | `locations` o `findNearbyLocations` |
| Historial | ordenes del usuario | `orders`, `purchase_orders`, `service_cases` segun rol |
| Perfil | usuario, rol, empresa asociada | Firebase Auth + `users`, `company_users` |
| Acceso ferretero | condiciones B2B, ordenes de compra | `companies`, `purchase_orders` |
| Servicio tecnico | casos y repuestos solicitados | `service_cases`, `service_case_events` |

## Acciones que la app puede disparar

- Crear orden segura: `createSecureOrder`.
- Solicitar cotizacion: crear `quotes` en estado `new` o Function futura.
- Buscar puntos cercanos: `findNearbyLocations`.
- Crear caso tecnico: Function futura o escritura controlada con reglas.
- Actualizar caso tecnico: `updateServiceCase`.
- Crear orden B2B: Function futura o Server Action/API equivalente.
- Adjuntar comprobante de pago: Storage + `payments` en estado `under_review`.

## Reglas criticas fuera de la app

- Calculo final de totales.
- Confirmacion de pagos.
- Cambio definitivo de estado de orden.
- Aprobacion/rechazo B2B.
- Cierre de casos tecnicos.
- Comisiones y cargos de plataforma.
- Validacion de permisos por rol.
- Auditoria de acciones sensibles.

## Primer corte movil real

Para iniciar la app movil real se necesita:

1. Completar Android SDK desde Android Studio.
2. Aceptar licencias Android.
3. Configurar Firebase Android con proyecto dev.
4. Probar `WULKAN_MOBILE_DATA_SOURCE=mock` en telefono/emulador.
5. Probar `WULKAN_MOBILE_AUTH_MODE=firebase` contra Firebase Auth.
6. Activar `WULKAN_MOBILE_DATA_SOURCE=firestore`.
7. Conectar checkout a `createSecureOrder`.

## Criterio de avance

La app movil pasa de mock a MVP conectado cuando:

- Login real funciona.
- Catalogo lee Firestore.
- Detalle lee precios/stock.
- Carrito conserva estado local.
- Checkout crea orden desde backend.
- Puntos cercanos leen ubicaciones reales.
- Perfil muestra rol real.
- Historial muestra ordenes reales del usuario.
