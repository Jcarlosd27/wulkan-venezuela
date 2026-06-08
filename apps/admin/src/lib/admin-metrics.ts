import type {
  AuthorizedLocation,
  BusinessVertical,
  Company,
  Order,
  Payment,
  Product,
  PurchaseOrder,
  Quote,
  ServiceCase
} from "@wulkan/domain";

export interface DashboardMetric {
  label: string;
  value: string;
  detail: string;
}

interface DashboardMetricInput {
  verticals: BusinessVertical[];
  products: Product[];
  companies: Company[];
  orders: Order[];
  purchaseOrders: PurchaseOrder[];
  serviceCases: ServiceCase[];
  quotes: Quote[];
  payments: Payment[];
  locations: AuthorizedLocation[];
}

export function getDashboardMetrics({
  verticals,
  products,
  companies,
  orders,
  purchaseOrders,
  serviceCases,
  quotes,
  payments,
  locations
}: DashboardMetricInput): DashboardMetric[] {
  const lowStock = products.filter((product) => product.stock <= 5).length;
  const pendingPayments = payments.filter((payment) => payment.status === "under_review").length;
  const openServiceCases = serviceCases.filter((serviceCase) => serviceCase.status !== "closed").length;

  return [
    { label: "Categorias", value: String(verticals.length), detail: "Configuradas para Venezuela" },
    { label: "Productos", value: String(products.length), detail: `${lowStock} con stock critico o cero` },
    { label: "Empresas", value: String(companies.length), detail: "Vendedores, ferreteros y red tecnica" },
    { label: "Ordenes B2C", value: String(orders.length), detail: `${pendingPayments} pago por validar` },
    { label: "Ordenes B2B", value: String(purchaseOrders.length), detail: "Revision operativa Wulkan" },
    { label: "Casos tecnicos", value: String(openServiceCases), detail: "Abiertos o en diagnostico" },
    { label: "Cotizaciones", value: String(quotes.length), detail: "Solicitudes comerciales o tecnicas" },
    { label: "Puntos", value: String(locations.length), detail: "Red fisica autorizada" }
  ];
}
