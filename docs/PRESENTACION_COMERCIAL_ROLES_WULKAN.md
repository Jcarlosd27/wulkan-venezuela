# Presentacion Comercial - Wulkan CRM Ecommerce B2B

Actualizacion: 10 de junio de 2026

## 1. Resumen ejecutivo

Wulkan Venezuela cuenta con una plataforma comercial B2B para administrar ventas de maquinaria, repuestos, productos tecnicos, clientes ferreteros, vendedores, credito, stock y ordenes desde un solo ecosistema.

La solucion esta compuesta por:

- **Admin Panel Web** para el equipo interno de Wulkan.
- **App Movil Android** para clientes ferreteros y vendedores.
- **Backend Flask API** publicado en DigitalOcean.
- **Dominio productivo**: `https://crmwulky.com.ve`.
- **Base de datos SQL** para informacion comercial real.
- **DigitalOcean Spaces/S3** para imagenes, galerias, PDFs y banners.
- **Bootstrap 5.3, UIX y Graphify** para una interfaz administrativa profesional y eficiente.

El objetivo es que Wulkan pueda digitalizar su proceso comercial sin depender de pagos online. Las ordenes se generan desde la app o desde el admin, y Wulkan gestiona cobro, validacion, despacho y seguimiento de manera operativa.

## 2. Estado comercial actual

El sistema ya esta preparado para iniciar carga de informacion real y operar un piloto comercial controlado con Wulkan.

Actualmente permite:

- Crear productos reales con SKU, descripcion, precios, descuento, stock, categoria, imagen principal, galeria de imagenes, PDFs tecnicos, variantes y especificaciones.
- Mostrar productos creados en el admin dentro de la app movil.
- Publicar banners/anuncios para el carrusel de la app movil.
- Crear categorias con imagen y estado.
- Cargar stock individual o masivo.
- Administrar clientes ferreteros con usuario, clave, estado, direccion, RIF, vendedor asignado y credito.
- Administrar vendedores con cartera, zona y comision.
- Crear ordenes con tipo de venta: contado, credito por dias o linea de credito.
- Consumir credito aprobado por cliente ferretero.
- Registrar abonos externos, sin pasarela de pago online.
- Calcular saldo pendiente, credito disponible, stock comprometido y comision del vendedor.
- Publicar servicios tecnicos visibles para la app.
- Importar informacion desde Excel/CSV con previsualizacion antes de guardar.
- Auditar cambios relevantes con trazabilidad.

Los datos demo fueron retirados para que Wulkan pueda comenzar a cargar informacion real sin contaminacion de pruebas.

## 3. Sincronizacion Admin Panel - App Movil

La app movil no necesita estar conectada al computador para recibir productos.

Cuando la APK esta instalada apuntando al backend productivo, el telefono consulta por internet:

```text
https://crmwulky.com.ve/api/mobile
```

Flujo real:

1. Wulkan crea o edita productos desde el admin web.
2. El backend guarda la informacion en la base de datos SQL.
3. La app movil consulta el backend por internet.
4. El cliente ferretero o vendedor ve productos, stock, precios, banners, credito y ordenes segun su rol.

Para que un producto se vea correctamente en la app debe estar activo y tener, como minimo:

- SKU.
- Nombre comercial.
- Categoria.
- Precio.
- Stock.
- Descripcion.
- Imagen principal.

Si se cargan varias imagenes en la galeria del producto, la app puede mostrarlas como carrusel/deslizamiento en el detalle del producto.

## 4. Identidad visual

El sistema ya esta alineado visualmente con Wulkan:

- Paleta naranja, negro y blanco.
- Login con logo Wulkan.
- Admin panel con acentos Wulkan sobre Bootstrap 5.3.
- App movil con identidad visual consistente.
- Icono/favico de navegador con concepto **CRM** para el admin.
- Componentes visuales limpios y enfocados en operacion comercial.

La paleta no satura todas las pantallas, sino que usa el naranja y negro en puntos clave: botones, navegacion activa, metricas, focus de formularios y elementos de marca.

## 5. Roles del Admin Panel Web

El admin panel esta pensado para usuarios internos de Wulkan. Los vendedores no deben operar desde el panel web; ellos trabajan desde la app movil.

### Super Admin

Control total del sistema.

Puede:

- Ver todos los modulos.
- Crear, editar y eliminar informacion.
- Administrar usuarios admin.
- Administrar vendedores.
- Administrar clientes ferreteros.
- Administrar productos, categorias, stock, biblioteca tecnica y anuncios.
- Aprobar o rechazar creditos.
- Gestionar ordenes y abonos.
- Gestionar comisiones.
- Ver auditoria.
- Ejecutar acciones sensibles de CRUD.

Uso recomendado:

- Gerencia general.
- Responsable maximo del sistema.
- Administracion principal de Wulkan.

### Gerente comercial

Rol enfocado en control comercial, credito y comisiones.

Puede:

- Ver dashboard comercial.
- Administrar vendedores.
- Administrar clientes ferreteros.
- Revisar solicitudes de credito.
- Aprobar o rechazar lineas de credito.
- Revisar vencimientos e historial de credito.
- Gestionar ordenes.
- Revisar comisiones.
- Revisar cartera comercial.

Restricciones:

- No administra usuarios internos del sistema.
- No elimina informacion critica salvo que tenga rol Super Admin.

### Operador

Rol para administracion diaria.

Puede:

- Gestionar productos.
- Gestionar categorias.
- Gestionar biblioteca tecnica.
- Gestionar anuncios de app.
- Gestionar clientes.
- Crear pedidos asistidos.
- Registrar informacion operativa.
- Cargar archivos Excel/CSV segun permisos.

Restricciones:

- No aprueba creditos.
- No gestiona comisiones globales.
- No administra usuarios admin.
- No elimina datos sensibles.

### Inventario

Rol enfocado en stock.

Puede:

- Ver stock disponible, fisico, reservado y comprometido.
- Registrar movimientos de entrada, salida, ajuste, reserva o liberacion.
- Cargar stock de forma masiva por SKU.
- Revisar rotacion con Graphify.

Restricciones:

- No administra clientes, credito ni comisiones.
- No modifica condiciones comerciales.

### Ventas / lectura administrativa

Roles administrativos secundarios para consulta o apoyo.

Pueden:

- Revisar informacion asignada segun permiso.
- Consultar catalogo, ordenes o clientes si corresponde.
- Apoyar operaciones sin acceso total.

Restricciones:

- No deben reemplazar al rol vendedor movil.
- No ven informacion sensible si el permiso no corresponde.

## 6. Roles en la App Movil

### Cliente ferretero

El cliente ferretero ingresa con correo y contrasena.

Puede:

- Ver catalogo de productos activos.
- Buscar productos por nombre, SKU o categoria.
- Ver precio, stock, descuento, imagenes y detalle del producto.
- Agregar cantidades al carrito.
- Crear ordenes de compra.
- Seleccionar condicion de pago permitida.
- Ver credito disponible, credito usado y saldo.
- Ver sus ordenes.
- Cambiar su clave temporal.
- Consultar servicios tecnicos publicados por Wulkan.

Condiciones de pago esperadas:

- Contado / efectivo.
- Credito 10, 15, 20, 30 o 40 dias.
- Linea de credito aprobada.
- Credito pendiente de autorizacion, cuando aplique.

### Vendedor

El vendedor trabaja desde la app movil.

Puede:

- Ver catalogo.
- Crear clientes ferreteros.
- Ver su cartera asignada.
- Generar pedidos asistidos.
- Ver ordenes de sus clientes.
- Ver sus comisiones.
- Dar seguimiento a clientes que hicieron pedidos.
- Asociar ventas a su gestion comercial.

Restricciones:

- No ingresa al admin panel web.
- No ve comisiones de otros vendedores.
- No administra usuarios internos.
- No cambia reglas globales de credito.

### Gerente en movil

Actualmente las aprobaciones principales se ejecutan desde el admin web.

Como fase futura se puede agregar una vista movil gerencial para:

- Aprobar creditos.
- Autorizar condiciones especiales.
- Revisar cartera comercial.
- Revisar metricas de vendedores.

## 7. Modulos del Admin Panel

### Dashboard

Resumen ejecutivo de operacion:

- Productos.
- Clientes.
- Vendedores.
- Ordenes.
- Ventas.
- Credito.
- Stock.
- Rotacion con Graphify.
- Ordenes recientes.

### Vendedores

Permite administrar la fuerza comercial:

- Crear vendedores.
- Definir zona.
- Definir porcentaje de comision.
- Ver cartera asignada.
- Ver ventas asociadas.
- Ver estado operativo.
- Importar vendedores por Excel/CSV.

### Clientes

Permite administrar ferreteros y clientes B2B:

- Razon social o nombre comercial.
- RIF/documento.
- Contacto.
- Correo.
- Telefono.
- Direccion.
- Ciudad/zona.
- Vendedor asignado.
- Acceso movil.
- Estado.
- Clave temporal.
- Condicion comercial.
- Importacion masiva por Excel/CSV.

### Credito B2B

Modulo para controlar riesgo y exposicion comercial.

Incluye:

- Lineas de credito.
- Solicitudes.
- Cupo otorgado.
- Cupo usado.
- Cupo disponible.
- Deuda manual.
- Ordenes abiertas.
- Dias de credito.
- Decision de aprobacion/rechazo.

Submodulos:

- **Lineas de credito**: vista principal de cupo por cliente.
- **Vencimientos**: ordenes o saldos por cobrar.
- **Historial credito**: abonos externos y movimientos historicos.

### Ordenes

Gestion operativa de pedidos:

- Cliente.
- Vendedor.
- Tipo de venta.
- Condicion de pago.
- Total.
- Abonado.
- Saldo.
- Estado.
- Estado de credito.
- Estado de inventario.
- Registro de abonos.
- Cambio de estado.

Las ordenes creadas desde la app quedan asociadas al cliente y, cuando corresponde, al vendedor responsable.

### Comisiones

Permite gestionar comisiones por vendedor:

- Vendedor.
- Orden.
- Porcentaje.
- Monto.
- Estado: pendiente, aprobada, pagada o anulada.

La comision se registra, pero puede liberarse segun la politica definida por Wulkan: venta validada, entregada o pagada.

### Productos

Permite administrar el catalogo:

- SKU.
- Nombre.
- Categoria.
- Tipo de producto.
- Precio publico USD.
- Precio B2B USD.
- Precio anterior.
- Descuento.
- Referencia VES.
- Stock inicial.
- Imagen principal.
- Galeria de imagenes.
- PDFs tecnicos.
- Descripcion.
- Variantes, tallas u opciones.
- Especificaciones.
- Requiere cotizacion.
- Requiere validacion tecnica.
- Estado.
- Importacion masiva por Excel/CSV.

### Biblioteca tecnica

Modulo profesional para recursos asociados a productos:

- Imagenes adicionales.
- PDFs tecnicos.
- Fichas tecnicas.
- Manuales.
- Recursos asociados a SKU.
- Archivos almacenables en DigitalOcean Spaces/S3.

### Categorias

Permite ordenar el catalogo:

- Nombre.
- Descripcion.
- Imagen.
- Estado.
- Visibilidad en app.
- Importacion masiva.

### Stock masivo

Modulo para inventario:

- Carga individual.
- Carga masiva por SKU.
- Movimientos de entrada/salida/ajuste/reserva/liberacion.
- Stock fisico.
- Stock comprometido.
- Stock disponible real.
- Rotacion.
- Estados: disponible, reposicion, agotado.

### Anuncios app

Modulo para banners del carrusel movil:

- Titulo.
- Mensaje.
- Imagen.
- Ubicacion.
- Prioridad.
- Fechas de inicio y cierre.
- Boton.
- Accion.
- Estado.
- Importacion masiva.

### Servicios tecnicos

Directorio visible para la app:

- Nombre del servicio.
- Contacto.
- Telefono.
- Zona.
- Direccion.
- Especialidad.
- Estado.
- Visibilidad.
- Importacion masiva.

### Planillas / Importaciones

El sistema incluye plantillas oficiales para que Wulkan cargue datos correctamente.

Cada plantilla define columnas requeridas y formato esperado para:

- Productos.
- Categorias.
- Stock.
- Clientes.
- Vendedores.
- Anuncios.
- Biblioteca tecnica.
- Servicios tecnicos.

La importacion tiene previsualizacion:

- Filas que se crearan.
- Filas que se actualizaran.
- Filas con advertencias.
- Filas con error.

Esto reduce riesgo antes de guardar informacion real.

### Auditoria

Modulo de trazabilidad:

- Usuario que realizo la accion.
- Fecha.
- Tipo de accion.
- Entidad afectada.
- Detalle del cambio.
- Origen.
- Datos antes/despues en acciones sensibles.

Eventos auditables:

- Creacion de clientes.
- Aprobacion o rechazo de credito.
- Cambios en ordenes.
- Abonos externos.
- Cambios de comision.
- Cambios de stock.
- Cambios en productos.
- Cambios en usuarios.

### Usuarios admin

Permite administrar quienes entran al panel web:

- Nombre.
- Email.
- Rol.
- Estado.
- Clave temporal.
- Cambio obligatorio de contrasena.
- Permisos segun rol.

## 8. Tecnologia utilizada

Backend y admin:

- Python.
- Flask.
- SQLAlchemy.
- Alembic.
- PostgreSQL / SQL administrado.
- Bootstrap 5.3.
- UIX.
- Graphify para visualizaciones ligeras.
- Docker.
- DigitalOcean App Platform.
- DigitalOcean Spaces/S3.

App movil:

- Flutter.
- Android APK.
- Consumo de API productiva.
- Login por rol.
- Catalogo, carrito, ordenes, credito y servicios.

Operacion:

- GitHub como repositorio.
- Autodeploy hacia DigitalOcean.
- Dominio productivo `crmwulky.com.ve`.
- Configuracion por variables de entorno.

## 9. Trazabilidad y control

La plataforma fue disenada para evitar inconsistencias.

Cada flujo comercial debe dejar evidencia de:

- Quien creo el cliente.
- A que vendedor quedo asignado.
- Quien solicito credito.
- Quien aprobo o rechazo credito.
- Que productos fueron solicitados.
- Que stock se comprometio.
- Que credito se consumio.
- Que saldo quedo pendiente.
- Que comision se genero.
- Que usuario registro abonos.
- Que usuario cambio estados.

Esto permite que Wulkan tenga control de la venta desde el origen del cliente hasta el cierre del pedido.

## 10. Flujo comercial principal

### Cliente ferretero con linea de credito

1. Wulkan crea el cliente ferretero o un vendedor lo registra desde la app.
2. El cliente queda asignado a un vendedor.
3. Se solicita apertura de credito si corresponde.
4. Gerencia comercial aprueba o rechaza.
5. El cliente ingresa a la app.
6. Revisa catalogo y stock.
7. Agrega productos al carrito.
8. Selecciona condicion de pago.
9. Genera la orden.
10. El sistema descuenta disponibilidad/compromete stock segun flujo.
11. El admin ve la orden.
12. El vendedor responsable puede contactar al cliente.
13. Wulkan valida, despacha y registra abonos externos.
14. El credito disponible se actualiza.
15. La comision del vendedor queda registrada segun regla.

### Venta asistida por vendedor

1. El vendedor inicia sesion en la app.
2. Ve su cartera.
3. Crea cliente o selecciona cliente asignado.
4. Revisa catalogo.
5. Genera pedido asistido.
6. La orden queda asociada al vendedor.
7. Wulkan revisa desde el admin.
8. Se registra tipo de venta y condicion.
9. Se gestiona despacho, saldo y comision.

## 11. Lo que no incluye actualmente

Para mantener expectativas claras, actualmente el sistema no incluye:

- Pagos online.
- Conciliacion bancaria automatica.
- Facturacion fiscal automatica.
- Integracion contable/ERP.
- Notificaciones push productivas.
- Aprobacion gerencial desde app movil.
- Login operativo para servicios tecnicos.
- Gestion avanzada de garantias o casos tecnicos.

Estos puntos pueden desarrollarse como fases posteriores.

## 12. Recomendaciones antes de salida comercial masiva

Antes de escalar a todos los usuarios, se recomienda:

1. Cargar productos reales con imagenes y galeria.
2. Cargar categorias reales con imagen.
3. Cargar stock real.
4. Cargar vendedores reales.
5. Cargar clientes ferreteros reales.
6. Definir politica formal de credito.
7. Definir politica formal de comisiones.
8. Definir estados de orden y responsables internos.
9. Probar 5 a 10 ordenes reales con ferreteros seleccionados.
10. Probar un cliente con credito aprobado y otro sin credito.
11. Instalar APK en telefonos reales sin cable.
12. Validar que la app consulte datos desde `https://crmwulky.com.ve`.
13. Validar carga de imagenes y PDFs en DigitalOcean Spaces.
14. Capacitar a los usuarios internos segun rol.

## 13. Mensaje comercial sugerido

Wulkan Venezuela cuenta con una plataforma CRM Ecommerce B2B conectada a una app movil Android, orientada a digitalizar la venta de maquinaria, repuestos y productos tecnicos para ferreteros y clientes comerciales.

El sistema permite administrar catalogo, imagenes, PDFs tecnicos, stock, vendedores, clientes, creditos, ordenes, comisiones y anuncios moviles desde un solo panel web. La app movil permite que clientes ferreteros y vendedores consulten productos, generen pedidos y trabajen con condiciones comerciales reales como contado, credito por dias o linea de credito aprobada.

La solucion opera sobre DigitalOcean, con dominio propio, base de datos SQL, almacenamiento S3 para recursos multimedia y trazabilidad de eventos comerciales clave.

El enfoque del producto es reducir trabajo manual, ordenar la cartera comercial, mejorar la disponibilidad de informacion para vendedores y clientes, y entregar a Wulkan una base escalable para su operacion ecommerce B2B en Venezuela.

## 14. Conclusion

El proyecto Wulkan se encuentra en condiciones de operar como piloto comercial productivo controlado.

La plataforma ya conecta admin web, backend productivo y app movil. Los productos, categorias, stock, banners, clientes, credito y ordenes pueden administrarse desde el panel y verse reflejados en la app sin mantener el telefono conectado a una computadora.

El siguiente paso comercial es cargar informacion real, ejecutar pruebas con usuarios reales y ajustar politicas internas de credito, comisiones, despacho y cobranza.
