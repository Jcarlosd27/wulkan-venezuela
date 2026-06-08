import { notFound } from "next/navigation";
import { AdminShell } from "../../../components/admin-shell";
import { StatusBadge } from "../../../components/status-badge";
import { adminRepository } from "../../../lib/repositories";

interface LocationDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function LocationDetailPage({ params }: LocationDetailPageProps) {
  const { id } = await params;
  const location = await adminRepository.getLocation(id);

  if (!location) {
    notFound();
  }

  return (
    <AdminShell title={location.name} description="Detalle de punto autorizado, servicios y cobertura." actionLabel="Editar punto">
      <section className="detailGrid">
        <article className="panel">
          <div className="panelHeader">
            <h2>Datos del punto</h2>
            <StatusBadge status={location.status} />
          </div>
          <dl className="detailList">
            <div>
              <dt>Tipo</dt>
              <dd>{location.type}</dd>
            </div>
            <div>
              <dt>Direccion</dt>
              <dd>
                {location.address.line1}, {location.address.city}, {location.address.state}
              </dd>
            </div>
            <div>
              <dt>Contacto</dt>
              <dd>{location.whatsapp ?? location.phone}</dd>
            </div>
            <div>
              <dt>Horario</dt>
              <dd>{location.schedule ?? "Sin horario"}</dd>
            </div>
          </dl>
        </article>

        <article className="panel">
          <div className="panelHeader">
            <h2>Mapa mock</h2>
            <span>{location.coordinates.lat}, {location.coordinates.lng}</span>
          </div>
          <div className="mapMock">
            <strong>{location.name}</strong>
            <span>{location.coverageAreas.map((area) => area.city ?? area.state).join(", ")}</span>
          </div>
        </article>
      </section>

      <section className="detailGrid">
        <article className="panel">
          <div className="panelHeader">
            <h2>Servicios</h2>
            <span>{location.availableServices.length}</span>
          </div>
          <div className="roleList">
            {location.availableServices.map((service) => (
              <span key={service}>{service}</span>
            ))}
          </div>
        </article>

        <article className="panel">
          <div className="panelHeader">
            <h2>Cobertura</h2>
            <span>{location.acceptsWalkIns ? "Atiende sin cita" : "Con cita"}</span>
          </div>
          <dl className="detailList">
            {location.coverageAreas.map((area) => (
              <div key={`${area.state}-${area.city ?? "all"}`}>
                <dt>{area.state}</dt>
                <dd>
                  {area.city ?? "Todo el estado"} {area.radiusKm ? `- radio ${area.radiusKm} km` : ""}
                </dd>
              </div>
            ))}
          </dl>
        </article>
      </section>
    </AdminShell>
  );
}

