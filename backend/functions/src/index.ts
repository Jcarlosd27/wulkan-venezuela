import { initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";
import { getFirestore } from "firebase-admin/firestore";
import type { Query } from "firebase-admin/firestore";
import { HttpsError, onCall } from "firebase-functions/v2/https";

type ManualPaymentDecision = "confirmed" | "rejected";
type OrderStatus =
  | "pending_payment"
  | "payment_under_review"
  | "paid"
  | "preparing"
  | "ready_for_pickup"
  | "shipped"
  | "delivered"
  | "cancelled"
  | "refunded";
type ServiceCaseStatus =
  | "received"
  | "diagnosed"
  | "waiting_approval"
  | "waiting_part"
  | "in_repair"
  | "repaired"
  | "delivered"
  | "closed"
  | "warranty_rejected";
type PurchaseOrderStatus = "approved" | "modified" | "rejected" | "preparing" | "shipped" | "closed";
type ServicePartDecision = "approved" | "rejected";
type UserRole =
  | "super_admin"
  | "wulkan_admin"
  | "wulkan_operator"
  | "company_owner"
  | "company_seller"
  | "hardware_store_owner"
  | "hardware_store_buyer"
  | "technical_service_owner"
  | "technical_service_operator"
  | "installer"
  | "customer";

interface ProductSnapshot {
  sku?: string;
  title?: string;
  publicPrice?: {
    amount?: number;
    currency?: string;
  };
  requiresQuote?: boolean;
  requiresTechnicalValidation?: boolean;
}

interface LocationSnapshot {
  name?: string;
  type?: string;
  status?: string;
  coordinates?: {
    lat?: number;
    lng?: number;
  };
  availableServices?: string[];
  address?: {
    state?: string;
    city?: string;
    line1?: string;
  };
}

initializeApp();

const db = getFirestore();

function isWulkanStaffRole(role: unknown): boolean {
  return role === "super_admin" || role === "wulkan_admin" || role === "wulkan_operator";
}

function isWulkanAdminRole(role: unknown): boolean {
  return role === "super_admin" || role === "wulkan_admin";
}

function calculateDistanceKm(origin: { lat: number; lng: number }, destination: { lat: number; lng: number }): number {
  const toRadians = (value: number) => (value * Math.PI) / 180;
  const earthRadiusKm = 6371;
  const deltaLat = toRadians(destination.lat - origin.lat);
  const deltaLng = toRadians(destination.lng - origin.lng);
  const originLat = toRadians(origin.lat);
  const destinationLat = toRadians(destination.lat);
  const haversine =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(originLat) * Math.cos(destinationLat) * Math.sin(deltaLng / 2) ** 2;

  return Number((earthRadiusKm * 2 * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine))).toFixed(2));
}

export const confirmManualPayment = onCall(async (request) => {
  const actor = request.auth;

  if (!actor) {
    throw new HttpsError("unauthenticated", "Debes iniciar sesion.");
  }

  const role = actor.token.role;
  const canConfirm = isWulkanStaffRole(role);

  if (!canConfirm) {
    throw new HttpsError("permission-denied", "No tienes permiso para confirmar pagos.");
  }

  const { paymentId, status } = request.data as {
    paymentId?: string;
    status?: ManualPaymentDecision;
  };

  if (!paymentId || (status !== "confirmed" && status !== "rejected")) {
    throw new HttpsError("invalid-argument", "paymentId y status valido son obligatorios.");
  }

  const paymentRef = db.collection("payments").doc(paymentId);
  const paymentSnap = await paymentRef.get();

  if (!paymentSnap.exists) {
    throw new HttpsError("not-found", "Pago no encontrado.");
  }

  await db.runTransaction(async (transaction) => {
    transaction.update(paymentRef, {
      status,
      confirmedBy: actor.uid,
      confirmedAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    });

    transaction.create(db.collection("audit_logs").doc(), {
      action: status === "confirmed" ? "payment_confirmed" : "payment_rejected",
      actorUserId: actor.uid,
      targetCollection: "payments",
      targetId: paymentId,
      after: { status },
      createdAt: new Date().toISOString(),
      origin: "cloud_function"
    });
  });

  return { ok: true };
});

export const createSecureOrder = onCall(async (request) => {
  const actor = request.auth;

  if (!actor) {
    throw new HttpsError("unauthenticated", "Debes iniciar sesion.");
  }

  const { items } = request.data as {
    items?: Array<{
      productId?: string;
      quantity?: number;
    }>;
  };

  if (!items?.length) {
    throw new HttpsError("invalid-argument", "La orden requiere al menos un item.");
  }

  const normalizedItems = items.map((item) => {
    if (!item.productId || !item.quantity || item.quantity <= 0) {
      throw new HttpsError("invalid-argument", "Cada item requiere productId y cantidad valida.");
    }

    return {
      productId: item.productId,
      quantity: item.quantity
    };
  });

  const now = new Date().toISOString();
  const orderRef = db.collection("orders").doc();
  const paymentRef = db.collection("payments").doc();
  const productRefs = normalizedItems.map((item) => db.collection("products").doc(item.productId));
  const productSnaps = await db.getAll(...productRefs);
  const orderItems = normalizedItems.map((item, index) => {
    const productSnap = productSnaps[index];

    if (!productSnap?.exists) {
      throw new HttpsError("not-found", `Producto no encontrado: ${item.productId}`);
    }

    const product = productSnap.data() as ProductSnapshot;
    const unitPrice = product.publicPrice?.amount;

    if (!unitPrice || product.publicPrice?.currency !== "USD") {
      throw new HttpsError("failed-precondition", `Producto sin precio publico USD: ${item.productId}`);
    }

    return {
      productId: item.productId,
      sku: product.sku ?? item.productId,
      title: product.title ?? item.productId,
      quantity: item.quantity,
      unitPrice: { amount: unitPrice, currency: "USD" },
      total: { amount: Number((unitPrice * item.quantity).toFixed(2)), currency: "USD" },
      requiresQuote: product.requiresQuote ?? false,
      requiresTechnicalValidation: product.requiresTechnicalValidation ?? false
    };
  });
  const subtotal = Number(orderItems.reduce((total, item) => total + item.total.amount, 0).toFixed(2));
  const requiresOperatorReview = orderItems.some((item) => item.requiresQuote || item.requiresTechnicalValidation);
  const status: OrderStatus = requiresOperatorReview ? "payment_under_review" : "pending_payment";

  await orderRef.create({
    customerId: actor.uid,
    items: orderItems,
    subtotal: { amount: subtotal, currency: "USD" },
    total: { amount: subtotal, currency: "USD" },
    status,
    currency: "USD",
    paymentId: paymentRef.id,
    requiresOperatorReview,
    createdAt: now,
    updatedAt: now,
    createdBy: actor.uid
  });

  await paymentRef.create({
    orderId: orderRef.id,
    method: "bank_transfer",
    amountUsd: subtotal,
    currency: "USD",
    status: requiresOperatorReview ? "under_review" : "created",
    createdAt: now,
    updatedAt: now,
    createdBy: actor.uid
  });

  await db.collection("audit_logs").add({
    action: "order_status_changed",
    actorUserId: actor.uid,
    targetCollection: "orders",
    targetId: orderRef.id,
    after: { status, totalUsd: subtotal, paymentId: paymentRef.id },
    createdAt: now,
    origin: "cloud_function"
  });

  return { ok: true, orderId: orderRef.id, paymentId: paymentRef.id, totalUsd: subtotal, status };
});

export const changeOrderStatus = onCall(async (request) => {
  const actor = request.auth;

  if (!actor) {
    throw new HttpsError("unauthenticated", "Debes iniciar sesion.");
  }

  if (!isWulkanStaffRole(actor.token.role)) {
    throw new HttpsError("permission-denied", "No tienes permiso para cambiar estados de orden.");
  }

  const { orderId, status } = request.data as {
    orderId?: string;
    status?: OrderStatus;
  };

  const allowedStatuses: OrderStatus[] = [
    "pending_payment",
    "payment_under_review",
    "paid",
    "preparing",
    "ready_for_pickup",
    "shipped",
    "delivered",
    "cancelled",
    "refunded"
  ];

  if (!orderId || !status || !allowedStatuses.includes(status)) {
    throw new HttpsError("invalid-argument", "orderId y status valido son obligatorios.");
  }

  const now = new Date().toISOString();
  const orderRef = db.collection("orders").doc(orderId);
  const orderSnap = await orderRef.get();

  if (!orderSnap.exists) {
    throw new HttpsError("not-found", "Orden no encontrada.");
  }

  await db.runTransaction(async (transaction) => {
    const before = orderSnap.data();

    transaction.update(orderRef, {
      status,
      updatedAt: now,
      updatedBy: actor.uid
    });

    transaction.create(db.collection("audit_logs").doc(), {
      action: "order_status_changed",
      actorUserId: actor.uid,
      targetCollection: "orders",
      targetId: orderId,
      before: { status: before?.status },
      after: { status },
      createdAt: now,
      origin: "cloud_function"
    });
  });

  return { ok: true };
});

export const updateServiceCase = onCall(async (request) => {
  const actor = request.auth;

  if (!actor) {
    throw new HttpsError("unauthenticated", "Debes iniciar sesion.");
  }

  const canUpdate =
    isWulkanStaffRole(actor.token.role) ||
    actor.token.role === "technical_service_owner" ||
    actor.token.role === "technical_service_operator";

  if (!canUpdate) {
    throw new HttpsError("permission-denied", "No tienes permiso para actualizar casos tecnicos.");
  }

  const { serviceCaseId, status, diagnosis, eventMessage } = request.data as {
    serviceCaseId?: string;
    status?: ServiceCaseStatus;
    diagnosis?: string;
    eventMessage?: string;
  };

  const allowedStatuses: ServiceCaseStatus[] = [
    "received",
    "diagnosed",
    "waiting_approval",
    "waiting_part",
    "in_repair",
    "repaired",
    "delivered",
    "closed",
    "warranty_rejected"
  ];

  if (!serviceCaseId || (status && !allowedStatuses.includes(status))) {
    throw new HttpsError("invalid-argument", "serviceCaseId y status valido son obligatorios.");
  }

  const now = new Date().toISOString();
  const caseRef = db.collection("service_cases").doc(serviceCaseId);
  const caseSnap = await caseRef.get();

  if (!caseSnap.exists) {
    throw new HttpsError("not-found", "Caso tecnico no encontrado.");
  }

  await db.runTransaction(async (transaction) => {
    const before = caseSnap.data();
    const patch: Record<string, unknown> = {
      updatedAt: now,
      updatedBy: actor.uid
    };

    if (status) {
      patch.status = status;
      if (status === "closed") {
        patch.closedAt = now;
      }
    }

    if (diagnosis) {
      patch.diagnosis = diagnosis;
    }

    transaction.update(caseRef, patch);

    const eventRef = db.collection("service_case_events").doc();
    transaction.create(eventRef, {
      serviceCaseId,
      type: diagnosis ? "diagnosis_added" : "status_changed",
      message: eventMessage ?? "Caso tecnico actualizado.",
      actorUserId: actor.uid,
      createdAt: now,
      statusAfter: status ?? before?.status
    });

    transaction.create(db.collection("audit_logs").doc(), {
      action: "service_case_updated",
      actorUserId: actor.uid,
      targetCollection: "service_cases",
      targetId: serviceCaseId,
      before: { status: before?.status, diagnosis: before?.diagnosis },
      after: { status: status ?? before?.status, diagnosis },
      createdAt: now,
      origin: "cloud_function"
    });
  });

  return { ok: true };
});

export const reviewPurchaseOrder = onCall(async (request) => {
  const actor = request.auth;

  if (!actor) {
    throw new HttpsError("unauthenticated", "Debes iniciar sesion.");
  }

  if (!isWulkanStaffRole(actor.token.role)) {
    throw new HttpsError("permission-denied", "No tienes permiso para revisar ordenes B2B.");
  }

  const { purchaseOrderId, status, notes, rejectionReason } = request.data as {
    purchaseOrderId?: string;
    status?: PurchaseOrderStatus;
    notes?: string;
    rejectionReason?: string;
  };
  const allowedStatuses: PurchaseOrderStatus[] = ["approved", "modified", "rejected", "preparing", "shipped", "closed"];

  if (!purchaseOrderId || !status || !allowedStatuses.includes(status)) {
    throw new HttpsError("invalid-argument", "purchaseOrderId y status valido son obligatorios.");
  }

  if (status === "rejected" && !rejectionReason) {
    throw new HttpsError("invalid-argument", "La razon de rechazo es obligatoria.");
  }

  const now = new Date().toISOString();
  const purchaseOrderRef = db.collection("purchase_orders").doc(purchaseOrderId);
  const purchaseOrderSnap = await purchaseOrderRef.get();

  if (!purchaseOrderSnap.exists) {
    throw new HttpsError("not-found", "Orden B2B no encontrada.");
  }

  await db.runTransaction(async (transaction) => {
    const before = purchaseOrderSnap.data();
    const patch: Record<string, unknown> = {
      status,
      reviewedAt: now,
      approvedBy: actor.uid,
      updatedAt: now,
      updatedBy: actor.uid
    };

    if (notes) {
      patch.notes = notes;
    }

    if (rejectionReason) {
      patch.rejectionReason = rejectionReason;
    }

    transaction.update(purchaseOrderRef, patch);
    transaction.create(db.collection("audit_logs").doc(), {
      action: "purchase_order_reviewed",
      actorUserId: actor.uid,
      targetCollection: "purchase_orders",
      targetId: purchaseOrderId,
      before: { status: before?.status },
      after: { status, notes, rejectionReason },
      createdAt: now,
      origin: "cloud_function"
    });
  });

  return { ok: true };
});

export const reviewServicePartRequest = onCall(async (request) => {
  const actor = request.auth;

  if (!actor) {
    throw new HttpsError("unauthenticated", "Debes iniciar sesion.");
  }

  if (!isWulkanStaffRole(actor.token.role)) {
    throw new HttpsError("permission-denied", "No tienes permiso para aprobar repuestos de servicio tecnico.");
  }

  const { serviceCaseId, decision, part, notes } = request.data as {
    serviceCaseId?: string;
    decision?: ServicePartDecision;
    part?: {
      productId?: string;
      sku?: string;
      description?: string;
      quantity?: number;
    };
    notes?: string;
  };

  if (!serviceCaseId || (decision !== "approved" && decision !== "rejected") || !part?.description || !part.quantity) {
    throw new HttpsError("invalid-argument", "serviceCaseId, decision y part valido son obligatorios.");
  }

  const now = new Date().toISOString();
  const caseRef = db.collection("service_cases").doc(serviceCaseId);
  const caseSnap = await caseRef.get();

  if (!caseSnap.exists) {
    throw new HttpsError("not-found", "Caso tecnico no encontrado.");
  }

  await db.runTransaction(async (transaction) => {
    const before = caseSnap.data();
    const nextStatus: ServiceCaseStatus = decision === "approved" ? "waiting_part" : "waiting_approval";

    transaction.update(caseRef, {
      status: nextStatus,
      updatedAt: now,
      updatedBy: actor.uid
    });

    transaction.create(db.collection("service_case_events").doc(), {
      serviceCaseId,
      type: decision === "approved" ? "part_requested" : "status_changed",
      message:
        notes ??
        (decision === "approved"
          ? "Repuesto aprobado para reserva operativa."
          : "Repuesto rechazado por operador Wulkan."),
      actorUserId: actor.uid,
      createdAt: now,
      statusAfter: nextStatus,
      part
    });

    transaction.create(db.collection("audit_logs").doc(), {
      action: decision === "approved" ? "service_part_approved" : "service_part_rejected",
      actorUserId: actor.uid,
      targetCollection: "service_cases",
      targetId: serviceCaseId,
      before: { status: before?.status },
      after: { status: nextStatus, part },
      createdAt: now,
      origin: "cloud_function"
    });
  });

  return { ok: true };
});

export const findNearbyLocations = onCall(async (request) => {
  const { lat, lng, service, limit } = request.data as {
    lat?: number;
    lng?: number;
    service?: string;
    limit?: number;
  };

  if (typeof lat !== "number" || typeof lng !== "number") {
    throw new HttpsError("invalid-argument", "lat y lng son obligatorios.");
  }

  const maxResults = Math.min(Math.max(limit ?? 10, 1), 25);
  let query: Query = db.collection("locations").where("status", "==", "active");

  if (service) {
    query = query.where("availableServices", "array-contains", service);
  }

  const snapshot = await query.get();
  const locations = snapshot.docs
    .map((doc) => {
      const location = doc.data() as LocationSnapshot;

      if (typeof location.coordinates?.lat !== "number" || typeof location.coordinates.lng !== "number") {
        return undefined;
      }

      return {
        id: doc.id,
        name: location.name ?? doc.id,
        type: location.type,
        service,
        address: location.address,
        distanceKm: calculateDistanceKm({ lat, lng }, { lat: location.coordinates.lat, lng: location.coordinates.lng })
      };
    })
    .filter((location): location is NonNullable<typeof location> => Boolean(location))
    .sort((current, next) => current.distanceKm - next.distanceKm)
    .slice(0, maxResults);

  return { ok: true, locations };
});

export const setUserRoleClaims = onCall(async (request) => {
  const actor = request.auth;

  if (!actor) {
    throw new HttpsError("unauthenticated", "Debes iniciar sesion.");
  }

  if (!isWulkanAdminRole(actor.token.role)) {
    throw new HttpsError("permission-denied", "No tienes permiso para administrar roles.");
  }

  const { uid, role, companyId, permissions } = request.data as {
    uid?: string;
    role?: UserRole;
    companyId?: string;
    permissions?: string[];
  };
  const allowedRoles: UserRole[] = [
    "super_admin",
    "wulkan_admin",
    "wulkan_operator",
    "company_owner",
    "company_seller",
    "hardware_store_owner",
    "hardware_store_buyer",
    "technical_service_owner",
    "technical_service_operator",
    "installer",
    "customer"
  ];

  if (!uid || !role || !allowedRoles.includes(role)) {
    throw new HttpsError("invalid-argument", "uid y role valido son obligatorios.");
  }

  const now = new Date().toISOString();
  const claims: Record<string, unknown> = { role };

  if (companyId) {
    claims.companyId = companyId;
  }

  if (permissions?.length) {
    claims.permissions = permissions;
  }

  await getAuth().setCustomUserClaims(uid, claims);
  await db.collection("users").doc(uid).set(
    {
      role,
      companyId: companyId ?? null,
      permissions: permissions ?? [],
      updatedAt: now,
      updatedBy: actor.uid
    },
    { merge: true }
  );

  await db.collection("audit_logs").add({
    action: "user_claims_updated",
    actorUserId: actor.uid,
    targetCollection: "users",
    targetId: uid,
    after: claims,
    createdAt: now,
    origin: "cloud_function"
  });

  return { ok: true };
});
