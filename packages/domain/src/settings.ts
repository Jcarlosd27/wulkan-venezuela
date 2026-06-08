import type { CurrencyCode } from "./base";

export interface ExchangeRateSetting {
  id: string;
  baseCurrency: CurrencyCode;
  targetCurrency: CurrencyCode;
  rate: number;
  source: "manual" | "provider";
  activeFrom: string;
  updatedBy: string;
}

export interface AppSettings {
  id: string;
  country: "VE";
  primaryCurrency: "USD";
  secondaryCurrency: "VES";
  exchangeRate: ExchangeRateSetting;
  maintenanceMode: boolean;
  whatsappSupportNumber?: string;
}

