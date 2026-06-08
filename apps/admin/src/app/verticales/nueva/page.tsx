import { AdminShell } from "../../../components/admin-shell";
import { FormField } from "../../../components/form-field";
import { entityStatusOptions, productTypeOptions } from "../../../lib/form-options";
import { createVerticalAction } from "../actions";

interface NewVerticalPageProps {
  searchParams?: Promise<{
    status?: string;
  }>;
}

export default async function NewVerticalPage({ searchParams }: NewVerticalPageProps) {
  const params = (await searchParams) ?? {};

  return (
    <AdminShell
      title="Nueva categoria"
      description="Configuracion base para agrupar productos, atributos tecnicos y tipos de venta."
    >
      {params.status === "invalid" ? (
        <section className="panel compactPanel">
          <p className="bodyCopy">Nombre, slug y al menos un tipo de producto son obligatorios.</p>
        </section>
      ) : null}
      <form className="formPanel" action={createVerticalAction}>
        <section className="formGrid">
          <FormField label="Nombre">
            <input name="name" placeholder="Ej: Energia solar" />
          </FormField>
          <FormField label="Slug">
            <input name="slug" placeholder="energia-solar" />
          </FormField>
          <FormField label="Estado">
            <select name="status" defaultValue="pending">
              {entityStatusOptions.map((option) => (
                <option value={option.value} key={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Pais inicial">
            <input name="country" value="VE" readOnly />
          </FormField>
        </section>

        <FormField label="Descripcion">
          <textarea name="description" rows={4} placeholder="Describe el alcance comercial y tecnico de la categoria." />
        </FormField>

        <section className="panel compactPanel">
          <div className="panelHeader">
            <h2>Tipos habilitados</h2>
            <span>Configuracion MVP</span>
          </div>
          <div className="checkGrid">
            {productTypeOptions.map((option) => (
              <label key={option.value}>
                <input type="checkbox" name="availableProductTypes" value={option.value} /> {option.label}
              </label>
            ))}
          </div>
        </section>

        <div className="formActions">
          <button type="submit">Guardar categoria</button>
        </div>
      </form>
    </AdminShell>
  );
}
