# Avance Fase 12 - App movil B2B

## Objetivo

Elevar la app Android a una experiencia comercial para ferreteros Wulkan: inicio de sesion obligatorio, visuales consistentes con el admin, lectura de catalogo/credito desde API y ordenes asociadas al cliente autenticado.

## Entregado

- Login inicial para clientes ferreteros:
  - Correo y clave.
  - Estado invitado sin acceso al ecommerce.
  - Sesion B2B activa despues de autenticar.
- Perfil convertido en centro de cuenta:
  - Datos del ferretero.
  - Linea de credito asignada.
  - Monto disponible y comprometido.
  - Cambio de clave temporal cuando el admin lo exige.
  - Cierre de sesion.
- Home movil mas comercial:
  - Tarjeta de cliente B2B con credito y estado operativo.
  - Hero ecommerce Wulkan.
  - Carrusel de promociones/anuncios cargables desde admin.
  - Categorias, productos destacados, busqueda y acceso a carrito.
- Carrito conectado a la sesion:
  - La orden usa `customer.id` y `customer.name` del cliente autenticado.
  - Si el cliente tiene clave temporal pendiente, se bloquea la creacion de orden hasta actualizarla.
- Autenticacion movil preparada para tres modos:
  - `mock` para demo local.
  - `api` contra Flask Admin.
  - `firebase` como alternativa futura.
- Contrato operativo con Flask:
  - `GET /api/mobile/products`
  - `GET /api/mobile/categories`
  - `GET /api/mobile/announcements`
  - `POST /api/mobile/auth/login`
  - `POST /api/mobile/auth/change-password`
  - `POST /api/mobile/orders`
- Tests moviles actualizados para validar login y shell ecommerce.

## Graphify operativo

```text
Login movil          Listo
Sesion ferretero     Listo
Credito visible      Listo
Orden con customer   Listo
Carrusel admin       Listo
Clave temporal       Listo
Modo API Flask       Configurable
Modo mock demo       Listo
```

## Como correr contra el admin Flask

1. Levantar el admin/API:

```bash
npm run dev:admin:flask
```

2. En emulador Android:

```bash
npm run mobile:run:api
```

3. En telefono fisico, usar la IP LAN del equipo en vez de `10.0.2.2`:

```bash
cd apps/mobile
flutter run ^
  --dart-define-from-file=dart_defines.example.json ^
  --dart-define=WULKAN_MOBILE_DATA_SOURCE=api ^
  --dart-define=WULKAN_MOBILE_AUTH_MODE=api ^
  --dart-define=WULKAN_ADMIN_API_URL=http://TU_IP_LAN:5000/api/mobile ^
  --dart-define=WULKAN_MOBILE_ORDER_API_URL=http://TU_IP_LAN:5000/api/mobile/orders
```

## Estado comercial

La app ya no entra directo al catalogo: primero autentica al cliente, luego muestra productos, categorias, anuncios, credito y carrito segun el estado sincronizado desde el admin.

Para venta final faltan pruebas externas con un cliente real:

- Crear ferretero desde admin.
- Asignar monto de credito.
- Publicar productos con stock.
- Publicar banners del carrusel.
- Iniciar sesion desde telefono fisico contra API HTTPS.
- Crear orden y confirmar que aparece en el modulo Ordenes del admin.
