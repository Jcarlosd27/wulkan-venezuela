# Checklist arquitectura de negocio Wulkan

Este checklist resume `ARQUITECTURA_NEGOCIO_WULKAN.md` para medir avance cada vez que se gestione algo del proyecto.

## Leyenda

- `[x]` Hecho.
- `[~]` En progreso.
- `[ ]` Pendiente.
- `N/A MVP` Fuera del MVP inicial.

## Estado general

- [x] Arquitectura de negocio definida.
- [x] Stack tecnologico definido.
- [x] Monorepo base creado.
- [x] Documentacion viva creada.
- [x] Fase 0 cerrada tecnicamente.
- [x] Fase 1 cerrada como fundacion operativa inicial.
- [~] Admin web MVP navegable.
- [~] App Android base con catalogo, detalle y carrito mock.
- [x] Contrato de integracion para app movil creado.
- [x] Configuracion movil por `--dart-define` creada.
- [x] Flutter SDK instalado y validado.
- [x] Android Studio instalado.
- [x] Runner Android creado.
- [x] App movil pasa `flutter analyze` y `flutter test`.
- [x] Repositorio movil mock/Firestore creado.
- [~] Home, catalogo, detalle y ubicaciones consumen repositorio movil.
- [x] Tests de repositorio movil mock agregados.
- [x] Bootstrap Firebase movil condicional agregado.
- [~] Auth movil mock/Firebase preparado.
- [x] Tests de Auth movil mock agregados.
- [x] Mapper Firestore movil alineado con seed MVP.
- [x] Android SDK instalado.
- [x] Licencias Android aceptadas.
- [x] Telefono Android fisico detectado por Flutter.
- [x] App movil instalada y ejecutada en Android fisico.
- [~] Firebase preparado con reglas, colecciones y selector de fuente de datos.
- [x] Configuracion de emuladores Firebase agregada.
- [x] Seed Firestore MVP agregado.
- [x] Estado porcentual del proyecto documentado.
- [~] Firebase local conectado con Firestore Emulator validado.
- [~] Auth Firebase preparado con frontera mock/Firebase.
- [ ] MVP operativo con datos persistentes.

## 1. Resumen ejecutivo

- [x] Plataforma multi-vertical B2B2C definida.
- [x] Enfoque Venezuela definido.
- [x] App movil Android definida.
- [x] App web admin definida.
- [x] Wulkan/Avalon Group definido como orquestador.
- [~] Base tecnica inicial creada.
- [ ] Operacion real con clientes, ferreteros y servicios tecnicos.

## 2. Tesis de negocio

- [x] Fricciones del mercado identificadas.
- [x] Diferenciacion por red de venta, repuesto y soporte definida.
- [ ] Validacion comercial real con usuarios.
- [ ] Validacion de recompra/repuesto/servicio tecnico.

## 3. Propuesta de valor

- [x] Valor para Wulkan/Avalon Group definido.
- [x] Valor para clientes finales definido.
- [x] Valor para ferreteros definido.
- [x] Valor para servicios tecnicos definido.
- [x] Valor para empresas vendedoras definido.
- [~] Admin inicial soporta parte de la operacion.
- [~] App movil mock para cliente, ferretero y servicio tecnico.
- [~] Panel/reporte mock por empresa vendedora.

## 4. Posicionamiento

- [x] Posicionamiento definido como plataforma tecnica multi-vertical.
- [x] Mensajes comerciales sugeridos definidos.
- [ ] Copy final de marca/producto.
- [ ] Material comercial final.

## 5. Productos digitales

### Alcance Venezuela

- [x] Pais operativo inicial `VE`.
- [x] Moneda principal `USD`.
- [x] Moneda secundaria `VES`.
- [x] Tasa USD/VES preparada en settings mock.
- [ ] Tasa USD/VES persistente en Firebase.
- [~] Pagos Venezuela con validacion manual persistente preparada.
- [ ] Logistica/retiro/despacho operativos.

### App movil Android

- [~] Home base.
- [~] Catalogo base.
- [~] Busqueda base.
- [~] Detalle de producto mock.
- [~] Carrito simple mock.
- [~] Checkout mock.
- [~] Cotizaciones base.
- [~] Puntos cercanos base.
- [~] Perfil mock.
- [~] Historial de ordenes mock.
- [~] Acceso ferretero base.
- [~] Acceso servicio tecnico base.
- [x] Android package `com.wulkan.mobile` configurado.
- [x] Frontera mock/Firestore documentada para movil.
- [x] Frontera mock/Firebase Auth documentada para movil.
- [~] Catalogo movil preparado para leer Firestore.
- [~] Puntos cercanos movil preparados para leer Firestore.
- [~] Inicializacion Firebase movil preparada por entorno.
- [~] Firebase Auth movil preparado, pendiente de configuracion Android real.
- [~] Firestore movil preparado, pendiente de configuracion Android real.
- [~] Carrito movil conectado a servicio de calculo.
- [~] Checkout movil genera payload para `createSecureOrder`.

### App web admin

- [x] Dashboard operativo inicial.
- [~] Dashboard conectado a repositorio mock/Firestore.
- [~] Formulario `Nueva vertical` conectado a Server Action.
- [~] Formulario `Nuevo producto` conectado a Server Action.
- [x] Verticales.
- [x] Productos.
- [x] Empresas.
- [x] Ordenes B2C.
- [x] Ordenes B2B.
- [x] Casos tecnicos.
- [x] Cotizaciones.
- [x] Pagos.
- [x] Ubicaciones.
- [x] Usuarios y roles.
- [x] Vista de estado Auth/claims.
- [x] Auditoria.
- [x] Settings.
- [~] Formularios base.
- [~] CRUD persistente iniciado con verticales, productos, empresas, ubicaciones, casos, B2B y proyectos.
- [~] Lectura Firestore preparada con fallback mock.
- [ ] Auth real.
- [~] Permisos reales preparados en matriz admin.
- [~] Reportes mock por empresa.
- [x] Documento `ESTADO_PROYECTO.md` creado.

## 6. Actores y permisos

- [x] Roles iniciales modelados.
- [x] Permisos base documentados.
- [x] Matriz admin de permisos por modulo.
- [~] Sidebar admin filtrado por permisos de sesion.
- [x] Usuarios mock creados.
- [~] Vista admin de usuarios.
- [~] Firebase Auth preparado, pendiente de login real.
- [~] Custom claims preparados con Cloud Function.
- [ ] Validacion real de permisos en backend.
- [ ] Invitaciones.
- [ ] Asociacion usuario-empresa persistente.

## 7. Modulos funcionales

### Verticales comerciales

- [x] Contrato `BusinessVertical`.
- [x] Atributos tecnicos por vertical.
- [x] Vista admin.
- [x] Detalle admin.
- [x] Formulario inicial.
- [~] CRUD persistente preparado para crear vertical en Firestore.
- [ ] Constructor completo de atributos.

### Catalogo maestro / Products

- [x] Contrato `Product`.
- [x] Datos mock.
- [x] Vista admin.
- [x] Detalle admin.
- [x] Formulario inicial.
- [~] Catalogo movil base con detalle tecnico.
- [~] CRUD persistente preparado para crear producto, precios y stock en Firestore.
- [ ] Imagenes.
- [ ] Manuales/fichas tecnicas.
- [x] Historial de precios modelado.

### Compatibilidad de repuestos

- [x] Campo `compatibilityIds`.
- [x] Ejemplo mock motosierra/cadena.
- [x] Modelo completo de compatibilidad.
- [~] Busqueda por maquina/modelo/SKU preparada en UI.
- [~] Validacion tecnica asistida preparada en UI.

### Proyectos e instalaciones

- [x] Contrato completo `TechnicalProject`.
- [x] Vista admin.
- [~] Flujo app mock.
- [~] Asignacion de instalador mock.
- [~] Cotizacion tecnica vinculada por `quoteId`.

### Ordenes B2C

- [x] Contrato `Order`.
- [x] Vista admin.
- [x] Mock inicial.
- [x] Cloud Function `createSecureOrder` base.
- [x] Cloud Function `changeOrderStatus` base.
- [x] Cloud Function `reviewPurchaseOrder` preparada.
- [x] Cloud Function `reviewServicePartRequest` preparada.
- [x] Cloud Function `findNearbyLocations` preparada.
- [~] Carrito mock con modelo compartido.
- [~] Checkout mock con calculo compartido.
- [x] Calculo backend de totales preparado en Cloud Function.
- [ ] Persistencia real.

### Ordenes B2B

- [x] Contrato `PurchaseOrder`.
- [x] Vista admin.
- [x] Mock inicial.
- [~] Crear OC desde ferretero en admin mock.
- [~] Condiciones B2B modeladas y visibles.
- [~] Aprobacion/rechazo preparada en Cloud Function y vista admin.
- [~] Solicitud de reposicion modelada y visible.

### Casos de servicio tecnico

- [x] Contrato `ServiceCase`.
- [x] Vista admin.
- [x] Mock inicial.
- [~] Vista movil base por rol con caso tecnico demo.
- [~] Crear caso en admin mock.
- [~] Diagnostico/fotos modelados y diagnostico visible.
- [~] Solicitud de repuestos modelada, visible y con revision backend preparada.
- [~] Cierre con auditoria preparado en Cloud Function.
- [x] Historial/eventos de caso tecnico modelados.

### Cotizaciones

- [x] Contrato `Quote`.
- [x] Vista admin.
- [x] Mock inicial.
- [~] Formulario movil base.
- [~] Responder cotizacion preparado con Server Action.
- [~] Convertir en orden preparado como estado operativo.
- [ ] Vencimientos.

### Puntos cercanos / Locations

- [x] Contrato `AuthorizedLocation`.
- [x] Vista admin.
- [x] Mock inicial.
- [~] Vista movil base con filtros y mapa mock.
- [~] Mapa mock.
- [~] Geolocalizacion preparada con coordenadas, cobertura y calculo de distancia.
- [~] Filtros por tipo y servicio en admin.
- [~] Vista admin de puntos cercanos por lat/lng.
- [~] Crear ubicacion preparado con Server Action.

## 8. Flujos operativos

- [x] Flujo cliente final documentado.
- [x] Flujo ferretero documentado.
- [x] Flujo servicio tecnico documentado.
- [x] Flujo proyecto/instalacion documentado.
- [x] Flujo empresa vendedora documentado.
- [~] Pantallas base para algunos flujos.
- [~] Flujo producto -> orden -> pago preparado en backend/mock.
- [ ] Pruebas de flujos criticos.

## 9. Datos principales

- [x] `User`.
- [x] `Company`.
- [x] `Product`.
- [x] `BusinessVertical`.
- [x] `TechnicalAttribute`.
- [x] `PurchaseOrder`.
- [x] `ServiceCase`.
- [x] `Quote`.
- [x] `Payment`.
- [x] `Location`.
- [x] `AuditLog`.
- [x] `AppSettings`.
- [x] `TechnicalProject`.
- [x] Variantes/precios/stock como entidades completas.
- [ ] Migracion a datos reales Firestore.

## 10. Arquitectura funcional

- [x] Firebase elegido para MVP.
- [x] Cloud Functions iniciales.
- [x] Firestore rules iniciales.
- [x] Firestore indexes iniciales.
- [x] Repositorio admin Firestore REST preparado.
- [x] Fallback mock/firestore por variable de entorno.
- [x] Backend futuro reservado en `backend/api`.
- [ ] Proyecto Firebase real.
- [x] Emulador Firestore ejecutado localmente en puerto `8085`.
- [~] Repositorio Firestore real preparado, pendiente de Auth/proyecto production.
- [x] Seed MVP ejecutado contra Firestore Emulator.

## 11. Integraciones

### Venezuela

- [~] Pago movil/transferencia modelados.
- [~] Validacion manual preparada.
- [ ] Mercado Pago/Mercado Libre.
- [ ] WhatsApp Business.
- [ ] Storage para comprobantes.
- [ ] Estados/ciudades/zonas reales.

### Transversales

- [~] Google Maps/Mapbox preparado a nivel UI mock.
- [ ] Email transaccional.
- [ ] Push notifications.
- [ ] Analytics.
- [ ] Crash reporting.

## 12. Monetizacion

- [x] Modelo conceptual definido.
- [x] Contratos iniciales de billing.
- [~] Medicion mock de facturacion por empresa.
- [~] Comision/cargo por plataforma modelado.
- [~] Periodos de cobro modelados en reportes/cargos.
- [~] Reportes financieros mock.

## 13. KPIs

- [x] KPIs definidos.
- [~] Dashboard muestra metricas mock.
- [ ] KPIs reales desde Firestore.
- [~] Reportes mock por empresa.
- [ ] Conversion y busquedas sin resultado.

## 14. UX y marketing

### App movil

- [~] Navegacion base.
- [~] Busqueda visible.
- [~] Verticales visibles.
- [~] UX base de detalle producto.
- [~] UX base carrito/checkout.
- [x] Calculo checkout movil probado.
- [x] Payload movil de orden segura probado.
- [x] Panel de entorno movil visible en app mock.
- [x] Runner Android con etiqueta `Wulkan`.
- [~] Estados loading/empty agregados en listas moviles.
- [ ] UX final ferretero.
- [~] UX base servicio tecnico.

### Admin web

- [x] Layout operativo.
- [x] Sidebar modular.
- [x] Tablas iniciales.
- [x] Badges de estado.
- [x] Formularios iniciales.
- [~] Densidad operativa base.
- [~] Filtros funcionales por query en catalogo admin.
- [~] Acciones reales iniciadas con Server Actions persistentes.
- [ ] Estados vacios/loading/error.

## 15. Riesgos

- [x] Riesgos documentados.
- [~] Separacion dominio/UI/backend iniciada.
- [~] Separacion repositorio mock/Firestore iniciada.
- [~] Separacion sesion mock/Firebase iniciada.
- [~] Permisos modelados.
- [~] Auditoria preparada.
- [ ] Evitar duplicar reglas en frontend con backend real.
- [~] Control de calidad de productos externos preparado en marketplace mock.
- [~] Trazabilidad orden-pago-items preparada en admin/backend mock.

## 16. MVP recomendado

### App movil MVP

- [~] Home.
- [~] Catalogo.
- [~] Verticales iniciales.
- [~] Busqueda.
- [~] Detalle tecnico mock.
- [~] Carrito simple mock.
- [~] Solicitud de cotizacion base.
- [~] Puntos cercanos base.
- [x] Configuracion por entorno para preparar telefono/emulador.
- [x] Proyecto Android generado para instalacion futura.
- [ ] Login por rol.
- [ ] Filtros dinamicos por vertical.
- [~] Vista ferretero simple con OC y condiciones B2B demo.
- [~] Vista servicio tecnico simple.

### Admin web MVP

- [ ] Login admin real.
- [x] Dashboard.
- [x] Verticales.
- [x] Productos.
- [x] Usuarios y roles.
- [x] Ferreteros/empresas.
- [x] Servicios tecnicos.
- [x] Ordenes B2C.
- [x] Ordenes B2B.
- [x] Casos tecnicos.
- [x] Cotizaciones.
- [ ] CRUD real.

### Fuera del MVP inicial

- [~] Marketplace controlado de empresas externas en modo mock. `N/A MVP`
- [ ] ERP. `N/A MVP`
- [ ] Facturacion automatica. `N/A MVP`
- [ ] App iOS. `N/A MVP`
- [ ] Analitica avanzada. `N/A MVP`
- [ ] Motor complejo de compatibilidades. `N/A MVP`
- [ ] Chile u otros paises. `N/A MVP`

## 17. Roadmap

- [x] Fase 0: Definicion/Fundacion.
- [x] Fase 1: Fundacion tecnica/Admin operativo inicial.
- [~] Fase 2: Ecommerce base avanzada en modo mock.
- [~] Fase 3: Ferreteros avanzada con aprobacion backend preparada.
- [~] Fase 4: Servicio tecnico avanzada con revision de repuestos preparada.
- [~] Fase 5: Red fisica avanzada con distancia/cercania preparada.
- [~] Fase 6: Marketplace controlado iniciada en modo mock.
- [ ] Fase 7: Escalamiento.
- [ ] Fase 8: Expansion internacional futura.

## 18. Definicion de exito

- [~] Clientes pueden simular compra o cotizacion con menos friccion.
- [~] Ferreteros tienen base de OC, reposicion, condiciones, aprobacion y reporte mock.
- [~] Servicios tecnicos tienen caso demo, diagnostico, eventos y revision de repuesto preparada.
- [ ] Wulkan tiene trazabilidad de productos, repuestos y maquinas.
- [~] Wulkan puede sumar verticales desde la arquitectura.
- [~] Admin reduce gestion manual en prototipo.
- [~] Red fisica visible como ventaja en prototipo.

## Ultima actualizacion

- Fecha: 2026-05-20.
- Estado: Fase 0 y 1 cerradas; admin preparado para alternar mock/Firestore/Auth y app movil con contrato de integracion inicial.
- Avance estimado: 69% del proyecto total; Firestore Emulator, seed MVP, Flutter SDK, Android Studio, runner Android, repositorio movil, bootstrap Firebase, Auth movil, carrito/checkout y tests validados.
- Proxima prioridad: completar Android SDK desde Android Studio para correr en telefono/emulador y agregar configuracion Firebase Android real.
