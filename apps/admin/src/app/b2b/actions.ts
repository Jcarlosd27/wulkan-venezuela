"use server";

import { firebaseCollections } from "@wulkan/config";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { writeFirestoreDocument } from "../../lib/firestore-writer";
import { adminRepository } from "../../lib/repositories";

function getString(formData: FormData, key: string): string {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function getQuantity(formData: FormData): number {
  const value = Math.floor(Number(getString(formData, "quantity")));
  return Number.isFinite(value) && value > 0 ? value : 1;
}

export async function createPurchaseOrderAction(formData: FormData) {
  const requesterCompanyId = getString(formData, "requesterCompanyId");
  const productId = getString(formData, "productId");
  const quantity = getQuantity(formData);
  const product = productId ? await adminRepository.getProduct(productId) : undefined;

  if (!requesterCompanyId || !product) {
    redirect("/b2b/nueva?status=invalid");
  }

  const unitAmount = product.b2bPrice?.amount ?? product.publicPrice?.amount ?? 0;
  const totalAmount = Number((unitAmount * quantity).toFixed(2));
  const purchaseOrderId = `po-${Date.now()}`;

  await writeFirestoreDocument(firebaseCollections.purchaseOrders, purchaseOrderId, {
    requesterCompanyId,
    requesterUserId: "admin-form",
    items: [
      {
        productId: product.id,
        sku: product.sku,
        title: product.title,
        quantity,
        unitPrice: { amount: unitAmount, currency: "USD" },
        total: { amount: totalAmount, currency: "USD" }
      }
    ],
    subtotal: { amount: totalAmount, currency: "USD" },
    total: { amount: totalAmount, currency: "USD" },
    currency: "USD",
    status: "under_wulkan_review",
    requestedDeliveryDate: getString(formData, "requestedDeliveryDate"),
    notes: getString(formData, "notes"),
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  });

  revalidatePath("/b2b");
  redirect("/b2b?status=purchase-order-created");
}
