import { formatUsd } from "@wulkan/shared";
import { AdminShell } from "../../components/admin-shell";
import { DataTable } from "../../components/data-table";
import { StatusBadge } from "../../components/status-badge";
import { adminRepository } from "../../lib/repositories";
import { reviewPaymentAction } from "./actions";

export default async function PaymentsPage() {
  const payments = await adminRepository.listPayments();

  return (
    <AdminShell
      title="Pagos"
      description="Intentos de pago, evidencias y validacion manual por operador."
      actionLabel="Validar pago"
    >
      <DataTable columns={["Pago", "Orden", "Metodo", "Monto", "Referencia", "Estado", "Accion"]}>
        {payments.map((payment) => (
          <tr key={payment.id}>
            <td>
              <strong>{payment.id}</strong>
              <small>{payment.exchangeRate ? `${payment.exchangeRate} VES/USD` : "Sin tasa"}</small>
            </td>
            <td>{payment.orderId}</td>
            <td>{payment.method}</td>
            <td>{formatUsd(payment.amountUsd)}</td>
            <td>{payment.referenceNumber ?? "Sin referencia"}</td>
            <td>
              <StatusBadge status={payment.status} />
            </td>
            <td>
              <form className="inlineActions" action={reviewPaymentAction}>
                <input type="hidden" name="paymentId" value={payment.id} />
                <button type="submit" name="status" value="confirmed">Confirmar</button>
                <button type="submit" name="status" value="rejected">Rechazar</button>
              </form>
            </td>
          </tr>
        ))}
      </DataTable>
    </AdminShell>
  );
}
