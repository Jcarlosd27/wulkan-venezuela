import { notFound } from "next/navigation";
import { AdminShell } from "../../../components/admin-shell";
import { DataTable } from "../../../components/data-table";
import { StatusBadge } from "../../../components/status-badge";
import { adminRepository } from "../../../lib/repositories";

interface VerticalDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function VerticalDetailPage({ params }: VerticalDetailPageProps) {
  const { id } = await params;
  const vertical = await adminRepository.getVertical(id);

  if (!vertical) {
    notFound();
  }

  return (
    <AdminShell title={vertical.name} description="Configuracion de atributos, filtros y reglas por categoria." actionLabel="Editar">
      <section className="detailGrid">
        <article className="panel">
          <div className="panelHeader">
            <h2>Resumen</h2>
            <StatusBadge status={vertical.status} />
          </div>
          <dl className="detailList">
            <div>
              <dt>Slug</dt>
              <dd>{vertical.slug}</dd>
            </div>
            <div>
              <dt>Paises</dt>
              <dd>{vertical.countries.join(", ")}</dd>
            </div>
            <div>
              <dt>Tipos</dt>
              <dd>{vertical.availableProductTypes.join(", ")}</dd>
            </div>
            <div>
              <dt>Atributos tecnicos</dt>
              <dd>{vertical.requiresTechnicalAttributes ? "Requeridos" : "Opcionales"}</dd>
            </div>
          </dl>
        </article>

        <article className="panel">
          <div className="panelHeader">
            <h2>Descripcion</h2>
            <span>MVP Venezuela</span>
          </div>
          <p className="bodyCopy">{vertical.description ?? "Categoria sin descripcion."}</p>
        </article>
      </section>

      <DataTable columns={["Atributo", "Tipo", "Obligatorio", "Filtro", "Detalle"]}>
        {vertical.attributeSchema.map((attribute) => (
          <tr key={attribute.id}>
            <td>
              <strong>{attribute.name}</strong>
              <small>{attribute.unit ?? attribute.options?.join(", ") ?? "Sin unidad"}</small>
            </td>
            <td>{attribute.type}</td>
            <td>{attribute.required ? "Si" : "No"}</td>
            <td>{attribute.visibleInFilters ? "Si" : "No"}</td>
            <td>{attribute.visibleInProductDetail ? "Si" : "No"}</td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}
