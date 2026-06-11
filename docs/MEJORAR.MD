# ESPECIFICACIÓN GLOBAL PROFESIONAL

# SISTEMA WULKAN B2B: ADMIN PANEL + APP MÓVIL

## Checklist de avance por fases

- [x] Fase 1.1 - Dashboard Ejecutivo: KPIs reales por ventas, ordenes, clientes, credito, cobranza, stock y comisiones; filtros por fecha, vendedor, cliente, categoria, producto, estado de orden, estado de credito, estado de cobranza y tipo de venta; graficos Graphify compactos.
- [x] Fase 1.2 - Gestion de Usuarios Admin: crear/editar usuarios internos, telefono, rol, estado, observacion interna, clave temporal con cambio obligatorio, intentos fallidos persistentes, bloqueo/activacion, reset de clave, cierre remoto de sesiones, ultimo acceso, IP y auditoria de login/logout.
- [x] Fase 1.3 - Roles y Permisos granulares: matriz centralizada por rol, modulo y accion; menu y rutas principales conectadas a permisos de ver/crear/editar/importar/aprobar/eliminar; vista profesional para Super Admin con KPIs de cobertura y validacion por roles internos.
- [x] Fase 1.4 - Clientes B2B / Ferreteros: ficha comercial completa con razon social, RIF, contactos, WhatsApp, direccion fiscal/despacho, vendedor asignado, lista de precios, descuento autorizado, estados de cliente, cobranza, riesgo, credito, filtros, acciones de activar/revisar/bloquear, detalle con ordenes recientes, importacion Excel ampliada, datos sincronizados hacia app movil y auditoria before/after.
- [x] Fase 1.5 - Vendedores: ficha comercial completa con codigo, zona, territorio, supervisor, fecha ingreso, acceso movil, comision, meta mensual, observaciones, filtros por estado/zona/busqueda, ranking, avance de meta, ticket promedio, cartera asignada, ventas, comisiones, creditos pendientes, detalle operativo, importacion Excel ampliada, bloqueo real de acceso movil y resumen sincronizado hacia la app vendedor.
- [ ] Fase 1.6 - Productos / Catalogo.
- [ ] Fase 1.7 - Categorias.
- [ ] Fase 1.8 - Inventario / Stock.
- [ ] Fase 1.9 - Ordenes.
- [ ] Fase 1.10 - Credito B2B.
- [ ] Fase 1.11 - Cobranza.
- [ ] Fase 1.12 - Despacho / Logistica.
- [ ] Fase 1.13 - Cotizaciones.
- [ ] Fase 1.14 - CRM Comercial.
- [ ] Fase 1.15 - Comisiones.
- [ ] Fase 1.16 - Reportes.
- [ ] Fase 1.17 - Auditoria.
- [ ] Fase 1.18 - Configuracion General.
- [ ] Fase 1.19 - Importaciones Masivas.
- [ ] Fase 1.20 - Documentos.
- [ ] Fase 2 - App Movil Cliente y Vendedor.
- [ ] Fase 3 - Backend API versionada y endpoints faltantes.
- [ ] Fase 4 - Seguridad avanzada.
- [ ] Fase 5 - UI/UX Admin Panel.
- [ ] Fase 6 - UI/UX App Movil.
- [ ] Fase 7 - Notificaciones.
- [ ] Fase 8 - Reglas de negocio criticas.
- [ ] Fase 9 - Escalabilidad y mantenimiento.

## Objetivo general

Construir una plataforma B2B profesional para Wulkan compuesta por:

1. Admin Panel Web.
2. Backend API.
3. App móvil para clientes ferreteros.
4. App móvil para vendedores.
5. Base de datos SQL.
6. Almacenamiento S3 para imágenes, documentos, PDFs y evidencias.
7. Sistema de roles, permisos, auditoría, crédito, inventario, cobranza, despacho, cotizaciones, comisiones y CRM.

El sistema debe permitir controlar todo el ciclo comercial:

Lead → Cliente → Cotización → Orden → Crédito → Stock → Despacho → Cobranza → Comisión → Reporte → Auditoría.

---

# 1. ADMIN PANEL WEB

El Admin Panel debe ser el centro de control interno de Wulkan.

Debe ser usado por:

* Super Admin.
* Gerencia General.
* Gerente Comercial.
* Operador Comercial.
* Inventario.
* Cobranza.
* Despacho.
* Auditor / Solo Lectura.

Los vendedores no deben operar desde el Admin Panel, salvo que Wulkan cree un permiso especial. El vendedor debe trabajar principalmente desde la app móvil.

---

## 1.1 Dashboard Ejecutivo

El dashboard debe mostrar información real y accionable.

### KPIs principales

* Ventas del día.
* Ventas del mes.
* Ventas acumuladas.
* Órdenes nuevas.
* Órdenes pendientes.
* Órdenes aprobadas.
* Órdenes rechazadas.
* Órdenes anuladas.
* Órdenes entregadas.
* Clientes activos.
* Clientes inactivos.
* Clientes nuevos.
* Clientes bloqueados.
* Clientes con deuda vencida.
* Crédito total aprobado.
* Crédito utilizado.
* Crédito disponible.
* Cuentas por cobrar.
* Deuda vencida.
* Stock crítico.
* Productos agotados.
* Productos más vendidos.
* Vendedores activos.
* Comisiones pendientes.
* Comisiones aprobadas.
* Comisiones pagadas.

### Filtros del dashboard

* Fecha.
* Rango de fechas.
* Vendedor.
* Cliente.
* Categoría.
* Producto.
* Estado de orden.
* Estado de crédito.
* Estado de cobranza.
* Estado logístico.
* Sucursal, si aplica.

### Gráficos

* Ventas por día.
* Ventas por mes.
* Ventas por vendedor.
* Ventas por categoría.
* Productos más vendidos.
* Clientes con mayor compra.
* Morosidad por cliente.
* Stock crítico.
* Comisiones por vendedor.

---

## 1.2 Gestión de Usuarios Admin

Debe permitir crear y administrar usuarios internos.

### Campos

* Nombre.
* Apellido.
* Email.
* Teléfono.
* Rol.
* Estado.
* Fecha creación.
* Último acceso.
* Contraseña temporal.
* Cambio obligatorio de contraseña.
* Intentos fallidos.
* Bloqueado / activo.
* Observación interna.

### Acciones

* Crear usuario.
* Editar usuario.
* Bloquear usuario.
* Activar usuario.
* Resetear contraseña.
* Cambiar rol.
* Ver historial de accesos.
* Cerrar sesiones activas.
* Eliminar lógico.

---

## 1.3 Roles y Permisos

El sistema debe tener permisos granulares.

### Roles mínimos

* Super Admin.
* Gerente General.
* Gerente Comercial.
* Operador Comercial.
* Inventario.
* Cobranza.
* Despacho.
* Auditor / Solo Lectura.

### Permisos por módulo

Cada módulo debe tener permisos de:

* Ver.
* Crear.
* Editar.
* Anular.
* Aprobar.
* Rechazar.
* Exportar.
* Importar.
* Eliminar lógico.
* Ver auditoría.

### Módulos con permisos

* Dashboard.
* Clientes.
* Vendedores.
* Productos.
* Categorías.
* Stock.
* Órdenes.
* Cotizaciones.
* Crédito.
* Cobranza.
* Despacho.
* Comisiones.
* Reportes.
* Usuarios.
* Configuración.
* Auditoría.
* Documentos.

---

## 1.4 Clientes B2B / Ferreteros

El módulo de clientes debe ser completo.

### Campos generales

* Razón social.
* Nombre comercial.
* RIF / documento fiscal.
* Email.
* Teléfono.
* WhatsApp.
* Dirección fiscal.
* Dirección de despacho.
* Ciudad.
* Zona.
* País.
* Contacto principal.
* Contacto administrativo.
* Contacto de recepción.
* Vendedor asignado.
* Estado del cliente.
* Fecha creación.
* Última compra.
* Observaciones internas.

### Datos comerciales

* Condición de pago.
* Tipo de cliente.
* Categoría comercial.
* Lista de precios.
* Descuento autorizado.
* Crédito aprobado.
* Días de crédito.
* Cupo utilizado.
* Cupo disponible.
* Estado crediticio.
* Estado de cobranza.

### Estados de cliente

* Activo.
* Inactivo.
* Prospecto.
* Bloqueado por deuda.
* Bloqueado por crédito.
* Bloqueado manualmente.
* En revisión.
* Suspendido.

### Acciones

* Crear cliente.
* Editar cliente.
* Asignar vendedor.
* Bloquear cliente.
* Activar cliente.
* Ver órdenes.
* Ver cotizaciones.
* Ver deuda.
* Ver crédito.
* Ver documentos.
* Ver historial comercial.
* Ver actividad CRM.
* Exportar cliente.
* Importar clientes por Excel/CSV.

---

## 1.5 Vendedores

El módulo de vendedores debe controlar la fuerza comercial.

### Campos

* Nombre.
* Apellido.
* Email.
* Teléfono.
* Zona.
* Estado.
* Porcentaje de comisión.
* Meta mensual.
* Clientes asignados.
* Fecha ingreso.
* Usuario móvil.
* Último acceso app.
* Observaciones internas.

### Funciones

* Crear vendedor.
* Editar vendedor.
* Asignar cartera.
* Ver clientes asignados.
* Ver ventas.
* Ver cotizaciones.
* Ver comisiones.
* Ver cumplimiento de meta.
* Ver actividades comerciales.
* Ver ranking.
* Activar / desactivar acceso móvil.

### KPIs por vendedor

* Ventas del mes.
* Cantidad de órdenes.
* Ticket promedio.
* Clientes atendidos.
* Clientes nuevos.
* Cotizaciones creadas.
* Cotizaciones convertidas.
* Tasa de conversión.
* Comisiones pendientes.
* Comisiones aprobadas.
* Meta cumplida.

---

## 1.6 Productos / Catálogo

El módulo de productos debe ser muy sólido.

### Campos principales

* SKU.
* Código interno.
* Nombre comercial.
* Descripción corta.
* Descripción larga.
* Categoría.
* Subcategoría.
* Marca.
* Modelo.
* Tipo de producto.
* Unidad de venta.
* Precio público USD.
* Precio B2B USD.
* Precio anterior.
* Descuento.
* Costo referencial.
* Margen estimado.
* Stock.
* Stock mínimo.
* Imagen principal.
* Galería de imágenes.
* PDFs técnicos.
* Manuales.
* Ficha técnica.
* Estado.
* Visible en app.
* Requiere cotización.
* Requiere validación técnica.
* Producto destacado.
* Producto en oferta.

### Estados de producto

* Activo.
* Inactivo.
* Agotado.
* En reposición.
* Oculto en app.
* Descontinuado.

### Funciones

* Crear producto.
* Editar producto.
* Duplicar producto.
* Activar / desactivar.
* Cargar imagen principal.
* Cargar galería.
* Cargar PDF técnico.
* Asociar categoría.
* Asociar productos relacionados.
* Importar productos por Excel/CSV.
* Exportar productos.
* Ver historial de cambios.
* Ver movimientos de stock.
* Ver ventas del producto.

---

## 1.7 Categorías

Las categorías deben ordenar el catálogo visible en la app.

### Campos

* Nombre.
* Slug.
* Descripción.
* Imagen.
* Icono.
* Orden de visualización.
* Estado.
* Visible en app.
* Categoría padre, si aplica.

### Funciones

* Crear categoría.
* Editar categoría.
* Ordenar categorías.
* Activar / desactivar.
* Subir imagen.
* Importar categorías.
* Exportar categorías.

---

## 1.8 Inventario / Stock

El inventario debe diferenciar stock físico, reservado, comprometido y disponible.

### Campos por SKU

* Stock físico.
* Stock reservado.
* Stock comprometido.
* Stock disponible real.
* Stock mínimo.
* Stock máximo.
* Stock en reposición.
* Ubicación.
* Último movimiento.
* Responsable último ajuste.
* Observación.

### Movimientos de inventario

* Entrada.
* Salida.
* Ajuste positivo.
* Ajuste negativo.
* Reserva.
* Liberación.
* Compromiso por orden.
* Descuento definitivo por entrega.
* Anulación.
* Devolución.

### Reglas

* No permitir vender stock negativo salvo permiso especial.
* Orden enviada puede reservar stock.
* Orden aprobada compromete stock.
* Orden anulada libera stock.
* Orden entregada descuenta stock definitivo.
* Todo movimiento debe quedar auditado.

### Funciones

* Ajuste manual.
* Carga masiva por SKU.
* Historial de movimientos.
* Alertas de stock crítico.
* Productos sin stock.
* Productos sin movimiento.
* Exportar stock.
* Importar stock.

---

## 1.9 Órdenes

El módulo de órdenes debe ser el corazón operativo.

### Campos

* Número de orden.
* Cliente.
* Vendedor.
* Fecha creación.
* Origen: admin, app cliente, app vendedor.
* Tipo de venta.
* Condición de pago.
* Estado comercial.
* Estado crédito.
* Estado inventario.
* Estado despacho.
* Total bruto.
* Descuento.
* Total neto.
* Abonado.
* Saldo.
* Productos.
* Cantidades.
* Precio unitario.
* Dirección despacho.
* Comentario cliente.
* Comentario interno.
* Responsable actual.

### Estados comerciales

* Borrador.
* Enviada.
* Pendiente revisión comercial.
* Pendiente aprobación crédito.
* Pendiente validación stock.
* Aprobada.
* Rechazada.
* En preparación.
* Lista para despacho.
* Despachada.
* Entregada.
* Facturada.
* Cerrada.
* Anulada.

### Acciones

* Crear orden.
* Editar orden antes de aprobación.
* Aprobar orden.
* Rechazar orden.
* Anular orden.
* Cambiar estado.
* Registrar abono.
* Generar despacho.
* Generar comisión.
* Descargar PDF.
* Ver historial.
* Ver auditoría.

### Reglas

* No aprobar si el cliente está bloqueado.
* No aprobar si no hay stock.
* No aprobar si supera crédito sin autorización.
* No cerrar si no está entregada.
* No pagar comisión si la orden fue anulada.
* Motivo obligatorio para rechazo/anulación.

---

## 1.10 Crédito B2B

El crédito debe ser un módulo de riesgo comercial.

### Campos

* Cliente.
* Cupo aprobado.
* Cupo utilizado.
* Cupo disponible.
* Días de crédito.
* Deuda vigente.
* Deuda vencida.
* Órdenes abiertas.
* Promedio días de pago.
* Último pago.
* Score interno.
* Nivel de riesgo.
* Estado crediticio.
* Observación de gerencia.

### Estados

* Sin crédito.
* Crédito solicitado.
* En evaluación.
* Aprobado.
* Rechazado.
* Suspendido.
* Bloqueado por mora.
* Bloqueado por exceso de cupo.

### Funciones

* Solicitar crédito.
* Aprobar crédito.
* Rechazar crédito.
* Suspender crédito.
* Aumentar cupo.
* Reducir cupo.
* Ver historial.
* Ver deuda.
* Ver pagos.
* Ver órdenes abiertas.

---

## 1.11 Cobranza

Debe existir un módulo completo de cuentas por cobrar.

### Vistas

* Cuentas por cobrar.
* Por vencer.
* Vencidas.
* Críticas.
* Incobrables.
* Pagadas.
* Estado de cuenta por cliente.

### Campos

* Cliente.
* Orden.
* Monto total.
* Abonado.
* Saldo.
* Fecha emisión.
* Fecha vencimiento.
* Días atraso.
* Estado cobranza.
* Responsable cobranza.
* Última gestión.
* Próxima gestión.
* Promesa de pago.
* Comentario interno.

### Estados

* Al día.
* Por vencer.
* Vencido.
* En gestión.
* Promesa de pago.
* Pago parcial.
* Crítico.
* Incobrable.
* Cerrado.

### Funciones

* Registrar abono.
* Registrar promesa de pago.
* Agregar comentario.
* Reprogramar gestión.
* Bloquear cliente por mora.
* Liberar cliente.
* Descargar estado de cuenta.
* Exportar cobranza.

---

## 1.12 Despacho / Logística

Debe existir módulo de despacho conectado a órdenes.

### Campos

* Orden.
* Cliente.
* Dirección despacho.
* Contacto receptor.
* Teléfono receptor.
* Transportista.
* Número guía.
* Fecha estimada despacho.
* Fecha real despacho.
* Fecha estimada entrega.
* Fecha real entrega.
* Evidencia entrega.
* Observación logística.
* Responsable interno.

### Estados

* Pendiente despacho.
* En preparación.
* Preparado.
* Listo para despacho.
* En ruta.
* Entregado.
* Entrega fallida.
* Reprogramado.
* Devuelto.
* Cerrado.

### Funciones

* Crear despacho desde orden.
* Cambiar estado logístico.
* Registrar transportista.
* Subir evidencia de entrega.
* Registrar entrega fallida.
* Reprogramar entrega.
* Cerrar despacho.
* Ver historial logístico.

---

## 1.13 Cotizaciones

Debe existir módulo de cotizaciones antes de la orden.

### Campos

* Número cotización.
* Cliente.
* Vendedor.
* Fecha creación.
* Fecha vencimiento.
* Productos.
* Cantidades.
* Precio unitario.
* Descuento.
* Total.
* Estado.
* Comentario.
* Versión.

### Estados

* Borrador.
* Enviada.
* Vista.
* En negociación.
* Aceptada.
* Rechazada.
* Vencida.
* Convertida en orden.

### Funciones

* Crear cotización.
* Editar cotización.
* Descargar PDF.
* Duplicar cotización.
* Enviar cotización.
* Convertir en orden.
* Ver versiones.
* Ver historial.

---

## 1.14 CRM Comercial

El sistema debe tener CRM real.

### Módulos

* Leads.
* Prospectos.
* Oportunidades.
* Actividades.
* Seguimientos.
* Tareas.
* Visitas.
* Comentarios.

### Pipeline

* Nuevo lead.
* Contactado.
* Calificado.
* Interesado.
* Cotización enviada.
* Negociación.
* Ganado.
* Perdido.
* Inactivo.

### Actividades

* Llamada.
* WhatsApp.
* Correo.
* Visita.
* Reunión.
* Seguimiento.
* Tarea interna.
* Nota comercial.

---

## 1.15 Comisiones

El sistema debe controlar comisiones profesionalmente.

### Campos

* Vendedor.
* Orden.
* Cliente.
* Total venta.
* Base comisionable.
* Porcentaje.
* Monto comisión.
* Estado.
* Fecha generación.
* Fecha aprobación.
* Fecha pago.
* Observación.

### Estados

* Pendiente.
* En revisión.
* Aprobada.
* Pagada.
* Retenida.
* Anulada.

### Reglas

* Comisión por venta generada.
* Comisión por venta cobrada.
* Comisión por venta entregada.
* Comisión por margen.
* Comisión por categoría.
* Comisión por producto.
* Comisión por cliente nuevo.

No liberar comisión si:

* Orden anulada.
* Orden impaga.
* Cliente moroso.
* Venta en disputa.
* Producto devuelto.

---

## 1.16 Reportes

Debe incluir reportes exportables a Excel/PDF.

### Reportes comerciales

* Ventas por fecha.
* Ventas por vendedor.
* Ventas por cliente.
* Ventas por categoría.
* Ventas por producto.
* Ticket promedio.
* Clientes nuevos.
* Clientes inactivos.
* Clientes recuperados.

### Reportes financieros

* Cuentas por cobrar.
* Saldos vencidos.
* Abonos.
* Crédito usado.
* Crédito disponible.
* Clientes morosos.
* Promesas de pago.

### Reportes inventario

* Stock crítico.
* Productos agotados.
* Productos sin movimiento.
* Rotación.
* Movimientos de stock.
* Productos más vendidos.

### Reportes vendedores

* Ranking.
* Meta mensual.
* Cumplimiento.
* Comisiones.
* Clientes atendidos.
* Cotizaciones creadas.
* Conversión cotización/orden.

---

## 1.17 Auditoría

Auditar todo evento sensible.

### Eventos

* Login.
* Logout.
* Intento fallido.
* Creación usuario.
* Cambio rol.
* Cambio contraseña.
* Creación cliente.
* Edición cliente.
* Bloqueo cliente.
* Solicitud crédito.
* Aprobación crédito.
* Rechazo crédito.
* Creación orden.
* Cambio estado orden.
* Anulación orden.
* Registro abono.
* Movimiento stock.
* Cambio comisión.
* Exportación reporte.
* Importación masiva.
* Eliminación lógica.
* Descarga documento.

---

## 1.18 Configuración General

Debe existir módulo de configuración para no modificar código.

### Configuraciones

* Datos empresa.
* Logo.
* Colores.
* Moneda principal.
* Tipo de cambio referencial.
* Días crédito permitidos.
* Montos que requieren aprobación.
* Reglas bloqueo por mora.
* Reglas de comisión.
* Estados activos de orden.
* Plantillas PDF.
* Textos comerciales.
* Correos de notificación.
* Parámetros de stock mínimo.
* Políticas de archivos.

---

## 1.19 Importaciones Masivas

Cada importación debe ser segura.

### Funciones

* Descargar plantilla.
* Subir archivo.
* Validar columnas.
* Previsualizar datos.
* Detectar duplicados.
* Mostrar errores por fila.
* Mostrar advertencias.
* Confirmar antes de guardar.
* Guardar historial.
* Descargar errores.
* Ver creados, actualizados y rechazados.

### Importaciones mínimas

* Productos.
* Categorías.
* Clientes.
* Vendedores.
* Stock.
* Servicios técnicos.
* Anuncios.
* Biblioteca técnica.

---

## 1.20 Documentos

Debe existir gestión documental.

### Por cliente

* RIF.
* Contratos.
* Documentos de crédito.
* Estado de cuenta.
* Documentos administrativos.

### Por producto

* Ficha técnica.
* Manual.
* Garantía.
* Certificados.
* Galería.
* Imagen principal.

### Por orden

* Cotización.
* Comprobante.
* Guía despacho.
* Evidencia entrega.
* Factura manual, si aplica.

---

# 2. APP MÓVIL

La app debe tener dos experiencias separadas:

1. Cliente ferretero.
2. Vendedor.

Ambos roles pueden usar la misma app, pero con pantallas y permisos diferentes según login.

---

# 2.1 Login App

### Funciones

* Login con email y contraseña.
* Detección automática de rol.
* Cambio obligatorio de clave temporal.
* Recuperación de contraseña.
* Mantener sesión.
* Cierre de sesión.
* Bloqueo por intentos fallidos.
* Mensajes claros de error.
* Validación de usuario activo.

---

# 2.2 App Cliente Ferretero

La app del cliente debe ser un portal B2B de compra.

## Home Cliente

Debe mostrar:

* Banners comerciales.
* Categorías destacadas.
* Productos destacados.
* Productos recientes.
* Productos con descuento.
* Acceso rápido a carrito.
* Acceso rápido a órdenes.
* Estado de crédito.
* Alertas de deuda, si aplica.

## Catálogo

### Funciones

* Ver productos activos.
* Buscar por nombre.
* Buscar por SKU.
* Buscar por categoría.
* Filtrar por categoría.
* Filtrar por marca.
* Filtrar por precio.
* Filtrar por stock.
* Filtrar por descuento.
* Ordenar por precio.
* Ordenar por novedades.
* Ordenar por más vendidos.
* Ver productos relacionados.

## Detalle producto

Debe mostrar:

* Imagen principal.
* Galería.
* SKU.
* Nombre.
* Categoría.
* Marca.
* Precio.
* Descuento.
* Stock disponible.
* Descripción.
* Especificaciones.
* Variantes.
* PDF técnico.
* Manual.
* Productos relacionados.
* Botón agregar al carrito.
* Botón solicitar cotización si aplica.

## Carrito

Debe permitir:

* Agregar productos.
* Editar cantidades.
* Eliminar productos.
* Ver subtotal.
* Ver descuento.
* Ver total.
* Validar stock.
* Validar crédito.
* Guardar carrito persistente.
* Vaciar carrito.

## Checkout

Antes de confirmar debe mostrar:

* Cliente.
* Dirección despacho.
* Vendedor asignado.
* Productos.
* Cantidades.
* Total.
* Condición de pago.
* Crédito disponible.
* Saldo actual.
* Advertencias.
* Comentario del cliente.

## Órdenes Cliente

Debe mostrar:

* Historial de órdenes.
* Estado de cada orden.
* Fecha.
* Total.
* Saldo.
* Estado despacho.
* Detalle de productos.
* Observaciones.
* Descarga PDF, si aplica.

## Crédito Cliente

Debe mostrar:

* Cupo aprobado.
* Cupo usado.
* Cupo disponible.
* Días de crédito.
* Saldo pendiente.
* Órdenes vencidas.
* Estado crediticio.
* Mensaje si está bloqueado.

## Perfil Cliente

Debe permitir ver:

* Razón social.
* RIF.
* Email.
* Teléfono.
* Dirección.
* Vendedor asignado.
* Condición comercial.
* Cambiar contraseña.
* Solicitar actualización de datos.

---

# 2.3 App Vendedor

La app del vendedor debe ser una herramienta comercial completa.

## Home Vendedor

Debe mostrar:

* Ventas del mes.
* Meta mensual.
* Avance de meta.
* Comisiones pendientes.
* Comisiones aprobadas.
* Clientes asignados.
* Órdenes recientes.
* Cotizaciones recientes.
* Clientes con deuda.
* Clientes sin compra reciente.
* Tareas pendientes.

## Cartera

Debe mostrar:

* Lista de clientes asignados.
* Búsqueda por nombre/RIF.
* Filtro por zona.
* Filtro por estado.
* Filtro por deuda.
* Filtro por última compra.
* Detalle cliente.

## Detalle Cliente para Vendedor

Debe mostrar:

* Datos comerciales.
* Contactos.
* Dirección.
* Crédito disponible.
* Saldo pendiente.
* Órdenes.
* Cotizaciones.
* Historial de compras.
* Actividades.
* Comentarios.
* Próxima acción.

## Crear Cliente

El vendedor debe poder crear cliente con:

* Razón social.
* Nombre comercial.
* RIF.
* Teléfono.
* WhatsApp.
* Email.
* Dirección.
* Ciudad.
* Zona.
* Contacto.
* Observación.

El cliente creado por vendedor debe quedar en estado:

* Pendiente revisión, o
* Activo limitado,

según configuración de Wulkan.

## Pedido Asistido

El vendedor debe poder:

* Seleccionar cliente.
* Ver catálogo.
* Agregar productos.
* Validar stock.
* Validar crédito.
* Seleccionar condición de pago permitida.
* Crear orden.
* Agregar comentario interno.
* Ver estado posterior de la orden.

## Cotizaciones Vendedor

Debe poder:

* Crear cotización.
* Agregar productos.
* Aplicar descuento permitido.
* Guardar borrador.
* Enviar / descargar PDF.
* Convertir en orden, si está aceptada.

## Actividades Comerciales

Debe poder registrar:

* Llamada.
* WhatsApp.
* Visita.
* Reunión.
* Seguimiento.
* Comentario.
* Próxima acción.
* Resultado de gestión.

## Comisiones Vendedor

Debe mostrar:

* Comisión pendiente.
* Comisión aprobada.
* Comisión pagada.
* Comisión retenida.
* Orden asociada.
* Fecha.
* Monto.
* Estado.

## Restricciones Vendedor

El vendedor no debe poder:

* Aprobar crédito.
* Cambiar cupo.
* Ver otros vendedores.
* Ver comisiones de otros.
* Editar precios globales.
* Cambiar stock.
* Anular órdenes sin permiso.
* Acceder al Admin Panel.

---

# 3. BACKEND API

El backend debe conectar Admin Panel y App Móvil.

## Requisitos

* API versionada.
* Autenticación por token.
* Validación por rol.
* Validación de permisos.
* Respuestas JSON consistentes.
* Manejo de errores.
* Logs.
* Paginación.
* Filtros.
* Ordenamiento.
* Protección de endpoints sensibles.
* Validación de archivos.
* Manejo seguro de imágenes/PDFs.

## Endpoints mínimos

### Auth

* Login.
* Logout.
* Refresh token.
* Cambiar contraseña.
* Recuperar contraseña.

### Mobile

* Obtener home.
* Obtener productos.
* Obtener detalle producto.
* Obtener categorías.
* Obtener banners.
* Obtener carrito.
* Crear orden.
* Ver órdenes.
* Ver crédito.
* Ver perfil.
* Crear cliente vendedor.
* Crear cotización vendedor.
* Registrar actividad vendedor.

### Admin

* CRUD clientes.
* CRUD productos.
* CRUD categorías.
* CRUD vendedores.
* CRUD órdenes.
* CRUD cotizaciones.
* CRUD crédito.
* CRUD cobranza.
* CRUD despacho.
* CRUD comisiones.
* Reportes.
* Auditoría.
* Configuración.

---

# 4. SEGURIDAD

La seguridad debe validarse en backend, no solo en frontend.

## Requisitos

* Contraseñas hasheadas.
* CSRF en Admin Panel.
* Tokens seguros para app.
* Bloqueo por intentos fallidos.
* Registro de IP.
* Registro de dispositivo.
* Sesiones activas.
* Cierre remoto.
* Permisos por endpoint.
* Validación de archivos.
* Límite tamaño archivos.
* URLs firmadas para documentos privados.
* Sanitización de inputs.
* Protección contra acciones no autorizadas.

---

# 5. UI/UX ADMIN PANEL

El panel debe verse moderno y ordenado.

## Componentes

* Menú lateral agrupado.
* Header con usuario.
* Buscador global.
* Breadcrumbs.
* Tarjetas KPI.
* Tablas con filtros.
* Tablas con paginación.
* Badges de estado.
* Colores por criticidad.
* Modales de confirmación.
* Toasts de éxito/error.
* Formularios por secciones.
* Validación visual.
* Estados vacíos.
* Skeleton loading.
* Exportación visible.
* Botones de acción claros.
* Responsive para tablet.

---

# 6. UI/UX APP MÓVIL

La app debe ser simple, rápida y profesional.

## Requisitos

* Navegación clara.
* Home diferenciada por rol.
* Catálogo visual.
* Búsqueda rápida.
* Filtros simples.
* Carrito limpio.
* Checkout corto.
* Estados de orden visibles.
* Alertas de crédito/deuda.
* Perfil accesible.
* Carga rápida.
* Mensajes de error claros.
* Modo sin datos demo.
* Diseño alineado a Wulkan.

---

# 7. NOTIFICACIONES

Crear notificaciones internas y móviles.

## Admin

* Nueva orden.
* Crédito solicitado.
* Orden pendiente aprobación.
* Cliente bloqueado.
* Stock crítico.
* Producto agotado.
* Abono registrado.
* Cotización aceptada.
* Cliente nuevo por vendedor.

## Vendedor

* Cliente asignado.
* Orden aprobada.
* Orden rechazada.
* Comisión aprobada.
* Cliente con deuda.
* Cliente sin compra reciente.
* Meta pendiente.

## Cliente

* Orden recibida.
* Orden aprobada.
* Orden despachada.
* Orden entregada.
* Crédito aprobado.
* Crédito rechazado.
* Saldo vencido.

---

# 8. REGLAS DE NEGOCIO CRÍTICAS

Implementar reglas para evitar errores.

## Reglas

* No crear orden sin cliente.
* No crear orden sin productos.
* No aprobar orden sin stock.
* No aprobar crédito sin usuario autorizado.
* No superar cupo sin autorización.
* No vender a cliente bloqueado.
* No liberar comisión por orden anulada.
* No eliminar productos con historial.
* No eliminar clientes con órdenes.
* No duplicar SKU.
* No duplicar RIF.
* No permitir precios negativos.
* No permitir stock negativo sin permiso.
* Todo cambio sensible debe auditarse.

---

# 9. ESCALABILIDAD Y MANTENIMIENTO

Preparar sistema para crecimiento.

## Requisitos

* Índices en base de datos.
* Paginación real.
* Consultas optimizadas.
* Separación dev/staging/prod.
* Backups automáticos.
* Logs de errores.
* Logs de actividad.
* Control de versiones.
* Migraciones con Alembic.
* Variables de entorno.
* Documentación técnica.
* Documentación funcional.
* Manual de usuario admin.
* Manual de usuario app.

---

# 10. RESULTADO ESPERADO

El resultado debe ser una plataforma B2B profesional donde:

* El Admin Panel controla toda la operación.
* La App Cliente permite comprar y revisar crédito.
* La App Vendedor permite vender, cotizar y gestionar cartera.
* El backend centraliza reglas, permisos y datos.
* El inventario se mantiene consistente.
* El crédito se controla con reglas.
* La cobranza queda trazable.
* Las órdenes tienen estados profesionales.
* Las comisiones se calculan con política clara.
* Los reportes permiten tomar decisiones.
* La auditoría deja evidencia de todo.
* El sistema puede escalar sin depender de procesos manuales desordenados.


