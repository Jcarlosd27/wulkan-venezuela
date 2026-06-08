import { notFound } from "next/navigation";
import { formatUsd } from "@wulkan/shared";
import { AdminShell } from "../../../components/admin-shell";
import { DataTable } from "../../../components/data-table";
import { StatusBadge } from "../../../components/status-badge";
import { adminRepository } from "../../../lib/repositories";

interface OrderDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function OrderDetailPage({ params }: OrderDetailPageProps) {
  const { id } = await params;
  const [order, payments] = await Promise.all([adminRepository.getOrder(id), adminRepository.listPayments()]);

  if (!order) {
    notFound();
  }

  const payment = payments.find((item) => item.id === order.paymentId);

  return (
    <AdminShell title={order.id} description="Detalle operativo de orden, pago e items." actionLabel="Cambiar estado">
      <section className="detailGrid">
        <article className="panel">
          <div className="panelHeader">
            <h2>Resumen orden</h2>
            <StatusBadge status={order.status} />
          </div>
          <dl className="detailList">
            <div>
              <dt>Cliente</dt>
              <dd>{order.customerId}</dd>
            </div>
            <div>
              <dt>Total</dt>
              <dd>{formatUsd(order.total.amount)}</dd>
            </div>
            <div>
              <dt>Tasa</dt>
              <dd>{order.exchangeRateUsdVes ? `${order.exchangeRateUsdVes} VES/USD` : "Sin tasa"}</dd>
            </div>
            <div>
              <dt>Notas</dt>
              <dd>{order.notes ?? "Sin notas"}</dd>
            </div>
          </dl>
        </article>

        <article className="panel">
          <div className="panelHeader">
            <h2>Pago</h2>
            <StatusBadge status={payment?.status ?? "pending"} />
          </div>
          <dl className="detailList">
            <div>
              <dt>ID pago</dt>
              <dd>{order.paymentId ?? "Sin pago"}</dd>
            </div>
            <div>
              <dt>Metodo</dt>
              <dd>{payment?.method ?? "No definido"}</dd>
            </div>
            <div>
              <dt>Referencia</dt>
              <dd>{payment?.referenceNumber ?? "Sin referencia"}</dd>
            </div>
            <div>
              <dt>Monto</dt>
              <dd>{payment ? formatUsd(payment.amountUsd) : "Sin monto"}</dd>
            </div>
          </dl>
        </article>
      </section>

      <DataTable columns={["SKU", "Producto", "Cantidad", "Unitario", "Total"]}>
        {order.items.map((item) => (
          <tr key={`${item.productId}-${item.sku}`}>
            <td>{item.sku}</td>
            <td>{item.title}</td>
            <td>{item.quantity}</td>
            <td>{formatUsd(item.unitPrice.amount)}</td>
            <td>{formatUsd(item.total.amount)}</td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}

