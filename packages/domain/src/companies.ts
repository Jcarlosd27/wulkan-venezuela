import type { Address, EntityStatus, GeoPoint } from "./base";

export type CompanyType =
  | "seller"
  | "hardware_store"
  | "technical_service"
  | "distributor"
  | "installer";

export interface CompanyContact {
  name: string;
  email?: string;
  phone: string;
  whatsapp?: string;
}

export interface CommercialTerms {
  b2bEnabled: boolean;
  creditEnabled: boolean;
  defaultDiscountPercent?: number;
  minimumPurchaseUsd?: number;
  paymentTermsDays?: number;
  priceListId?: string;
  notes?: string;
}

export interface Company {
  id: string;
  legalName: string;
  commercialName: string;
  taxId?: string;
  type: CompanyType;
  status: EntityStatus;
  contacts: CompanyContact[];
  address: Address;
  location?: GeoPoint;
  commercialTerms: CommercialTerms;
  activeVerticalIds: string[];
}
