# Avance Fase 10 - Identidad, contrasenas y readiness productivo

## Objetivo

Llevar Wulkan Admin y la app movil un nivel mas cerca de operacion comercial real, cerrando puntos de identidad, contrasenas temporales, bloqueo de intentos y verificacion de salud del servicio.

## Entregado

- Politica minima de contrasena:
  - 10 caracteres o mas.
  - Letras.
  - Numeros.
- Cambio obligatorio de contrasena para:
  - Usuarios admin creados o actualizados con nueva clave.
  - Clientes ferreteros creados o actualizados con nueva clave.
- Pantalla admin `/account/password` para cambiar clave propia.
- Acceso admin bloqueado a otros modulos cuando `mustChangePassword` esta activo.
- Endpoint movil `POST /api/mobile/auth/change-password`.
- Ordenes moviles bloqueadas si el ferretero no cambio la contrasena temporal.
- App Flutter con panel de cambio de contrasena para clientes ferreteros.
- Rate limit basico en memoria para login admin y login movil.
- Auditoria de:
  - Login exitoso admin.
  - Login fallido admin.
  - Login bloqueado admin.
  - Login exitoso movil.
  - Login fallido movil.
  - Login bloqueado movil.
  - Cambio de contrasena admin.
  - Cambio de contrasena movil.
  - Cambio fallido de contrasena movil.
- Endpoints operativos:
  - `GET /healthz`
  - `GET /readyz`
- Configuracion productiva reforzada:
  - Cookies `HttpOnly`.
  - `SameSite=Lax`.
  - Cookies seguras en produccion.
  - Limite de upload configurable.
  - Headers basicos de seguridad.
  - Produccion falla al arrancar si usa secreto de desarrollo, JSON como backend, SQLite o fallback a JSON.
- Migracion Alembic `20260608_0003_password_hardening.py`.
- SQL store, seed y JSON store alineados con `mustChangePassword`.

## Graphify operativo

```text
Admin password flow     Conectado
Mobile password flow    Conectado
Login rate limit        Activo
Audit login failures    Activo
Health endpoint         Activo
Readiness endpoint      Activo
Alembic head            20260608_0003
Flutter tests           Pasando
```

## Contrato movil nuevo

Login ferretero:

```text
POST /api/mobile/auth/login
```

La respuesta del cliente incluye:

```json
{
  "mustChangePassword": true
}
```

Cambio de contrasena:

```text
POST /api/mobile/auth/change-password
Authorization: Bearer <accessToken>
```

Body:

```json
{
  "currentPassword": "temporal",
  "newPassword": "nuevaClave2026"
}
```

Respuesta:

```json
{
  "status": "updated",
  "mustChangePassword": false
}
```

## Configuracion productiva minima

```bash
WULKAN_ENV=production
WULKAN_SECRET_KEY=<secreto-real-largo>
WULKAN_DATA_BACKEND=sql
WULKAN_SQL_FALLBACK_TO_JSON=0
WULKAN_REQUIRE_MOBILE_TOKEN=1
WULKAN_DATABASE_URL=postgresql+psycopg://user:password@host:5432/wulkan
WULKAN_LOGIN_MAX_ATTEMPTS=5
WULKAN_LOGIN_WINDOW_SECONDS=300
WULKAN_MAX_UPLOAD_MB=16
```

En produccion el servicio no debe arrancar si:

- Usa `WULKAN_SECRET_KEY=wulkan-dev`.
- Usa `WULKAN_DATA_BACKEND=json`.
- Usa SQLite.
- Tiene `WULKAN_SQL_FALLBACK_TO_JSON=1`.

## Validacion realizada

- `python -m py_compile` en backend, stores, config, modelos, migraciones y seed.
- `python -m alembic upgrade head`.
- `python -m alembic current` con salida `20260608_0003 (head)`.
- `flutter analyze`.
- `flutter test`.
- Prueba SQL estricta:
  - `/healthz` responde `200`.
  - `/readyz` responde `200`.
  - Login admin con clave temporal redirige a cambio de contrasena.
  - Cambio de contrasena admin funciona.
  - Login movil devuelve `mustChangePassword`.
  - Orden movil se bloquea con contrasena temporal.
  - Cambio de contrasena movil funciona.
  - Login movil aplica rate limit.

## Estado comercial

Wulkan queda en nivel **piloto comercial cerrado / pre-produccion avanzada**.

Ya esta conectado:

- Admin Flask.
- Store SQL/JSON mediante `load_store()` y `save_store()`.
- API movil Flask.
- App Flutter en modo API.
- Clientes ferreteros.
- Credito B2B.
- Ordenes moviles.
- Inventario disponible/reservado.
- Auditoria.
- Seguridad admin basica.
- Contraseñas temporales y cambio obligatorio.

Para declararlo producto final vendible en produccion aun se recomienda cerrar:

- Despliegue HTTPS con dominio real.
- PostgreSQL administrado.
- Backups automaticos y prueba de restauracion.
- Storage externo para imagenes/PDF.
- Rate limit persistente con Redis o servicio similar.
- Recuperacion de contrasena por operador o flujo seguro.
- QA end-to-end en dispositivo real con backend HTTPS.
- Prueba comercial con ferretero real y orden de credito completa.
