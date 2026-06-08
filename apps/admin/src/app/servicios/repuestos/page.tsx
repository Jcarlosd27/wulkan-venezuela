import { AdminShell } from "../../../components/admin-shell";
import { DataTable } from "../../../components/data-table";
import { ModuleActions } from "../../../components/module-actions";
import { StatusBadge } from "../../../components/status-badge";
import { adminRepository } from "../../../lib/repositories";

export default async function ServicePartsPage() {
  const serviceCases = await adminRepository.listServiceCases();
  const partRequests = serviceCases.flatMap((serviceCase) =>
    serviceCase.requestedParts.map((part) => ({
      serviceCase,
      part
    }))
  );

  return (
    <AdminShell
      title="Repuestos de servicio"
      description="Solicitudes de piezas vinculadas a diagnosticos y reparaciones."
      actionLabel="Volver"
    >
      <ModuleActions
        actions={[
          { label: "Casos tecnicos", href: "/servicios" },
          { label: "Crear caso", href: "/servicios/nuevo" }
        ]}
      />
      <DataTable columns={["Caso", "Cliente", "Repuesto", "Cantidad", "Decision operativa", "Estado"]}>
        {partRequests.map(({ serviceCase, part }) => (
          <tr key={`${serviceCase.id}-${part.sku ?? part.description}`}>
            <td>
              <a href={`/servicios/${serviceCase.id}`}>
                <strong>{serviceCase.id}</strong>
              </a>
              <small>{serviceCase.technicalServiceId}</small>
            </td>
            <td>{serviceCase.customerName}</td>
            <td>
              <strong>{part.sku ?? "Sin SKU"}</strong>
              <small>{part.description}</small>
            </td>
            <td>{part.quantity}</td>
            <td>
              <strong>reviewServicePartRequest</strong>
              <small>Aprobar o rechazar pieza con evento y auditoria.</small>
            </td>
            <td>
              <StatusBadge status={serviceCase.status} />
            </td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}
