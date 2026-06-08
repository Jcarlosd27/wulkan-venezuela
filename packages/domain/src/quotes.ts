import type { Money } from "./base";
import type { OrderItem } from "./orders";

export type QuoteRequesterType = "customer" | "hardware_store" | "technical_service" | "company";
export type QuoteStatus = "requested" | "under_review" | "answered" | "accepted" | "rejected" | "expired" | "converted";

export interface QuoteResponse {
  message: string;
  total?: Money;
  validUntil?: string;
  respondedBy: string;
  respondedAt: string;
}

export interface Quote {
  id: string;
  requesterType: QuoteRequesterType;
  requesterId: string;
  items: OrderItem[];
  message?: string;
  status: QuoteStatus;
  response?: QuoteResponse;
  validUntil?: string;
  convertedOrderId?: string;
}

