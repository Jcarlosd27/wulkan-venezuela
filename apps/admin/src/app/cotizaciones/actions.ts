"use server";

import { firebaseCollections } from "@wulkan/config";
import { revalidatePath } from "next/cache";
import { writeFirestoreDocument } from "../../lib/firestore-writer";

export async function respondQuoteAction(formData: FormData) {
  const quoteId = String(formData.get("quoteId") ?? "");
  const status = String(formData.get("status") ?? "");

  if (!quoteId || !["answered", "rejected", "converted"].includes(status)) {
    return;
  }

  const now = new Date().toISOString();

  await writeFirestoreDocument(firebaseCollections.quotes, quoteId, {
    status,
    respondedBy: "admin-form",
    respondedAt: now,
    updatedAt: now
  });

  await writeFirestoreDocument(firebaseCollections.auditLogs, `audit-quote-${quoteId}-${Date.now()}`, {
    action: "quote_status_changed",
    actorUserId: "admin-form",
    targetCollection: "quotes",
    targetId: quoteId,
    after: { status },
    createdAt: now,
    origin: "admin_server_action"
  });

  revalidatePath("/cotizaciones");
}
