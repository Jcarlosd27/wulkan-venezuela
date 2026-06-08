import { formatUsd } from "@wulkan/shared";
import { normalizeSearchText } from "@wulkan/shared";
import Link from "next/link";
import { AdminShell } from "../../components/admin-shell";
import { Breadcrumb } from "../../components/breadcrumb";
import { DataTable } from "../../components/data-table";
import { ModuleActions } from "../../components/module-actions";
import { StatusBadge } from "../../components/status-badge";
import { EmptyState } from "../../components/empty-state";
import { avalonGardenImportSummary } from "../../lib/avalon-garden-catalog";
import { adminRepository } from "../../lib/repositories";

interface ProductsPageProps {
  searchParams?: Promise<{
    q?: string;
    vertical?: string;
    category?: string;
    status?: string;
  }>;
}

export default async function ProductsPage({ searchParams }: ProductsPageProps) {
  const params = (await searchParams) ?? {};
  const [products, verticals, stockRows, compatibilities] = await Promise.all([
    adminRepository.listProducts(),
    adminRepository.listVerticals(),
    adminRepository.listProductStock(),
    adminRepository.listProductCompatibilities()
  ]);
  const query = normalizeSearchText(params.q ?? "");
  const filteredProducts = products.filter((product) => {
    const compatibilityMatches = compatibilities.some((item) => {
      const belongsToProduct = item.sourceProductId === product.id || item.compatibleProductId === product.id;
      const model = normalizeSearchText(`${item.machineModel ?? ""} ${item.engineModel ?? ""}`);

      return belongsToProduct && model.includes(query);
    });
    const text = normalizeSearchText(`${product.title} ${product.sku} ${product.description ?? ""}`);
    const matchesQuery = !query || text.includes(query) || compatibilityMatches;
    const selectedCategory = params.category ?? params.vertical;
    const matchesVertical = !selectedCategory || product.verticalId === selectedCategory;
    const matchesStatus = !params.status || product.status === params.status;

    return matchesQuery && matchesVertical && matchesStatus;
  });

  return (
    <AdminShell
      title="Productos"
      description="Catálogo ecommerce con imágenes, precios, stock y validación técnica."
      actionLabel="Crear producto"
    >
      <Breadcrumb
        items={[
          { label: "Dashboard", href: "/" },
          { label: "Productos" }
        ]}
      />

      <section className="importBanner">
        <div>
          <strong>✓ Avalon Jardinería y Bosque</strong>
          <span>
            {avalonGardenImportSummary.productCount} productos importados desde CLP a USD con tasa{" "}
            {avalonGardenImportSummary.clpToUsdRate}. Editar precios desde historial antes de publicar.
          </span>
        </div>
        <a href={avalonGardenImportSummary.sourceUrl} target="_blank" rel="noopener noreferrer">
          Ver fuente ↗
        </a>
      </section>
      <ModuleActions actions={[{ label: "Nuevo producto", href: "/productos/nuevo" }]} />
      <form className="filterBar">
        <input name="q" defaultValue={params.q ?? ""} placeholder="Buscar por nombre, SKU o modelo compatible" />
        <select name="category" defaultValue={params.category ?? params.vertical ?? ""} aria-label="Filtrar por categoría">
          <option value="">Todas las categorías</option>
          {verticals.map((vertical) => (
            <option value={vertical.id} key={vertical.id}>
              {vertical.name}
            </option>
          ))}
        </select>
        <select name="status" defaultValue={params.status ?? ""} aria-label="Filtrar por estado">
          <option value="">Todos los estados</option>
          <option value="active">Activo</option>
          <option value="pending">Pendiente</option>
          <option value="inactive">Inactivo</option>
        </select>
        <button type="submit">Filtrar</button>
      </form>

      {filteredProducts.length === 0 ? (
        <EmptyState
          icon="📦"
          title="No hay productos"
          description={query ? "Intenta ajustar tu búsqueda o filtros" : "Comienza agregando el primer producto"}
          action={<Link href="/productos/nuevo" className="btnPrimary">Crear producto</Link>}
        />
      ) : (
        <DataTable columns={["Producto", "SKU", "Categoría", "Precio", "Stock", "Compatibilidad", "Estado"]}>
          {filteredProducts.map((product) => {
            const vertical = verticals.find((item) => item.id === product.verticalId);
            const stock = stockRows.find((item) => item.productId === product.id);
            const compatibilityCount = compatibilities.filter(
              (item) => item.sourceProductId === product.id || item.compatibleProductId === product.id
            ).length;

            return (
              <tr key={product.id}>
                <td>
                  <div className="productCell">
                    {product.imageUrls[0] ? (
                      <img className="productThumb" src={product.imageUrls[0]} alt="" />
                    ) : (
                      <span className="productThumb productThumbEmpty">Sin imagen</span>
                    )}
                    <div>
                      <a href={`/productos/${product.id}`}>
                        <strong>{product.title}</strong>
                      </a>
                      <small>{product.description}</small>
                    </div>
                  </div>
                </td>
                <td>{product.sku}</td>
                <td>{vertical?.name ?? product.verticalId}</td>
                <td>
                  <strong>{product.publicPrice ? formatUsd(product.publicPrice.amount) : "Cotización"}</strong>
                  <small>{product.b2bPrice ? `B2B ${formatUsd(product.b2bPrice.amount)}` : "Sin precio B2B"}</small>
                </td>
                <td>
                  <strong>{stock?.available ?? product.stock}</strong>
                  <small>Reservado {stock?.reserved ?? 0}</small>
                </td>
                <td>{compatibilityCount ? `${compatibilityCount} relación(es)` : "Sin relaciones"}</td>
                <td>
                  <StatusBadge status={product.status} />
                </td>
              </tr>
            );
          })}
        </DataTable>
      )}
    </AdminShell>
  );
}
