# Catalogo admin hacia app movil

## Objetivo

El admin panel debe ser la fuente operativa del catalogo ecommerce de Wulkan.

La app movil no debe crear ni confirmar productos. Solo consume productos publicados desde el admin.

## Flujo operativo

1. Operador crea producto en admin desde `/productos/nuevo`.
2. Admin guarda documento en `products`.
3. Admin guarda historial en `product_prices`.
4. Admin guarda stock inicial en `product_stock`.
5. App movil lee `products` activos desde Firestore.
6. App muestra imagen principal, precio publico, precio B2B, stock y reglas tecnicas.

## Campos minimos del producto

- `sku`.
- `title`.
- `description`.
- `verticalId`.
- `type`.
- `categoryId`.
- `sellerId`.
- `publicPrice.amount`.
- `b2bPrice.amount`.
- `stock`.
- `imageUrls`.
- `technicalSheetUrl`.
- `manualUrl`.
- `warranty`.
- `requiresQuote`.
- `requiresInstallation`.
- `requiresTechnicalValidation`.
- `status`.

## Imagenes

En esta etapa el admin guarda URLs de imagen en `imageUrls`.

La primera URL es la imagen principal que muestra la app movil.

Siguiente paso recomendado:

- Subida real a Firebase Storage desde el admin.
- Guardar URLs privadas/publicables en `imageUrls`.
- Validar tipo, peso y dimensiones.
- Generar miniaturas optimizadas para app movil.

## Activar conexion real

Admin:

```env
WULKAN_ADMIN_DATA_SOURCE=firestore
FIREBASE_PROJECT_ID=wulkan-dev
FIRESTORE_EMULATOR_HOST=127.0.0.1:8085
```

App movil:

```json
{
  "WULKAN_FIREBASE_PROJECT_ID": "wulkan-dev",
  "WULKAN_MOBILE_DATA_SOURCE": "firestore",
  "WULKAN_MOBILE_AUTH_MODE": "mock",
  "WULKAN_FIRESTORE_EMULATOR_HOST": "10.0.2.2:8085"
}
```

Cuando se use Firebase real, la app Android debe tener configuracion Firebase valida para el proyecto correspondiente.
