import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { adminRepository } from "../../lib/repositories";

export default async function AuditPage() {
  const logs = await adminRepository.listAuditLogs();

  return (
    <AdminShell
      title="Auditoria"
      description="Registro inicial de acciones sensibles y cambios operativos."
    >
      <DataTable columns={["Evento", "Actor", "Destino", "Origen", "Fecha"]}>
        {logs.map((log) => (
          <tr key={log.id}>
            <td>
              <strong>{log.action}</strong>
              <small>{log.id}</small>
            </td>
            <td>{log.actorUserId}</td>
            <td>
              {log.targetCollection}/{log.targetId}
            </td>
            <td>{log.origin}</td>
            <td>{log.createdAt}</td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}

