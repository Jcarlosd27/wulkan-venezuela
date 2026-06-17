# FVENTAS - Funcionalidades del Admin Panel y App Movil

Fecha: 2026-06-15
Proyecto: FVENTAS
Mercado objetivo: Chile
Modelo: Plataforma B2B para venta asistida, catalogo movil, credito comercial, pedidos, comisiones y trazabilidad.

## Resumen ejecutivo

FVENTAS es una plataforma comercial compuesta por un panel administrativo web y una app movil. El panel permite administrar la operacion interna de ventas, clientes B2B, catalogo, stock, credito, ordenes, comisiones, documentos, auditoria y configuraciones. La app movil permite que vendedores y clientes B2B operen desde el telefono, consulten productos, creen clientes, generen pedidos y sincronicen informacion con el backend productivo.

La informacion creada desde el admin se refleja en la app movil mediante API HTTPS. La informacion creada desde la app, como clientes, pedidos o solicitudes comerciales, queda registrada en el panel administrativo con trazabilidad.

## Que se puede hacer desde el Admin Panel

### Dashboard

- Ver indicadores principales de la operacion comercial.
- Revisar metricas de catalogo, clientes, ventas, ordenes, credito, stock y actividad.
- Consultar resumenes visuales tipo FVENTAS Insights para evitar pantallas pesadas y facilitar lectura ejecutiva.

### Vendedores

- Crear, editar y administrar vendedores.
- Definir zona, datos de contacto, estado y porcentaje de comision.
- Asociar cartera de clientes B2B a cada vendedor.
- Revisar ventas, avance de metas, comisiones y cartera asignada.

### Clientes B2B

- Crear, editar y administrar clientes B2B.
- Registrar razon social, RUT, correo, telefono, contacto principal, direccion, region y ciudad.
- Asignar vendedor responsable.
- Activar o desactivar acceso movil.
- Gestionar estado comercial del cliente.
- Controlar trazabilidad de origen: creado desde admin o desde app movil.

### CRM Comercial

- Dar seguimiento comercial a clientes y prospectos.
- Registrar notas, actividad, estado comercial y responsable.
- Mantener una base ordenada para ventas futuras y gestion de cartera.

### Credito B2B

- Administrar lineas de credito por cliente.
- Ver cupo otorgado, saldo usado, saldo disponible y deuda.
- Aprobar o rechazar solicitudes de credito.
- Controlar condiciones comerciales como credito a plazo o linea aprobada.
- Consultar vencimientos por cobrar.
- Revisar historial de abonos externos y movimientos de credito.

Submodulos recomendados o disponibles:

- Lineas de credito.
- Vencimientos.
- Historial de credito.

### Cobranza

- Revisar saldos pendientes de pago.
- Registrar abonos externos, ya que el sistema no depende de pasarela de pago online.
- Consultar estado de deuda por cliente y por orden.
- Mantener control operativo de pagos manuales.

### Ordenes

- Ver ordenes creadas desde app movil o admin.
- Revisar cliente, vendedor, condicion de pago, monto, saldo, estado y fecha.
- Identificar si la venta fue contado, credito a plazo o linea de credito.
- Validar ordenes, cambiar estados y registrar seguimiento.
- Controlar saldo pendiente y credito comprometido.

### Despacho

- Revisar ordenes preparadas o pendientes de despacho.
- Controlar estado logistico.
- Mantener continuidad entre venta, preparacion y entrega.

### Cotizaciones

- Gestionar cotizaciones comerciales.
- Convertir oportunidades en pedidos cuando corresponda.
- Mantener respaldo de condiciones ofertadas.

### Comisiones

- Calcular comisiones por vendedor y orden.
- Ver comisiones pendientes, aprobadas, pagadas o anuladas.
- Asociar la comision a la venta real, al vendedor responsable y al estado de la orden.
- Evitar pago de comisiones sin validacion comercial previa.

### Reportes

- Consultar resumenes de operacion.
- Revisar ventas, cartera, credito, stock, ordenes y comisiones.
- Preparar informacion para gerencia comercial.

### Productos

- Crear, editar y eliminar productos, segun permisos.
- Registrar SKU, nombre, descripcion, categoria, precio, descuentos, stock, imagen principal, galeria, documentos tecnicos, especificaciones y variantes.
- Definir si el producto es visible en app movil.
- Asociar productos a categorias.
- Preparar catalogo sincronizado para vendedores y clientes B2B.

### Categorias

- Crear, editar y eliminar categorias.
- Definir jerarquia: categoria raiz y subcategoria.
- Asignar imagen, icono, orden, estado y visibilidad en app.
- Organizar el catalogo de productos para navegacion movil.

### Biblioteca tecnica

- Administrar imagenes, fichas PDF y recursos asociados a productos.
- Cargar documentos tecnicos visibles para soporte comercial.
- Mantener material de apoyo para vendedores y clientes.

### Stock masivo

- Cargar stock individual o masivo.
- Importar archivos Excel o CSV.
- Actualizar existencias por SKU.
- Revisar stock fisico, reservado, disponible y movimientos.
- Identificar productos disponibles, en reposicion o agotados.

### Anuncios app

- Crear banners y campanas para la app movil.
- Definir imagen, titulo, mensaje, prioridad, ubicacion y estado.
- Alimentar el carrusel o secciones promocionales de la app.

### Servicios tecnicos

- Registrar servicios tecnicos disponibles para clientes.
- Definir nombre, contacto, zona, direccion, especialidad y visibilidad en app.
- Mantener un directorio util para postventa.

### Plantillas

- Descargar formatos oficiales para carga masiva.
- Usar planillas para productos, categorias, clientes, vendedores, stock y otros modulos.
- Reducir errores de importacion al usar columnas estandar.

### Documentos

- Gestionar documentos operativos o comerciales de la plataforma.
- Mantener archivos disponibles para procesos internos.

### Notificaciones

- Revisar alertas internas o moviles generadas por eventos reales.
- Identificar acciones pendientes, riesgos o avisos del sistema.

### Reglas de negocio

- Configurar condiciones operativas de ventas, credito, comisiones y validaciones.
- Centralizar reglas para que el flujo sea consistente.

### Mantenimiento

- Revisar tareas tecnicas o administrativas del sistema.
- Apoyar limpieza, verificacion y continuidad operativa.

### Auditoria

- Ver trazabilidad de accesos, cambios y operaciones sensibles.
- Consultar quien creo, edito, elimino o aprobo informacion.
- Revisar eventos de seguridad, cambios comerciales y acciones administrativas.
- Exportar registros para revision interna.

### Configuracion

- Ajustar parametros generales de la plataforma.
- Mantener datos de empresa, preferencias, moneda y comportamiento operativo.

### Roles y permisos

- Ver permisos por rol.
- Controlar acceso a modulos segun perfil.
- Evitar que usuarios vean informacion que no corresponde a su funcion.

### Usuarios admin

- Crear y administrar usuarios administrativos.
- Asignar roles como super admin, gerente comercial, inventario, cobranza, despacho, auditor u operador.
- Activar, desactivar o cambiar acceso.

## Que se puede hacer desde la App Movil

La app movil trabaja con pantallas segun rol. No todos los usuarios ven lo mismo.

### Cliente B2B

- Iniciar sesion con correo y contrasena.
- Ver catalogo disponible.
- Consultar productos, precios, stock e informacion comercial.
- Revisar detalle del producto, imagenes y datos relevantes.
- Agregar productos al carrito.
- Crear ordenes de compra.
- Seleccionar condicion de pago permitida.
- Consultar credito disponible, si tiene linea aprobada.
- Ver historial o estado de pedidos.
- Consultar servicios tecnicos disponibles.
- Recibir notificaciones.
- Actualizar contrasena cuando corresponda.

### Vendedor

- Iniciar sesion desde app movil.
- Ver catalogo para venta asistida.
- Crear clientes B2B desde terreno.
- Registrar datos comerciales del cliente.
- Solicitar apertura de credito para un cliente.
- Crear pedidos asistidos.
- Ver cartera asignada.
- Revisar ordenes de sus clientes.
- Consultar comisiones propias.
- Dar seguimiento comercial desde el telefono.

### Super admin o gerente comercial en app movil

- Puede ingresar a la app con acceso ampliado.
- Puede probar flujos comerciales.
- Puede actuar como vendedor cuando sea necesario.
- Puede validar que la informacion movil esta sincronizada con el panel.

## Flujo comercial principal

1. El administrador crea categorias, productos, stock y anuncios desde el panel.
2. La app movil sincroniza catalogo, categorias, banners y stock.
3. El vendedor crea o registra un cliente B2B desde la app o desde el admin.
4. El cliente queda asociado a un vendedor responsable.
5. Si aplica, se solicita linea de credito.
6. El gerente comercial aprueba o rechaza el credito desde el admin.
7. El cliente B2B o vendedor crea una orden.
8. La orden queda registrada en el panel con cliente, vendedor, condicion de pago, monto y estado.
9. El stock se reserva o actualiza segun el flujo configurado.
10. La comision queda calculada para el vendedor.
11. La cobranza registra abonos externos cuando el cliente paga fuera de la plataforma.
12. Auditoria registra los cambios relevantes.

## Como se conectan Admin y App Movil

- El admin panel y la app movil usan el mismo backend.
- La app consume endpoints API por HTTPS.
- El telefono no necesita estar conectado al computador para recibir informacion.
- Solo requiere tener internet y que el backend productivo este disponible.
- Los productos, categorias, anuncios, stock, clientes, ordenes, credito y notificaciones se sincronizan desde el backend.

## Roles principales

### Super admin

- Control total del sistema.
- Puede crear, editar y eliminar datos.
- Puede administrar usuarios, roles, configuracion, auditoria y reglas.

### Gerente comercial

- Aprueba credito.
- Supervisa vendedores, clientes, ordenes y comisiones.
- Puede revisar condiciones especiales.

### Operador

- Gestiona tareas comerciales y operativas permitidas.
- Accede a modulos asignados por permisos.

### Inventario

- Gestiona stock, productos y movimientos relacionados.
- No deberia tener acceso a informacion sensible comercial si no corresponde.

### Cobranza

- Gestiona saldos, abonos externos y deuda.
- Revisa vencimientos y estado de pago.

### Despacho

- Gestiona preparacion y entrega de ordenes.

### Auditor

- Consulta trazabilidad.
- Puede revisar eventos sin alterar datos sensibles.

### Solo lectura

- Puede consultar informacion autorizada sin modificarla.

### Vendedor movil

- Opera desde app movil.
- Crea clientes, genera pedidos asistidos y revisa su cartera.
- No debe acceder al panel administrativo web si la politica comercial lo restringe.

### Cliente B2B

- Opera desde app movil.
- Consulta productos y crea pedidos.
- Puede usar condiciones de pago autorizadas.

## Trazabilidad

El sistema debe mantener registro de:

- Creacion de clientes.
- Edicion de productos, categorias y stock.
- Solicitudes y aprobaciones de credito.
- Creacion y cambios de ordenes.
- Cambios de comisiones.
- Abonos externos.
- Inicio de sesion y acciones sensibles.
- Usuario, fecha, modulo, entidad afectada y detalle del evento.

La trazabilidad ayuda a:

- Prevenir cambios no autorizados.
- Detectar errores operativos.
- Revisar quien aprobo credito o modifico una orden.
- Respaldar procesos de auditoria interna.
- Evitar inconsistencias comerciales.

## Seguridad operativa

- Acceso por usuario y contrasena.
- Roles y permisos por modulo.
- Separacion entre usuarios administrativos, vendedores y clientes B2B.
- Proteccion de endpoints moviles mediante token o autenticacion.
- Uso de HTTPS en produccion.
- Auditoria de acciones sensibles.
- Credenciales administrativas reales, sin depender de usuarios demo.

## Importacion masiva

El sistema contempla carga masiva mediante Excel o CSV para modulos clave:

- Productos.
- Categorias.
- Clientes B2B.
- Vendedores.
- Stock.
- Servicios tecnicos.

La importacion debe validar previamente:

- Filas que se crearan.
- Filas que se actualizaran.
- Filas con error.
- Campos obligatorios faltantes.
- Duplicados por SKU, RUT, correo u otro identificador.

## Estado comercial de la plataforma

FVENTAS esta orientado a operar como una herramienta comercial B2B con panel web y app movil. El sistema permite gestionar ventas, cartera, catalogo, credito, pedidos y comisiones desde un flujo centralizado.

Para operar en produccion se recomienda confirmar:

- Base de datos productiva limpia y respaldada.
- Usuarios reales creados con roles correctos.
- Pruebas manuales por modulo antes de cargar informacion definitiva.
- App movil instalada apuntando al backend productivo.
- Politica de privacidad publicada.
- Backups activos.
- Monitoreo de errores.
- Revision final con equipo TI del cliente.

## Alcance recomendado para entrega a cliente

La plataforma puede presentarse como:

- Admin panel para gestion comercial B2B.
- App movil para vendedores y clientes B2B.
- Catalogo sincronizado con stock.
- Flujo de credito comercial.
- Registro de ordenes y cobranza manual.
- Comisiones por vendedor.
- Auditoria y control por roles.
- Importacion masiva de informacion.

## Puntos pendientes recomendados

- Ejecutar una prueba completa con datos reales controlados.
- Crear usuarios de prueba por cada rol.
- Validar creacion, edicion y eliminacion en cada modulo.
- Confirmar que la app movil cree clientes y ordenes sin error.
- Confirmar que los datos creados en movil aparezcan en admin.
- Confirmar que las acciones del admin se reflejen en la app.
- Revisar permisos sensibles antes de entregar a usuarios finales.
- Documentar el procedimiento de respaldo y restauracion.
- Definir reglas finales de comision, credito y cobranza con la empresa.
