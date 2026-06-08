import type { CountryCode, CurrencyCode, EntityStatus, Money } from "./base";

export type ProductType = "machine" | "spare_part" | "accessory" | "service" | "project";
export type TechnicalAttributeType = "text" | "number" | "boolean" | "select" | "multi_select" | "file" | "range";

export interface BusinessVertical {
  id: string;
  name: string;
  slug: string;
  description?: string;
  status: EntityStatus;
  countries: CountryCode[];
  icon?: string;
  bannerImage?: string;
  requiresTechnicalAttributes: boolean;
  availableProductTypes: ProductType[];
  attributeSchema: TechnicalAttribute[];
}

export interface TechnicalAttribute {
  id: string;
  verticalId: string;
  name: string;
  type: TechnicalAttributeType;
  unit?: string;
  required: boolean;
  options?: string[];
  visibleInFilters: boolean;
  visibleInProductDetail: boolean;
  appliesToProductTypes: ProductType[];
}

export interface Product {
  id: string;
  sku: string;
  title: string;
  description?: string;
  verticalId: string;
  type: ProductType;
  brandId?: string;
  categoryId: string;
  sellerId?: string;
  publicPrice?: Money;
  b2bPrice?: Money;
  baseCurrency: CurrencyCode;
  stock: number;
  countryAvailability: CountryCode[];
  imageUrls: string[];
  technicalSheetUrl?: string;
  manualUrl?: string;
  warranty?: string;
  compatibilityIds: string[];
  requiresQuote: boolean;
  requiresInstallation: boolean;
  requiresTechnicalValidation: boolean;
  status: EntityStatus;
}

export interface ProductVariant {
  id: string;
  productId: string;
  sku: string;
  title: string;
  attributes: Record<string, string | number | boolean>;
  status: EntityStatus;
}

export type ProductPriceType = "public" | "b2b" | "promotional";

export interface ProductPrice {
  id: string;
  productId: string;
  variantId?: string;
  type: ProductPriceType;
  amount: number;
  currency: CurrencyCode;
  validFrom: string;
  validUntil?: string;
  changedBy: string;
}

export interface ProductStock {
  id: string;
  productId: string;
  variantId?: string;
  companyId: string;
  locationId?: string;
  available: number;
  reserved: number;
  lowStockThreshold: number;
  updatedAt: string;
}

export interface ProductCompatibility {
  id: string;
  sourceProductId: string;
  compatibleProductId: string;
  machineModel?: string;
  engineModel?: string;
  notes?: string;
  requiresTechnicalValidation: boolean;
  status: EntityStatus;
}

