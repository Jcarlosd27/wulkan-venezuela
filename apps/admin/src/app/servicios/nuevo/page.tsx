import { AdminShell } from "../../../components/admin-shell";
import { FormField } from "../../../components/form-field";
import { adminRepository } from "../../../lib/repositories";
import { createServiceCaseAction } from "../actions";

interface NewServiceCasePageProps {
  searchParams?: Promise<{ status?: string }>;
}

export default async function NewServiceCasePage({ searchParams }: NewServiceCasePageProps) {
  const params = (await searchParams) ?? {};
  const [companies, products] = await Promise.all([adminRepository.listCompanies(), adminRepository.listProducts()]);
  const technicalServices = companies.filter((company) => company.type === "technical_service");

  return (
    <AdminShell title="Crear caso tecnico" description="Formulario base para diagnostico, evidencias y solicitud de repuestos.">
      {params.status === "invalid" ? (
        <section className="panel compactPanel">
          <p className="bodyCopy">Servicio tecnico, cliente, contacto y sintomas son obligatorios.</p>
        </section>
      ) : null}
      <form className="formPanel" action={createServiceCaseAction}>
        <section className="formGrid">
          <FormField label="Servicio tecnico">
            <select name="technicalServiceId" defaultValue="">
              <option value="">Seleccionar servicio</option>
              {technicalServices.map((company) => (
                <option value={company.id} key={company.id}>
                  {company.commercialName}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Cliente">
            <input name="customerName" placeholder="Nombre del cliente" />
          </FormField>
          <FormField label="Contacto">
            <input name="customerContact" placeholder="+58..." />
          </FormField>
          <FormField label="Maquina">
            <select name="machineId" defaultValue="prod-motosierra-45cc">
              {products.map((product) => (
                <option value={product.id} key={product.id}>
                  {product.sku} - {product.title}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Serial">
            <input name="serialNumber" placeholder="Serial o placa" />
          </FormField>
          <FormField label="Estado inicial">
            <select name="status" defaultValue="received">
              <option value="received">Recibida</option>
              <option value="diagnosed">Diagnosticada</option>
              <option value="waiting_part">Esperando repuesto</option>
            </select>
          </FormField>
        </section>

        <FormField label="Sintomas">
          <textarea name="symptoms" rows={4} placeholder="Describe falla, condiciones y observaciones del cliente." />
        </FormField>

        <FormField label="Diagnostico inicial">
          <textarea name="diagnosis" rows={4} placeholder="Resumen tecnico, repuesto sugerido o garantia." />
        </FormField>

        <div className="formActions">
          <button type="submit">Guardar caso</button>
        </div>
      </form>
    </AdminShell>
  );
}
