# Firebase

La configuracion principal de Firebase esta en la raiz del repositorio en `firebase.json`.

Esta carpeta contiene:

- `firestore.rules`: reglas de seguridad iniciales.
- `firestore.indexes.json`: indices iniciales para catalogo, ordenes y casos tecnicos.

## Admin con Firestore

El admin puede seguir usando mocks o leer Firestore por REST:

- `WULKAN_ADMIN_DATA_SOURCE=mock`: modo local actual.
- `WULKAN_ADMIN_DATA_SOURCE=firestore`: activa `FirestoreRestAdminRepository`.
- `FIREBASE_PROJECT_ID`: proyecto Firebase objetivo.
- `FIRESTORE_EMULATOR_HOST`: host del emulador, por ejemplo `127.0.0.1:8085`.
- `FIRESTORE_REST_BEARER_TOKEN`: token temporal para lectura REST contra un proyecto real.

Mientras no exista proyecto Firebase real, el modo recomendado sigue siendo `mock`.

El puerto local usado para Firestore Emulator es `8085`.

## Seed MVP

El script `npm run seed:firestore` escribe datos iniciales en:

- `users`
- `business_verticals`
- `companies`
- `products`
- `product_stock`
- `product_compatibilities`
- `orders`
- `payments`
- `purchase_orders`
- `service_cases`
- `locations`
- `app_settings`
- `audit_logs`

Para usarlo localmente:

1. Ejecutar `npm run emulators:firebase`.
2. Ejecutar `FIREBASE_PROJECT_ID=wulkan-dev FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 npm run seed:firestore`.

Validacion realizada:

- Firestore Emulator arranco en `127.0.0.1:8085`.
- `seed-firestore.mjs` escribio 17 documentos en `wulkan-dev`.
