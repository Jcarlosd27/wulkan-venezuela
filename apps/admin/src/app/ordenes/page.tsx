import { formatUsd } from "@wulkan/shared";
import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { ModuleActions } from "../../components/module-actions";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";

export default async function OrdersPage() {
  const orders = await adminRepository.listOrders();

  return (
    <AdminShell
      title="Ordenes B2C"
      description="Seguimiento de compras de clientes finales y validacion operativa."
      actionLabel="Registrar orden"
    >
      <ModuleActions actions={[{ label: "Nueva orden B2C", href: "/ordenes/nueva" }, { label: "Ventas", href: "/ventas" }]} />
      <DataTable columns={["Orden", "Cliente", "Items", "Total", "Pago", "Estado"]}>
        {orders.map((order) => (
          <tr key={order.id}>
            <td>
              <a href={`/ordenes/${order.id}`}>
                <strong>{order.id}</strong>
              </a>
              <small>{order.paymentId}</small>
            </td>
            <td>{order.customerId}</td>
            <td>{order.items.length}</td>
            <td>{formatUsd(order.total.amount)}</td>
            <td>{order.exchangeRateUsdVes ? `${order.exchangeRateUsdVes} VES/USD` : "Sin tasa"}</td>
            <td>
              <StatusBadge status={order.status} />
            </td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}
