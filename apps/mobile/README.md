# Wulkan Mobile

App Android Flutter para clientes ferreteros y vendedores Wulkan. La app inicia con login, consume catalogo/stock desde el admin Flask y crea ordenes sin pagos online, bajo revision operativa de Wulkan.

## Stack

- Flutter.
- Dart.
- Riverpod.
- GoRouter.
- API Flask publica en `https://crmwulky.com.ve/api/mobile`.
- Storage seguro local para sesion movil.

La app ya no usa Firebase ni Firestore.

## Entornos

Produccion y DigitalOcean usan API:

```json
{
  "WULKAN_MOBILE_DATA_SOURCE": "api",
  "WULKAN_MOBILE_AUTH_MODE": "api",
  "WULKAN_ADMIN_API_URL": "https://crmwulky.com.ve/api/mobile",
  "WULKAN_MOBILE_ORDER_API_URL": "https://crmwulky.com.ve/api/mobile/orders"
}
```

Mock local solo puede usarse en desarrollo con `WULKAN_ALLOW_MOCK=true`.

## Comandos

Desde `apps/mobile`:

```powershell
flutter pub get
flutter analyze
flutter test
flutter run --dart-define-from-file=dart_defines.digitalocean.example.json
```

Compilar APK de produccion:

```powershell
flutter build apk --release --dart-define-from-file=dart_defines.digitalocean.example.json
```

Instalar en telefono conectado:

```powershell
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

## Experiencia Actual

- Login por correo y contrasena creados en el admin.
- Cliente ferretero ve catalogo, carrusel, categorias, detalle, carrito, credito disponible, ordenes y servicios tecnicos.
- Vendedor ve catalogo, crea clientes, toma pedidos asistidos, revisa cartera y comisiones propias.
- Las ordenes se registran en el backend con cliente, vendedor, tipo de venta, saldo, credito consumido y trazabilidad.
- Las imagenes de producto soportan galeria/carrusel cuando el admin carga mas de una imagen.
