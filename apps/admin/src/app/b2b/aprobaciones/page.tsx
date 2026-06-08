import { formatUsd } from "@wulkan/shared";
import { AdminShell } from "../../../components/admin-shell";
import { DataTable } from "../../../components/data-table";
import { ModuleActions } from "../../../components/module-actions";
import { StatusBadge } from "../../../components/status-badge";
import { adminRepository } from "../../../lib/repositories";

export default async function B2BApprovalsPage() {
  const [companies, purchaseOrders] = await Promise.all([
    adminRepository.listCompanies(),
    adminRepository.listPurchaseOrders()
  ]);
  const pendingOrders = purchaseOrders.filter((order) =>
    ["submitted", "under_wulkan_review", "modified"].includes(order.status)
  );

  return (
    <AdminShell
      title="Aprobaciones B2B"
      description="Revision operativa de ordenes de compra antes de preparacion o despacho."
      actionLabel="Volver"
    >
      <ModuleActions
        actions={[
          { label: "Ordenes B2B", href: "/b2b" },
          { label: "Reposicion", href: "/b2b/reposicion" }
        ]}
      />
      <DataTable columns={["Orden", "Empresa", "Total", "Revision", "Decision operativa", "Estado"]}>
        {pendingOrders.map((order) => {
          const company = companies.find((item) => item.id === order.requesterCompanyId);

          return (
            <tr key={order.id}>
              <td>
                <a href={`/b2b/${order.id}`}>
                  <strong>{order.id}</strong>
                </a>
                <small>{order.notes ?? "Sin notas del comprador"}</small>
              </td>
              <td>{company?.commercialName ?? order.requesterCompanyId}</td>
              <td>{formatUsd(order.total.amount)}</td>
              <td>{order.reviewedAt ?? "Pendiente"}</td>
              <td>
                <strong>reviewPurchaseOrder</strong>
                <small>Aprobar, modificar o rechazar con auditoria.</small>
              </td>
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
