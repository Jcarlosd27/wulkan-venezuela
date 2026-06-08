# Flujos MVP

## Cliente final

1. Explora verticales o busca por SKU, modelo, repuesto o producto.
2. Revisa ficha tecnica, compatibilidad, garantia y disponibilidad.
3. Compra, solicita cotizacion o contacta soporte.
4. Si compra, backend calcula total y crea intento de pago.
5. Operador o webhook confirma pago.
6. Orden avanza a preparacion, retiro, despacho o entrega.

## Ferretero

1. Wulkan aprueba ferretero y usuario.
2. Ferretero entra a catalogo B2B.
3. Crea orden de compra.
4. Wulkan revisa disponibilidad y condiciones.
5. Orden se aprueba, modifica o rechaza.
6. Ferretero consulta seguimiento y reordena.

## Servicio tecnico

1. Servicio tecnico autorizado crea caso.
2. Registra maquina, cliente, falla, fotos y diagnostico.
3. Solicita repuestos.
4. Wulkan aprueba o cotiza repuestos.
5. Tecnico registra reparacion.
6. Caso se cierra con historial.

## Actualizacion de caso tecnico

1. Servicio tecnico u operador abre el caso.
2. Registra diagnostico, estado o repuesto solicitado.
3. Backend valida permisos.
4. Backend actualiza el caso.
5. Backend crea evento en `service_case_events`.
6. Backend registra auditoria.
7. Admin ve historial completo del caso.

## Pago manual

1. Usuario selecciona pago movil o transferencia.
2. Sistema crea intento de pago.
3. Usuario adjunta referencia y evidencia.
4. Operador autorizado valida.
5. Backend confirma o rechaza.
6. Auditoria registra usuario, fecha, origen y decision.

## Orden segura ecommerce

1. Usuario envia items del carrito.
2. Cloud Function valida usuario autenticado.
3. Backend lee productos desde Firestore.
4. Backend calcula subtotal y total en USD.
5. Backend detecta si la orden requiere cotizacion o validacion tecnica.
6. Backend crea orden y pago inicial.
7. Backend registra auditoria.
8. Admin puede revisar orden, items y pago.

## Alta de producto desde admin

1. Operador entra a Productos.
2. Crea producto con SKU, vertical, tipo, precio, stock y descripcion tecnica.
3. Define si requiere cotizacion, instalacion o validacion tecnica.
4. Producto queda como pendiente.
5. Admin autorizado aprueba publicacion.
6. Auditoria registra alta y aprobacion.

## Alta de vertical desde admin

1. Admin crea vertical comercial.
2. Define slug, pais operativo, tipos de producto y atributos iniciales.
3. La vertical queda pendiente o activa segun permiso.
4. Productos futuros usan esa vertical para filtros y ficha tecnica.

## Solicitud de proyecto tecnico

1. Cliente selecciona una vertical como iluminacion, energia solar o electricidad limpia.
2. Registra direccion, medidas y requerimiento.
3. Wulkan revisa la solicitud desde admin.
4. Wulkan asigna operador o instalador.
5. Se agenda visita o evaluacion.
6. Se vincula cotizacion tecnica.
7. El proyecto avanza a aprobado, instalacion, instalado y cerrado.

## Orden de compra B2B

1. Ferretero habilitado revisa catalogo B2B.
2. Selecciona productos, cantidades y fecha solicitada.
3. Sistema aplica condiciones B2B visibles para esa empresa.
4. La OC entra en revision Wulkan.
5. Operador revisa stock, minimo de compra y condiciones comerciales.
6. Wulkan aprueba, modifica o rechaza.
7. La OC pasa a preparacion, despacho y cierre.

## Solicitud de reposicion B2B

1. Ferretero solicita un producto aunque no exista stock inmediato.
2. Wulkan registra SKU, descripcion y cantidad requerida.
3. Wulkan responde con cotizacion o alternativa.
4. La solicitud puede convertirse en orden de compra.

## Busqueda de punto autorizado

1. Usuario abre puntos cercanos.
2. Filtra por retiro, ferretero, servicio tecnico o instalacion.
3. Sistema muestra puntos autorizados con servicios y cobertura.
4. Usuario revisa contacto, horario y ubicacion.
5. Usuario decide retirar, contactar o crear caso tecnico.

## Marketplace controlado

1. Empresa vendedora solicita acceso.
2. Wulkan revisa verticales solicitadas y datos de empresa.
3. Wulkan aprueba o rechaza la solicitud.
4. Empresa carga productos.
5. Wulkan revisa calidad, ficha tecnica, garantia y stock.
6. Producto se aprueba, rechaza o queda con cambios solicitados.
7. Wulkan mide ventas, cumplimiento e incidentes por vendedor.
