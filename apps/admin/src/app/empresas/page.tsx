import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { ModuleActions } from "../../components/module-actions";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";

export default async function CompaniesPage() {
  const companies = await adminRepository.listCompanies();

  return (
    <AdminShell
      title="Empresas"
      description="Vendedores, ferreteros, servicios tecnicos e instaladores habilitados por Wulkan."
      actionLabel="Crear empresa"
    >
      <ModuleActions actions={[{ label: "Crear empresa", href: "/empresas/nueva" }]} />
      <DataTable columns={["Empresa", "Tipo", "Ubicacion", "B2B", "Estado"]}>
        {companies.map((company) => (
          <tr key={company.id}>
            <td>
              <strong>{company.commercialName}</strong>
              <small>{company.legalName}</small>
            </td>
            <td>{company.type}</td>
            <td>
              {company.address.city}, {company.address.state}
            </td>
            <td>{company.commercialTerms.b2bEnabled ? "Habilitado" : "No habilitado"}</td>
            <td>
              <StatusBadge status={company.status} />
            </td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}
