import type { MobileAnnouncement } from "@wulkan/domain";
import { AdminShell } from "../../components/admin-shell";
import { Breadcrumb } from "../../components/breadcrumb";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";
import { createMobileAnnouncementAction } from "./actions";

interface AnnouncementsPageProps {
  searchParams?: Promise<{
    status?: string;
  }>;
}

function formatDate(value?: string): string {
  if (!value) {
    return "Sin cierre";
  }

  return new Intl.DateTimeFormat("es-VE", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function sortAnnouncements(current: MobileAnnouncement, next: MobileAnnouncement): number {
  return next.priority - current.priority || next.updatedAt.localeCompare(current.updatedAt);
}

export default async function AnnouncementsPage({ searchParams }: AnnouncementsPageProps) {
  const params = (await searchParams) ?? {};
  const announcements = (await adminRepository.listMobileAnnouncements()).sort(sortAnnouncements);
  const activeCount = announcements.filter((announcement) => announcement.status === "active").length;

  return (
    <AdminShell
      title="Anuncios app"
      description="Publicaciones que aparecen en la app movil Android de Wulkan."
    >
      <Breadcrumb
        items={[
          { label: "Dashboard", href: "/" },
          { label: "Anuncios app" }
        ]}
      />

      {params.status === "created" ? (
        <div className="alert alert-success border-0" role="status">
          Anuncio creado. Si usas Firestore, la app movil lo leera al refrescar.
        </div>
      ) : null}

      {params.status === "invalid" ? (
        <div className="alert alert-warning border-0" role="status">
          Titulo, mensaje e inicio son obligatorios.
        </div>
      ) : null}

      <section className="row g-3 mb-3">
        <div className="col-12 col-lg-4">
          <article className="card border-0 shadow-sm h-100">
            <div className="card-body">
              <span className="text-secondary small fw-semibold text-uppercase">Activos</span>
              <strong className="d-block display-6">{activeCount}</strong>
              <p className="mb-0 text-secondary">Visibles en home, catalogo o checkout.</p>
            </div>
          </article>
        </div>
        <div className="col-12 col-lg-4">
          <article className="card border-0 shadow-sm h-100">
            <div className="card-body">
              <span className="text-secondary small fw-semibold text-uppercase">Total</span>
              <strong className="d-block display-6">{announcements.length}</strong>
              <p className="mb-0 text-secondary">Campanas cargadas para la app.</p>
            </div>
          </article>
        </div>
        <div className="col-12 col-lg-4">
          <article className="card border-0 shadow-sm h-100">
            <div className="card-body">
              <span className="text-secondary small fw-semibold text-uppercase">Prioridad alta</span>
              <strong className="d-block display-6">
                {announcements.filter((announcement) => announcement.priority >= 80).length}
              </strong>
              <p className="mb-0 text-secondary">Se muestran primero en Android.</p>
            </div>
          </article>
        </div>
      </section>

      <section className="row g-3">
        <div className="col-12 col-xl-5">
          <form className="card border-0 shadow-sm" action={createMobileAnnouncementAction}>
            <div className="card-header bg-white">
              <h2 className="h5 mb-1">Crear anuncio</h2>
              <p className="mb-0 text-secondary">Contenido administrado por Wulkan para Android.</p>
            </div>
            <div className="card-body">
              <div className="mb-3">
                <label className="form-label fw-semibold" htmlFor="title">
                  Titulo
                </label>
                <input className="form-control" id="title" name="title" required placeholder="Oferta de lanzamiento" />
              </div>
              <div className="mb-3">
                <label className="form-label fw-semibold" htmlFor="body">
                  Mensaje
                </label>
                <textarea
                  className="form-control"
                  id="body"
                  name="body"
                  rows={4}
                  required
                  placeholder="Texto visible para clientes finales."
                />
              </div>
              <div className="row g-3">
                <div className="col-12 col-md-6">
                  <label className="form-label fw-semibold" htmlFor="placement">
                    Ubicacion
                  </label>
                  <select className="form-select" id="placement" name="placement" defaultValue="home">
                    <option value="home">Home</option>
                    <option value="catalog">Catalogo</option>
                    <option value="checkout">Checkout</option>
                  </select>
                </div>
                <div className="col-12 col-md-6">
                  <label className="form-label fw-semibold" htmlFor="priority">
                    Prioridad
                  </label>
                  <input className="form-control" id="priority" name="priority" inputMode="numeric" defaultValue="50" />
                </div>
                <div className="col-12 col-md-6">
                  <label className="form-label fw-semibold" htmlFor="startsAt">
                    Inicio
                  </label>
                  <input className="form-control" id="startsAt" name="startsAt" type="datetime-local" required />
                </div>
                <div className="col-12 col-md-6">
                  <label className="form-label fw-semibold" htmlFor="endsAt">
                    Cierre
                  </label>
                  <input className="form-control" id="endsAt" name="endsAt" type="datetime-local" />
                </div>
              </div>
              <div className="mt-3">
                <label className="form-label fw-semibold" htmlFor="imageUrl">
                  Imagen o logo
                </label>
                <input className="form-control" id="imageUrl" name="imageUrl" placeholder="/brand/wulkan-logo.svg" />
              </div>
              <div className="row g-3 mt-0">
                <div className="col-12 col-md-5">
                  <label className="form-label fw-semibold" htmlFor="ctaLabel">
                    Boton
                  </label>
                  <input className="form-control" id="ctaLabel" name="ctaLabel" placeholder="Ver catalogo" />
                </div>
                <div className="col-12 col-md-7">
                  <label className="form-label fw-semibold" htmlFor="ctaUrl">
                    Accion
                  </label>
                  <input className="form-control" id="ctaUrl" name="ctaUrl" placeholder="wulkan://catalog" />
                </div>
              </div>
              <div className="mt-3">
                <label className="form-label fw-semibold" htmlFor="status">
                  Estado
                </label>
                <select className="form-select" id="status" name="status" defaultValue="active">
                  <option value="active">Activo</option>
                  <option value="pending">Pendiente</option>
                  <option value="inactive">Inactivo</option>
                </select>
              </div>
            </div>
            <div className="card-footer bg-white d-flex justify-content-end">
              <button className="btn btn-primary" type="submit">
                Publicar anuncio
              </button>
            </div>
          </form>
        </div>

        <div className="col-12 col-xl-7">
          <div className="card border-0 shadow-sm">
            <div className="card-header bg-white">
              <h2 className="h5 mb-1">Campanas actuales</h2>
              <p className="mb-0 text-secondary">Ordenadas por prioridad y ultima actualizacion.</p>
            </div>
            <div className="table-responsive">
              <table className="table align-middle mb-0">
                <thead>
                  <tr>
                    <th>Anuncio</th>
                    <th>Ubicacion</th>
                    <th>Vigencia</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {announcements.map((announcement) => (
                    <tr key={announcement.id}>
                      <td>
                        <strong>{announcement.title}</strong>
                        <small className="text-secondary d-block">{announcement.body}</small>
                        <span className="badge text-bg-light mt-1">Prioridad {announcement.priority}</span>
                      </td>
                      <td className="text-capitalize">{announcement.placement}</td>
                      <td>
                        <small className="d-block">Desde {formatDate(announcement.startsAt)}</small>
                        <small className="text-secondary d-block">Hasta {formatDate(announcement.endsAt)}</small>
                      </td>
                      <td>
                        <StatusBadge status={announcement.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>
    </AdminShell>
  );
}
