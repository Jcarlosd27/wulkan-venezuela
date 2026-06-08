import type { Permission, UserRole } from "@wulkan/domain";
import type { AdminSession } from "./auth";

export interface AdminNavItem {
  label: string;
  href: string;
  requiredPermissions: Permission[];
  allowedRoles?: UserRole[];
}

export const adminNavItems: AdminNavItem[] = [
  { label: "Dashboard", href: "/", requiredPermissions: [] },
  { label: "Categorias", href: "/verticales", requiredPermissions: ["vertical.manage"] },
  { label: "Productos", href: "/productos", requiredPermissions: ["catalog.view"] },
  { label: "Empresas", href: "/empresas", requiredPermissions: ["user.manage"] },
  { label: "Ventas", href: "/ventas", requiredPermissions: ["order.view", "payment.view"] },
  { label: "Ordenes B2C", href: "/ordenes", requiredPermissions: ["order.view"] },
  { label: "Ordenes B2B", href: "/b2b", requiredPermissions: ["purchase_order.approve"] },
  { label: "Casos tecnicos", href: "/servicios", requiredPermissions: ["service_case.update"] },
  { label: "Proyectos", href: "/proyectos", requiredPermissions: ["service_case.update"] },
  { label: "Cotizaciones", href: "/cotizaciones", requiredPermissions: ["catalog.view"] },
  { label: "Pagos", href: "/pagos", requiredPermissions: ["payment.view"] },
  { label: "Ubicaciones", href: "/ubicaciones", requiredPermissions: ["location.manage"] },
  { label: "Usuarios", href: "/usuarios", requiredPermissions: ["user.manage"] },
  { label: "Reportes", href: "/reportes", requiredPermissions: ["report.view"] },
  { label: "Marketplace", href: "/marketplace", requiredPermissions: ["product.approve"] },
  { label: "Anuncios app", href: "/anuncios", requiredPermissions: ["catalog.view", "permission.manage"] },
  { label: "Billing", href: "/billing", requiredPermissions: ["report.view"], allowedRoles: ["super_admin", "wulkan_admin"] },
  { label: "Auditoria", href: "/auditoria", requiredPermissions: ["permission.manage"], allowedRoles: ["super_admin", "wulkan_admin"] },
  { label: "Settings", href: "/settings", requiredPermissions: ["permission.manage"], allowedRoles: ["super_admin", "wulkan_admin"] }
];

export function hasAnyPermission(session: AdminSession, requiredPermissions: Permission[]): boolean {
  if (session.user.role === "super_admin") {
    return true;
  }

  if (requiredPermissions.length === 0) {
    return true;
  }

  return requiredPermissions.some((permission) => session.user.permissions.includes(permission));
}

export function canAccessNavItem(session: AdminSession, item: AdminNavItem): boolean {
  const roleAllowed = !item.allowedRoles?.length || item.allowedRoles.includes(session.user.role as UserRole);

  return roleAllowed && hasAnyPermission(session, item.requiredPermissions);
}

export function getVisibleNavItems(session: AdminSession): AdminNavItem[] {
  return adminNavItems.filter((item) => canAccessNavItem(session, item));
}
