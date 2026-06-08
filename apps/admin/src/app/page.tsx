import { WULKAN_PRIMARY_CURRENCY, WULKAN_SECONDARY_CURRENCY } from "@wulkan/shared";
import { AdminShell } from "../components/admin-shell";
import { StatusBadge } from "../components/status-badge";
import { getDashboardMetrics } from "../lib/admin-metrics";
import { adminRepository } from "../lib/repositories";

export default async function AdminHome() {
  const [verticals, products, companies, orders, purchaseOrders, serviceCases, quotes, payments, locations] =
    await Promise.all([
      adminRepository.listVerticals(),
      adminRepository.listProducts(),
      adminRepository.listCompanies(),
      adminRepository.listOrders(),
      adminRepository.listPurchaseOrders(),
      adminRepository.listServiceCases(),
      adminRepository.listQuotes(),
      adminRepository.listPayments(),
      adminRepository.listLocations()
    ]);
  const metrics = getDashboardMetrics({
    verticals,
    products,
    companies,
    orders,
    purchaseOrders,
    serviceCases,
    quotes,
    payments,
    locations
  });
  const alerts = [
    {
      label: "Pagos por validar",
      value: payments.filter((payment) => payment.status === "under_review").length,
      status: "payment_under_review"
    },
    {
      label: "Productos con stock critico",
      value: products.filter((product) => product.stock <= 5).length,
      status: "pending"
    },
    {
      label: "B2B en revision",
      value: purchaseOrders.filter((order) => order.status === "under_wulkan_review").length,
      status: "under_wulkan_review"
    },
    {
      label: "Casos tecnicos abiertos",
      value: serviceCases.filter((serviceCase) => serviceCase.status !== "closed").length,
      status: "diagnosed"
    }
  ];

  return (
    <AdminShell
      title="Dashboard operativo"
      description={`Moneda principal ${WULKAN_PRIMARY_CURRENCY}, referencia ${WULKAN_SECONDARY_CURRENCY}.`}
      actionLabel="Nueva accion"
    >
      <section className="grid">
        {metrics.map((metric) => (
          <article className="metric" key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <small>{metric.detail}</small>
          </article>
        ))}
      </section>

      <section className="split">
        <article className="panel">
          <div className="panelHeader">
            <h2>Alertas operativas</h2>
            <span>{alerts.length} focos</span>
          </div>
          <div className="alertList">
            {alerts.map((alert) => (
              <div className="alertRow" key={alert.label}>
                <div>
                  <strong>{alert.value}</strong>
                  <span>{alert.label}</span>
                </div>
                <StatusBadge status={alert.status} />
              </div>
            ))}
          </div>
        </article>

        <article className="panel">
          <div className="panelHeader">
            <h2>Empresas activas</h2>
            <span>{companies.length} registros</span>
          </div>
          <div className="roleList">
            {companies.map((company) => (
              <span key={company.id}>{company.commercialName}</span>
            ))}
          </div>
        </article>
      </section>
    </AdminShell>
  );
}
