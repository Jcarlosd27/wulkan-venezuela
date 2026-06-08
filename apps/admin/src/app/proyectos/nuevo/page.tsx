import { AdminShell } from "../../../components/admin-shell";
import { FormField } from "../../../components/form-field";
import { adminRepository } from "../../../lib/repositories";
import { createTechnicalProjectAction } from "../actions";

interface NewProjectPageProps {
  searchParams?: Promise<{ status?: string }>;
}

export default async function NewProjectPage({ searchParams }: NewProjectPageProps) {
  const params = (await searchParams) ?? {};
  const [verticals, users] = await Promise.all([adminRepository.listVerticals(), adminRepository.listUsers()]);
  const installers = users.filter((user) => user.role === "installer" || user.role === "technical_service_operator");

  return (
    <AdminShell
      title="Nuevo proyecto tecnico"
      description="Formulario base para instalaciones, visitas tecnicas y cotizaciones por categoria."
    >
      {params.status === "invalid" ? (
        <section className="panel compactPanel">
          <p className="bodyCopy">Categoria, solicitante y requerimiento tecnico son obligatorios.</p>
        </section>
      ) : null}
      <form className="formPanel" action={createTechnicalProjectAction}>
        <section className="formGrid">
          <FormField label="Categoria">
            <select name="verticalId" defaultValue="lighting">
              {verticals.map((vertical) => (
                <option value={vertical.id} key={vertical.id}>
                  {vertical.name}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Solicitante">
            <input name="requesterId" placeholder="customer-demo" />
          </FormField>
          <FormField label="Estado">
            <select name="status" defaultValue="requested">
              <option value="requested">Solicitado</option>
              <option value="under_evaluation">En evaluacion</option>
              <option value="visit_scheduled">Visita agendada</option>
              <option value="quoted">Cotizado</option>
            </select>
          </FormField>
          <FormField label="Instalador asignado">
            <select name="assignedInstallerId" defaultValue="">
              <option value="">Sin asignar</option>
              {installers.map((installer) => (
                <option value={installer.id} key={installer.id}>
                  {installer.name}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Estado">
            <input name="state" placeholder="Distrito Capital" />
          </FormField>
          <FormField label="Ciudad">
            <input name="city" placeholder="Caracas" />
          </FormField>
        </section>

        <FormField label="Requerimiento tecnico">
          <textarea name="requirements" rows={5} placeholder="Describe uso, medidas, fotos requeridas y condicion del sitio." />
        </FormField>

        <div className="formActions">
          <button type="submit">Guardar proyecto</button>
        </div>
      </form>
    </AdminShell>
  );
}
