# Roadmap MVP Wulkan

## Fase 0: Fundacion

- Estructura de monorepo.
- Contratos de dominio.
- Documentacion viva.
- Reglas iniciales Firebase.
- Semillas de verticales, roles y permisos.

**Estado:** cerrada tecnicamente.

## Fase 1: Admin operativo

- Login admin.
- Dashboard inicial con datos MVP.
- Verticales.
- Productos.
- Usuarios y roles.
- Empresas, ferreteros y servicios tecnicos.
- Ordenes B2C.
- Ordenes B2B.
- Casos tecnicos.
- Cotizaciones.
- Pagos.
- Ubicaciones.
- Usuarios y roles.
- Auditoria.
- Settings operativos.
- App Android base.
- Autenticacion preparada.

**Estado:** cerrada como fundacion operativa inicial. La persistencia real queda para fases siguientes.

### Avance actual Fase 1

- Layout admin navegable.
- Dashboard con metricas y alertas operativas.
- Tabla de verticales.
- Tabla de productos.
- Tabla de empresas.
- Tabla de ordenes B2C.
- Tabla de ordenes B2B.
- Tabla de casos tecnicos.
- Tabla de pagos.
- Tabla de cotizaciones.
- Tabla de ubicaciones autorizadas.
- Detalle de productos.
- Detalle de verticales.
- Formularios iniciales para crear productos y verticales.
- Capa `AdminRepository` para cambiar mocks por Firestore sin rehacer pantallas.
- Selector `WULKAN_ADMIN_DATA_SOURCE` para alternar mock/Firestore.
- `FirestoreRestAdminRepository` preparado para emulador o proyecto Firebase real.
- Script `seed:firestore` para cargar datos MVP en emulador o proyecto real.
- Configuracion de emuladores en `firebase.json`.
- Capa `getAdminSession` para alternar sesion mock/Firebase.
- Cloud Function `setUserRoleClaims` para roles, empresa, permisos y auditoria.
- Matriz central de permisos admin por ruta y modulo.
- Sidebar admin filtrado por permisos de sesion.
- Escritura Firestore reusable preparada para server actions.
- Primer CRUD persistente preparado: crear vertical comercial.
- Segundo CRUD persistente preparado: crear producto con precio publico, precio B2B y stock inicial.
- CRUD persistente preparado para empresas, ubicaciones, casos tecnicos, ordenes B2B y proyectos.
- Acciones operativas preparadas para validacion manual de pagos y respuesta de cotizaciones.
- App movil mock completa Perfil e Historial de ordenes.
- Contrato de integracion movil creado en `docs/product/CONTRATO_APP_MOVIL.md`.
- Configuracion movil por `--dart-define` creada.
- Flutter SDK instalado y runner Android creado.
- Android Studio y Android SDK instalados.
- Licencias Android aceptadas.
- App movil instalada y ejecutada en telefono fisico `25098RA98G`.
- App movil validada con `flutter analyze` y `flutter test`.
- Repositorio movil `MockMobileRepository` / `FirestoreMobileRepository` creado.
- Home, catalogo, detalle y ubicaciones consumen la frontera de datos movil.
- Tests de repositorio movil mock agregados.
- Bootstrap Firebase movil condicional agregado para Auth/Firestore por entorno.
- Auth movil mock/Firebase preparado.
- Mapper Firestore movil alineado con el seed MVP.
- Carrito/checkout movil conectado a servicio de calculo.
- Payload movil preparado para `createSecureOrder`.
- Tests moviles subidos a repositorio, mappers, Auth, carrito, checkout y shell.
- Datos MVP mock preparados para migrar a Firestore.

## Fase 2: App Android MVP

- Home.
- Catalogo.
- Busqueda.
- Detalle tecnico base.
- Carrito simple mock.
- Cotizacion.
- Puntos cercanos.
- Login por rol.
- Vista ferretero simple.
- Vista servicio tecnico simple.

### Avance actual Fase 2

- Modelo de variantes, precios, stock y compatibilidades.
- Modelo de carrito y resumen checkout.
- Admin de productos con filtros base, stock reservado y compatibilidades.
- Detalle admin de producto con variantes, inventario, precios y compatibilidades.
- App movil con detalle tecnico mock.
- App movil con carrito y checkout mock.
- App movil muestra entorno activo: mock/Firestore y mock/Firebase Auth.
- Archivo de ejemplo `apps/mobile/dart_defines.example.json` preparado para telefono/emulador.
- Android package configurado como `com.wulkan.mobile`.
- Catalogo movil preparado para cambiar de mock a Firestore por entorno.
- Checkout movil preparado para llamar backend cuando Firebase Android este configurado.
- Calculo compartido de checkout.
- Cloud Function `createSecureOrder` totaliza productos y crea pago inicial.
- Detalle admin de orden con pago e items.
- Filtros funcionales en catalogo admin por query, vertical y estado.

## Fase 3: Operacion real Venezuela

- Tasa USD/VES configurable.
- Pagos asistidos.
- Validacion manual por operador.
- Auditoria de cambios.
- Reportes basicos.
- Notificaciones de estados.

## Avance adicional sobre fases futuras

- Proyectos tecnicos modelados para instalaciones y evaluaciones.
- Admin de proyectos tecnicos.
- Formulario inicial de proyecto tecnico.
- Reportes mock por empresa.
- App movil con solicitud de proyecto tecnico.
- App movil con caso tecnico demo en acceso por rol.
- Condiciones B2B modeladas.
- Detalle admin de orden de compra B2B.
- Formulario mock de nueva OC B2B.
- Solicitudes de reposicion B2B.
- App movil con orden B2B y condiciones demo.
- Eventos e historial de casos tecnicos.
- Detalle admin de caso tecnico.
- Formulario mock de caso tecnico.
- Cloud Function `updateServiceCase` con auditoria.
- Cobertura y servicios por ubicacion autorizada.
- Filtros admin por tipo y servicio de punto.
- Detalle admin de ubicacion con mapa mock.
- Formulario mock de punto autorizado.
- App movil con filtros y mapa mock de puntos cercanos.
- Marketplace application para empresas vendedoras.
- Aprobacion de productos externos.
- Quality score de vendedores.
- Billing/cargos de plataforma mock.
