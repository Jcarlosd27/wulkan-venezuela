# Roles y permisos

## Roles iniciales

| Rol | Alcance |
| --- | --- |
| `super_admin` | Control total del sistema. |
| `wulkan_admin` | Administracion Wulkan y configuracion de negocio. |
| `wulkan_operator` | Operacion diaria, ordenes, pagos, cotizaciones y casos. |
| `company_owner` | Gestion de empresa vendedora. |
| `company_seller` | Gestion comercial limitada de empresa. |
| `hardware_store_owner` | Compras B2B y cuenta ferretera. |
| `hardware_store_buyer` | Creacion y seguimiento de ordenes B2B. |
| `technical_service_owner` | Gestion de servicio tecnico autorizado. |
| `technical_service_operator` | Casos tecnicos y solicitudes de repuestos. |
| `installer` | Proyectos e instalaciones asignadas. |
| `customer` | Compra, cotizacion, soporte y seguimiento. |

## Permisos base

- `catalog.view`
- `product.create`
- `product.edit`
- `product.approve`
- `price.change`
- `order.view`
- `order.status.change`
- `purchase_order.create`
- `purchase_order.approve`
- `payment.view`
- `payment.confirm`
- `service_case.create`
- `service_case.update`
- `service_case.close`
- `vertical.manage`
- `technical_attribute.manage`
- `location.manage`
- `report.view`
- `user.manage`
- `permission.manage`

## Regla critica

El frontend solo adapta la experiencia. La autorizacion real se valida en backend y queda registrada en auditoria.

