# Seguridad operativa Wulkan

## Sesiones admin

Variables recomendadas en produccion:

```bash
WULKAN_ADMIN_SESSION_IDLE_SECONDS=3600
WULKAN_ADMIN_SESSION_ABSOLUTE_SECONDS=28800
WULKAN_LOGIN_MAX_ATTEMPTS=5
WULKAN_LOGIN_WINDOW_SECONDS=300
```

El panel registra IP, user-agent, huella de dispositivo y sesiones activas por usuario. El cierre remoto desde Usuarios admin invalida la version de sesion y marca sesiones como revocadas.

## App movil

```bash
WULKAN_REQUIRE_MOBILE_TOKEN=1
WULKAN_MOBILE_TOKEN_MAX_AGE_SECONDS=604800
WULKAN_REJECT_LEGACY_MOBILE_TOKENS=1
```

Los tokens moviles incluyen version de sesion y dispositivo. Si cambia la clave, se bloquea el acceso o se revocan sesiones, los tokens anteriores dejan de ser validos.

## Archivos

```bash
WULKAN_MAX_UPLOAD_MB=16
WULKAN_MAX_IMPORT_ROWS=5000
```

Las cargas validan extension, MIME declarado, firma real del archivo y tamano maximo. Las importaciones Excel/CSV tienen limite de filas para evitar cargas accidentales demasiado grandes.

## Smoke de seguridad

```bash
python backend/api/scripts/smoke_security.py
```

Valida headers, sesiones activas, permisos por endpoint, rechazo de archivos falsos y tokens moviles versionados.
