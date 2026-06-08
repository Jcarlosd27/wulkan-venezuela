# Avance Fase 9 - Seguridad admin y auditoria

## Objetivo

Elevar el admin Flask a un nivel mas comercial incorporando proteccion de formularios, permisos por rol y trazabilidad de cambios sensibles.

## Entregado

- Proteccion CSRF para formularios del admin.
- API movil excluida de CSRF para mantener autenticacion por token y JSON.
- Helper global `csrf_field()` para plantillas.
- Control de roles:
  - `super_admin`.
  - `operator`.
  - `sales`.
  - `inventory`.
  - `readonly`.
- Menu lateral filtrado por permisos del rol activo.
- Pantalla de acceso restringido profesional.
- Auditoria operativa en `audit_events`.
- Nueva tabla SQL `audit_events`.
- Migracion Alembic `20260608_0002_audit_events.py`.
- Pantalla `/audit` para super admin.
- Auditoria registrada para:
  - Login admin.
  - Usuarios admin.
  - Clientes ferreteros.
  - Productos.
  - Categorias.
  - Stock.
  - Biblioteca tecnica.
  - Ordenes.
  - Pagos externos.
  - Anuncios app.

## Graphify operativo

```text
CSRF admin       Activo
API movil        Sin CSRF / token bearer preparado
Roles            5 perfiles
Auditoria SQL    Conectada
Rutas admin      Validadas
Modo SQL         Validado sin fallback
```

## Permisos por rol

| Rol | Puede hacer |
| --- | --- |
| `super_admin` | Todo, incluyendo usuarios admin y auditoria. |
| `operator` | Operacion comercial completa, excepto funciones exclusivas de super admin. |
| `sales` | Clientes, credito, ordenes, pagos y anuncios. |
| `inventory` | Productos, categorias, biblioteca tecnica y stock. |
| `readonly` | Lectura operativa, sin escritura. |

## Validacion realizada

- Compilacion Python de app, store, SQL store, modelos, migraciones y seed.
- Alembic actualizado a `20260608_0002 (head)`.
- Login admin con CSRF: `302`.
- POST admin sin CSRF: `400`.
- Rol `readonly` intentando borrar producto: `403`.
- API movil login sin CSRF: `200`.
- Vista `/audit`: `200`.
- Modo SQL estricto con `WULKAN_SQL_FALLBACK_TO_JSON=0`:
  - Login admin con CSRF.
  - Auditoria en SQL.
  - API movil sin CSRF.
  - Tabla `audit_events` registra eventos.
- Rutas admin validadas:
  - `/`
  - `/products`
  - `/categories`
  - `/stock`
  - `/orders`
  - `/clients`
  - `/admin-users`
  - `/credit`
  - `/announcements`
  - `/media-library`
  - `/audit`

## Estado comercial

El admin ya tiene seguridad minima seria para operar comercialmente en staging: CSRF, roles y auditoria.

Para produccion final aun falta:

- HTTPS en despliegue.
- Secretos reales.
- PostgreSQL administrado.
- Backups automaticos.
- Rate limiting de login.
- Politica de contrasenas temporales y cambio obligatorio.
- Auditoria de fallos de login.
