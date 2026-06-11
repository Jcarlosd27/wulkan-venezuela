# Setup Movil Wulkan

Estado actual:

- Flutter SDK instalado en `C:\Users\sidne\development\flutter`.
- Android package: `com.wulkan.mobile`.
- App label: `Wulkan`.
- Backend productivo: `https://crmwulky.com.ve/api/v1/mobile`.
- La app movil usa API Flask. No usa Firebase ni Firestore.

## PATH Recomendado

Agregar a variables de entorno de usuario:

```text
C:\Users\sidne\development\flutter\bin
```

Mientras no este en PATH, usar comandos con ruta completa:

```powershell
C:\Users\sidne\development\flutter\bin\flutter.bat doctor -v
```

## Comandos

Desde `apps/mobile`:

```powershell
flutter pub get
flutter analyze
flutter test
flutter run --dart-define-from-file=dart_defines.digitalocean.example.json
```

Compilar APK contra produccion:

```powershell
flutter build apk --release --dart-define-from-file=dart_defines.digitalocean.example.json
```

Instalar APK en telefono conectado:

```powershell
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

## Telefono Fisico

1. Conectar telefono Android con depuracion USB.
2. Verificar dispositivo:

```powershell
flutter devices
```

3. Ejecutar en vivo:

```powershell
flutter run --dart-define-from-file=dart_defines.digitalocean.example.json
```

Mientras `flutter run` esta abierto, cada cambio se puede enviar al movil con `r`. Para reinicio completo usa `R`.

## Produccion

La app instalada por APK no necesita estar conectada a la computadora. Mientras el telefono tenga internet, consulta el backend publico:

- `WULKAN_ADMIN_API_URL=https://crmwulky.com.ve/api/v1/mobile`
- `WULKAN_MOBILE_ORDER_API_URL=https://crmwulky.com.ve/api/v1/mobile/orders`
