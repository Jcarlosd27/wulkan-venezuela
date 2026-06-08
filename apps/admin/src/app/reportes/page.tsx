import { formatUsd } from "@wulkan/shared";
import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";

export default async function ReportsPage() {
  const [reports, companies] = await Promise.all([adminRepository.listCompanyReports(), adminRepository.listCompanies()]);

  return (
    <AdminShell
      title="Reportes por empresa"
      description="Vista mock de facturacion, ordenes, tickets y alertas operativas por empresa."
    >
      <DataTable columns={["Empresa", "Periodo", "Facturacion", "Ordenes", "Ticket promedio", "Alertas", "Estado"]}>
        {reports.map((report) => {
          const company = companies.find((item) => item.id === report.companyId);

          return (
            <tr key={report.id}>
              <td>
                <strong>{company?.commercialName ?? report.companyId}</strong>
                <small>{report.companyId}</small>
              </td>
              <td>{report.period}</td>
              <td>{formatUsd(report.grossRevenueUsd)}</td>
              <td>
                B2C {report.orderCount}, B2B {report.purchaseOrderCount}
              </td>
              <td>{formatUsd(report.averageTicketUsd)}</td>
              <td>
                Pagos {report.pendingPayments}, casos {report.openServiceCases}
              </td>
              <td>
                <StatusBadge status={report.status} />
              </td>
            </tr>
          );
        })}
      </DataTable>
    </AdminShell>
  );
}

