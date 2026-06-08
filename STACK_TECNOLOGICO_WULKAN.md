# Stack tecnologico profesional Wulkan

## 1. Vision tecnologica

Wulkan debe construirse como una plataforma digital B2B2C para Venezuela, no como una aplicacion aislada.

El sistema debe soportar:

- App movil Android para clientes, ferreteros, servicios tecnicos e instaladores.
- Admin web para Wulkan y operadores internos.
- Paneles por empresa proveedora.
- Catalogo tecnico multi-vertical.
- Venta directa al consumidor.
- Ordenes de compra B2B.
- Solicitudes de repuestos.
- Casos de servicio tecnico.
- Ubicacion de puntos cercanos.
- Pagos y validaciones locales.
- Futuro cobro por uso de plataforma segun facturacion de cada empresa.

La estrategia tecnologica correcta es empezar con una base simple, pero disenada con orden profesional desde el primer dia.

## 2. Decision principal

La recomendacion es construir Wulkan como un monolito modular, no como microservicios al inicio.

Esto significa:

- Un solo producto coherente.
- Modulos bien separados por area de negocio.
- Capas internas dentro de cada modulo.
- Backend inicial simple con Firebase.
- Posibilidad real de evolucionar a NestJS + PostgreSQL cuando el negocio lo justifique.

No se recomienda iniciar con microservicios porque aumentarian la complejidad operativa antes de validar el negocio.

## 3. Principios tecnicos

Toda decision tecnologica debe respetar estos principios:

1. Mantenibilidad antes que moda.
2. Seguridad antes que velocidad.
3. Modulos antes que archivos gigantes.
4. Dominio de negocio separado de la tecnologia.
5. Reglas criticas fuera del frontend.
6. Datos auditables.
7. Crecimiento gradual.
8. Experiencia visual profesional.
9. Costos controlados en etapa inicial.
10. Preparacion para escalar sin rehacer todo.

## 4. Arquitectura recomendada

### Enfoque principal

Wulkan debe usar una arquitectura modular por dominios de negocio.

Cada modulo representa una parte real del negocio:

- identity.
- companies.
- catalog.
- products.
- inventory.
- orders.
- b2b_purchase_orders.
- payments.
- billing.
- technical_services.
- locations.
- notifications.
- analytics.
- admin.

Dentro de cada modulo se pueden usar capas:

- presentation.
- application.
- domain.
- infrastructure.

Esto entrega orden sin hacer el proyecto innecesariamente complejo.

## 5. Estructura profesional del repositorio

Estructura recomendada:

```text
wulkan/
  apps/
    mobile/
    admin/
  packages/
    domain/
    shared/
    ui/
    config/
  backend/
    functions/
    api/
  docs/
    business/
    architecture/
    product/
    operations/
  infra/
    firebase/
    scripts/
```

### apps/mobile

App Android de Wulkan.

Debe contener:

- Pantallas.
- Navegacion.
- Estado de UI.
- Integracion con servicios de aplicacion.
- Tema visual.
- Componentes moviles.

No debe contener:

- Calculo final de pagos.
- Confirmacion de pagos.
- Validacion definitiva de permisos.
- Comisiones.
- Reglas de facturacion de empresas.

### apps/admin

Panel web administrativo.

Debe contener:

- Dashboard operativo.
- Gestion de empresas.
- Gestion de productos.
- Gestion de ordenes.
- Gestion B2B.
- Gestion de pagos.
- Gestion de servicios tecnicos.
- Gestion de usuarios.
- Reportes.
- Auditoria.

### packages/domain

Contiene conceptos centrales del negocio.

Ejemplos:

- Product.
- Company.
- UserRole.
- Order.
- PurchaseOrder.
- ServiceCase.
- Payment.
- BillingPeriod.
- PlatformFeeRule.

Este paquete no debe depender de Firebase, Flutter, React ni Next.js.

### packages/shared

Contiene utilidades compartidas:

- Formato de moneda.
- Conversion USD/VES.
- Validaciones comunes.
- Constantes.
- Tipos base.
- Estados de orden.
- Estados de pago.

### packages/ui

Contiene componentes visuales reutilizables:

- Botones.
- Badges.
- Inputs.
- Tablas.
- Cards.
- Modales.
- Estados vacios.
- Componentes de carga.
- Componentes de error.

### backend/functions

Cloud Functions para la etapa inicial.

Debe manejar:

- Creacion segura de ordenes.
- Calculo de totales.
- Calculo de comisiones.
- Webhooks de pago.
- Auditoria.
- Notificaciones.
- Cambios de estado.

### backend/api

Backend profesional futuro con NestJS.

No se necesita al inicio, pero la estructura queda preparada.

### docs

Documentacion viva del proyecto.

Debe contener:

- Arquitectura de negocio.
- Stack tecnologico.
- Modelo de datos.
- Roadmap.
- Roles y permisos.
- Manual operativo.
- Flujos de usuario.
- Decisiones tecnicas.

## 6. Tecnologias recomendadas por producto

## 6.1 App movil Android

Stack recomendado:

- Flutter.
- Dart.
- Riverpod.
- GoRouter.
- Firebase SDK.
- Firebase Cloud Messaging.
- Firebase Crashlytics.
- Google Maps o Mapbox.
- URL Launcher.

### Por que Flutter

Flutter es adecuado para Wulkan porque permite:

- Lanzar rapido en Android.
- Crear una interfaz moderna y fluida.
- Mantener una sola base de codigo.
- Escalar hacia iOS en el futuro.
- Construir componentes visuales consistentes.

### Estado

Se recomienda Riverpod porque:

- Mantiene el estado separado de la UI.
- Funciona bien con modulos.
- Facilita tests.
- Evita dependencias globales dificiles de mantener.

### Navegacion

Se recomienda GoRouter porque:

- Permite rutas declarativas.
- Funciona bien con autenticacion y roles.
- Facilita deep links.
- Ordena la navegacion por modulos.

### Modulos moviles iniciales

- Inicio.
- Catalogo.
- Busqueda.
- Producto.
- Carrito.
- Checkout.
- Cotizaciones.
- Puntos cercanos.
- Perfil.
- Historial de ordenes.
- Acceso ferretero.
- Acceso servicio tecnico.

## 6.2 Admin web

Stack recomendado:

- Next.js.
- React.
- TypeScript.
- Tailwind CSS.
- TanStack Query.
- TanStack Table.
- React Hook Form.
- Zod.
- Radix UI.
- Shadcn/ui como base inicial, adaptado a identidad Wulkan.

### Por que Next.js

El admin de Wulkan sera una herramienta operativa con:

- Tablas grandes.
- Filtros.
- Formularios.
- Reportes.
- Permisos.
- Auditoria.
- Dashboard.
- Acciones administrativas.

Next.js + TypeScript permite mantener ese tipo de sistema de forma mas profesional que Flutter Web.

### Criterio visual del admin

El admin no debe parecer una landing page.

Debe ser:

- Claro.
- Rapido.
- Denso pero ordenado.
- Profesional.
- Accionable.
- Preparado para trabajo diario.

## 6.3 Backend inicial

Stack recomendado:

- Firebase Authentication.
- Cloud Firestore.
- Firebase Storage.
- Cloud Functions.
- Firebase Hosting.
- Firebase Cloud Messaging.
- Firebase Analytics.
- Firebase Crashlytics.

### Por que Firebase al inicio

Firebase permite:

- Lanzar rapido.
- Reducir infraestructura inicial.
- Usar autenticacion segura.
- Enviar notificaciones.
- Guardar archivos.
- Tener base de datos en tiempo real suficiente para MVP.
- Probar el negocio antes de invertir en infraestructura mas pesada.

### Limite importante

Firebase no debe usarse como excusa para poner toda la logica en la app.

Las reglas criticas deben vivir en backend:

- Confirmacion de pagos.
- Creacion definitiva de ordenes.
- Validacion de permisos.
- Calculo de comisiones.
- Cambio de estados.
- Auditoria.
- Resumenes de facturacion.
- Activacion o suspension de empresas.

## 6.4 Backend futuro

Cuando el negocio crezca, se recomienda evolucionar hacia:

- Node.js.
- NestJS.
- TypeScript.
- PostgreSQL.
- Prisma ORM.
- Redis.
- Meilisearch o Algolia.
- Docker.
- Cloud Run.

### Cuando migrar

Conviene considerar NestJS + PostgreSQL cuando ocurra una o varias de estas senales:

- Muchas empresas operando.
- Alto volumen de ordenes.
- Reportes complejos.
- Facturacion recurrente.
- Comisiones por tramos.
- Necesidad de integracion con ERP.
- Reglas B2B avanzadas.
- Busquedas tecnicas exigentes.
- Costos de Firebase altos.

## 7. Modelo modular recomendado

## 7.1 Identity

Responsable de:

- Login.
- Registro.
- Roles.
- Permisos.
- Invitaciones.
- Usuarios habilitados.
- Sesiones.

Tecnologias:

- Firebase Authentication inicial.
- Custom Claims.
- Firestore para perfil extendido.
- RBAC propio en etapa avanzada.

## 7.2 Companies

Responsable de:

- Empresas proveedoras.
- Ferreteros.
- Servicios tecnicos.
- Instaladores.
- Estado de habilitacion.
- Documentos.
- Contactos.
- Condiciones comerciales.

Debe permitir:

- Aprobar empresas.
- Suspender empresas.
- Asociar usuarios.
- Definir tipo de empresa.
- Definir verticales activas.

## 7.3 Catalog

Responsable de:

- Categorias.
- Marcas.
- Verticales.
- Atributos tecnicos.
- Compatibilidades.

Debe estar preparado para:

- Herramientas.
- Repuestos.
- Iluminacion.
- Electricidad limpia.
- Energia solar.
- Seguridad industrial.
- Nuevas verticales futuras.

## 7.4 Products

Responsable de:

- Productos.
- Variantes.
- Imagenes.
- Fichas tecnicas.
- Manuales.
- SKU.
- Codigos internos.
- Publicacion.
- Estado comercial.

Debe soportar:

- Producto simple.
- Producto con variantes.
- Repuesto compatible.
- Producto tecnico.
- Producto por cotizacion.
- Producto con precio visible.
- Producto con precio privado B2B.

## 7.5 Inventory

Responsable de:

- Stock disponible.
- Stock reservado.
- Stock por empresa.
- Stock por ubicacion.
- Alertas de bajo stock.

En el MVP puede ser simple.

En etapa avanzada debe considerar:

- Movimientos de inventario.
- Reservas.
- Ajustes.
- Auditoria.
- Inventario por almacen.

## 7.6 Orders

Responsable de:

- Ordenes B2C.
- Estados.
- Items.
- Totales.
- Cliente.
- Pago.
- Entrega.
- Historial.

Estados sugeridos:

- draft.
- pending_payment.
- payment_under_review.
- paid.
- preparing.
- ready_for_pickup.
- shipped.
- delivered.
- cancelled.
- refunded.

## 7.7 B2B Purchase Orders

Responsable de:

- Ordenes de compra de ferreteros.
- Solicitudes de reposicion.
- Condiciones B2B.
- Aprobacion interna.
- Seguimiento.

Debe permitir:

- Crear orden desde lista de productos.
- Solicitar productos sin stock.
- Adjuntar referencia.
- Validar condiciones por ferretero.
- Cambiar estado desde admin.

## 7.8 Payments

Responsable de:

- Intentos de pago.
- Metodos.
- Webhooks.
- Validacion manual.
- Evidencias.
- Estados.

Metodos iniciales Venezuela:

- Mercado Pago / Mercado Libre.
- Pago movil.
- Transferencia bancaria.
- Confirmacion asistida por WhatsApp.

Regla clave:

El cliente nunca confirma su propio pago. El backend o un operador autorizado confirma.

## 7.9 Billing

Responsable de:

- Facturacion de empresas dentro de Wulkan.
- Tramos segun ventas.
- Comisiones.
- Cargos de plataforma.
- Periodos.
- Estados de cobro.

Aunque no se cobre al inicio, debe medirse desde el primer dia.

Entidades clave:

- PlatformFeeRule.
- BillingPeriod.
- CompanyRevenuePeriod.
- PlatformCharge.
- Invoice.

## 7.10 Technical Services

Responsable de:

- Casos tecnicos.
- Diagnosticos.
- Reparaciones.
- Repuestos usados.
- Fotos.
- Comentarios.
- Historial.
- Cierre del caso.

Debe permitir:

- Crear caso.
- Asignar servicio tecnico.
- Registrar diagnostico.
- Registrar reparacion.
- Adjuntar evidencias.
- Solicitar repuestos.
- Cerrar caso.

## 7.11 Locations

Responsable de:

- Ferreteros cercanos.
- Servicios tecnicos cercanos.
- Instaladores.
- Puntos de retiro.
- Cobertura geografica.

Tecnologias:

- Google Maps para MVP.
- Mapbox u OpenStreetMap si se busca reducir costos a futuro.

## 7.12 Notifications

Responsable de:

- Push notifications.
- Emails.
- WhatsApp asistido.
- Eventos de sistema.

Eventos importantes:

- Orden creada.
- Pago pendiente.
- Pago confirmado.
- Orden lista.
- Orden enviada.
- Cotizacion respondida.
- Caso tecnico actualizado.
- Empresa aprobada.
- Stock bajo.

## 8. Base de datos

## 8.1 Firestore para MVP

Colecciones recomendadas:

- users.
- companies.
- company_users.
- roles.
- permissions.
- business_verticals.
- categories.
- brands.
- products.
- product_variants.
- product_prices.
- product_stock.
- product_compatibilities.
- locations.
- orders.
- order_items.
- purchase_orders.
- purchase_order_items.
- service_cases.
- service_case_events.
- quotes.
- quote_items.
- payments.
- payment_methods.
- platform_fee_rules.
- billing_periods.
- company_revenue_periods.
- platform_charges.
- audit_logs.
- notifications.
- app_settings.

## 8.2 PostgreSQL futuro

Tablas recomendadas:

- users.
- companies.
- company_users.
- roles.
- permissions.
- role_permissions.
- business_verticals.
- product_categories.
- brands.
- products.
- product_variants.
- product_prices.
- product_stock.
- product_compatibilities.
- locations.
- orders.
- order_items.
- purchase_orders.
- purchase_order_items.
- service_cases.
- service_case_events.
- quotes.
- quote_items.
- payments.
- invoices.
- platform_fee_rules.
- billing_periods.
- company_revenue_periods.
- platform_charges.
- audit_logs.

## 9. Seguridad

La seguridad debe disenarse como parte del producto, no como una tarea final.

Reglas obligatorias:

- Ningun usuario B2B opera sin habilitacion.
- El frontend solo muestra u oculta opciones.
- El backend valida permisos reales.
- Toda accion critica genera auditoria.
- Los archivos privados no deben ser publicos.
- Los pagos manuales requieren evidencia.
- Los cambios de precio guardan historial.
- Los cambios de estado guardan usuario, fecha y origen.

Roles iniciales:

- super_admin.
- wulkan_admin.
- wulkan_operator.
- company_owner.
- company_seller.
- hardware_store_owner.
- hardware_store_buyer.
- technical_service_owner.
- technical_service_operator.
- installer.
- customer.

## 10. Pagos para Venezuela

Metodos iniciales:

- Mercado Pago / Mercado Libre.
- Pago movil.
- Transferencia bancaria.
- Validacion manual.
- Confirmacion asistida por WhatsApp.

Flujo recomendado:

1. Usuario crea orden.
2. Backend calcula total.
3. Backend crea intento de pago.
4. Usuario paga.
5. Webhook confirma cuando aplique.
6. Operador valida si es pago manual.
7. Backend actualiza estado.
8. Sistema registra auditoria.
9. Usuario recibe notificacion.

Datos del pago:

- paymentId.
- orderId.
- companyId.
- method.
- amountUsd.
- amountVes.
- exchangeRate.
- referenceNumber.
- proofImageUrl.
- status.
- confirmedBy.
- confirmedAt.

## 11. Tasa USD/VES

MVP:

- Tasa configurable desde admin.
- Historial por fecha.
- Productos con precio base USD.
- Conversion VES al momento de compra.

Futuro:

- Integracion con proveedor de tasa.
- Tasa oficial.
- Tasa comercial.
- Reglas por empresa.
- Auditoria de cambios.

## 12. Modelo de cobro por facturacion

Wulkan debe estar preparado para cobrar a empresas segun facturacion dentro de la plataforma.

Modelo inicial recomendado:

- Sin mensualidad al comienzo.
- Medicion de ventas desde el primer dia.
- Comision por orden procesada.
- Tramos por facturacion mensual.
- Cargos premium opcionales.

Ejemplo conceptual:

- Tramo 1: empresa nueva, baja comision.
- Tramo 2: empresa con ventas recurrentes, comision normal.
- Tramo 3: empresa de alto volumen, comision negociada.
- Servicios premium: posicionamiento, reportes, integraciones y soporte.

El sistema debe calcular:

- Facturacion mensual por empresa.
- Comision estimada.
- Comision confirmada.
- Cargos pendientes.
- Cargos pagados.
- Historial de cargos.

## 13. Busqueda

La busqueda es un punto critico para Wulkan.

Usuarios podran buscar por:

- Nombre.
- SKU.
- Marca.
- Categoria.
- Repuesto.
- Modelo de maquina.
- Compatibilidad.
- Vertical.
- Ferretero cercano.
- Servicio tecnico.

MVP:

- Firestore indexes.
- Keywords normalizadas.
- SKU normalizado.
- Filtros por categoria, marca y vertical.

Etapa profesional:

- Meilisearch si se busca control y costo bajo.
- Algolia si se busca experiencia premium y velocidad de implementacion.

## 14. Sistema visual

Wulkan debe tener un sistema visual propio.

No se debe construir pantalla por pantalla sin reglas.

Elementos obligatorios:

- Paleta de colores.
- Tipografia.
- Escala de espaciados.
- Botones.
- Inputs.
- Selectores.
- Tablas.
- Badges.
- Estados.
- Alertas.
- Modales.
- Empty states.
- Loading states.
- Error states.

### Paleta recomendada

Inspiracion Venezuela, aplicada con sobriedad:

- Azul profundo: confianza, tecnologia, navegacion.
- Amarillo controlado: acciones comerciales y CTA.
- Rojo: alertas y estados criticos.
- Verde: exito, disponibilidad y pagos aprobados.
- Blanco: claridad.
- Gris neutro: fondos, tablas y bordes.

La interfaz no debe verse como una bandera literal. Debe sentirse venezolana, moderna y confiable.

### Modo horario

Se recomienda:

- Tema claro profesional.
- Tema oscuro profesional.
- Preferencia manual.
- Adaptacion opcional por horario.

La logica de tema debe estar centralizada.

## 15. Analitica y observabilidad

Herramientas iniciales:

- Firebase Analytics.
- Firebase Crashlytics.
- Cloud Logging.
- Alertas de errores.

Eventos recomendados:

- product_viewed.
- search_performed.
- add_to_cart.
- checkout_started.
- order_created.
- payment_started.
- payment_confirmed.
- quote_requested.
- purchase_order_created.
- service_case_created.
- nearby_location_opened.
- company_product_published.

Metricas de negocio:

- Ventas por empresa.
- Ordenes por dia.
- Ticket promedio.
- Productos mas vistos.
- Busquedas sin resultado.
- Conversion catalogo a orden.
- Tiempo de respuesta a cotizaciones.
- Tiempo de cierre de casos tecnicos.
- Facturacion mensual por empresa.
- Comision potencial de Wulkan.

## 16. Calidad de codigo

Estandares:

- TypeScript estricto.
- Dart analysis activo.
- Lints obligatorios.
- Formateo automatico.
- Tests unitarios.
- Tests de integracion.
- Tests end-to-end para flujos criticos.
- Pull requests con revision.
- Commits descriptivos.

Herramientas:

- ESLint.
- Prettier.
- Vitest.
- Playwright.
- Flutter analyze.
- Flutter test.
- GitHub Actions.

Flujos que deben probarse:

- Login por rol.
- Crear producto.
- Publicar producto.
- Crear orden.
- Crear orden B2B.
- Confirmar pago.
- Cambiar estado de orden.
- Crear caso tecnico.
- Cerrar caso tecnico.
- Calcular comision.
- Aplicar tasa USD/VES.

## 17. CI/CD

Automatizaciones recomendadas:

- Validar formato.
- Ejecutar lints.
- Ejecutar tests.
- Build Android.
- Build admin web.
- Deploy a staging.
- Deploy manual a produccion.

Ambientes:

- dev.
- staging.
- production.

Cada ambiente debe tener:

- Firebase project separado.
- Variables separadas.
- Credenciales separadas.
- Reglas de seguridad propias.
- Datos semilla controlados.

## 18. Infraestructura

MVP:

- Firebase Hosting.
- Firestore.
- Firebase Storage.
- Cloud Functions.
- Firebase Authentication.
- Firebase Cloud Messaging.

Etapa avanzada:

- Cloud Run.
- PostgreSQL administrado.
- Redis administrado.
- Meilisearch administrado o Algolia.
- CDN.
- Backups programados.
- Monitoreo avanzado.

## 19. Documentacion necesaria

Documentos que deben existir:

- Arquitectura de negocio.
- Stack tecnologico.
- Modelo de datos.
- Roles y permisos.
- Flujos de usuario.
- Flujos administrativos.
- Manual de operaciones.
- Guia de despliegue.
- Guia de soporte.
- Registro de decisiones tecnicas.

El registro de decisiones tecnicas debe explicar:

- Que se decidio.
- Por que se decidio.
- Que alternativas se descartaron.
- Que impacto tiene.
- Cuando se debe revisar.

## 20. Estrategia de mantenimiento

Para mantener Wulkan en el tiempo, se recomienda:

- Versionado semantico.
- Roadmap por fases.
- Backlog separado por modulo.
- Documentacion actualizada.
- Tests en flujos criticos.
- Logs claros.
- Auditoria de acciones sensibles.
- Backups probados.
- Revisiones tecnicas periodicas.

Categorias de soporte:

- Error de pago.
- Error de orden.
- Problema de catalogo.
- Problema de empresa.
- Problema de usuario.
- Problema de servicio tecnico.
- Problema de ubicacion.
- Problema de stock.

## 21. Que no hacer al inicio

No se recomienda al inicio:

- Microservicios.
- Kubernetes.
- ERP propio completo.
- Sistema contable completo.
- Motor de facturacion fiscal complejo.
- App iOS antes de validar Android.
- Multipais antes de validar Venezuela.
- Reglas comerciales duplicadas en frontend.
- Admin hecho solo con pantallas improvisadas.

Estas cosas pueden llegar despues, pero no deben bloquear el lanzamiento.

## 22. Fases recomendadas

### Fase 1: MVP profesional Venezuela

Objetivo:

Validar operacion real con clientes, ferreteros, empresas y servicios tecnicos.

Stack:

- Flutter Android.
- Next.js Admin.
- Firebase Auth.
- Firestore.
- Firebase Storage.
- Cloud Functions.
- Firebase Hosting.
- Firebase Cloud Messaging.
- Google Maps.
- Mercado Pago / Mercado Libre.
- Pago movil y transferencia manual.

Modulos:

- Identity.
- Companies.
- Catalog.
- Products.
- Orders.
- Payments.
- Locations.
- Technical Services basico.

### Fase 2: Operacion B2B completa

Objetivo:

Convertir Wulkan en una plataforma operativa para empresas y ferreteros.

Agregar:

- Ordenes de compra B2B.
- Condiciones por empresa.
- Reportes por empresa.
- Auditoria completa.
- Billing medido.
- Notificaciones mas robustas.
- Busqueda mejorada.
- Paneles por rol.

### Fase 3: Monetizacion formal

Objetivo:

Activar cobro por uso de plataforma.

Agregar:

- Reglas de comision.
- Periodos de facturacion.
- Cargos de plataforma.
- Estados de cobro.
- Reportes financieros.
- Servicios premium.

### Fase 4: Escalamiento tecnico

Objetivo:

Preparar el crecimiento de volumen.

Evaluar:

- NestJS.
- PostgreSQL.
- Prisma.
- Redis.
- Meilisearch o Algolia.
- BigQuery o Looker Studio.
- WhatsApp Business API.
- Integraciones ERP.

## 23. Decision final recomendada

La decision recomendada para Wulkan es:

1. Construir la app Android con Flutter.
2. Construir el admin web con Next.js + TypeScript.
3. Usar Firebase como backend inicial.
4. Crear Cloud Functions para reglas criticas.
5. Organizar todo como monolito modular.
6. Separar dominio, aplicacion e infraestructura dentro de los modulos importantes.
7. Medir facturacion por empresa desde el primer dia.
8. No construir microservicios hasta que el volumen lo exija.
9. Preparar una migracion futura a NestJS + PostgreSQL.
10. Mantener documentacion y pruebas desde el inicio.

Esta estrategia permite lanzar en Venezuela con velocidad, pero con una base profesional para que Wulkan pueda crecer, mantenerse y convertirse en una plataforma comercial real.
