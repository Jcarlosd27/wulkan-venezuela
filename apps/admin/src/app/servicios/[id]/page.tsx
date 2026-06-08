import { notFound } from "next/navigation";
import { formatUsd } from "@wulkan/shared";
import { AdminShell } from "../../../components/admin-shell";
import { DataTable } from "../../../components/data-table";
import { StatusBadge } from "../../../components/status-badge";
import { adminRepository } from "../../../lib/repositories";

interface ServiceCaseDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function ServiceCaseDetailPage({ params }: ServiceCaseDetailPageProps) {
  const { id } = await params;
  const [serviceCase, events] = await Promise.all([
    adminRepository.getServiceCase(id),
    adminRepository.listServiceCaseEvents(id)
  ]);

  if (!serviceCase) {
    notFound();
  }

  return (
    <AdminShell title={serviceCase.id} description="Detalle tecnico, diagnostico, repuestos e historial del caso." actionLabel="Actualizar caso">
      <section className="detailGrid">
        <article className="panel">
          <div className="panelHeader">
            <h2>Cliente y maquina</h2>
            <StatusBadge status={serviceCase.status} />
          </div>
          <dl className="detailList">
            <div>
              <dt>Cliente</dt>
              <dd>{serviceCase.customerName}</dd>
            </div>
            <div>
              <dt>Contacto</dt>
              <dd>{serviceCase.customerContact}</dd>
            </div>
            <div>
              <dt>Maquina</dt>
              <dd>{serviceCase.machineId ?? "Sin maquina"}</dd>
            </div>
            <div>
              <dt>Serial</dt>
              <dd>{serviceCase.serialNumber ?? "Sin serial"}</dd>
            </div>
          </dl>
        </article>

        <article className="panel">
          <div className="panelHeader">
            <h2>Diagnostico</h2>
            <span>{serviceCase.diagnosisDetail?.failureCode ?? "Sin codigo"}</span>
          </div>
          <dl className="detailList">
            <div>
              <dt>Sintomas</dt>
              <dd>{serviceCase.symptoms}</dd>
            </div>
            <div>
              <dt>Resumen</dt>
              <dd>{serviceCase.diagnosisDetail?.summary ?? serviceCase.diagnosis ?? "Sin diagnostico"}</dd>
            </div>
            <div>
              <dt>Accion</dt>
              <dd>{serviceCase.diagnosisDetail?.recommendedAction ?? "Pendiente"}</dd>
            </div>
            <div>
              <dt>Mano de obra</dt>
              <dd>
                {serviceCase.diagnosisDetail?.estimatedLaborUsd
                  ? formatUsd(serviceCase.diagnosisDetail.estimatedLaborUsd)
                  : "Sin estimacion"}
              </dd>
            </div>
          </dl>
        </article>
      </section>

      <section className="detailGrid">
        <article className="panel">
          <div className="panelHeader">
            <h2>Repuestos solicitados</h2>
            <span>{serviceCase.requestedParts.length}</span>
          </div>
          <dl className="detailList">
            {serviceCase.requestedParts.map((part) => (
              <div key={`${part.sku}-${part.description}`}>
                <dt>{part.sku ?? "Sin SKU"}</dt>
                <dd>
                  {part.quantity} x {part.description}
                </dd>
              </div>
            ))}
          </dl>
        </article>

        <article className="panel">
          <div className="panelHeader">
            <h2>Repuestos usados</h2>
            <span>{serviceCase.usedParts.length}</span>
          </div>
          <dl className="detailList">
            {serviceCase.usedParts.length ? (
              serviceCase.usedParts.map((part) => (
                <div key={`${part.sku}-${part.description}`}>
                  <dt>{part.sku ?? "Sin SKU"}</dt>
                  <dd>
                    {part.quantity} x {part.description}
                  </dd>
                </div>
              ))
            ) : (
              <div>
                <dt>Pendiente</dt>
                <dd>No hay repuestos usados</dd>
              </div>
            )}
          </dl>
        </article>
      </section>

      <DataTable columns={["Evento", "Mensaje", "Actor", "Estado", "Fecha"]}>
        {events.map((event) => (
          <tr key={event.id}>
            <td>{event.type}</td>
            <td>{event.message}</td>
            <td>{event.actorUserId}</td>
            <td>{event.statusAfter ? <StatusBadge status={event.statusAfter} /> : "Sin cambio"}</td>
            <td>{event.createdAt}</td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}

