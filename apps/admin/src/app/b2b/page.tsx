import { formatUsd } from "@wulkan/shared";
import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { ModuleActions } from "../../components/module-actions";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";

export default async function B2BPage() {
  const [companies, purchaseOrders] = await Promise.all([
    adminRepository.listCompanies(),
    adminRepository.listPurchaseOrders()
  ]);

  return (
    <AdminShell title="Ordenes B2B" description="Solicitudes de ferreteros y compradores autorizados." actionLabel="Nueva OC">
      <ModuleActions
        actions={[
          { label: "Nueva OC", href: "/b2b/nueva" },
          { label: "Reposicion", href: "/b2b/reposicion" },
          { label: "Aprobaciones", href: "/b2b/aprobaciones" }
        ]}
      />
      <DataTable columns={["Orden", "Ferretero", "Items", "Total", "Entrega", "Estado"]}>
        {purchaseOrders.map((order) => {
          const company = companies.find((item) => item.id === order.requesterCompanyId);

          return (
            <tr key={order.id}>
              <td>
                <a href={`/b2b/${order.id}`}>
                  <strong>{order.id}</strong>
                </a>
                <small>{order.requesterUserId}</small>
              </td>
              <td>{company?.commercialName ?? order.requesterCompanyId}</td>
              <td>{order.items.length}</td>
              <td>{formatUsd(order.total.amount)}</td>
              <td>{order.requestedDeliveryDate ?? "Sin fecha"}</td>
              <td>
                <StatusBadge status={order.status} />
              </td>
            </tr>
          );
        })}
      </DataTable>
    </AdminShell>
  );
}
