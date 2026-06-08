import type { Address, EntityStatus, GeoPoint } from "./base";

export type LocationType = "hardware_store" | "technical_service" | "pickup_point" | "distributor" | "installer";
export type LocationService = "retail_sale" | "b2b_sale" | "pickup" | "technical_support" | "case_reception" | "installation";

export interface CoverageArea {
  country: "VE";
  state: string;
  city?: string;
  municipality?: string;
  radiusKm?: number;
}

export interface AuthorizedLocation {
  id: string;
  name: string;
  type: LocationType;
  address: Address;
  coordinates: GeoPoint;
  phone: string;
  whatsapp?: string;
  schedule?: string;
  availableServices: LocationService[];
  coverageAreas: CoverageArea[];
  mapProviderPlaceId?: string;
  acceptsWalkIns: boolean;
  status: EntityStatus;
  companyId?: string;
}
