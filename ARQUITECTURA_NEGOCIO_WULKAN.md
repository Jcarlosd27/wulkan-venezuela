# Arquitectura de negocio Wulkan

## 1. Resumen ejecutivo

Wulkan debe construirse como una plataforma multi-vertical B2B2C para maquinaria, repuestos, ferreteria tecnica, iluminacion, electricidad limpia, servicios autorizados y postventa. La oportunidad no esta solo en vender productos por internet, sino en controlar y conectar ciclos comerciales y tecnicos completos: descubrimiento, compra, repuesto, instalacion, reparacion, garantia, recompra y soporte.

La plataforma tendra dos productos digitales:

- App movil Android: canal comercial y operativo para clientes finales, ferreteros autorizados y servicios tecnicos.
- App web admin: backoffice maestro para Wulkan/Avalon Group y portales operativos para empresas vendedoras, ferreteros, tecnicos y operadores internos.

Wulkan/Avalon Group sera el orquestador del ecosistema. Eso significa que ninguna empresa, ferretero, instalador, servicio tecnico o vendedor especializado opera libremente sin habilitacion, permisos y reglas comerciales definidas por Wulkan.

La primera vertical puede ser maquinaria, repuestos y servicio tecnico, pero la arquitectura debe permitir sumar nuevas verticales como iluminacion, electricidad limpia, energia solar, climatizacion, seguridad industrial o ferreteria industrial sin reconstruir el sistema.

La primera salida comercial sera Venezuela. Todo el MVP debe optimizarse para el mercado venezolano: moneda, pagos, logistica, ferreteros, servicios tecnicos, estados/ciudades y comportamiento comercial local. Chile queda fuera del alcance inicial y se considera solamente una expansion futura.

## 2. Tesis de negocio

El mercado de maquinaria y repuestos tiene fricciones que un ecommerce tradicional no resuelve bien:

- El cliente muchas veces no sabe que repuesto corresponde.
- El ferretero necesita abastecimiento rapido y confiable.
- El servicio tecnico necesita repuestos, trazabilidad y respaldo.
- El vendedor necesita canal digital, pero la plataforma debe controlar calidad.
- La garantia requiere historial: maquina, cliente, compra, servicio y repuestos usados.
- Venezuela requiere reglas comerciales, logisticas y de pago propias; Chile u otros paises se evaluaran en una etapa posterior.
- Cada vertical tecnica tiene atributos, servicios, garantias y reglas de cotizacion propias.

Wulkan puede diferenciarse convirtiendose en la red que resuelve esas fricciones.

## 3. Propuesta de valor

### Para Wulkan/Avalon Group

- Centralizar ventas B2C, ventas B2B, cotizaciones y soporte tecnico.
- Controlar catalogo, verticales, precios, stock, puntos autorizados y permisos.
- Crear trazabilidad completa entre maquina, repuesto, orden, ferretero y servicio tecnico.
- Mejorar la disponibilidad de repuestos y reducir atencion manual.
- Vender mas a traves de clientes finales, ferreteros, servicios tecnicos y empresas autorizadas.
- Convertir datos operativos en inteligencia comercial: que se vende, que falla, que repuesto rota, que vertical crece y donde falta cobertura.

### Para clientes finales

- Comprar maquinaria, accesorios, repuestos, iluminacion o soluciones tecnicas con respaldo.
- Encontrar ferreteros cercanos.
- Contactar servicios tecnicos autorizados.
- Solicitar cotizaciones si no conoce el repuesto exacto.
- Consultar estado de pedidos, garantias y soporte.

### Para ferreteros

- Comprar a Wulkan con condiciones comerciales B2B.
- Crear ordenes de compra.
- Reordenar productos frecuentes.
- Consultar disponibilidad y estados de despacho.
- Ser visibles como punto autorizado, si Wulkan lo aprueba.
- Acceder a informacion tecnica para vender mejor.

### Para servicios tecnicos

- Registrar diagnosticos y reparaciones.
- Solicitar repuestos desde un caso tecnico.
- Mantener historial por maquina, cliente o numero de serie.
- Documentar fotos, mano de obra, repuestos usados y recomendaciones.
- Dar soporte con respaldo y trazabilidad.

### Para empresas vendedoras

- Publicar productos en un canal especializado.
- Acceder a demanda del ecosistema Wulkan.
- Gestionar stock y ventas propias.
- Operar bajo reglas de calidad, comision y aprobacion.

## 4. Posicionamiento

Wulkan no debe posicionarse como una tienda generica ni como un catalogo limitado a una sola categoria. Debe presentarse como:

> Plataforma tecnica multi-vertical de venta, abastecimiento, instalacion, repuestos y soporte autorizado.

### Mensajes comerciales sugeridos

- Compra maquinaria y repuestos con respaldo tecnico.
- Encuentra soluciones para maquinaria, iluminacion, electricidad limpia y nuevas verticales tecnicas.
- Encuentra ferreteros y servicios tecnicos autorizados cerca de ti.
- Solicita repuestos por modelo, SKU o maquina compatible.
- Gestiona tus ordenes B2B desde un solo lugar.
- Registra reparaciones y solicita repuestos desde el caso tecnico.

## 5. Productos digitales

## Alcance inicial: Venezuela

La primera version debe estar enfocada solo en Venezuela. La plataforma puede mantener campos preparados para expansion internacional, pero la experiencia, los pagos, la logistica y la operacion deben resolverse primero para Venezuela.

### Reglas de mercado inicial

- Pais operativo: Venezuela.
- Moneda comercial principal: USD.
- Moneda local referencial o secundaria: VES.
- Tasa de cambio configurable desde admin.
- Pagos principales: Mercado Libre / Mercado Pago, pago movil, transferencia y coordinacion por WhatsApp.
- Logistica: retiro, delivery local, envio nacional y coordinacion manual.
- Direcciones: estado, ciudad, municipio, parroquia/sector, referencia y telefono.
- Red fisica: ferreteros, distribuidores, servicios tecnicos e instaladores autorizados en Venezuela.
- Chile queda excluido del MVP.

### Expansion futura

La arquitectura puede conservar `country`, `currency` y disponibilidad por pais para no cerrar puertas. Sin embargo, durante el MVP todos los flujos deben asumir:

- `country = VE`
- `primaryCurrency = USD`
- `secondaryCurrency = VES`

## App movil Android

La app movil debe tener experiencia publica y experiencia por rol.

### Publico sin login

- Home comercial.
- Catalogo.
- Busqueda.
- Detalle de producto.
- Puntos ferreteros cercanos.
- Servicios tecnicos cercanos.
- Solicitud de cotizacion.
- Contacto WhatsApp.
- Navegacion por vertical: maquinaria, repuestos, iluminacion, electricidad limpia y futuras areas.

### Cliente final autenticado

- Perfil.
- Direcciones.
- Favoritos.
- Carrito.
- Historial de compras.
- Seguimiento de pedidos.
- Solicitudes de cotizacion.
- Soporte y garantias.

### Ferretero autenticado

- Home B2B.
- Catalogo ferretero.
- Precios y condiciones B2B.
- Ordenes de compra.
- Reordenar productos frecuentes.
- Estado de aprobacion, preparacion, despacho o retiro.
- Solicitud de cotizacion B2B.

### Servicio tecnico autenticado

- Home tecnico.
- Crear caso tecnico.
- Registrar maquina y cliente.
- Diagnostico, fotos y observaciones.
- Solicitud de repuestos.
- Estados de reparacion.
- Historial por maquina.

## App web admin

La app web debe operar como backoffice modular, no como una simple pantalla de productos.

### Vista Wulkan master

- Dashboard general.
- Usuarios y roles.
- Empresas vendedoras.
- Ferreteros.
- Servicios tecnicos.
- Clientes.
- Productos y repuestos.
- Verticales comerciales.
- Ordenes B2C.
- Ordenes de compra B2B.
- Casos tecnicos.
- Cotizaciones.
- Pagos.
- Despachos.
- Garantias.
- Banners y contenido.
- Reportes.
- Auditoria.

### Vista empresa vendedora

- Productos propios.
- Stock propio.
- Ventas propias.
- Ordenes asignadas.
- Reportes de rendimiento.

### Vista operador Wulkan

- Ordenes pendientes.
- Cotizaciones pendientes.
- Solicitudes de repuestos.
- Casos tecnicos abiertos.
- Alertas de stock.
- Tareas operativas del dia.

## 6. Actores y permisos

| Actor | Acceso | Objetivo | Control Wulkan |
| --- | --- | --- | --- |
| Admin maestro | Web | Control total | Sin restricciones |
| Operador Wulkan | Web | Operacion diaria | Permisos limitados |
| Empresa vendedora | Web | Vender productos propios | Requiere aprobacion |
| Ferretero | App/Web futuro | Comprar B2B y generar OC | Requiere habilitacion |
| Servicio tecnico | App/Web futuro | Registrar trabajos y pedir repuestos | Requiere habilitacion |
| Instalador autorizado | App/Web futuro | Ejecutar instalaciones o proyectos tecnicos | Requiere habilitacion |
| Cliente final | App | Comprar, cotizar y buscar soporte | Registro opcional/obligatorio segun flujo |

### Permisos base

- Ver catalogo.
- Crear producto.
- Editar producto.
- Aprobar producto.
- Cambiar precio.
- Ver ordenes.
- Aprobar orden B2B.
- Gestionar despacho.
- Crear caso tecnico.
- Cerrar caso tecnico.
- Gestionar vertical comercial.
- Gestionar atributos tecnicos por vertical.
- Asignar instalador autorizado.
- Ver reportes.
- Administrar usuarios.
- Administrar permisos.

## 7. Modulos funcionales

### Verticales comerciales

Wulkan debe organizar el negocio por verticales. Una vertical es una linea comercial o tecnica con categorias, atributos, reglas de cotizacion, servicios, garantias y actores asociados.

Verticales iniciales sugeridas:

- Maquinaria y jardin.
- Repuestos.
- Ferreteria tecnica.
- Iluminacion.
- Electricidad limpia.
- Energia solar.
- Climatizacion.
- Seguridad industrial.
- Servicios tecnicos.

Cada vertical debe poder definir:

- Categorias propias.
- Atributos tecnicos propios.
- Tipos de producto.
- Reglas de cotizacion.
- Reglas de garantia.
- Servicios asociados.
- Empresas vendedoras habilitadas.
- Ferreteros o distribuidores asociados.
- Servicios tecnicos o instaladores asociados.
- Banners y contenido comercial propio.
- Disponibilidad inicial en Venezuela.

Ejemplos de atributos por vertical:

| Vertical | Atributos tecnicos sugeridos |
| --- | --- |
| Maquinaria | Potencia, cilindrada, motor, uso recomendado, combustible, garantia |
| Repuestos | SKU, compatibilidad, maquina asociada, familia, posicion, version |
| Iluminacion | Watts, lumenes, temperatura de color, voltaje, IP, interior/exterior |
| Electricidad limpia | Capacidad, voltaje, eficiencia, certificacion, instalador requerido |
| Energia solar | Panel, inversor, bateria, potencia, autonomia, dimensionamiento |
| Climatizacion | BTU, consumo, cobertura, instalacion requerida, garantia |
| Seguridad industrial | norma, certificacion, talla, material, uso recomendado |

Esta capa evita que Wulkan quede atrapado en una sola linea de negocio. La app y el admin deben leer la configuracion de cada vertical para mostrar formularios, filtros y fichas tecnicas adecuadas.

### Catalogo maestro

El catalogo maestro es el corazon de Wulkan. Debe ordenar productos propios, productos de vendedores, maquinaria, repuestos, accesorios, iluminacion, soluciones electricas, servicios y futuras verticales.

Campos principales:

- SKU.
- Nombre.
- Marca.
- Categoria.
- Tipo: maquinaria, repuesto, accesorio, servicio.
- Vertical comercial.
- Precio publico.
- Precio B2B.
- Precio en USD.
- Precio referencial en VES.
- Stock.
- Stock por bodega o vendedor.
- Imagenes.
- Ficha tecnica.
- Manuales.
- Garantia.
- Maquinas compatibles.
- Repuestos relacionados.
- Requiere cotizacion.
- Requiere instalacion.
- Requiere validacion tecnica.
- Disponible en Venezuela.
- Disponible para expansion futura.

### Compatibilidad de repuestos

Este modulo es clave para diferenciarse.

- Repuesto compatible con una o varias maquinas.
- Maquina compatible con varios repuestos.
- Busqueda por modelo, motor, SKU, serie o categoria.
- Recomendaciones de repuestos frecuentes.
- Validacion tecnica antes de comprar si hay duda.

### Proyectos e instalaciones

Este modulo sera necesario para verticales como iluminacion, electricidad limpia, energia solar o climatizacion, donde la compra puede depender de una evaluacion tecnica.

Funciones:

- Solicitud de proyecto.
- Registro de direccion y requerimiento.
- Adjuntar fotos, planos o medidas.
- Asignar instalador autorizado.
- Crear cotizacion tecnica.
- Convertir cotizacion en orden.
- Registrar instalacion realizada.
- Activar garantia del proyecto.

Estados sugeridos:

- Solicitado.
- En evaluacion.
- Visita agendada.
- Cotizado.
- Aprobado.
- En instalacion.
- Instalado.
- Cerrado.

### Ordenes B2C

Ordenes de clientes finales.

Estados sugeridos:

- Creada.
- Pago pendiente.
- Pagada.
- En revision.
- Preparando.
- En despacho.
- Lista para retiro.
- Entregada.
- Cancelada.
- Devuelta.

### Ordenes de compra B2B

Ordenes generadas por ferreteros.

Estados sugeridos:

- Borrador.
- Enviada.
- En revision Wulkan.
- Aprobada.
- Modificada.
- Rechazada.
- Preparando.
- Despachada.
- Cerrada.

### Casos de servicio tecnico

Registro tecnico de reparaciones.

Estados sugeridos:

- Recibida.
- Diagnosticada.
- Esperando aprobacion.
- Esperando repuesto.
- En reparacion.
- Reparada.
- Entregada.
- Cerrada.
- Garantia rechazada.

### Cotizaciones

Flujo comercial asistido.

Usos:

- Producto de alto valor.
- Repuesto dudoso.
- Envio pesado.
- Compra B2B especial.
- Producto sin stock inmediato.

Estados:

- Solicitada.
- En revision.
- Respondida.
- Aceptada.
- Rechazada.
- Vencida.
- Convertida en orden.

### Puntos cercanos

Permite conectar app movil con red fisica.

Tipos:

- Ferreteria autorizada.
- Servicio tecnico autorizado.
- Punto de retiro.
- Distribuidor.

Campos:

- Nombre.
- Tipo.
- Direccion.
- Coordenadas.
- Telefono.
- WhatsApp.
- Horario.
- Servicios disponibles.
- Pais.
- Estado activo/inactivo.

## 8. Flujos operativos

### Flujo cliente final

1. Cliente entra a la app.
2. Busca producto, repuesto o servicio.
3. Revisa ficha tecnica.
4. Compra, cotiza o contacta soporte.
5. Si compra, se genera orden B2C.
6. Wulkan valida pago y stock.
7. Se despacha o deriva a retiro.
8. Cliente recibe seguimiento.

### Flujo ferretero

1. Wulkan crea o aprueba usuario ferretero.
2. Ferretero inicia sesion.
3. Ve catalogo B2B y precios propios.
4. Crea orden de compra.
5. Wulkan revisa disponibilidad y condiciones.
6. Wulkan aprueba, modifica o rechaza.
7. Se prepara despacho o retiro.
8. Ferretero consulta historial y reordena.

### Flujo servicio tecnico

1. Wulkan habilita servicio tecnico.
2. Tecnico crea caso.
3. Registra maquina, falla, fotos y diagnostico.
4. Solicita repuestos.
5. Wulkan aprueba o cotiza repuestos.
6. Tecnico actualiza reparacion.
7. Caso queda cerrado con historial.

### Flujo proyecto tecnico o instalacion

1. Cliente o ferretero solicita proyecto desde una vertical como iluminacion, electricidad limpia, energia solar o climatizacion.
2. El sistema solicita datos minimos: ubicacion, uso esperado, fotos, medidas y observaciones.
3. Wulkan revisa la solicitud.
4. Wulkan asigna operador o instalador autorizado.
5. Se genera cotizacion tecnica.
6. Cliente aprueba la cotizacion.
7. Se agenda instalacion o despacho.
8. Instalador registra trabajo realizado, fotos y observaciones.
9. Wulkan cierra el proyecto y activa garantia.

### Flujo empresa vendedora

1. Empresa solicita acceso o Wulkan la invita.
2. Wulkan valida antecedentes.
3. Empresa carga productos.
4. Wulkan aprueba publicacion.
5. Cliente compra o cotiza.
6. Orden se asigna segun reglas.
7. Wulkan supervisa cumplimiento.

## 9. Datos principales

### User

- id.
- name.
- email.
- phone.
- role.
- status.
- country.
- companyId.
- permissions.
- createdAt.
- lastLoginAt.

### Company

- id.
- legalName.
- commercialName.
- taxId.
- country.
- type: seller, hardwareStore, technicalService, distributor.
- contacts.
- address.
- location.
- status.
- commercialTerms.

### Product

- id.
- sku.
- title.
- description.
- verticalId.
- type.
- brandId.
- categoryId.
- sellerId.
- publicPrice.
- b2bPrice.
- currency.
- stock.
- countryAvailability.
- images.
- technicalSheetUrl.
- manualUrl.
- warranty.
- compatibilityIds.
- requiresQuote.
- requiresInstallation.
- requiresTechnicalValidation.
- status.

### BusinessVertical

- id.
- name.
- description.
- slug.
- status.
- countries.
- icon.
- bannerImage.
- requiresTechnicalAttributes.
- availableProductTypes.
- attributeSchema.
- quoteRules.
- warrantyRules.
- serviceRules.
- sellerIds.
- authorizedServiceIds.
- authorizedInstallerIds.

### TechnicalAttribute

- id.
- verticalId.
- name.
- type: text, number, boolean, select, multiSelect, file, range.
- unit.
- required.
- options.
- visibleInFilters.
- visibleInProductDetail.
- appliesToProductTypes.

### PurchaseOrder

- id.
- requesterCompanyId.
- requesterUserId.
- items.
- subtotal.
- discounts.
- total.
- currency.
- status.
- notes.
- approvedBy.
- createdAt.
- updatedAt.

### ServiceCase

- id.
- technicalServiceId.
- customerName.
- customerContact.
- machineId.
- serialNumber.
- symptoms.
- diagnosis.
- photos.
- requestedParts.
- usedParts.
- laborNotes.
- status.
- warrantyRelated.
- createdAt.
- closedAt.

### Quote

- id.
- requesterType.
- requesterId.
- items.
- message.
- status.
- response.
- validUntil.
- convertedOrderId.

### TechnicalProject

- id.
- verticalId.
- requesterId.
- requesterType.
- location.
- requirements.
- photos.
- measurements.
- assignedOperatorId.
- assignedInstallerId.
- quoteId.
- status.
- scheduledAt.
- installedAt.
- warrantyStartAt.
- warrantyEndAt.
- closingNotes.

## 10. Arquitectura funcional sugerida

### Backend

Para una primera version puede usarse Firebase:

- Firebase Authentication para usuarios.
- Firestore para datos transaccionales.
- Firebase Storage para imagenes, manuales y fotos tecnicas.
- Firebase Hosting para admin web.
- Cloud Functions para pagos, notificaciones, webhooks y reglas criticas.

### Futuro backend dedicado

Cuando crezca el negocio, conviene evaluar un backend propio:

- API REST/GraphQL.
- Base de datos relacional para ordenes, inventario y compatibilidades.
- Motor de busqueda tipo Meilisearch/Algolia/Elastic.
- Servicio de notificaciones.
- Integracion ERP/contabilidad.

## 11. Integraciones

### Venezuela

- Mercado Libre / Mercado Pago.
- Pago movil.
- Transferencia.
- WhatsApp Business.
- Despacho local, retiro o envio nacional.
- Tasa USD/VES configurable.
- Confirmacion manual de pagos asistidos.
- Registro de referencia bancaria o comprobante.
- Estados, ciudades, municipios y zonas de cobertura.

### Expansion futura fuera de Venezuela

Chile u otros paises deben quedar como expansion posterior. Cuando llegue esa etapa se agregaran pagos, monedas, documentos, impuestos, operadores logisticos y reglas comerciales propias de cada pais.

### Transversales

- Google Maps para puntos cercanos.
- Email transaccional.
- Push notifications.
- Analytics.
- Crash reporting.
- Storage para documentos tecnicos.
- Formularios dinamicos por vertical.
- Motor de atributos tecnicos.

## 12. Monetizacion

Wulkan puede monetizar por:

- Margen de productos propios.
- Margen por vertical nueva.
- Venta recurrente a ferreteros.
- Venta de repuestos a servicios tecnicos.
- Comision a empresas vendedoras.
- Servicios de garantia/postventa.
- Cotizaciones de productos complejos.
- Proyectos e instalaciones tecnicas.
- Convenios con puntos autorizados.
- Reportes comerciales premium para vendedores.

## 13. KPIs

### Comerciales

- Ventas totales.
- Ventas Venezuela.
- Ventas por canal.
- Ventas por vertical.
- Ticket promedio.
- Conversion de cotizaciones.
- Productos mas vendidos.
- Repuestos mas solicitados.
- Verticales con mayor crecimiento.

### Operativos

- Ordenes pendientes.
- Tiempo promedio de aprobacion B2B.
- Tiempo promedio de despacho.
- Productos con stock critico.
- Productos sin ficha tecnica.
- Productos sin atributos obligatorios de su vertical.
- Cotizaciones vencidas.
- Proyectos tecnicos pendientes.

### Tecnicos

- Casos abiertos.
- Casos cerrados.
- Tiempo promedio de reparacion.
- Repuestos usados por tipo de maquina.
- Fallas recurrentes.
- Garantias activadas.
- Instalaciones cerradas.

### Red comercial

- Ferreteros activos.
- Servicios tecnicos activos.
- Empresas vendedoras activas.
- Cobertura geografica.
- Ventas por punto autorizado.

## 14. UX y marketing

### App movil

- La busqueda debe ser protagonista.
- El usuario debe poder buscar por SKU, modelo, repuesto o maquina.
- La navegacion debe permitir explorar por vertical sin mezclar necesidades tecnicas diferentes.
- La ficha de producto debe explicar compatibilidad, garantia y soporte.
- Cada vertical debe mostrar filtros y atributos relevantes. No se debe mostrar el mismo formulario para una motosierra, una luminaria o un sistema solar.
- Cada producto debe tener CTA claro: Comprar, Cotizar, WhatsApp o Ver repuestos.
- Los productos con instalacion o validacion tecnica deben priorizar Cotizar o Solicitar evaluacion.
- Puntos cercanos deben ser faciles de encontrar.
- El modo ferretero y tecnico deben sentirse como herramientas de trabajo, no como una tienda comun.

### Admin web

- Debe ser operativo, rapido y claro.
- Sidebar por modulos.
- Dashboard con alertas accionables.
- Tablas con filtros y estados.
- Acciones visibles: aprobar, rechazar, modificar, despachar, cerrar.
- Historial de cambios en ordenes y casos.
- Permisos por rol desde el inicio.
- Constructor de verticales: atributos, filtros, reglas comerciales y servicios asociados.

## 15. Riesgos

- Construir demasiados modulos antes de validar el flujo principal.
- Mezclar roles sin permisos claros.
- No separar precios publicos y precios B2B.
- No separar estado de pago, estado operativo y estado logistico.
- No controlar la calidad de productos externos.
- No documentar compatibilidades de repuestos.
- Diseñar multi-pais antes de validar Venezuela y volver pesado el MVP.
- No definir bien tasa USD/VES y comprobantes de pago.
- Construir categorias rigidas en vez de verticales configurables.
- Crear atributos tecnicos como texto libre sin estructura.
- Depender solo de WhatsApp sin registrar trazabilidad.

## 16. MVP recomendado

El MVP debe demostrar el valor central: venta + repuesto + soporte tecnico + B2B.

### App movil MVP

- Home Wulkan.
- Catalogo.
- Verticales iniciales.
- Busqueda.
- Detalle tecnico.
- Carrito simple.
- Solicitud de cotizacion.
- Puntos cercanos cargados manualmente.
- Login por rol.
- Filtros dinamicos por vertical.
- Vista ferretero simple.
- Vista servicio tecnico simple.

### Admin web MVP

- Login admin.
- Dashboard.
- Verticales.
- Productos.
- Usuarios y roles.
- Ferreteros.
- Servicios tecnicos.
- Ordenes B2C.
- Ordenes B2B.
- Casos tecnicos.
- Cotizaciones.

### Fuera del MVP inicial

- Marketplace completo de empresas externas.
- ERP.
- Facturacion automatica.
- App iOS.
- Analitica avanzada.
- Motor complejo de compatibilidades.
- Chile u otros paises.

## 17. Roadmap

### Fase 0: Definicion

- Cerrar arquitectura.
- Definir roles.
- Definir datos maestros.
- Definir permisos.
- Definir MVP.
- Definir verticales iniciales.
- Definir atributos tecnicos por vertical.
- Definir reglas operativas Venezuela.
- Definir tasa USD/VES, pagos asistidos y logistica local.

### Fase 1: Fundacion tecnica

- Crear proyecto desde cero.
- Configurar marca Wulkan.
- Crear app Android.
- Crear admin web.
- Crear autenticacion.
- Crear estructura de roles.
- Crear estructura de verticales.
- Crear formularios dinamicos basados en vertical.

### Fase 2: Ecommerce base

- Catalogo.
- Verticales comerciales.
- Productos.
- Categorias.
- Busqueda.
- Carrito.
- Ordenes B2C.
- Dashboard admin.

### Fase 3: Ferreteros

- Alta de ferreteros.
- Catalogo B2B.
- Ordenes de compra.
- Precios B2B.
- Estados de aprobacion.

### Fase 4: Servicio tecnico

- Alta de servicios tecnicos.
- Casos tecnicos.
- Diagnostico y fotos.
- Solicitud de repuestos.
- Historial por maquina.

### Fase 5: Red fisica

- Ferreteros cercanos.
- Servicios tecnicos cercanos.
- Instaladores cercanos.
- Mapa.
- Contacto.
- Retiro o derivacion.

### Fase 6: Marketplace controlado

- Empresas vendedoras.
- Catalogo por vendedor.
- Aprobacion de productos.
- Reportes por vendedor.
- Comisiones.

### Fase 7: Escalamiento

- Nuevas verticales como iluminacion, electricidad limpia, solar o climatizacion.
- Pagos Venezuela.
- Despachos integrados.
- Notificaciones.
- Auditoria.
- Analytics.
- Automatizaciones.

### Fase 8: Expansion internacional futura

- Evaluar entrada a Chile u otros paises.
- Agregar moneda local.
- Agregar metodos de pago locales.
- Agregar operadores logisticos locales.
- Ajustar impuestos, documentos y reglas comerciales.
- Activar disponibilidad por pais.

## 18. Definicion de exito

La plataforma sera exitosa si logra:

- Que clientes compren o coticen con menos friccion.
- Que ferreteros generen ordenes de compra recurrentes.
- Que servicios tecnicos registren reparaciones y pidan repuestos.
- Que Wulkan tenga trazabilidad de productos, repuestos y maquinas.
- Que Wulkan pueda sumar nuevas verticales sin rehacer la app ni el admin.
- Que el admin reduzca gestion manual.
- Que la red fisica se convierta en ventaja competitiva.

La idea central es construir una red operativa de venta y soporte tecnico. El ecommerce es solo una parte; el valor real esta en conectar actores, datos y procesos que hoy suelen estar dispersos.
