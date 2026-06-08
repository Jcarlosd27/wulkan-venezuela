# Guia de despliegue inicial

## Ambientes

- `dev`: trabajo local y emuladores.
- `staging`: validacion operativa interna.
- `production`: operacion real Venezuela.

Cada ambiente debe tener proyecto Firebase separado.

## Admin web

1. Copiar `apps/admin/.env.example` a `.env.local`.
2. Mantener `WULKAN_ADMIN_DATA_SOURCE=mock` para desarrollo local sin Firebase.
3. Usar `WULKAN_ADMIN_DATA_SOURCE=firestore` cuando exista proyecto Firebase o emulador.
4. Configurar `FIREBASE_PROJECT_ID`.
5. Configurar `FIRESTORE_EMULATOR_HOST` para emulador o `FIRESTORE_REST_BEARER_TOKEN` para lectura REST contra proyecto real.
6. Configurar variables `NEXT_PUBLIC_FIREBASE_*` para Auth/SDK web.
7. Ejecutar `npm install`.
8. Ejecutar `npm run typecheck:npm`.
9. Ejecutar `npm run build:admin:npm`.
10. Publicar a Firebase Hosting cuando el proyecto Firebase exista.

### Fuente de datos del admin

- `mock`: usa los datos locales en `apps/admin/src/lib/mvp-data.ts`.
- `firestore`: usa `FirestoreRestAdminRepository` y lee colecciones reales por REST.
- Si no se define `WULKAN_ADMIN_DATA_SOURCE`, el admin permanece en modo mock.

Colecciones esperadas por el admin:

- `users`
- `companies`
- `business_verticals`
- `products`
- `product_variants`
- `product_prices`
- `product_stock`
- `product_compatibilities`
- `orders`
- `purchase_orders`
- `replenishment_requests`
- `service_cases`
- `service_case_events`
- `quotes`
- `payments`
- `locations`
- `technical_projects`
- `company_performance_reports`
- `marketplace_applications`
- `product_approvals`
- `seller_quality_scores`
- `platform_charges`
- `audit_logs`
- `app_settings`

## Cloud Functions

1. Configurar Firebase CLI.
2. Asociar proyecto con `firebase use`.
3. Ejecutar build de functions.
4. Desplegar solo funciones revisadas.

## Pendiente para despliegue real

- Crear proyectos Firebase.
- Configurar credenciales.
- Configurar custom claims.
- Activar emuladores.
- Definir proceso staging -> production.

## Emuladores y seed local

1. Copiar `.env.example` a `.env`.
2. Definir `FIREBASE_PROJECT_ID=wulkan-dev`.
3. Ejecutar `npm run emulators:firebase`.
4. En otra terminal, ejecutar `npm run seed:firestore`.
5. En `apps/admin/.env.local`, usar:

```text
WULKAN_ADMIN_DATA_SOURCE=firestore
WULKAN_ADMIN_AUTH_MODE=mock
FIREBASE_PROJECT_ID=wulkan-dev
FIRESTORE_EMULATOR_HOST=127.0.0.1:8085
```

El seed escribe datos MVP en Firestore usando REST y no requiere credenciales cuando apunta al emulador.

Nota local: Firestore Emulator quedo configurado en `127.0.0.1:8085` porque `8080` estaba ocupado/bloqueado en esta maquina.

Requisitos locales comprobados:

- `firebase-tools` instalado como dependencia dev.
- JDK 21 instalado.
- `npx firebase emulators:exec --only firestore --project wulkan-dev "node infra/scripts/seed-firestore.mjs"` ejecutado correctamente.
- Seed validado: 17 documentos escritos.

## Auth y custom claims

El admin soporta dos modos:

- `WULKAN_ADMIN_AUTH_MODE=mock`: sesion local de desarrollo.
- `WULKAN_ADMIN_AUTH_MODE=firebase`: frontera preparada para validar sesion Firebase real.

La Cloud Function `setUserRoleClaims` queda preparada para que un `super_admin` o `wulkan_admin` asigne:

- `role`
- `companyId`
- `permissions`

Tambien actualiza el documento `users/{uid}` y registra auditoria en `audit_logs`.

## Permisos del admin

La matriz de acceso vive en `apps/admin/src/lib/permissions.ts`.

Cada item de navegacion declara:

- Ruta.
- Permisos requeridos.
- Roles restringidos cuando aplica.

El sidebar del admin ya filtra modulos segun la sesion actual. La pantalla `/usuarios/auth` muestra la matriz completa y si la sesion actual puede acceder a cada modulo.

## CRUD persistente inicial

El formulario `/verticales/nueva` usa una Server Action:

- En modo `mock`, valida y vuelve al listado sin escribir datos reales.
- En modo `firestore`, escribe en `business_verticals/{slug}` por REST.
- Despues de guardar, revalida `/verticales`.

La escritura reusable vive en `apps/admin/src/lib/firestore-writer.ts`.

El formulario `/productos/nuevo` tambien usa Server Action:

- Escribe en `products/{productId}`.
- Si hay precio publico, escribe `product_prices/{price-productId-public}`.
- Si hay precio B2B, escribe `product_prices/{price-productId-b2b}`.
- Siempre prepara `product_stock/{stock-productId-main}`.
- En modo mock vuelve al listado sin crear datos reales.

Tambien quedan preparadas Server Actions para:

- `/empresas/nueva`: crea `companies/{companyId}`.
- `/ubicaciones/nueva`: crea `locations/{locationId}`.
- `/servicios/nuevo`: crea `service_cases/{serviceCaseId}` y evento inicial.
- `/b2b/nueva`: crea `purchase_orders/{purchaseOrderId}`.
- `/proyectos/nuevo`: crea `technical_projects/{projectId}`.
- `/pagos`: confirma o rechaza pagos manuales y registra auditoria.
- `/cotizaciones`: responde, convierte o rechaza cotizaciones y registra auditoria.
