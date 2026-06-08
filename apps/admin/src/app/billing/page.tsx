import { formatUsd } from "@wulkan/shared";
import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";

export default async function BillingPage() {
  const [reports, charges, companies] = await Promise.all([
    adminRepository.listCompanyReports(),
    adminRepository.listPlatformCharges(),
    adminRepository.listCompanies()
  ]);

  return (
    <AdminShell
      title="Billing medido"
      description="Medicion mock de facturacion, comisiones y cargos de plataforma."
    >
      <DataTable columns={["Empresa", "Periodo", "Facturacion", "Comision/Cargo", "Concepto", "Estado"]}>
        {charges.map((charge) => {
          const company = companies.find((item) => item.id === charge.companyId);
          const report = reports.find((item) => item.companyId === charge.companyId && item.period === charge.period);

          return (
            <tr key={charge.id}>
              <td>
                <strong>{company?.commercialName ?? charge.companyId}</strong>
                <small>{charge.companyId}</small>
              </td>
              <td>{charge.period}</td>
              <td>{formatUsd(report?.grossRevenueUsd ?? 0)}</td>
              <td>{formatUsd(charge.amountUsd)}</td>
              <td>{charge.concept}</td>
              <td>
                <StatusBadge status={charge.status} />
              </td>
            </tr>
          );
        })}
      </DataTable>
    </AdminShell>
  );
}

