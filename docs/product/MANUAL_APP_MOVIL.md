# Manual App Movil Wulkan

La app movil consume la API productiva de Wulkan. No necesita estar conectada a una computadora si el APK fue compilado apuntando a `https://crmwulky.com.ve` y el telefono tiene internet.

## Login

1. Abrir la app Wulkan.
2. Ingresar correo y contrasena.
3. Si la cuenta tiene clave temporal, cambiarla antes de comprar o vender.

## Cliente Ferretero

El ferretero puede:

- Ver catalogo real publicado desde el Admin Panel.
- Revisar categorias, productos, stock, precios USD y referencia VES.
- Abrir detalle de producto con carrusel de imagenes.
- Agregar cantidades al carrito.
- Elegir condicion de pago permitida.
- Crear orden de compra.
- Ver credito aprobado, usado y disponible.
- Revisar ordenes propias.
- Consultar servicios tecnicos visibles.

La orden enviada desde la app queda asociada al cliente, vendedor asignado, tipo de venta, saldo, credito consumido y estado operativo.

## Vendedor

El vendedor puede:

- Ver catalogo y disponibilidad.
- Crear clientes de su cartera.
- Tomar pedidos asistidos.
- Solicitar apertura de credito para clientes.
- Ver sus clientes, ordenes, cotizaciones, actividades y comisiones.
- Registrar seguimiento comercial.

El vendedor no opera el Admin Panel web. Su trabajo queda controlado desde la app para evitar acceso a informacion de otros vendedores.

## Gerencia

Las aprobaciones principales se hacen desde el Admin Panel:

- Lineas de credito.
- Condiciones especiales.
- Comisiones.
- Reglas comerciales sensibles.

Una vista movil gerencial puede agregarse mas adelante si Wulkan lo solicita.

## Sincronizacion

La app consulta el backend:

- Productos: `/api/v1/mobile/products`
- Detalle producto: `/api/v1/mobile/products/<id>`
- Home/carrusel: `/api/v1/mobile/home`
- Ordenes: `/api/v1/mobile/orders`
- Credito: `/api/v1/mobile/profile`
- Servicios tecnicos: endpoints moviles de servicios.

Los cambios del Admin Panel se reflejan en la app cuando esta consulta nuevamente la API. Si el telefono esta desconectado de la computadora, sigue funcionando mientras tenga internet.

## Reglas Importantes

- No se muestran productos ocultos, eliminados o no publicados.
- El stock visible viene del Admin Panel.
- La linea de credito se consume al crear/aprobar ordenes segun reglas Wulkan.
- El vendedor responsable se toma del cliente asignado o del pedido asistido.
- Las acciones relevantes generan auditoria en el backend.
