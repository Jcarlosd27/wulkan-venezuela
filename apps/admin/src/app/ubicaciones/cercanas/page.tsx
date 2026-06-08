import type { LocationService } from "@wulkan/domain";
import { AdminShell } from "../../../components/admin-shell";
import { DataTable } from "../../../components/data-table";
import { ModuleActions } from "../../../components/module-actions";
import { StatusBadge } from "../../../components/status-badge";
import { adminRepository } from "../../../lib/repositories";

interface NearbyLocationsPageProps {
  searchParams?: Promise<{
    lat?: string;
    lng?: string;
    service?: LocationService;
  }>;
}

export default async function NearbyLocationsPage({ searchParams }: NearbyLocationsPageProps) {
  const params = (await searchParams) ?? {};
  const origin = {
    lat: Number(params.lat ?? 10.4806),
    lng: Number(params.lng ?? -66.9036)
  };
  const nearbyFilters: { service?: LocationService; limit: number } = { limit: 10 };

  if (params.service) {
    nearbyFilters.service = params.service;
  }

  const nearbyLocations = await adminRepository.listNearbyLocations(origin, nearbyFilters);

  return (
    <AdminShell
      title="Puntos cercanos"
      description="Orden de ferreteros, servicios tecnicos y puntos de retiro por distancia estimada."
      actionLabel="Volver"
    >
      <ModuleActions
        actions={[
          { label: "Ubicaciones", href: "/ubicaciones" },
          { label: "Nuevo punto", href: "/ubicaciones/nueva" }
        ]}
      />
      <form className="filterBar">
        <input name="lat" defaultValue={String(origin.lat)} aria-label="Latitud" />
        <input name="lng" defaultValue={String(origin.lng)} aria-label="Longitud" />
        <select name="service" defaultValue={params.service ?? ""}>
          <option value="">Todos los servicios</option>
          <option value="retail_sale">Venta retail</option>
          <option value="b2b_sale">Venta B2B</option>
          <option value="pickup">Retiro</option>
          <option value="technical_support">Soporte tecnico</option>
          <option value="case_reception">Recepcion de casos</option>
          <option value="installation">Instalacion</option>
        </select>
        <button type="submit">Buscar</button>
      </form>
      <DataTable columns={["Punto", "Tipo", "Ciudad", "Distancia", "Servicios", "Estado"]}>
        {nearbyLocations.map(({ location, distanceKm }) => (
          <tr key={location.id}>
            <td>
              <a href={`/ubicaciones/${location.id}`}>
                <strong>{location.name}</strong>
              </a>
              <small>{location.address.line1}</small>
            </td>
            <td>{location.type}</td>
            <td>
              {location.address.city}, {location.address.state}
            </td>
            <td>{distanceKm} km</td>
            <td>{location.availableServices.join(", ")}</td>
            <td>
              <StatusBadge status={location.status} />
            </td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}
