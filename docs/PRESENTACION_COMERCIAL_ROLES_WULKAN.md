# Wulkan Venezuela - Alcance Comercial del Admin Panel y App Movil

## 1. Resumen Ejecutivo

Wulkan Venezuela cuenta actualmente con una plataforma ecommerce B2B/B2C orientada a la venta de maquinaria, repuestos y productos asociados al mercado venezolano.

La solucion esta compuesta por:

- **Admin Panel Web** para operacion interna, gestion comercial, inventario, catalogo, credito B2B, ordenes, comisiones, servicios tecnicos y auditoria.
- **App Movil Android** para clientes ferreteros y vendedores, conectada al backend productivo.
- **Backend Flask API** publicado en DigitalOcean, con dominio productivo `https://crmwulky.com.ve`.
- **Base de datos SQL** para persistencia comercial.
- **DigitalOcean Spaces/S3** para imagenes, PDFs y recursos multimedia.
- **Bootstrap 5.3 + UIX + Graphify** en el panel administrativo para una experiencia profesional, clara y eficiente.

El objetivo de la plataforma es permitir que Wulkan administre su catalogo, stock, clientes ferreteros, vendedores, creditos, ordenes y anuncios moviles desde un solo sistema, con trazabilidad completa.

## 2. Estado Actual del Producto

Hoy el sistema ya permite operar un flujo comercial real:

- Crear y administrar productos.
- Asociar categorias, imagenes, galerias y PDFs tecnicos.
- Administrar stock y movimientos de inventario.
- Crear clientes ferreteros con acceso movil.
- Crear vendedores con acceso desde la app movil.
- Asignar clientes a vendedores.
- Solicitar y aprobar lineas de credito B2B.
- Registrar ordenes desde app movil o desde el admin.
- Registrar tipo de venta: contado, credito por dias o linea de credito.
- Calcular saldo, credito disponible, stock comprometido y comision del vendedor.
- Publicar banners/anuncios visibles en el carrusel de la app.
- Publicar servicios tecnicos visibles en la app.
- Ver auditoria de eventos criticos.
- Importar informacion masivamente desde Excel/CSV con previsualizacion antes de guardar.

La plataforma productiva ya esta preparada para recibir informacion real de Wulkan. No depende de que el telefono este conectado al computador: la app, compilada apuntando al backend productivo, consulta los datos por internet desde `https://crmwulky.com.ve/api/mobile`.

## 3. Roles del Admin Panel Web

### Super Admin

Rol de control total del sistema.

Puede:

- Ver todos los modulos del admin.
- Crear, editar y eliminar datos.
- Administrar usuarios administrativos.
- Administrar vendedores.
- Administrar clientes ferreteros.
- Administrar productos, categorias, stock, biblioteca tecnica y anuncios.
- Aprobar o rechazar lineas de credito.
- Gestionar ordenes y abonos.
- Gestionar estados de comisiones.
- Ver auditoria operativa.
- Eliminar registros cuando corresponda.

Uso recomendado:

- Gerencia general, direccion de tecnologia o responsable maximo del sistema.

### Gerente Comercial

Rol orientado al control comercial y financiero de la operacion.

Puede:

- Ver dashboard comercial.
- Administrar vendedores.
- Administrar clientes ferreteros.
- Revisar y aprobar/rechazar creditos B2B.
- Revisar vencimientos e historial de credito.
- Gestionar ordenes.
- Gestionar comisiones.
- Administrar anuncios de app.
- Administrar servicios tecnicos.
- Crear y editar informacion comercial relevante.

Restricciones:

- No administra usuarios internos del sistema.
- No tiene acceso completo a auditoria de sistema.
- No elimina registros criticos, salvo que sea Super Admin.

Uso recomendado:

- Gerente comercial de Wulkan Venezuela.

### Operador

Rol operativo para administracion diaria.

Puede:

- Gestionar productos.
- Gestionar clientes.
- Gestionar ordenes.
- Gestionar categorias.
- Gestionar biblioteca tecnica.
- Gestionar anuncios app.
- Gestionar servicios tecnicos.
- Crear pedidos asistidos desde el panel.
- Cargar informacion mediante Excel/CSV donde aplique.

Restricciones:

- No aprueba lineas de credito.
- No gestiona comisiones.
- No administra usuarios del sistema.
- No elimina registros criticos.

Uso recomendado:

- Personal administrativo de Wulkan que opera catalogo, pedidos y carga de informacion.

### Inventario

Rol enfocado en stock y disponibilidad.

Puede:

- Ver catalogo/productos.
- Administrar stock.
- Cargar stock masivo.
- Registrar movimientos de inventario.
- Revisar disponibilidad fisica, reservada y comprometida.

Restricciones:

- No gestiona creditos.
- No gestiona comisiones.
- No administra clientes ni vendedores.
- No elimina registros.

Uso recomendado:

- Encargado de almacen, inventario o logistica.

### Solo Lectura

Rol de consulta.

Puede:

- Ver informacion operativa segun los modulos habilitados.
- Consultar productos, clientes, ordenes u otros datos permitidos.

Restricciones:

- No crea, edita ni elimina informacion.
- No aprueba creditos.
- No cambia estados comerciales.

Uso recomendado:

- Auditores, supervisores o personal que solo requiere consulta.

## 4. Roles en App Movil

### Cliente Ferretero

El cliente ferretero ingresa desde la app movil con correo y contrasena.

Puede:

- Iniciar sesion en la app.
- Cambiar contrasena temporal cuando corresponda.
- Ver catalogo de productos activos.
- Ver productos con precio en USD y referencia en VES.
- Ver stock disponible.
- Ver imagenes de productos y galeria.
- Buscar productos por nombre, SKU, descripcion, categoria, variantes o especificaciones.
- Ver categorias.
- Ver anuncios/carrusel publicados desde el admin.
- Agregar productos al carrito.
- Seleccionar cantidades.
- Crear ordenes de compra.
- Elegir condicion de pago permitida:
  - contado/efectivo,
  - credito por dias,
  - linea de credito aprobada.
- Ver credito disponible, credito usado, saldo expuesto y vendedor asignado.
- Ver historial de ordenes.
- Ver servicios tecnicos o puntos autorizados publicados por Wulkan.

Reglas comerciales:

- Si usa linea de credito, el sistema valida cupo disponible.
- Si no tiene credito aprobado, la orden queda para revision.
- No existen pagos online dentro de la app; los pagos se gestionan externamente y se registran en el admin como abonos/manuales.

### Vendedor

El vendedor trabaja desde la app movil, no desde el admin panel web.

Puede:

- Iniciar sesion en la app.
- Ver catalogo actualizado.
- Ver su resumen comercial.
- Ver su cartera de clientes asignados.
- Crear clientes ferreteros.
- Solicitar apertura de credito para un cliente.
- Crear pedidos asistidos para clientes de su cartera.
- Ver ordenes asociadas a sus clientes.
- Ver comisiones asociadas a sus ventas.
- Dar seguimiento a pedidos, saldos y clientes.

Restricciones:

- No ingresa al admin panel web.
- No aprueba lineas de credito.
- No ve comisiones de otros vendedores.
- No modifica reglas comerciales globales.
- No elimina datos.

### Gerente Comercial en App Movil

Actualmente el backend permite autenticar roles comerciales en la app como usuarios moviles operativos, pero el flujo principal de aprobaciones comerciales esta pensado para ejecutarse desde el admin web.

Uso actual recomendado:

- Aprobar creditos desde el panel web.
- Revisar clientes, ordenes y comisiones desde el panel web.

Mejora futura:

- Agregar una vista movil especifica para aprobaciones de credito y autorizaciones comerciales.

### Servicio Tecnico

Actualmente "Servicio Tecnico" esta implementado como directorio visible en la app, no como usuario operativo con login.

Desde el admin se puede cargar:

- Nombre del servicio tecnico.
- Empresa.
- Contacto.
- Telefono.
- WhatsApp.
- Email.
- Estado/ciudad.
- Direccion.
- Especialidades.
- Cobertura.
- Estado activo/inactivo.
- Visibilidad en app.

En la app el cliente puede ver los servicios tecnicos publicados para contactar soporte autorizado.

Mejora futura:

- Crear login para servicios tecnicos si Wulkan decide que ellos gestionen casos, diagnosticos, repuestos o garantias desde una vista propia.

## 5. Modulos Actuales del Admin Panel

### Dashboard

Muestra metricas operativas para seguimiento rapido:

- Productos.
- Activos.
- Stock bajo.
- Ordenes.
- Ventas.
- Anuncios.
- Rotacion de productos mediante Graphify.
- Salud de inventario.
- Ordenes recientes.

### Vendedores

Permite administrar la red comercial.

Incluye:

- Usuarios vendedores.
- Zona.
- Porcentaje de comision.
- Meta de venta.
- Telefono.
- Estado.
- Cartera asociada.

Impacto en app:

- Los vendedores pueden iniciar sesion en la app.
- Las ordenes quedan asociadas al vendedor responsable.
- Las comisiones se calculan sobre las ventas asociadas.

### Clientes

Permite administrar clientes ferreteros.

Incluye:

- Razon social / nombre comercial.
- RIF o identificador fiscal.
- Contacto principal.
- Telefono / WhatsApp.
- Email de acceso.
- Direccion.
- Estado, ciudad y zona.
- Vendedor asignado.
- Condicion comercial.
- Estado activo/inactivo.
- Acceso movil con contrasena.

Impacto en app:

- El cliente puede iniciar sesion.
- El cliente ve su credito disponible.
- Las ordenes quedan asociadas a su cuenta.
- El vendedor asignado puede dar seguimiento.

### Credito B2B

Modulo dividido en submodulos para mayor claridad:

- **Lineas de credito:** cupo aprobado, usado, disponible, estado y decision.
- **Vencimientos:** ordenes a credito o linea aprobada con saldo pendiente.
- **Historial credito:** abonos externos y movimientos registrados.

Permite:

- Aprobar o rechazar creditos.
- Definir cupo en USD.
- Definir plazo de pago.
- Ver exposicion de credito.
- Ver disponible real.
- Registrar abonos externos.
- Mantener trazabilidad de decisiones.

Impacto en app:

- El cliente ferretero ve su credito disponible.
- La app valida si puede usar linea de credito.
- La orden consume credito si corresponde.

### Ordenes

Permite gestionar ordenes creadas desde la app movil o desde el panel.

Incluye:

- Cliente.
- Vendedor.
- Tipo de venta.
- Condicion de pago.
- Total USD.
- Total VES referencial.
- Abonado.
- Saldo.
- Estado de credito.
- Estado de inventario.
- Estado operativo.
- Acciones de cambio de estado.
- Registro de abonos.

Tipos de venta soportados:

- Contado / efectivo.
- Pago movil.
- Transferencia.
- Credito por dias.
- Linea de credito.

Impacto comercial:

- La orden queda asociada al cliente y vendedor.
- El saldo se mantiene visible.
- El stock puede quedar reservado o liberado segun estado.
- La comision queda calculada para seguimiento.

### Comisiones

Permite gestionar comisiones por vendedor.

Incluye:

- Vendedor.
- Orden asociada.
- Porcentaje.
- Monto.
- Estado:
  - pendiente,
  - aprobada,
  - pagada,
  - anulada.

Regla actual:

- La comision se calcula y registra con la orden.
- Gerencia puede cambiar su estado segun la politica comercial de Wulkan.

### Productos

Permite administrar el catalogo ecommerce.

Incluye:

- SKU.
- Nombre comercial.
- Tipo de producto.
- Categoria.
- Estado.
- Precio publico USD.
- Precio anterior USD.
- Descuento.
- Precio B2B USD.
- Tasa USD/VES referencial.
- Stock inicial.
- Imagen principal.
- Galeria de imagenes.
- PDFs tecnicos.
- Descripcion.
- Variantes/tallas/opciones.
- Especificaciones.
- Requiere cotizacion.
- Requiere validacion tecnica.

Impacto en app:

- Solo productos activos aparecen en la app.
- La app recibe SKU, nombre, descripcion, precios, stock, descuentos, imagenes, variantes y especificaciones.
- Las imagenes pueden mostrarse como galeria/carrusel de producto.

### Categorias

Permite organizar el catalogo.

Incluye:

- Nombre.
- Descripcion.
- Imagen de categoria.
- Estado.

Impacto en app:

- Las categorias activas aparecen en la app.
- Ayudan a ordenar busquedas y catalogo.

### Biblioteca Tecnica

Modulo para recursos asociados a productos.

Incluye:

- Imagenes de producto.
- Galerias adicionales.
- PDFs tecnicos.
- Fichas o documentos asociados.
- Asociacion por SKU/producto.

Impacto en app:

- Permite enriquecer la ficha del producto.
- Las imagenes adicionales alimentan la galeria del producto.
- Los PDFs pueden mantenerse como soporte tecnico/comercial del producto.

### Stock Masivo

Permite administrar inventario.

Incluye:

- Carga individual.
- Carga masiva por Excel/CSV.
- Stock fisico.
- Stock reservado.
- Stock disponible real.
- Movimientos recientes.
- Rotacion mediante Graphify.

Impacto en app:

- La app muestra disponibilidad real del producto.
- Las ordenes pueden reservar stock segun estado.

### Anuncios App

Permite administrar banners y mensajes visibles en la app movil.

Incluye:

- Titulo.
- Mensaje.
- Imagen.
- Ubicacion:
  - home,
  - catalogo,
  - checkout.
- Prioridad.
- Vigencia.
- Boton/CTA.
- Estado.

Impacto en app:

- Alimenta el carrusel y banners promocionales.
- Permite publicar descuentos, campanas o mensajes operativos.

### Servicios Tecnicos

Permite administrar el directorio de soporte visible para clientes.

Incluye:

- Nombre.
- Empresa.
- Contacto.
- Telefono.
- WhatsApp.
- Email.
- Estado/ciudad.
- Direccion.
- Especialidades.
- Cobertura.
- Visibilidad en app.

Impacto en app:

- Los clientes pueden ubicar servicios tecnicos autorizados.

### Plantillas de Importacion

Modulo para descargar formatos oficiales de Excel/CSV.

Incluye plantillas para:

- Productos.
- Stock.
- Clientes.
- Vendedores.
- Categorias.
- Biblioteca tecnica.
- Anuncios app.
- Servicios tecnicos.

La importacion tiene previsualizacion:

- Filas que se crearan.
- Filas que se actualizaran.
- Filas con error.
- Advertencias.
- Confirmacion antes de guardar.

Esto reduce riesgos al cargar informacion real de Wulkan.

### Auditoria

Modulo de trazabilidad.

Registra eventos relevantes como:

- Inicio de sesion.
- Intentos fallidos.
- Creacion de clientes.
- Aprobacion/rechazo de creditos.
- Creacion de ordenes.
- Cambios de estado.
- Registro de abonos.
- Cambios de comisiones.
- Acciones de importacion.

Objetivo:

- Saber quien hizo cada cambio.
- Mantener control operativo.
- Reducir inconsistencias.

### Usuarios Admin

Modulo exclusivo para Super Admin.

Permite:

- Crear usuarios administrativos.
- Definir rol.
- Activar/inactivar usuarios.
- Obligar cambio de contrasena.
- Separar accesos web y movil.

Importante:

- Los vendedores trabajan desde la app movil.
- El admin web queda reservado para perfiles administrativos autorizados.

## 6. Flujo Comercial Actual

### Flujo Cliente Ferretero

1. Wulkan crea el cliente desde el admin o un vendedor lo registra desde la app.
2. El cliente queda asociado a un vendedor.
3. El cliente recibe usuario y contrasena.
4. El cliente ingresa a la app.
5. El cliente revisa productos, stock, precios y promociones.
6. El cliente agrega productos al carrito.
7. El cliente selecciona condicion de pago.
8. El sistema registra la orden.
9. El admin ve la orden.
10. El vendedor responsable puede contactar al cliente.
11. Wulkan gestiona despacho, abonos y cierre de la venta.

### Flujo Vendedor

1. El vendedor ingresa a la app.
2. Ve su cartera de clientes.
3. Crea clientes nuevos si corresponde.
4. Solicita apertura de credito para clientes.
5. Genera pedidos asistidos.
6. Da seguimiento a ordenes.
7. Consulta comisiones asociadas a sus ventas.

### Flujo Credito B2B

1. Cliente o vendedor solicita credito.
2. Gerente comercial revisa solicitud.
3. Gerente aprueba o rechaza.
4. Si aprueba, define cupo USD y plazo.
5. La app muestra credito disponible.
6. Cada orden con linea de credito consume disponibilidad.
7. Los abonos externos se registran desde el admin.
8. El sistema muestra saldo, vencimientos e historial.

### Flujo Catalogo-App

1. Admin crea producto.
2. Admin asigna categoria, imagenes, PDFs, precios y stock.
3. Producto activo queda disponible en API movil.
4. App movil consulta catalogo desde el backend productivo.
5. Cliente/vendedor ve el producto sin depender de una computadora conectada.

## 7. Trazabilidad y Control

La plataforma mantiene trazabilidad en los puntos criticos:

- Quien crea clientes.
- Que vendedor tiene asignado cada cliente.
- Quien aprueba credito.
- Que cupo fue aprobado.
- Que orden se genero.
- Que cliente y vendedor estan asociados a la orden.
- Que tipo de venta se selecciono.
- Que saldo queda pendiente.
- Que stock queda reservado o liberado.
- Que comision queda registrada.
- Que usuario registra abonos o cambia estados.

Esto permite que Wulkan tenga control comercial y operativo sobre el ciclo completo de venta.

## 8. Integracion Admin Panel - App Movil

La app movil consume informacion desde el backend Flask publicado en DigitalOcean.

Endpoints principales:

- `/api/mobile/auth/login`: inicio de sesion movil.
- `/api/mobile/auth/change-password`: cambio de contrasena.
- `/api/mobile/products`: catalogo de productos.
- `/api/mobile/categories`: categorias.
- `/api/mobile/announcements`: banners/carrusel.
- `/api/mobile/orders`: ordenes de cliente ferretero.
- `/api/mobile/credit`: credito disponible del cliente.
- `/api/mobile/service-technicians`: servicios tecnicos.
- `/api/mobile/locations`: puntos/directorio.
- `/api/mobile/seller/summary`: resumen del vendedor.
- `/api/mobile/seller/clients`: cartera y creacion de clientes.
- `/api/mobile/seller/orders`: pedidos asistidos del vendedor.
- `/api/mobile/seller/commissions`: comisiones del vendedor.

La app debe compilarse con:

- `WULKAN_MOBILE_DATA_SOURCE=api`
- `WULKAN_MOBILE_AUTH_MODE=api`
- `WULKAN_ADMIN_API_URL=https://crmwulky.com.ve/api/mobile`
- `WULKAN_MOBILE_ORDER_API_URL=https://crmwulky.com.ve/api/mobile/orders`

Con esta configuracion, el telefono recibe productos, categorias, anuncios, ordenes y credito directamente desde produccion.

## 9. Que No Incluye Actualmente

Para mantener expectativas claras, actualmente el sistema no incluye:

- Pagos online integrados.
- Conciliacion bancaria automatica.
- Facturacion fiscal automatica.
- Integracion contable/ERP.
- Notificaciones push productivas.
- Aprobacion de credito desde una vista movil gerencial dedicada.
- Login operativo para servicios tecnicos.
- Gestion avanzada de garantias/casos tecnicos desde app de servicio tecnico.

Estos puntos pueden agregarse como fases posteriores.

## 10. Recomendaciones para Comercializacion

Antes de una entrega comercial formal, se recomienda:

1. Cargar productos reales de Wulkan usando las plantillas oficiales.
2. Cargar categorias reales con imagenes.
3. Cargar stock real.
4. Cargar vendedores reales.
5. Cargar clientes ferreteros reales.
6. Validar 5 a 10 ordenes reales de prueba.
7. Validar flujo de credito con un cliente aprobado y otro sin credito.
8. Validar que la app instalada en telefono consulte datos sin estar conectada al computador.
9. Definir politica comercial de comisiones.
10. Definir politica de estados de orden y liberacion de stock.
11. Definir responsables internos por rol.

## 11. Mensaje Comercial Sugerido

Wulkan Venezuela cuenta con una plataforma ecommerce B2B conectada a una app movil Android, orientada a digitalizar la venta de maquinaria, repuestos y productos tecnicos para ferreteros y clientes finales.

El sistema permite administrar catalogo, imagenes, PDFs tecnicos, stock, vendedores, clientes, creditos, ordenes, comisiones y anuncios moviles desde un solo panel web. La app movil permite que clientes ferreteros y vendedores consulten productos, generen pedidos y trabajen con condiciones comerciales reales como contado, credito por dias o linea de credito aprobada.

La solucion esta preparada para operar en produccion sobre DigitalOcean, con dominio propio, base de datos SQL, almacenamiento S3 para recursos multimedia y trazabilidad de los eventos comerciales clave.

El enfoque del producto es reducir trabajo manual, ordenar la cartera comercial, mejorar la disponibilidad de informacion para vendedores y clientes, y entregar a Wulkan una base escalable para su ecommerce B2B en Venezuela.

