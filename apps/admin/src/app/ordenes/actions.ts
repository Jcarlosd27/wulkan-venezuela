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

function getPositiveNumber(formData: FormData, key: string, fallback: number): number {
  const value = Number(getString(formData, key));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function getQuantity(formData: FormData): number {
  return Math.max(1, Math.floor(getPositiveNumber(formData, "quantity", 1)));
}

export async function createOrderAction(formData: FormData) {
  const customerId = getString(formData, "customerId");
  const productId = getString(formData, "productId");
  const quantity = getQuantity(formData);
  const paymentMethod = getString(formData, "paymentMethod") || "pago_movil";
  const exchangeRateUsdVes = getPositiveNumber(formData, "exchangeRateUsdVes", 38.5);
  const notes = getString(formData, "notes");
  const product = productId ? await adminRepository.getProduct(productId) : undefined;

  if (!customerId || !product) {
    redirect("/ordenes/nueva?status=invalid");
  }

  const unitAmount = product.publicPrice?.amount ?? product.b2bPrice?.amount ?? 0;

  if (unitAmount <= 0) {
    redirect("/ordenes/nueva?status=invalid-price");
  }

  const totalAmount = Number((unitAmount * quantity).toFixed(2));
  const orderId = `ord-${Date.now()}`;
  const paymentId = `pay-${orderId}`;
  const now = new Date().toISOString();
  const sellerId = product.sellerId ?? "wulkan-direct";
  const requiresOperatorReview = product.requiresQuote || product.requiresTechnicalValidation || paymentMethod !== "mercado_pago";

  await writeFirestoreDocument(firebaseCollections.payments, paymentId, {
    orderId,
    companyId: sellerId,
    method: paymentMethod,
    amountUsd: totalAmount,
    amountVes: Number((totalAmount * exchangeRateUsdVes).toFixed(2)),
    currency: "USD",
    exchangeRate: exchangeRateUsdVes,
    status: requiresOperatorReview ? "under_review" : "pending",
    createdAt: now,
    updatedAt: now
  });

  await writeFirestoreDocument(firebaseCollections.orders, orderId, {
    customerId,
    companyId: sellerId,
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
    exchangeRateUsdVes,
    status: requiresOperatorReview ? "payment_under_review" : "pending_payment",
    paymentId,
    notes,
    createdAt: now,
    updatedAt: now
  });

  await writeFirestoreDocument(firebaseCollections.auditLogs, `audit-${orderId}-created`, {
    actorUserId: "admin-form",
    actorRole: "wulkan_operator",
    action: "order_created",
    targetCollection: firebaseCollections.orders,
    targetId: orderId,
    metadata: {
      source: "admin_panel",
      paymentId,
      requiresOperatorReview
    },
    createdAt: now
  });

  revalidatePath("/ordenes");
  revalidatePath("/ventas");
  redirect("/ordenes?status=order-created");
}
