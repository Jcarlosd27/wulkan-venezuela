# Wulkan Mobile

App Android Flutter para clientes, ferreteros, servicios tecnicos e instaladores.

## Modulos previstos

- `identity`: login, perfil, roles y permisos.
- `catalog`: verticales, categorias, busqueda y detalle tecnico.
- `cart`: carrito y checkout.
- `orders`: historial y seguimiento.
- `b2b`: catalogo ferretero y ordenes de compra.
- `service_cases`: casos tecnicos y solicitudes de repuestos.
- `locations`: puntos cercanos, ferreteros y servicios autorizados.
- `settings`: tema, pais operativo y soporte.

## Stack previsto

- Flutter.
- Dart.
- Riverpod.
- GoRouter.
- Firebase SDK.
- Firebase Cloud Messaging.
- Firebase Crashlytics.

## Entorno

La app ya tiene una frontera de configuracion en `lib/src/config/mobile_environment.dart`.

Valores de ejemplo:

```bash
C:\Users\sidne\development\flutter\bin\flutter.bat run --dart-define-from-file=dart_defines.example.json
```

Desde la raiz del proyecto puedes levantar la app en el telefono o emulador con:

```bash
npm run mobile:run
```

Para leer productos y anuncios desde Firestore Emulator:

```bash
npm run mobile:run:firestore
```

Para leer productos, anuncios y ordenes desde Flask Admin:

```bash
npm run mobile:run:api
```

Mientras `flutter run` esta abierto, cada cambio se puede enviar al movil con `r` en la terminal. Para reinicio completo usa `R`.

Para Android Emulator, `WULKAN_FIRESTORE_EMULATOR_HOST` debe apuntar a `10.0.2.2:8085`.

Para telefono fisico, debe apuntar a la IP local del equipo donde corre Firebase Emulator.

## Siguiente corte

1. Instalar Android Studio / Android SDK.
2. Aceptar licencias Android con `flutter doctor --android-licenses`.
3. Probar la app en telefono o emulador.
4. Conectar Firebase Auth.
5. Conectar catalogo y detalle a Firestore Emulator.

## Validacion actual

- Flutter SDK: `C:\Users\sidne\development\flutter`.
- Runner Android: creado.
- Android package: `com.wulkan.mobile`.
- `flutter analyze`: OK.
- `flutter test`: OK.
