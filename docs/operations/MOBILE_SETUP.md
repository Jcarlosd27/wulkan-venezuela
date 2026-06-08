# Setup movil Wulkan

Estado actual:

- Flutter SDK instalado en `C:\Users\sidne\development\flutter`.
- Version validada: Flutter 3.44.0 stable, Dart 3.12.0.
- Android Studio instalado en `C:\Program Files\Android\Android Studio`.
- Android SDK instalado en `C:\Users\sidne\AppData\Local\Android\Sdk`.
- Licencias Android aceptadas.
- Runner Android creado en `apps/mobile/android`.
- Android package: `com.wulkan.mobile`.
- App label: `Wulkan`.
- `flutter analyze`: OK.
- `flutter test`: OK.
- App instalada y ejecutada en telefono fisico `25098RA98G`.

## PATH recomendado

Agregar a variables de entorno de usuario:

```text
C:\Users\sidne\development\flutter\bin
```

Mientras no este en PATH, usar comandos con ruta completa:

```powershell
C:\Users\sidne\development\flutter\bin\flutter.bat doctor -v
```

## Comandos del proyecto movil

Desde `apps/mobile`:

```powershell
C:\Users\sidne\development\flutter\bin\flutter.bat analyze
C:\Users\sidne\development\flutter\bin\flutter.bat test
C:\Users\sidne\development\flutter\bin\flutter.bat run --dart-define-from-file=dart_defines.example.json
```

## Estado Android

`flutter doctor` detecta Android toolchain completo:

- Android Studio instalado.
- Android SDK 36 instalado.
- Platform Tools instalado.
- Build Tools 36 instalado.
- Licencias Android aceptadas.
- Telefono fisico `25098RA98G` detectado por ADB.

No hace falta Visual Studio para Android; ese aviso solo aplica para apps Windows Desktop.

## Siguiente paso para telefono

1. Conectar telefono Android con depuracion USB.
2. Verificar dispositivo:

```powershell
C:\Users\sidne\development\flutter\bin\flutter.bat doctor -v
```

3. Ejecutar:

```powershell
C:\Users\sidne\development\flutter\bin\flutter.bat devices
C:\Users\sidne\development\flutter\bin\flutter.bat run --dart-define-from-file=dart_defines.example.json
```

## Firebase Emulator en Android

Para Android Emulator usar:

```json
"WULKAN_FIRESTORE_EMULATOR_HOST": "10.0.2.2:8085"
```

Para telefono fisico usar la IP local del equipo donde corre Firebase Emulator, por ejemplo:

```json
"WULKAN_FIRESTORE_EMULATOR_HOST": "192.168.1.20:8085"
```
