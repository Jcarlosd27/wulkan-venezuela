import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { ModuleActions } from "../../components/module-actions";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";

export default async function ServicesPage() {
  const serviceCases = await adminRepository.listServiceCases();

  return (
    <AdminShell
      title="Casos tecnicos"
      description="Diagnosticos, repuestos solicitados, reparaciones y garantia."
      actionLabel="Crear caso"
    >
      <ModuleActions
        actions={[
          { label: "Crear caso", href: "/servicios/nuevo" },
          { label: "Repuestos", href: "/servicios/repuestos" }
        ]}
      />
      <DataTable columns={["Caso", "Cliente", "Maquina", "Repuestos", "Garantia", "Estado"]}>
        {serviceCases.map((serviceCase) => (
          <tr key={serviceCase.id}>
            <td>
              <a href={`/servicios/${serviceCase.id}`}>
                <strong>{serviceCase.id}</strong>
              </a>
              <small>{serviceCase.technicalServiceId}</small>
            </td>
            <td>{serviceCase.customerName}</td>
            <td>{serviceCase.machineId ?? "Sin maquina"}</td>
            <td>{serviceCase.requestedParts.length}</td>
            <td>{serviceCase.warrantyRelated ? "Si" : "No"}</td>
            <td>
              <StatusBadge status={serviceCase.status} />
            </td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}
