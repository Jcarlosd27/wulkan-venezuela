import type { CurrencyCode } from "./base";

export type PaymentMethod = "mercado_pago" | "pago_movil" | "bank_transfer" | "whatsapp_assisted";
export type PaymentStatus = "created" | "pending" | "under_review" | "confirmed" | "rejected" | "refunded";

export interface Payment {
  id: string;
  orderId: string;
  companyId?: string;
  method: PaymentMethod;
  amountUsd: number;
  amountVes?: number;
  currency: CurrencyCode;
  exchangeRate?: number;
  referenceNumber?: string;
  proofImageUrl?: string;
  status: PaymentStatus;
  confirmedBy?: string;
  confirmedAt?: string;
}

