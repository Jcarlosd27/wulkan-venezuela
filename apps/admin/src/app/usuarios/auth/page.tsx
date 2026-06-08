import { AdminShell } from "../../../components/admin-shell";
import { DataTable } from "../../../components/data-table";
import { ModuleActions } from "../../../components/module-actions";
import { StatusBadge } from "../../../components/status-badge";
import { getAdminSession } from "../../../lib/auth";
import { adminNavItems, canAccessNavItem } from "../../../lib/permissions";
import { adminRepository } from "../../../lib/repositories";

export default async function AuthStatusPage() {
  const [session, users] = await Promise.all([getAdminSession(), adminRepository.listUsers()]);
  const privilegedUsers = users.filter((user) => ["super_admin", "wulkan_admin", "wulkan_operator"].includes(user.role));

  return (
    <AdminShell
      title="Estado Auth"
      description="Preparacion de Firebase Auth, roles, permisos y custom claims."
      actionLabel="Volver"
    >
      <ModuleActions actions={[{ label: "Usuarios", href: "/usuarios" }]} />
      <section className="panel compactPanel">
        <div className="panelHeader">
          <div>
            <h2>Sesion actual</h2>
            <p className="bodyCopy">
              El modo mock mantiene el admin navegable. El modo Firebase queda listo para validar ID token,
              claims y permisos reales cuando conectemos Auth.
            </p>
          </div>
          <StatusBadge status={session.claimsReady ? "active" : "pending"} />
        </div>
        <dl className="detailList">
          <div>
            <dt>Modo</dt>
            <dd>{session.authMode}</dd>
          </div>
          <div>
            <dt>Sesion</dt>
            <dd>{session.signedIn ? "Activa" : "Pendiente"}</dd>
          </div>
          <div>
            <dt>Usuario</dt>
            <dd>{session.user.name}</dd>
          </div>
          <div>
            <dt>Rol</dt>
            <dd>{session.user.role}</dd>
          </div>
        </dl>
      </section>
      <section className="panel">
        <div className="panelHeader">
          <div>
            <h2>Custom claims preparados</h2>
            <p className="bodyCopy">La Cloud Function `setUserRoleClaims` asigna rol, empresa y permisos.</p>
          </div>
        </div>
        <DataTable columns={["Usuario", "Rol claim", "Empresa", "Permisos", "Estado"]}>
          {privilegedUsers.map((user) => (
            <tr key={user.id}>
              <td>
                <strong>{user.name}</strong>
                <small>{user.email}</small>
              </td>
              <td>{user.role}</td>
              <td>{user.companyId ?? "Wulkan"}</td>
              <td>{user.permissions.length}</td>
              <td>
                <StatusBadge status={user.status} />
              </td>
            </tr>
          ))}
        </DataTable>
      </section>
      <section className="panel">
        <div className="panelHeader">
          <div>
            <h2>Matriz de acceso admin</h2>
            <p className="bodyCopy">Cada modulo declara permisos requeridos y roles restringidos.</p>
          </div>
        </div>
        <DataTable columns={["Modulo", "Ruta", "Permisos", "Roles", "Sesion actual"]}>
          {adminNavItems.map((item) => (
            <tr key={item.href}>
              <td>
                <strong>{item.label}</strong>
              </td>
              <td>{item.href}</td>
              <td>{item.requiredPermissions.length ? item.requiredPermissions.join(", ") : "Sin permiso requerido"}</td>
              <td>{item.allowedRoles?.join(", ") ?? "Cualquier rol con permiso"}</td>
              <td>
                <StatusBadge status={canAccessNavItem(session, item) ? "active" : "pending"} />
              </td>
            </tr>
          ))}
        </DataTable>
      </section>
    </AdminShell>
  );
}
