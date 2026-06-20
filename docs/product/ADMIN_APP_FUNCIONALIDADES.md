# FVENTAS - Alcance funcional de lanzamiento movil

Fecha: 2026-06-19
Proyecto: FVENTAS
Objetivo: lanzar la app movil iOS/Android con un panel administrativo comercial simple, vendible y seguro.

## Resumen ejecutivo

FVENTAS opera como una plataforma B2B con dos superficies:

- Panel administrativo web para la empresa suscriptora.
- App movil para clientes B2B y vendedores autorizados.

El alcance de lanzamiento se concentra en catalogo, clientes, vendedores, credito B2B, pedidos, stock, comisiones, documentos, anuncios, puntos/servicios tecnicos, notificaciones, reglas de negocio, configuracion, usuarios y auditoria.

Los modulos de CRM, cotizaciones web, cobranza dedicada, despacho dedicado, reportes avanzados, mantenimiento y matriz granular de permisos quedan archivados para empresas en esta version. El codigo puede existir para evolucion futura, pero no forma parte del panel comercial entregado al cliente suscriptor.

## Modulos activos del Admin Panel

### Dashboard

- Ver resumen comercial de ventas, clientes, catalogo, stock, credito y actividad.
- Detectar pendientes relevantes sin entrar en pantallas tecnicas.

### Vendedores

- Crear y administrar vendedores.
- Definir datos de contacto, zona, estado, meta y porcentaje de comision.
- Asignar cartera de clientes B2B.
- Habilitar o bloquear acceso movil del vendedor.

### Clientes B2B

- Crear y administrar clientes.
- Registrar razon social, documento fiscal, contacto, telefono, correo, direccion, region/estado/provincia y ciudad/comuna.
- Asignar vendedor responsable.
- Habilitar o bloquear acceso movil.
- Registrar cupo solicitado y notas comerciales.
- Gestionar estado comercial y condiciones B2B.

### Credito B2B

- Ver solicitudes de credito creadas desde app o panel.
- Aprobar, revisar o rechazar cupos.
- Definir dias de pago permitidos.
- Revisar vencimientos e historial de movimientos.

### Ordenes

- Ver pedidos creados por clientes o vendedores.
- Validar condicion de pago, cliente, vendedor, stock, saldo y estado comercial.
- Registrar abonos externos cuando aplica.
- Cambiar estados permitidos con auditoria.

### Comisiones

- Consultar comisiones por vendedor y pedido.
- Aprobar, retener, pagar o anular comisiones segun reglas comerciales.
- Mantener trazabilidad antes de liquidar pagos.

### Productos

- Crear y editar catalogo.
- Definir SKU, nombre, descripcion, categoria, precio, descuento, stock, imagenes, PDFs, especificaciones y visibilidad en app.
- Marcar productos que requieren revision operativa antes de cerrar pedido.

### Categorias

- Organizar familias visibles en la app.
- Definir imagen, icono, orden, jerarquia y estado.

### Biblioteca tecnica

- Administrar imagenes, fichas y recursos de producto.
- Alimentar visualmente catalogo, detalle de producto y soporte comercial.

### Stock

- Actualizar stock fisico, reservado y disponible.
- Importar movimientos por Excel/CSV.
- Evitar pedidos sobre productos sin disponibilidad cuando la regla lo exija.

### Anuncios app

- Crear banners o mensajes comerciales visibles en la app.
- Definir vigencia, prioridad, ubicacion y estado.

### Servicios tecnicos / puntos

- Publicar puntos de soporte, retiro o servicio tecnico visibles en la app.
- Mantener direccion, contacto, zona y especialidades.

### Notificaciones

- Revisar alertas operativas y moviles.
- Marcar eventos como leidos o pendientes.

### Reglas de negocio

- Ver validaciones criticas de ventas, credito, stock, comisiones y seguridad.
- Detectar condiciones que bloquean salida a produccion.

### Configuracion

- Mantener datos de empresa, pais, moneda, tasa referencial cuando corresponda y condiciones de compra visibles en app.
- Definir textos comerciales de pedidos y reglas base de credito/comisiones.

### Usuarios admin

- Crear usuarios administrativos de empresa.
- Roles vigentes: super admin, gerente general, gerente comercial, operador, inventario, auditor y solo lectura.
- El rol platform admin queda reservado para el dueno de la plataforma.

### Documentos

- Gestionar documentos internos o recursos comerciales.
- Mantener acceso controlado y auditable.

### Plantillas

- Descargar formatos oficiales para carga masiva de productos, categorias, clientes, vendedores, stock y servicios tecnicos.

### Auditoria

- Revisar accesos, cambios sensibles y acciones administrativas.
- Respaldar investigacion de incidentes y control interno.

## Modulos archivados para empresas suscriptoras

Estos modulos no aparecen en el panel de una empresa y sus rutas deben responder 403 para roles de empresa:

- CRM Comercial.
- Cotizaciones web.
- Cobranza dedicada.
- Despacho dedicado.
- Reportes avanzados.
- Mantenimiento.
- Roles y permisos granular.

El mantenimiento se conserva solo para `platform_admin`, como herramienta interna del dueno de la plataforma.

## App movil: perfil cliente B2B

El cliente B2B puede:

- Iniciar sesion con correo y contrasena.
- Ver catalogo, categorias, imagenes, fichas y stock disponible.
- Ver precios y moneda segun la empresa/pais configurado.
- Agregar productos al carrito.
- Crear pedidos con condiciones permitidas.
- Revisar credito disponible, saldo comprometido y estado de ordenes.
- Consultar puntos de soporte o servicio tecnico.
- Ver notificaciones.
- Cambiar contrasena y solicitar eliminacion o desactivacion de cuenta.

El cliente B2B no puede:

- Ver otros clientes.
- Ver vendedores que no correspondan.
- Editar precios, stock, credito o comisiones.
- Acceder al panel administrativo.
- Consultar datos de otra empresa suscriptora.

## App movil: perfil vendedor

El vendedor puede:

- Iniciar sesion desde la app.
- Ver catalogo para venta asistida.
- Crear clientes B2B desde terreno.
- Solicitar cupo/credito para clientes de su cartera.
- Crear pedidos asistidos.
- Revisar clientes asignados.
- Revisar pedidos vinculados a su cartera.
- Consultar comisiones propias.

El vendedor no puede:

- Ver clientes o pedidos de otra empresa.
- Ver cartera de vendedores no autorizados.
- Aprobar credito propio.
- Cambiar precios base, stock o reglas comerciales.
- Acceder al panel web si su rol es solo vendedor movil.

## App movil: super admin / gerente comercial

Cuando la empresa lo permita, un super admin o gerente comercial puede entrar a la app para probar flujos comerciales o asistir ventas. Este acceso no convierte al usuario en dueno de plataforma y no debe exponer datos de otras empresas.

## Flujo comercial principal

1. La empresa se registra desde la landing y acepta terminos/politica.
2. FVENTAS activa la suscripcion y crea/entrega acceso al panel.
3. El admin configura pais, moneda, condiciones de compra y usuarios.
4. El admin carga categorias, productos, imagenes, stock, vendedores y clientes.
5. La app movil consume catalogo, banners, puntos, stock y condiciones desde el backend.
6. El vendedor crea clientes o pedidos asistidos desde terreno.
7. El cliente B2B compra desde catalogo segun su condicion permitida.
8. El pedido llega al panel con cliente, vendedor, total, stock, credito y comision.
9. Gerencia aprueba credito o revisiones comerciales cuando corresponda.
10. Auditoria registra cambios sensibles y eventos de seguridad.

## Seguridad y aislamiento comercial

- Cada empresa solo puede ver y operar sus propios datos.
- Las rutas web y API deben validar empresa, rol y accion.
- Los usuarios `sales` y `client` no son roles de panel web.
- Los modulos de plataforma solo pueden ser operados por `platform_admin`.
- Los modulos archivados no pueden abrirse por URL desde roles de empresa.
- La app movil requiere token y versionado de sesion en produccion.
- La eliminacion de cuenta bloquea acceso movil mientras se revisa.

## Checklist para entrega comercial

- Base productiva en PostgreSQL.
- Storage S3/Spaces configurado.
- Dominio HTTPS activo.
- Cuentas demo o de revision creadas para Apple/Google sin datos reales sensibles.
- Empresa base con pais, moneda, condiciones y aceptacion legal.
- Catalogo inicial con imagenes reales.
- Vendedor y cliente de prueba activos.
- Smokes de seguridad, negocio, admin y app movil ejecutados.
- Politica de privacidad, terminos y eliminacion publicados.
- App movil apuntando al backend productivo.

## Criterio de listo para vender

La plataforma esta lista para comercializar cuando una empresa nueva puede registrarse, recibir acceso, cargar catalogo/clientes/vendedores, probar la app movil con un cliente y un vendedor, crear pedidos reales y verlos en el panel sin exponer datos de otra empresa.
