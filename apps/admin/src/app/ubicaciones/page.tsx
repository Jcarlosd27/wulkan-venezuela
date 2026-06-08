import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { ModuleActions } from "../../components/module-actions";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";
import type { LocationService, LocationType } from "@wulkan/domain";

interface LocationsPageProps {
  searchParams?: Promise<{
    type?: LocationType;
    service?: LocationService;
  }>;
}

export default async function LocationsPage({ searchParams }: LocationsPageProps) {
  const params = (await searchParams) ?? {};
  const filters: { type?: LocationType; service?: LocationService } = {};

  if (params.type) {
    filters.type = params.type;
  }

  if (params.service) {
    filters.service = params.service;
  }

  const locations = await adminRepository.listLocations(filters);

  return (
    <AdminShell
      title="Ubicaciones"
      description="Ferreteros, servicios tecnicos, puntos de retiro e instaladores autorizados."
      actionLabel="Crear punto"
    >
      <ModuleActions
        actions={[
          { label: "Nuevo punto", href: "/ubicaciones/nueva" },
          { label: "Cercanos", href: "/ubicaciones/cercanas" }
        ]}
      />
      <form className="filterBar">
        <select name="type" defaultValue={params.type ?? ""}>
          <option value="">Todos los tipos</option>
          <option value="hardware_store">Ferreteria</option>
          <option value="technical_service">Servicio tecnico</option>
          <option value="pickup_point">Punto de retiro</option>
          <option value="distributor">Distribuidor</option>
          <option value="installer">Instalador</option>
        </select>
        <select name="service" defaultValue={params.service ?? ""}>
          <option value="">Todos los servicios</option>
          <option value="retail_sale">Venta retail</option>
          <option value="b2b_sale">Venta B2B</option>
          <option value="pickup">Retiro</option>
          <option value="technical_support">Soporte tecnico</option>
          <option value="case_reception">Recepcion de casos</option>
          <option value="installation">Instalacion</option>
        </select>
        <button type="submit">Filtrar</button>
      </form>
      <DataTable columns={["Punto", "Tipo", "Ciudad", "Servicios", "Contacto", "Estado"]}>
        {locations.map((location) => (
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
            <td>{location.availableServices.join(", ")}</td>
            <td>{location.whatsapp ?? location.phone}</td>
            <td>
              <StatusBadge status={location.status} />
            </td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}
