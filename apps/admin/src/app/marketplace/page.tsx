import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { ModuleActions } from "../../components/module-actions";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";

export default async function MarketplacePage() {
  const [applications, companies, scores] = await Promise.all([
    adminRepository.listMarketplaceApplications(),
    adminRepository.listCompanies(),
    adminRepository.listSellerQualityScores()
  ]);

  return (
    <AdminShell
      title="Marketplace controlado"
      description="Solicitudes de empresas vendedoras, calidad operativa y categorias habilitadas."
      actionLabel="Revisar solicitud"
    >
      <ModuleActions actions={[{ label: "Aprobacion productos", href: "/marketplace/productos" }]} />
      <DataTable columns={["Solicitud", "Empresa", "Categorias", "Calidad", "Estado"]}>
        {applications.map((application) => {
          const company = companies.find((item) => item.id === application.companyId);
          const score = scores.find((item) => item.companyId === application.companyId);

          return (
            <tr key={application.id}>
              <td>
                <strong>{application.id}</strong>
                <small>{application.companyType}</small>
              </td>
              <td>{company?.commercialName ?? application.companyId}</td>
              <td>{application.requestedVerticalIds.join(", ")}</td>
              <td>
                {score ? `${Math.round(score.fulfillmentRate * 100)}% cumplimiento, ${score.openIncidents} incidentes` : "Sin score"}
              </td>
              <td>
                <StatusBadge status={application.status} />
              </td>
            </tr>
          );
        })}
      </DataTable>
    </AdminShell>
  );
}
