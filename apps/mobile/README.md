# FVENTAS Mobile

App Flutter para Android e iOS orientada a clientes B2B y vendedores FVENTAS. La app inicia con login, consume catalogo/stock desde el admin Flask y crea ordenes sin pagos online, bajo revision operativa de FVENTAS.

## Stack

- Flutter.
- Dart.
- Riverpod.
- GoRouter.
- API Flask publica en `https://fventas.cl/api/v1/mobile`.
- Storage seguro local para sesion movil.

La app ya no usa Firebase ni Firestore.

## Entornos

Produccion y DigitalOcean usan API:

```json
{
  "FVENTAS_MOBILE_DATA_SOURCE": "api",
  "FVENTAS_MOBILE_AUTH_MODE": "api",
  "FVENTAS_ADMIN_API_URL": "https://fventas.cl/api/v1/mobile",
  "FVENTAS_MOBILE_ORDER_API_URL": "https://fventas.cl/api/v1/mobile/orders"
}
```

Mock local solo puede usarse en desarrollo con `FVENTAS_ALLOW_MOCK=true`.

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

## Firma Android

La firma release usa `android/key.properties` y `android/FVENTAS-release-key.jks`. Esos archivos son secretos locales y no se suben al repositorio.

Formato esperado:

```text
storePassword=<password>
keyPassword=<password>
keyAlias=FVENTAS-release
storeFile=FVENTAS-release-key.jks
```

Verificar firma:

```powershell
%LOCALAPPDATA%\Android\Sdk\build-tools\36.0.0\apksigner.bat verify --verbose --print-certs build\app\outputs\flutter-apk\app-release.apk
```

Instalar en telefono conectado:

```powershell
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

## iOS

La carpeta `ios/` esta creada para publicar la misma app en App Store Connect. La compilacion iOS debe hacerse desde macOS con Xcode:

```bash
flutter pub get
flutter build ipa --release --dart-define-from-file=dart_defines.digitalocean.example.json
```

Antes de subir a App Store Connect se debe configurar en Xcode el equipo de firma, el bundle id definitivo y los iconos finales de FVENTAS.

## Eliminacion de cuenta

La app incluye la solicitud de eliminacion de cuenta desde Perfil. Al confirmar, el backend registra la solicitud, bloquea el acceso movil de la cuenta y conserva solo la informacion necesaria para trazabilidad comercial, seguridad, auditoria o cumplimiento legal.

Tambien existe la pagina publica `https://fventas.cl/account-deletion` para usuarios que ya no tengan la app instalada.

## Experiencia Actual

- Login por correo y contrasena creados en el admin.
- Cliente B2B ve catalogo, carrusel, categorias, detalle, carrito, credito disponible, ordenes y servicios tecnicos.
- Vendedor ve catalogo, crea clientes, toma pedidos asistidos, revisa cartera y comisiones propias.
- Las ordenes se registran en el backend con cliente, vendedor, tipo de venta, saldo, credito consumido y trazabilidad.
- Las imagenes de producto soportan galeria/carrusel cuando el admin carga mas de una imagen.
