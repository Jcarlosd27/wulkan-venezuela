import { firebaseCollections } from "@wulkan/config";
import { NextResponse } from "next/server";
import { writeFirestoreDocument } from "../../../../lib/firestore-writer";

interface MobileOrderItemPayload {
  productId?: string;
  sku?: string;
  title?: string;
  quantity?: number;
  unitPriceUsd?: number;
  imageUrl?: string | null;
  requiresQuote?: boolean;
  requiresTechnicalValidation?: boolean;
}

interface MobileOrderPayload {
  source?: string;
  customer?: {
    id?: string;
    name?: string;
  };
  items?: MobileOrderItemPayload[];
  preview?: {
    subtotalUsd?: number;
    totalUsd?: number;
    totalVes?: number;
    exchangeRateUsdVes?: number;
    requiresOperatorReview?: boolean;
    blockingReasons?: string[];
  };
}

export async function POST(request: Request) {
  const payload = (await request.json()) as MobileOrderPayload;
  const items = normalizeItems(payload.items ?? []);

  if (items.length === 0) {
    return NextResponse.json({ error: "El carrito no tiene productos validos." }, { status: 400 });
  }

  const now = new Date().toISOString();
  const orderId = `ord-mobile-${Date.now()}`;
  const paymentId = `pay-${orderId}`;
  const customerId = payload.customer?.id || "customer-mobile-demo";
  const requiresOperatorReview = Boolean(payload.preview?.requiresOperatorReview);
  const subtotalUsd = roundMoney(payload.preview?.subtotalUsd ?? sumOrder(items));
  const totalUsd = roundMoney(payload.preview?.totalUsd ?? subtotalUsd);
  const exchangeRateUsdVes = Number(payload.preview?.exchangeRateUsdVes ?? 38.5);
  const totalVes = roundMoney(payload.preview?.totalVes ?? totalUsd * exchangeRateUsdVes);

  const order = {
    customerId,
    companyId: "wulkan-direct",
    items,
    subtotal: {
      amount: subtotalUsd,
      currency: "USD"
    },
    total: {
      amount: totalUsd,
      currency: "USD"
    },
    currency: "USD",
    exchangeRateUsdVes,
    status: requiresOperatorReview ? "payment_under_review" : "pending_payment",
    paymentId,
    notes: "Orden creada desde app movil Wulkan.",
    source: payload.source || "mobile_app",
    createdAt: now,
    updatedAt: now
  };

  const payment = {
    orderId,
    companyId: "wulkan-direct",
    method: "whatsapp_assisted",
    amountUsd: totalUsd,
    amountVes: totalVes,
    currency: "USD",
    exchangeRate: exchangeRateUsdVes,
    status: "under_review",
    createdAt: now,
    updatedAt: now
  };

  const auditLog = {
    actorUserId: customerId,
    actorRole: "customer",
    action: "order_created",
    targetCollection: firebaseCollections.orders,
    targetId: orderId,
    metadata: {
      source: payload.source || "mobile_app",
      paymentId,
      requiresOperatorReview,
      blockingReasons: payload.preview?.blockingReasons ?? []
    },
    createdAt: now
  };

  await Promise.all([
    writeFirestoreDocument(firebaseCollections.orders, orderId, order),
    writeFirestoreDocument(firebaseCollections.payments, paymentId, payment),
    writeFirestoreDocument(firebaseCollections.auditLogs, `audit-${orderId}-created`, auditLog)
  ]);

  return NextResponse.json({ orderId, paymentId, persisted: true });
}

function normalizeItems(items: MobileOrderItemPayload[]) {
  return items
    .map((item) => {
      const quantity = Math.max(1, Number(item.quantity ?? 1));
      const unitPriceUsd = roundMoney(Number(item.unitPriceUsd ?? 0));

      return {
        productId: String(item.productId ?? ""),
        sku: String(item.sku ?? ""),
        title: String(item.title ?? ""),
        quantity,
        unitPrice: {
          amount: unitPriceUsd,
          currency: "USD"
        },
        total: {
          amount: roundMoney(quantity * unitPriceUsd),
          currency: "USD"
        },
        imageUrl: item.imageUrl ?? null,
        requiresQuote: Boolean(item.requiresQuote),
        requiresTechnicalValidation: Boolean(item.requiresTechnicalValidation)
      };
    })
    .filter((item) => item.productId && item.sku && item.title && item.unitPrice.amount > 0);
}

function sumOrder(items: ReturnType<typeof normalizeItems>) {
  return roundMoney(items.reduce((total, item) => total + item.total.amount, 0));
}

function roundMoney(value: number) {
  return Number.isFinite(value) ? Number(value.toFixed(2)) : 0;
}
