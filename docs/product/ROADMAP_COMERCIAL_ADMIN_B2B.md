# Roadmap comercial del Admin Wulkan B2B

## Objetivo

Convertir el panel Wulkan en una plataforma comercial B2B para ferreteros en Venezuela.

El producto final debe permitir que Wulkan administre catalogo, stock, clientes ferreteros, lineas de credito, ordenes y pagos externos, mientras la app movil permite que cada ferretero vea productos disponibles y compre contra su credito autorizado.

## Estado actual

El proyecto actual es una plataforma en **pre-produccion avanzada / piloto comercial cerrado**.

Ya existe:

- Admin Flask con Bootstrap 5.3.
- Modulos de dashboard, productos, categorias, biblioteca tecnica, stock, anuncios, ordenes, clientes, credito, usuarios admin y auditoria.
- API movil para productos, categorias, anuncios, ubicaciones, autenticacion, credito, ordenes y cambio de contrasena.
- App Flutter que puede consumir datos desde Flask si se ejecuta con `WULKAN_MOBILE_DATA_SOURCE=api`.
- SQLAlchemy y Alembic con runtime SQL activable.
- Clientes ferreteros con usuario, contrasena temporal y linea de credito.
- Ordenes B2B asociadas a cliente.
- Abonos/pagos externos.
- Reglas de credito y bloqueo por contrasena temporal.
- CSRF, roles y auditoria.
- Tests moviles pasando.

Todavia falta para venderlo como produccion final:

- Activar despliegue HTTPS con dominio real.
- Configurar PostgreSQL administrado o el compose productivo.
- Programar backups automaticos y probar restauracion.
- Configurar credenciales de storage externo para imagenes y PDFs.
- QA end-to-end con backend real y telefono fisico.
- Recuperacion segura de contrasenas.
- Rate limit persistente para login.

## Modelo comercial correcto

Wulkan no sera un ecommerce de pago online tradicional.

El flujo correcto es:

1. Wulkan crea un cliente ferretero.
2. Wulkan le asigna usuario y contrasena.
3. Wulkan define si tiene credito o no.
4. Wulkan define el limite de credito en USD.
5. El ferretero entra a la app movil.
6. El ferretero ve productos activos con stock.
7. El ferretero crea una orden.
8. La orden usa credito disponible o queda en revision.
9. Wulkan gestiona entrega y cobro externo.
10. El ferretero paga por efectivo, transferencia, pago movil u otro medio manual.
11. El admin registra el abono.
12. El credito disponible se recalcula.

## Fase 0 - Estabilizacion del MVP actual

Objetivo: dejar el demo actual ordenado y coherente como base comercial.

Entregables:

- Panel visual consistente con Bootstrap 5.3.
- Login con marca Wulkan.
- Sidebar sin duplicidades.
- Buscadores solo por modulo.
- Productos con SKU obligatorio.
- Categorias con imagen.
- Anuncios con forma visual igual a categorias.
- Stock con estados claros.
- API movil validada.

Criterio de salida:

- Todas las rutas del admin cargan con `200`.
- App movil puede leer productos desde Flask en modo API.
- `flutter analyze` sin errores.
- `flutter test` pasando.

Estado: en progreso avanzado.

## Fase 1 - Base productiva y seguridad minima

Objetivo: reemplazar la demo local por una base operable.

Entregables tecnicos:

- Migrar de JSON local a PostgreSQL.
- Incorporar SQLAlchemy.
- Crear migraciones con Alembic.
- Usar variables de entorno para secretos.
- Separar configuracion `development`, `staging` y `production`.
- Desactivar credenciales hardcodeadas.
- Activar HTTPS en despliegue.
- Incorporar CSRF para formularios admin.
- Logs operativos basicos.
- Backups automaticos de base de datos.

Modulos afectados:

- Login.
- Productos.
- Categorias.
- Stock.
- Ordenes.
- Anuncios.

Criterio de salida:

- Ningun dato comercial se guarda en JSON.
- Reiniciar el servidor no pierde datos.
- Admin requiere sesion real.
- API movil no expone datos sensibles.
- Existe backup y restauracion probada.

## Fase 2 - Usuarios, roles y clientes ferreteros

Objetivo: permitir administrar quienes entran al sistema.

Modulos nuevos:

- Usuarios admin.
- Roles y permisos.
- Clientes ferreteros.

Usuarios admin:

- Nombre.
- Email.
- Contrasena segura.
- Rol.
- Estado.
- Ultimo acceso.

Roles iniciales:

- Super admin.
- Operador Wulkan.
- Inventario.
- Ventas.
- Solo lectura.

Clientes ferreteros:

- Nombre comercial.
- RIF o cedula.
- Responsable.
- Telefono.
- Email.
- Direccion.
- Usuario de acceso movil.
- Contrasena temporal.
- Estado: activo, suspendido, bloqueado.
- Tipo: ferretero, distribuidor, cliente especial.
- Observaciones internas.

Criterio de salida:

- Wulkan puede crear usuarios admin.
- Wulkan puede crear clientes ferreteros.
- Cada ferretero puede iniciar sesion en la app.
- Un ferretero solo ve su propia informacion comercial.

## Fase 3 - Linea de credito B2B

Objetivo: controlar el credito otorgado a cada ferretero.

Modulo nuevo:

- Credito clientes.

Campos por cliente:

- Credito habilitado: si/no.
- Limite de credito USD.
- Credito usado USD.
- Credito disponible USD.
- Ordenes pendientes USD.
- Dias de credito.
- Estado crediticio.
- Bloqueo por deuda.
- Notas internas.

Regla base:

```text
credito_disponible = limite_credito - credito_usado - ordenes_pendientes_no_pagadas
```

Casos:

- Cliente con credito suficiente: orden queda aprobable.
- Cliente sin credito: orden queda en revision.
- Cliente con credito insuficiente: orden queda bloqueada o requiere aprobacion.
- Cliente bloqueado: no puede crear ordenes.

Criterio de salida:

- Admin puede asignar credito por cliente.
- App muestra credito disponible.
- Checkout muestra total, credito disponible y credito restante.
- Orden no puede exceder credito sin quedar marcada para revision.

## Fase 4 - Ordenes B2B y pagos externos

Objetivo: convertir ordenes en flujo operativo real.

Modulo ordenes:

- Numero de orden.
- Cliente ferretero.
- Productos.
- Total USD.
- Total VES referencial.
- Credito usado.
- Credito disponible posterior.
- Estado.
- Fecha.
- Usuario que gestiona.

Estados recomendados:

- Creada.
- En revision.
- Aprobada con credito.
- Sin credito suficiente.
- Preparando.
- Entregada.
- Pagada parcialmente.
- Pagada.
- Cancelada.

Modulo pagos externos:

- Cliente.
- Orden asociada.
- Monto USD.
- Monto VES.
- Metodo: efectivo, transferencia, pago movil, otro.
- Referencia.
- Fecha.
- Observacion.
- Usuario admin que registro.

Regla:

- Crear orden consume o reserva credito.
- Registrar abono libera credito.
- Cancelar orden libera credito reservado.
- Entregar orden consolida deuda si no esta pagada.

Criterio de salida:

- Orden creada desde app aparece en admin.
- Orden afecta credito del cliente.
- Abono manual actualiza deuda y credito disponible.
- Historial de credito queda auditable.

## Fase 5 - Inventario comercial real

Objetivo: que stock sea confiable para venta B2B.

Entregables:

- Stock disponible.
- Stock reservado.
- Stock comprometido por orden.
- Stock entregado.
- Ajustes manuales con motivo.
- Carga masiva por CSV.
- Kardex por producto.
- Alertas de reposicion.

Reglas:

- Orden aprobada reserva stock.
- Orden cancelada libera stock.
- Orden entregada descuenta stock definitivo.
- No se puede vender mas de lo disponible salvo permiso especial.

Criterio de salida:

- Inventario del admin y app coinciden.
- Toda variacion de stock queda registrada.
- Stock bajo aparece en dashboard.

## Fase 6 - App movil ferretera

Objetivo: que la app sea un portal B2B, no solo un catalogo.

Pantallas requeridas:

- Login ferretero.
- Inicio con credito disponible.
- Catalogo con stock.
- Detalle producto.
- Carrito.
- Checkout con credito.
- Ordenes del cliente.
- Estado de orden.
- Perfil comercial.

Datos visibles para ferretero:

- Nombre comercial.
- Credito aprobado.
- Credito usado.
- Credito disponible.
- Ordenes pendientes.
- Productos disponibles.
- Precios en USD.
- Referencia VES.

Criterio de salida:

- El ferretero inicia sesion con usuario real.
- El ferretero solo ve sus ordenes.
- El ferretero sabe cuanto credito tiene antes de comprar.
- Una orden creada en la app aparece en admin.

## Fase 7 - Produccion comercial

Objetivo: dejar el producto listo para operar clientes reales.

Checklist:

- Base de datos PostgreSQL productiva.
- Backups diarios.
- Admin con HTTPS.
- API movil con HTTPS.
- Variables de entorno.
- Roles y permisos.
- Logs y auditoria.
- Proteccion CSRF.
- Validaciones de formularios.
- Manejo de errores.
- Politica de contrasenas.
- Recuperacion de contrasena.
- App compilada con modo API productivo.
- Manual de operacion.
- Manual de soporte.
- Prueba de recuperacion de backup.

Criterio de salida:

- Wulkan puede crear ferreteros reales.
- Ferreteros pueden comprar por credito.
- Admin puede gestionar ordenes y abonos.
- Credito disponible se calcula correctamente.
- Stock se reserva y descuenta correctamente.
- Sistema soporta operacion diaria sin depender de datos mock.

## Tecnologia recomendada para produccion

Backend:

- Flask.
- SQLAlchemy.
- Alembic.
- PostgreSQL.
- Flask-Login para admin.
- JWT para API movil.
- Flask-WTF para CSRF.

Frontend admin:

- Bootstrap 5.3.
- UIX local para densidad y layout.
- Graphify o Chart.js para metricas.

App movil:

- Flutter.
- Riverpod.
- GoRouter.
- API Flask productiva.
- Autenticacion movil por API Flask con token.

Storage:

- DigitalOcean Spaces o storage S3 compatible.
- No guardar imagenes comerciales solo en disco local.

Deploy:

- VPS o nube con HTTPS.
- Gunicorn o Waitress segun entorno.
- Nginx como reverse proxy.
- Backups automaticos.
- Logs centralizados.

## Orden recomendado de trabajo

1. Migrar datos a PostgreSQL.
2. Crear usuarios admin y roles.
3. Crear clientes ferreteros.
4. Crear modulo de credito.
5. Rehacer ordenes con cliente y credito.
6. Crear pagos externos/abonos.
7. Amarrar ordenes con stock.
8. Ajustar app movil para login ferretero.
9. Compilar app siempre en modo API.
10. Hacer pruebas comerciales end-to-end.

## Prueba comercial end-to-end obligatoria

Antes de vender, este flujo debe funcionar completo:

1. Admin crea ferretero.
2. Admin asigna USD 1,000 de credito.
3. Ferretero entra a la app.
4. Ferretero ve credito disponible.
5. Ferretero agrega productos al carrito.
6. Ferretero confirma orden de USD 185.
7. Admin ve orden.
8. Credito disponible baja a USD 815.
9. Admin registra abono externo de USD 100.
10. Credito disponible sube a USD 915.
11. Orden conserva historial.
12. Stock queda reservado/descontado segun estado.

Si este flujo no funciona, el producto aun no esta comercializable.
