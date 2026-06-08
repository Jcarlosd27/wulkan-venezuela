import { AdminShell } from "../../../components/admin-shell";
import { FormField } from "../../../components/form-field";
import { adminRepository } from "../../../lib/repositories";
import { createOrderAction } from "../actions";

interface NewOrderPageProps {
  searchParams?: Promise<{ status?: string }>;
}

export default async function NewOrderPage({ searchParams }: NewOrderPageProps) {
  const params = (await searchParams) ?? {};
  const [products, users, settings] = await Promise.all([
    adminRepository.listProducts(),
    adminRepository.listUsers(),
    adminRepository.getAppSettings()
  ]);
  const customers = users.filter((user) => user.role === "customer");
  const activeProducts = products.filter((product) => product.status === "active");

  return (
    <AdminShell
      title="Nueva orden B2C"
      description="Registro operativo de compra de cliente final. La validacion final de pago queda en backend/operador."
    >
      {params.status === "invalid" ? (
        <section className="panel compactPanel">
          <p className="bodyCopy">Cliente y producto son obligatorios.</p>
        </section>
      ) : null}
      {params.status === "invalid-price" ? (
        <section className="panel compactPanel">
          <p className="bodyCopy">El producto seleccionado no tiene precio publico valido.</p>
        </section>
      ) : null}

      <form className="formPanel" action={createOrderAction}>
        <section className="formGrid">
          <FormField label="Cliente">
            <select name="customerId" defaultValue={customers[0]?.id ?? "customer-demo"}>
              {customers.length ? (
                customers.map((customer) => (
                  <option value={customer.id} key={customer.id}>
                    {customer.name} - {customer.email}
                  </option>
                ))
              ) : (
                <option value="customer-demo">Cliente demo</option>
              )}
            </select>
          </FormField>

          <FormField label="Producto">
            <select name="productId" defaultValue={activeProducts[0]?.id ?? ""}>
              {activeProducts.map((product) => (
                <option value={product.id} key={product.id}>
                  {product.sku} - {product.title}
                </option>
              ))}
            </select>
          </FormField>

          <FormField label="Cantidad">
            <input name="quantity" inputMode="numeric" defaultValue="1" />
          </FormField>

          <FormField label="Metodo de pago">
            <select name="paymentMethod" defaultValue="pago_movil">
              <option value="pago_movil">Pago movil</option>
              <option value="bank_transfer">Transferencia bancaria</option>
              <option value="mercado_pago">Mercado Pago</option>
              <option value="whatsapp_assisted">WhatsApp asistido</option>
            </select>
          </FormField>

          <FormField label="Tasa USD/VES">
            <input name="exchangeRateUsdVes" inputMode="decimal" defaultValue={String(settings.exchangeRate.rate ?? 38.5)} />
          </FormField>
        </section>

        <FormField label="Notas operativas">
          <textarea name="notes" rows={4} placeholder="Referencia de pago, entrega, retiro o comentario del operador." />
        </FormField>

        <div className="formActions">
          <button type="submit">Crear orden B2C</button>
        </div>
      </form>
    </AdminShell>
  );
}
