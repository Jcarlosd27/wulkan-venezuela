# Modelo de datos MVP

## Colecciones Firestore iniciales

| Coleccion | Proposito |
| --- | --- |
| `users` | Perfil extendido de usuarios autenticados. |
| `companies` | Empresas vendedoras, ferreteros, servicios tecnicos e instaladores. |
| `company_users` | Relacion usuario-empresa y rol operativo. |
| `business_verticals` | Verticales comerciales configurables. |
| `categories` | Categorias por vertical. |
| `brands` | Marcas de productos. |
| `products` | Catalogo maestro. |
| `product_variants` | Variantes de producto. |
| `product_prices` | Precios publicos, B2B e historial. |
| `product_stock` | Stock por empresa o ubicacion. |
| `product_compatibilities` | Relaciones entre maquinas, repuestos y modelos. |
| `locations` | Puntos autorizados, retiro y servicios cercanos. |
| `orders` | Ordenes B2C. |
| `order_items` | Items de orden B2C. |
| `purchase_orders` | Ordenes B2B. |
| `purchase_order_items` | Items de orden B2B. |
| `service_cases` | Casos tecnicos. |
| `service_case_events` | Historial de casos tecnicos. |
| `quotes` | Cotizaciones comerciales o tecnicas. |
| `payments` | Intentos, evidencias y validaciones de pago. |
| `platform_fee_rules` | Reglas de comision futura. |
| `billing_periods` | Periodos de medicion y cobro. |
| `company_revenue_periods` | Facturacion por empresa. |
| `platform_charges` | Cargos de plataforma. |
| `audit_logs` | Auditoria de acciones sensibles. |
| `notifications` | Eventos notificados a usuarios. |
| `app_settings` | Tasa USD/VES y parametros operativos. |

## Convenciones

- `country` inicial: `VE`.
- `primaryCurrency`: `USD`.
- `secondaryCurrency`: `VES`.
- Toda accion sensible debe tener `createdBy`, `updatedBy`, `createdAt`, `updatedAt` o evento equivalente.
- Los pagos manuales requieren evidencia y confirmacion por operador autorizado.

## Estado actual de implementacion

Ya existen contratos TypeScript iniciales para:

- Usuarios, roles y permisos.
- Empresas y terminos comerciales.
- Verticales, atributos tecnicos y productos.
- Ordenes B2C y ordenes B2B.
- Pagos manuales y asistidos.
- Casos tecnicos.
- Cotizaciones.
- Ubicaciones autorizadas.
- Billing futuro y auditoria.

