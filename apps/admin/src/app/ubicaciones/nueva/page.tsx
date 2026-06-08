import { AdminShell } from "../../../components/admin-shell";
import { FormField } from "../../../components/form-field";
import { createLocationAction } from "../actions";

interface NewLocationPageProps {
  searchParams?: Promise<{ status?: string }>;
}

export default async function NewLocationPage({ searchParams }: NewLocationPageProps) {
  const params = (await searchParams) ?? {};

  return (
    <AdminShell title="Nuevo punto autorizado" description="Formulario base para red fisica, cobertura y servicios.">
      {params.status === "invalid" ? (
        <section className="panel compactPanel">
          <p className="bodyCopy">Nombre, ubicacion, direccion y al menos un servicio son obligatorios.</p>
        </section>
      ) : null}
      <form className="formPanel" action={createLocationAction}>
        <section className="formGrid">
          <FormField label="Nombre">
            <input name="name" placeholder="Punto autorizado Caracas" />
          </FormField>
          <FormField label="Tipo">
            <select name="type" defaultValue="pickup_point">
              <option value="hardware_store">Ferreteria</option>
              <option value="technical_service">Servicio tecnico</option>
              <option value="pickup_point">Punto de retiro</option>
              <option value="distributor">Distribuidor</option>
              <option value="installer">Instalador</option>
            </select>
          </FormField>
          <FormField label="Estado">
            <input name="state" placeholder="Distrito Capital" />
          </FormField>
          <FormField label="Ciudad">
            <input name="city" placeholder="Caracas" />
          </FormField>
          <FormField label="Latitud">
            <input name="lat" inputMode="decimal" placeholder="10.498" />
          </FormField>
          <FormField label="Longitud">
            <input name="lng" inputMode="decimal" placeholder="-66.853" />
          </FormField>
          <FormField label="Telefono">
            <input name="phone" placeholder="+58..." />
          </FormField>
        </section>
        <FormField label="Direccion">
          <textarea name="line1" rows={3} placeholder="Direccion, referencia y telefono." />
        </FormField>
        <section className="checkGrid">
          <label><input type="checkbox" name="services" value="pickup" /> Retiro</label>
          <label><input type="checkbox" name="services" value="b2b_sale" /> Venta B2B</label>
          <label><input type="checkbox" name="services" value="technical_support" /> Soporte tecnico</label>
          <label><input type="checkbox" name="services" value="case_reception" /> Recepcion de casos</label>
          <label><input type="checkbox" name="services" value="installation" /> Instalacion</label>
        </section>
        <div className="formActions">
          <button type="submit">Guardar punto</button>
        </div>
      </form>
    </AdminShell>
  );
}
