export type CountryCode = "VE";
export type CurrencyCode = "USD" | "VES";

export type EntityStatus = "active" | "inactive" | "pending" | "suspended" | "archived";

export interface EntityTimestamps {
  createdAt: string;
  updatedAt: string;
}

export interface AuditedEntity extends EntityTimestamps {
  createdBy: string;
  updatedBy?: string;
}

export interface Money {
  amount: number;
  currency: CurrencyCode;
}

export interface Address {
  country: CountryCode;
  state: string;
  city: string;
  municipality?: string;
  sector?: string;
  line1: string;
  reference?: string;
  phone: string;
}

export interface GeoPoint {
  lat: number;
  lng: number;
}

