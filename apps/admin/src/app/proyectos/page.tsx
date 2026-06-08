import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { ModuleActions } from "../../components/module-actions";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";

export default async function ProjectsPage() {
  const [projects, verticals, users] = await Promise.all([
    adminRepository.listTechnicalProjects(),
    adminRepository.listVerticals(),
    adminRepository.listUsers()
  ]);

  return (
    <AdminShell
      title="Proyectos tecnicos"
      description="Solicitudes de instalacion, evaluacion tecnica, cotizacion y garantia."
      actionLabel="Crear proyecto"
    >
      <ModuleActions actions={[{ label: "Nuevo proyecto", href: "/proyectos/nuevo" }]} />
      <DataTable columns={["Proyecto", "Categoria", "Solicitante", "Instalador", "Visita", "Estado"]}>
        {projects.map((project) => {
          const vertical = verticals.find((item) => item.id === project.verticalId);
          const installer = users.find((item) => item.id === project.assignedInstallerId);

          return (
            <tr key={project.id}>
              <td>
                <strong>{project.id}</strong>
                <small>{project.requirements}</small>
              </td>
              <td>{vertical?.name ?? project.verticalId}</td>
              <td>{project.requesterId}</td>
              <td>{installer?.name ?? project.assignedInstallerId ?? "Sin asignar"}</td>
              <td>{project.scheduledAt ?? "Sin agenda"}</td>
              <td>
                <StatusBadge status={project.status} />
              </td>
            </tr>
          );
        })}
      </DataTable>
    </AdminShell>
  );
}
