import { formatUsd } from "@wulkan/shared";
import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";
import { respondQuoteAction } from "./actions";

export default async function QuotesPage() {
  const quotes = await adminRepository.listQuotes();

  return (
    <AdminShell
      title="Cotizaciones"
      description="Solicitudes asistidas para repuestos, proyectos tecnicos y compras especiales."
      actionLabel="Responder"
    >
      <DataTable columns={["Cotizacion", "Solicitante", "Items", "Total estimado", "Mensaje", "Estado", "Accion"]}>
        {quotes.map((quote) => {
          const estimatedTotal = quote.items.reduce((total, item) => total + item.total.amount, 0);

          return (
            <tr key={quote.id}>
              <td>
                <strong>{quote.id}</strong>
                <small>{quote.requesterType}</small>
              </td>
              <td>{quote.requesterId}</td>
              <td>{quote.items.length}</td>
              <td>{formatUsd(estimatedTotal)}</td>
              <td>{quote.message ?? "Sin mensaje"}</td>
              <td>
                <StatusBadge status={quote.status} />
              </td>
              <td>
                <form className="inlineActions" action={respondQuoteAction}>
                  <input type="hidden" name="quoteId" value={quote.id} />
                  <button type="submit" name="status" value="answered">Responder</button>
                  <button type="submit" name="status" value="converted">Convertir</button>
                  <button type="submit" name="status" value="rejected">Rechazar</button>
                </form>
              </td>
            </tr>
          );
        })}
      </DataTable>
    </AdminShell>
  );
}
