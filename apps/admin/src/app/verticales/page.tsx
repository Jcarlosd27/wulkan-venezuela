import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { ModuleActions } from "../../components/module-actions";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";

export default async function VerticalsPage() {
  const verticals = await adminRepository.listVerticals();

  return (
    <AdminShell
      title="Categorias"
      description="Categorias comerciales que ordenan el catalogo, atributos tecnicos y reglas de venta."
      actionLabel="Crear categoria"
    >
      <ModuleActions actions={[{ label: "Nueva categoria", href: "/verticales/nueva" }]} />
      <DataTable columns={["Categoria", "Slug", "Tipos", "Atributos", "Estado"]}>
        {verticals.map((vertical) => (
          <tr key={vertical.id}>
            <td>
              <a href={`/verticales/${vertical.id}`}>
                <strong>{vertical.name}</strong>
              </a>
              <small>{vertical.description}</small>
            </td>
            <td>{vertical.slug}</td>
            <td>{vertical.availableProductTypes.join(", ")}</td>
            <td>{vertical.attributeSchema.length}</td>
            <td>
              <StatusBadge status={vertical.status} />
            </td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}
