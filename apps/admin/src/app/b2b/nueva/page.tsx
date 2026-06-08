import { AdminShell } from "../../../components/admin-shell";
import { FormField } from "../../../components/form-field";
import { adminRepository } from "../../../lib/repositories";
import { createPurchaseOrderAction } from "../actions";

interface NewPurchaseOrderPageProps {
  searchParams?: Promise<{ status?: string }>;
}

export default async function NewPurchaseOrderPage({ searchParams }: NewPurchaseOrderPageProps) {
  const params = (await searchParams) ?? {};
  const [companies, products] = await Promise.all([adminRepository.listCompanies(), adminRepository.listProducts()]);
  const hardwareStores = companies.filter((company) => company.type === "hardware_store");

  return (
    <AdminShell title="Nueva orden B2B" description="Formulario base para ordenes de compra de ferreteros.">
      {params.status === "invalid" ? (
        <section className="panel compactPanel">
          <p className="bodyCopy">Ferretero y producto son obligatorios.</p>
        </section>
      ) : null}
      <form className="formPanel" action={createPurchaseOrderAction}>
        <section className="formGrid">
          <FormField label="Ferretero">
            <select name="requesterCompanyId" defaultValue="ferreteria-demo">
              {hardwareStores.map((company) => (
                <option value={company.id} key={company.id}>
                  {company.commercialName}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Fecha solicitada de entrega">
            <input name="requestedDeliveryDate" type="date" />
          </FormField>
          <FormField label="Producto">
            <select name="productId" defaultValue="prod-cadena-18">
              {products.map((product) => (
                <option value={product.id} key={product.id}>
                  {product.sku} - {product.title}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Cantidad">
            <input name="quantity" inputMode="numeric" defaultValue="10" />
          </FormField>
        </section>
        <FormField label="Notas">
          <textarea name="notes" rows={4} placeholder="Condiciones, referencia o comentarios de reposicion." />
        </FormField>
        <div className="formActions">
          <button type="submit">Guardar OC</button>
        </div>
      </form>
    </AdminShell>
  );
}
