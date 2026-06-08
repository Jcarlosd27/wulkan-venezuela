import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { ModuleActions } from "../../components/module-actions";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";

export default async function UsersPage() {
  const users = await adminRepository.listUsers();

  return (
    <AdminShell
      title="Usuarios y roles"
      description="Estructura inicial de accesos, permisos y estados de habilitacion."
      actionLabel="Invitar usuario"
    >
      <ModuleActions actions={[{ label: "Estado Auth", href: "/usuarios/auth" }]} />
      <DataTable columns={["Usuario", "Rol", "Empresa", "Permisos", "Ultimo acceso", "Estado"]}>
        {users.map((user) => (
          <tr key={user.id}>
            <td>
              <strong>{user.name}</strong>
              <small>{user.email}</small>
            </td>
            <td>{user.role}</td>
            <td>{user.companyId ?? "Wulkan"}</td>
            <td>{user.permissions.length}</td>
            <td>{user.lastLoginAt ?? "Sin acceso"}</td>
            <td>
              <StatusBadge status={user.status} />
            </td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}
