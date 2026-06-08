import { AdminShell } from "../../../components/admin-shell";
import { DataTable } from "../../../components/data-table";
import { StatusBadge } from "../../../components/status-badge";
import { adminRepository } from "../../../lib/repositories";

export default async function MarketplaceProductsPage() {
  const [approvals, products, companies] = await Promise.all([
    adminRepository.listProductApprovals(),
    adminRepository.listProducts(),
    adminRepository.listCompanies()
  ]);

  return (
    <AdminShell
      title="Aprobacion de productos"
      description="Control de calidad para productos de empresas vendedoras antes de publicar."
      actionLabel="Solicitar cambios"
    >
      <DataTable columns={["Producto", "Vendedor", "Cambios requeridos", "Notas", "Estado"]}>
        {approvals.map((approval) => {
          const product = products.find((item) => item.id === approval.productId);
          const seller = companies.find((item) => item.id === approval.sellerId);

          return (
            <tr key={approval.id}>
              <td>
                <strong>{product?.title ?? approval.productId}</strong>
                <small>{product?.sku ?? approval.productId}</small>
              </td>
              <td>{seller?.commercialName ?? approval.sellerId}</td>
              <td>{approval.requiredChanges?.join(", ") ?? "Sin cambios"}</td>
              <td>{approval.notes ?? "Sin notas"}</td>
              <td>
                <StatusBadge status={approval.status} />
              </td>
            </tr>
          );
        })}
      </DataTable>
    </AdminShell>
  );
}

