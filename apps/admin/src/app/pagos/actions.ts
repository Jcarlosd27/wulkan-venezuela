"use server";

import { firebaseCollections } from "@wulkan/config";
import { revalidatePath } from "next/cache";
import { writeFirestoreDocument } from "../../lib/firestore-writer";

export async function reviewPaymentAction(formData: FormData) {
  const paymentId = String(formData.get("paymentId") ?? "");
  const status = String(formData.get("status") ?? "");

  if (!paymentId || !["confirmed", "rejected"].includes(status)) {
    return;
  }

  const now = new Date().toISOString();

  await writeFirestoreDocument(firebaseCollections.payments, paymentId, {
    status,
    confirmedBy: "admin-form",
    confirmedAt: now,
    updatedAt: now
  });

  await writeFirestoreDocument(firebaseCollections.auditLogs, `audit-payment-${paymentId}-${Date.now()}`, {
    action: status === "confirmed" ? "payment_confirmed" : "payment_rejected",
    actorUserId: "admin-form",
    targetCollection: "payments",
    targetId: paymentId,
    after: { status },
    createdAt: now,
    origin: "admin_server_action"
  });

  revalidatePath("/pagos");
}
