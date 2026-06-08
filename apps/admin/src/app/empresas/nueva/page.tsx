import { AdminShell } from "../../../components/admin-shell";
import { FormField } from "../../../components/form-field";
import { createCompanyAction } from "../actions";

interface NewCompanyPageProps {
  searchParams?: Promise<{ status?: string }>;
}

export default async function NewCompanyPage({ searchParams }: NewCompanyPageProps) {
  const params = (await searchParams) ?? {};

  return (
    <AdminShell title="Nueva empresa" description="Alta inicial de vendedor, ferretero, servicio tecnico o instalador.">
      {params.status === "invalid" ? (
        <section className="panel compactPanel">
          <p className="bodyCopy">Razon social, nombre comercial, telefono, estado y ciudad son obligatorios.</p>
        </section>
      ) : null}
      <form className="formPanel" action={createCompanyAction}>
        <section className="formGrid">
          <FormField label="Razon social">
            <input name="legalName" placeholder="Empresa Demo C.A." />
          </FormField>
          <FormField label="Nombre comercial">
            <input name="commercialName" placeholder="Empresa Demo" />
          </FormField>
          <FormField label="RIF / identificacion fiscal">
            <input name="taxId" placeholder="J-00000000-0" />
          </FormField>
          <FormField label="Tipo">
            <select name="type" defaultValue="seller">
              <option value="seller">Vendedor</option>
              <option value="hardware_store">Ferretero</option>
              <option value="technical_service">Servicio tecnico</option>
              <option value="distributor">Distribuidor</option>
              <option value="installer">Instalador</option>
            </select>
          </FormField>
          <FormField label="Contacto">
            <input name="contactName" placeholder="Nombre del responsable" />
          </FormField>
          <FormField label="Email">
            <input name="email" type="email" placeholder="contacto@empresa.com" />
          </FormField>
          <FormField label="Telefono">
            <input name="phone" placeholder="+58..." />
          </FormField>
          <FormField label="WhatsApp">
            <input name="whatsapp" placeholder="+58..." />
          </FormField>
          <FormField label="Estado">
            <input name="state" placeholder="Distrito Capital" />
          </FormField>
          <FormField label="Ciudad">
            <input name="city" placeholder="Caracas" />
          </FormField>
        </section>
        <FormField label="Direccion">
          <textarea name="line1" rows={3} placeholder="Direccion fiscal u operativa." />
        </FormField>
        <section className="checkGrid">
          <label>
            <input type="checkbox" name="b2bEnabled" /> Habilitar B2B
          </label>
        </section>
        <div className="formActions">
          <button type="submit">Guardar empresa</button>
        </div>
      </form>
    </AdminShell>
  );
}
