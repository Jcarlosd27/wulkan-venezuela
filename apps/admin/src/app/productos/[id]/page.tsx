import { notFound } from "next/navigation";
import { formatUsd } from "@wulkan/shared";
import { AdminShell } from "../../../components/admin-shell";
import { FormField } from "../../../components/form-field";
import { StatusBadge } from "../../../components/status-badge";
import { adminRepository } from "../../../lib/repositories";
import { updateProductPricingAction } from "../actions";

interface ProductDetailPageProps {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ status?: string }>;
}

export default async function ProductDetailPage({ params, searchParams }: ProductDetailPageProps) {
  const { id } = await params;
  const query = (await searchParams) ?? {};
  const [product, verticals, variants, prices, stockRows, compatibilities] = await Promise.all([
    adminRepository.getProduct(id),
    adminRepository.listVerticals(),
    adminRepository.listProductVariants(id),
    adminRepository.listProductPrices(id),
    adminRepository.listProductStock(id),
    adminRepository.listProductCompatibilities(id)
  ]);

  if (!product) {
    notFound();
  }

  const vertical = verticals.find((item) => item.id === product.verticalId);

  return (
    <AdminShell title={product.title} description="Ficha operativa de producto dentro del catalogo maestro." actionLabel="Editar">
      {product.imageUrls.length ? (
        <article className="panel productHeroPanel">
          <img src={product.imageUrls[0]} alt="" />
          <div>
            <span className="statusBadge">Galeria tecnica</span>
            <h2>{product.title}</h2>
            <p>{product.description ?? "Producto sin descripcion."}</p>
            <div className="mediaStrip">
              {product.imageUrls.slice(0, 4).map((imageUrl) => (
                <img key={imageUrl} src={imageUrl} alt="" />
              ))}
            </div>
          </div>
        </article>
      ) : null}

      <section className="detailGrid">
        <article className="panel">
          <div className="panelHeader">
            <h2>Datos comerciales</h2>
            <StatusBadge status={product.status} />
          </div>
          <dl className="detailList">
            <div>
              <dt>SKU</dt>
              <dd>{product.sku}</dd>
            </div>
            <div>
              <dt>Categoria</dt>
              <dd>{vertical?.name ?? product.verticalId}</dd>
            </div>
            <div>
              <dt>Tipo</dt>
              <dd>{product.type}</dd>
            </div>
            <div>
              <dt>Precio publico</dt>
              <dd>{product.publicPrice ? formatUsd(product.publicPrice.amount) : "Cotizacion"}</dd>
            </div>
            <div>
              <dt>Precio B2B</dt>
              <dd>{product.b2bPrice ? formatUsd(product.b2bPrice.amount) : "No definido"}</dd>
            </div>
            <div>
              <dt>Stock</dt>
              <dd>{product.stock}</dd>
            </div>
            <div>
              <dt>Garantia</dt>
              <dd>{product.warranty ?? "Sin garantia registrada"}</dd>
            </div>
          </dl>
        </article>

        <article className="panel">
          <div className="panelHeader">
            <h2>Reglas tecnicas</h2>
            <span>{product.countryAvailability.join(", ")}</span>
          </div>
          <dl className="detailList">
            <div>
              <dt>Requiere cotizacion</dt>
              <dd>{product.requiresQuote ? "Si" : "No"}</dd>
            </div>
            <div>
              <dt>Requiere instalacion</dt>
              <dd>{product.requiresInstallation ? "Si" : "No"}</dd>
            </div>
            <div>
              <dt>Validacion tecnica</dt>
              <dd>{product.requiresTechnicalValidation ? "Si" : "No"}</dd>
            </div>
            <div>
              <dt>Compatibilidades</dt>
              <dd>{product.compatibilityIds.length ? product.compatibilityIds.join(", ") : "Sin compatibilidades"}</dd>
            </div>
            <div>
              <dt>Ficha tecnica</dt>
              <dd>{product.technicalSheetUrl ? <a href={product.technicalSheetUrl}>Abrir ficha</a> : "Sin ficha"}</dd>
            </div>
            <div>
              <dt>Manual</dt>
              <dd>{product.manualUrl ? <a href={product.manualUrl}>Abrir manual</a> : "Sin manual"}</dd>
            </div>
          </dl>
        </article>
      </section>

      <article className="panel">
        <div className="panelHeader">
          <h2>Descripcion</h2>
          <span>{product.warranty ?? "Sin garantia registrada"}</span>
        </div>
        <p className="bodyCopy">{product.description ?? "Producto sin descripcion."}</p>
      </article>

      <section className="detailGrid">
        <article className="panel">
          <div className="panelHeader">
            <h2>Variantes</h2>
            <span>{variants.length}</span>
          </div>
          <dl className="detailList">
            {variants.length ? (
              variants.map((variant) => (
                <div key={variant.id}>
                  <dt>{variant.sku}</dt>
                  <dd>{variant.title}</dd>
                </div>
              ))
            ) : (
              <div>
                <dt>Sin variantes</dt>
                <dd>Producto simple</dd>
              </div>
            )}
          </dl>
        </article>

        <article className="panel">
          <div className="panelHeader">
            <h2>Inventario</h2>
            <span>{stockRows.length} ubicacion(es)</span>
          </div>
          <dl className="detailList">
            {stockRows.map((stock) => (
              <div key={stock.id}>
                <dt>{stock.locationId ?? stock.companyId}</dt>
                <dd>
                  Disponible {stock.available}, reservado {stock.reserved}
                </dd>
              </div>
            ))}
          </dl>
        </article>
      </section>

      <section className="detailGrid">
        <article className="panel">
          <div className="panelHeader">
            <h2>Precios editables</h2>
            <span>{prices.length}</span>
          </div>
          {query.status === "invalid-price" ? <p className="bodyCopy">El precio publico debe ser mayor a cero.</p> : null}
          {query.status === "price-updated" ? <p className="bodyCopy">Precio actualizado y registrado en historial.</p> : null}
          <form className="priceEditForm" action={updateProductPricingAction}>
            <input type="hidden" name="productId" value={product.id} />
            <input type="hidden" name="changedBy" value="admin-product-detail" />
            <FormField label="Precio publico USD">
              <input
                name="publicPrice"
                inputMode="decimal"
                defaultValue={product.publicPrice?.amount ?? ""}
                placeholder="0.00"
              />
            </FormField>
            <FormField label="Precio B2B USD">
              <input
                name="b2bPrice"
                inputMode="decimal"
                defaultValue={product.b2bPrice?.amount ?? ""}
                placeholder="0.00"
              />
            </FormField>
            <button type="submit">Guardar nuevo precio</button>
          </form>
          <dl className="detailList">
            {prices.map((price) => (
              <div key={price.id}>
                <dt>{price.type}</dt>
                <dd>
                  {formatUsd(price.amount)} desde {price.validFrom}
                </dd>
              </div>
            ))}
          </dl>
        </article>

        <article className="panel">
          <div className="panelHeader">
            <h2>Compatibilidades</h2>
            <span>{compatibilities.length}</span>
          </div>
          <dl className="detailList">
            {compatibilities.length ? (
              compatibilities.map((compatibility) => (
                <div key={compatibility.id}>
                  <dt>{compatibility.machineModel ?? compatibility.compatibleProductId}</dt>
                  <dd>{compatibility.notes ?? "Sin notas"}</dd>
                </div>
              ))
            ) : (
              <div>
                <dt>Sin compatibilidad</dt>
                <dd>No hay relaciones registradas</dd>
              </div>
            )}
          </dl>
        </article>
      </section>
    </AdminShell>
  );
}
