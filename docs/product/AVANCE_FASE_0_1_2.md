# Avance Fase 0, 1 y 2

Fecha: 2026-06-08

## Resumen

Se inicio la transicion del admin desde demo ecommerce hacia plataforma B2B para ferreteros con linea de credito.

Este corte no reemplaza todavia el almacenamiento JSON por PostgreSQL. Ese cambio queda como siguiente hito de Fase 1 porque requiere migracion y pruebas de datos. El avance actual deja lista la estructura funcional inicial para usuarios internos, clientes ferreteros, credito y ordenes B2B.

## Fase 0 - Estabilizacion

Estado: avanzado.

Hecho:

- Rutas principales del admin validadas.
- Login operativo.
- Sidebar coherente.
- Buscador global removido.
- Busqueda compacta por modulo en Productos.
- Productos con SKU obligatorio.
- Categorias, stock, anuncios y biblioteca tecnica operativos.
- API movil activa.
- Tests moviles pasando.

Validacion:

- `/`
- `/products`
- `/products/new`
- `/stock`
- `/categories`
- `/media-library`
- `/announcements`
- `/orders`
- `/clients`
- `/admin-users`

## Fase 1 - Base productiva y seguridad minima

Estado: iniciado.

Hecho:

- Login admin dejo de depender de constantes hardcodeadas simples.
- Se creo coleccion `admin_users` en el store.
- Las contrasenas admin se guardan como hash.
- La sesion guarda `admin_user_id`, `admin_name` y `admin_role`.

Pendiente para cerrar Fase 1:

- Migrar de JSON a PostgreSQL.
- Incorporar SQLAlchemy.
- Incorporar Alembic.
- Variables de entorno para `SECRET_KEY`.
- CSRF formal.
- Roles aplicados a permisos reales por modulo.
- Backups.
- HTTPS y despliegue productivo.

## Fase 2 - Usuarios y clientes ferreteros

Estado: iniciado funcionalmente.

Hecho:

- Nuevo modulo `Usuarios admin`.
- Nuevo modulo `Clientes ferreteros`.
- Cliente ferretero demo creado.
- Credito habilitado por cliente.
- Limite de credito USD.
- Credito usado USD.
- Credito comprometido por ordenes aprobadas con credito.
- Credito disponible calculado contra deuda manual y ordenes B2B abiertas.
- Estado de cliente: activo, suspendido, bloqueado.
- Endpoint inicial de login ferretero:

```text
POST /api/mobile/auth/login
```

- Ordenes moviles ahora pueden vincularse a cliente ferretero.
- Ordenes muestran credito antes y credito despues.
- Historial movil de ordenes disponible por cliente ferretero:

```text
GET /api/mobile/orders?customerId=client-ferreteria-valencia
```

- App movil en modo API envia el cliente demo `client-ferreteria-valencia` para pruebas B2B.

Credenciales demo:

```text
Admin:
admin@wulkan.local
wulkan2026

Cliente ferretero:
ferreteria@wulkan.local
ferretero2026
```

Pendiente para cerrar Fase 2:

- Login ferretero real dentro de la app movil.
- Token/JWT para API movil.
- Recuperacion de contrasena.
- Permisos reales para administradores.
- Historial de accesos.
- Bloqueo automatico por mora o suspension.

## Validaciones realizadas

Backend:

- Login admin correcto.
- Rutas admin cargan con `200`.
- API movil productos/categorias/anuncios carga con `200`.
- Login ferretero API responde con credito disponible.
- Historial movil de ordenes responde por cliente.
- Orden movil demo se crea con estado `approved_with_credit`.

Mobile:

```text
flutter analyze: OK
flutter test: OK
16 tests passed
```

## Siguiente hito recomendado

Cerrar Fase 1 productiva:

1. Migrar store JSON a PostgreSQL.
2. Crear modelos SQLAlchemy.
3. Crear migracion inicial Alembic.
4. Preservar datos actuales como seed.
5. Aplicar permisos reales por rol.

Despues de eso, continuar Fase 2 con login ferretero real en Flutter y sesion JWT.
