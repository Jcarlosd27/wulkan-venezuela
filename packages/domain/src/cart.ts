import type { CurrencyCode, Money } from "./base";

export interface CartItem {
  productId: string;
  variantId?: string;
  sku: string;
  title: string;
  quantity: number;
  unitPrice: Money;
  requiresQuote: boolean;
  requiresTechnicalValidation: boolean;
}

export interface Cart {
  id: string;
  userId?: string;
  items: CartItem[];
  currency: CurrencyCode;
  subtotal: Money;
  estimatedTotal: Money;
  updatedAt: string;
}

export interface CheckoutSummary {
  cartId: string;
  subtotal: Money;
  exchangeRateUsdVes?: number;
  estimatedTotalUsd: number;
  estimatedTotalVes?: number;
  requiresOperatorReview: boolean;
  blockingReasons: string[];
}

