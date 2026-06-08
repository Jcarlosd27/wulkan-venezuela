import type { Address, CurrencyCode, Money } from "./base";

export type OrderStatus =
  | "draft"
  | "pending_payment"
  | "payment_under_review"
  | "paid"
  | "preparing"
  | "ready_for_pickup"
  | "shipped"
  | "delivered"
  | "cancelled"
  | "refunded";

export type PurchaseOrderStatus =
  | "draft"
  | "submitted"
  | "under_wulkan_review"
  | "approved"
  | "modified"
  | "rejected"
  | "preparing"
  | "shipped"
  | "closed";

export interface OrderItem {
  productId: string;
  sku: string;
  title: string;
  quantity: number;
  unitPrice: Money;
  total: Money;
}

export interface Order {
  id: string;
  customerId: string;
  companyId?: string;
  items: OrderItem[];
  subtotal: Money;
  discounts?: Money;
  total: Money;
  currency: CurrencyCode;
  exchangeRateUsdVes?: number;
  status: OrderStatus;
  deliveryAddress?: Address;
  paymentId?: string;
  notes?: string;
}

export interface PurchaseOrder {
  id: string;
  requesterCompanyId: string;
  requesterUserId: string;
  items: OrderItem[];
  subtotal: Money;
  discounts?: Money;
  total: Money;
  currency: CurrencyCode;
  status: PurchaseOrderStatus;
  notes?: string;
  approvedBy?: string;
  requestedDeliveryDate?: string;
  referenceDocumentUrl?: string;
  reviewedAt?: string;
  rejectionReason?: string;
}

export type ReplenishmentRequestStatus = "requested" | "quoted" | "approved" | "rejected" | "converted";

export interface ReplenishmentRequest {
  id: string;
  requesterCompanyId: string;
  requesterUserId: string;
  productId?: string;
  sku?: string;
  description: string;
  requestedQuantity: number;
  status: ReplenishmentRequestStatus;
  quoteId?: string;
  convertedPurchaseOrderId?: string;
  createdAt: string;
  updatedAt: string;
}
