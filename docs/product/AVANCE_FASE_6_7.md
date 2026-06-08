# Avance Fase 6 y arranque Fase 7

Fecha: 2026-06-08

## Resumen

Se avanzo la app movil ferretera para que pueda iniciar sesion contra Flask y consultar credito/ordenes usando token firmado.

Esto no reemplaza todavia JWT productivo ni PostgreSQL. Es una capa inicial para operar en desarrollo y preparar el cierre comercial.

## Fase 6 - App movil ferretera

Estado: avanzada.

Hecho:

- Modo de autenticacion movil `api`.
- Repositorio `ApiMobileAuthRepository`.
- Formulario de login en pantalla Perfil.
- Credenciales demo:

```text
ferreteria@wulkan.local
ferretero2026
```

- Perfil muestra:
  - cliente activo
  - linea de credito
  - limite
  - comprometido
  - disponible
  - dias de credito
  - ordenes recientes

- La app envia bearer token si la sesion lo tiene.
- El catalogo sigue usando stock disponible real desde admin.
- La creacion de orden puede enviar bearer token al backend.

## Fase 7 - Produccion comercial

Estado: iniciada, no cerrada.

Hecho:

- `SECRET_KEY` se puede configurar con variable de entorno:

```text
WULKAN_SECRET_KEY
```

- Login ferretero retorna token firmado:

```text
POST /api/mobile/auth/login
```

- Endpoints moviles pueden leer cliente desde:

```text
Authorization: Bearer <token>
```

- Endpoints probados con token:

```text
GET /api/mobile/credit
GET /api/mobile/orders
```

- Se preparo bloqueo opcional por entorno:

```text
WULKAN_REQUIRE_MOBILE_TOKEN=1
```

## Validacion ejecutada

Backend:

```text
python -m py_compile: OK
/              200
/stock         200
/orders        200
/credit        200
/products      200
/clients       200
/admin-users   200
```

API movil:

```text
Login ferretero: OK
Token devuelto: OK
Credito con bearer: OK
Ordenes con bearer: OK
```

Mobile:

```text
flutter analyze: OK
flutter test: OK
17 tests passed
```

## Pendiente para cerrar Fase 7

- Migrar JSON a PostgreSQL.
- SQLAlchemy y Alembic.
- JWT estandar con expiracion y refresh.
- CSRF en formularios admin.
- Roles aplicados por permiso real.
- HTTPS.
- Backups automaticos.
- Auditoria persistente.
- Recuperacion de contrasena.
- Manual de operacion y soporte.

## Comando recomendado para probar app en modo API

```powershell
flutter run --dart-define=WULKAN_MOBILE_DATA_SOURCE=api --dart-define=WULKAN_MOBILE_AUTH_MODE=api --dart-define=WULKAN_ADMIN_API_URL=http://10.0.2.2:5000/api/mobile --dart-define=WULKAN_MOBILE_ORDER_API_URL=http://10.0.2.2:5000/api/mobile/orders
```

En telefono fisico conectado por USB, usar antes:

```powershell
adb reverse tcp:5000 tcp:5000
```

Y reemplazar URLs por:

```text
http://127.0.0.1:5000/api/mobile
http://127.0.0.1:5000/api/mobile/orders
```
