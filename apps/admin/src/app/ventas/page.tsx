import { formatUsd } from "@wulkan/shared";
import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { ModuleActions } from "../../components/module-actions";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";

function sum(values: number[]): number {
  return Number(values.reduce((total, value) => total + value, 0).toFixed(2));
}

function salePriority(status: string): number {
  if (["payment_under_review", "under_wulkan_review", "pending_payment", "submitted"].includes(status)) {
    return 0;
  }

  if (["paid", "approved", "preparing"].includes(status)) {
    return 1;
  }

  return 2;
}

export default async function SalesPage() {
  const [orders, purchaseOrders, payments, companies] = await Promise.all([
    adminRepository.listOrders(),
    adminRepository.listPurchaseOrders(),
    adminRepository.listPayments(),
    adminRepository.listCompanies()
  ]);

  const b2cRevenue = sum(orders.map((order) => order.total.amount));
  const b2bRevenue = sum(purchaseOrders.map((order) => order.total.amount));
  const confirmedPayments = payments.filter((payment) => payment.status === "confirmed");
  const pendingPayments = payments.filter((payment) => ["pending", "under_review"].includes(payment.status));
  const salesRows = [
    ...orders.map((order) => {
      const payment = payments.find((item) => item.id === order.paymentId);

      return {
        id: order.id,
        channel: "B2C",
        customer: order.customerId,
        items: order.items.length,
        total: order.total.amount,
        paymentStatus: payment?.status ?? "pending",
        status: order.status,
        href: `/ordenes/${order.id}`,
        nextStep: order.status === "payment_under_review" ? "Validar pago" : "Gestionar entrega"
      };
    }),
    ...purchaseOrders.map((order) => {
      const company = companies.find((item) => item.id === order.requesterCompanyId);

      return {
        id: order.id,
        channel: "B2B",
        customer: company?.commercialName ?? order.requesterCompanyId,
        items: order.items.length,
        total: order.total.amount,
        paymentStatus: order.status === "approved" ? "confirmed" : "pending",
        status: order.status,
        href: `/b2b/${order.id}`,
        nextStep: order.status === "under_wulkan_review" ? "Revisar condiciones" : "Preparar despacho"
      };
    })
  ].sort((left, right) => salePriority(left.status) - salePriority(right.status));

  return (
    <AdminShell
      title="Ventas"
      description="Vista comercial unificada para ordenes B2C, ordenes B2B, pagos y seguimiento operativo."
      actionLabel="Nueva venta"
    >
      <ModuleActions
        actions={[
          { label: "Nueva OC B2B", href: "/b2b/nueva" },
          { label: "Ordenes B2C", href: "/ordenes" },
          { label: "Pagos", href: "/pagos" },
          { label: "Reportes", href: "/reportes" }
        ]}
      />

      <section className="grid">
        <article className="metric">
          <small>Venta B2C</small>
          <strong>{formatUsd(b2cRevenue)}</strong>
          <span>{orders.length} orden(es)</span>
        </article>
        <article className="metric">
          <small>Venta B2B</small>
          <strong>{formatUsd(b2bRevenue)}</strong>
          <span>{purchaseOrders.length} orden(es)</span>
        </article>
        <article className="metric">
          <small>Pagos confirmados</small>
          <strong>{formatUsd(sum(confirmedPayments.map((payment) => payment.amountUsd)))}</strong>
          <span>{confirmedPayments.length} pago(s)</span>
        </article>
        <article className="metric">
          <small>Pendiente por cobrar</small>
          <strong>{formatUsd(sum(pendingPayments.map((payment) => payment.amountUsd)))}</strong>
          <span>{pendingPayments.length} pago(s) por revisar</span>
        </article>
      </section>

      <article className="panel">
        <div className="panelHeader">
          <h2>Pipeline comercial</h2>
          <span>{salesRows.length} movimiento(s)</span>
        </div>
        <DataTable columns={["Venta", "Canal", "Cliente", "Items", "Total", "Pago", "Estado", "Siguiente paso"]}>
          {salesRows.map((sale) => (
            <tr key={`${sale.channel}-${sale.id}`}>
              <td>
                <a href={sale.href}>
                  <strong>{sale.id}</strong>
                </a>
              </td>
              <td>{sale.channel}</td>
              <td>{sale.customer}</td>
              <td>{sale.items}</td>
              <td>{formatUsd(sale.total)}</td>
              <td>
                <StatusBadge status={sale.paymentStatus} />
              </td>
              <td>
                <StatusBadge status={sale.status} />
              </td>
              <td>{sale.nextStep}</td>
            </tr>
          ))}
        </DataTable>
      </article>
    </AdminShell>
  );
}
