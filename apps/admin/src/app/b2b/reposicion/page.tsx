import { AdminShell } from "../../../components/admin-shell";
import { DataTable } from "../../../components/data-table";
import { StatusBadge } from "../../../components/status-badge";
import { adminRepository } from "../../../lib/repositories";

export default async function ReplenishmentPage() {
  const [requests, companies] = await Promise.all([
    adminRepository.listReplenishmentRequests(),
    adminRepository.listCompanies()
  ]);

  return (
    <AdminShell title="Solicitudes de reposicion" description="Productos requeridos por ferreteros, incluso sin stock inmediato.">
      <DataTable columns={["Solicitud", "Ferretero", "SKU", "Cantidad", "Cotizacion", "Estado"]}>
        {requests.map((request) => {
          const company = companies.find((item) => item.id === request.requesterCompanyId);

          return (
            <tr key={request.id}>
              <td>
                <strong>{request.id}</strong>
                <small>{request.description}</small>
              </td>
              <td>{company?.commercialName ?? request.requesterCompanyId}</td>
              <td>{request.sku ?? "Sin SKU"}</td>
              <td>{request.requestedQuantity}</td>
              <td>{request.quoteId ?? "Sin cotizacion"}</td>
              <td>
                <StatusBadge status={request.status} />
              </td>
            </tr>
          );
        })}
      </DataTable>
    </AdminShell>
  );
}

