import { notFound } from "next/navigation";
import { formatUsd } from "@wulkan/shared";
import { AdminShell } from "../../../components/admin-shell";
import { DataTable } from "../../../components/data-table";
import { StatusBadge } from "../../../components/status-badge";
import { adminRepository } from "../../../lib/repositories";

interface PurchaseOrderDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function PurchaseOrderDetailPage({ params }: PurchaseOrderDetailPageProps) {
  const { id } = await params;
  const [order, companies] = await Promise.all([adminRepository.getPurchaseOrder(id), adminRepository.listCompanies()]);

  if (!order) {
    notFound();
  }

  const company = companies.find((item) => item.id === order.requesterCompanyId);

  return (
    <AdminShell title={order.id} description="Detalle operativo de orden de compra B2B." actionLabel="Revisar OC">
      <section className="detailGrid">
        <article className="panel">
          <div className="panelHeader">
            <h2>Ferretero</h2>
            <StatusBadge status={company?.status ?? "pending"} />
          </div>
          <dl className="detailList">
            <div>
              <dt>Empresa</dt>
              <dd>{company?.commercialName ?? order.requesterCompanyId}</dd>
            </div>
            <div>
              <dt>Descuento</dt>
              <dd>{company?.commercialTerms.defaultDiscountPercent ?? 0}%</dd>
            </div>
            <div>
              <dt>Minimo compra</dt>
              <dd>{formatUsd(company?.commercialTerms.minimumPurchaseUsd ?? 0)}</dd>
            </div>
            <div>
              <dt>Credito</dt>
              <dd>{company?.commercialTerms.creditEnabled ? `${company.commercialTerms.paymentTermsDays ?? 0} dias` : "No habilitado"}</dd>
            </div>
          </dl>
        </article>

        <article className="panel">
          <div className="panelHeader">
            <h2>Estado OC</h2>
            <StatusBadge status={order.status} />
          </div>
          <dl className="detailList">
            <div>
              <dt>Total</dt>
              <dd>{formatUsd(order.total.amount)}</dd>
            </div>
            <div>
              <dt>Entrega solicitada</dt>
              <dd>{order.requestedDeliveryDate ?? "Sin fecha"}</dd>
            </div>
            <div>
              <dt>Aprobado por</dt>
              <dd>{order.approvedBy ?? "Pendiente"}</dd>
            </div>
            <div>
              <dt>Notas</dt>
              <dd>{order.notes ?? "Sin notas"}</dd>
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

