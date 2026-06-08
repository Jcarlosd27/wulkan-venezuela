export const WULKAN_COUNTRY = "VE" as const;
export const WULKAN_PRIMARY_CURRENCY = "USD" as const;
export const WULKAN_SECONDARY_CURRENCY = "VES" as const;

export function formatUsd(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD"
  }).format(amount);
}

export function convertUsdToVes(amountUsd: number, exchangeRate: number): number {
  return Number((amountUsd * exchangeRate).toFixed(2));
}

export function normalizeSearchText(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

export interface GeoCoordinate {
  lat: number;
  lng: number;
}

export interface DistanceResult<T> {
  item: T;
  distanceKm: number;
}

function toRadians(value: number): number {
  return (value * Math.PI) / 180;
}

export function calculateDistanceKm(origin: GeoCoordinate, destination: GeoCoordinate): number {
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

export function sortByDistance<T>(
  items: T[],
  origin: GeoCoordinate,
  getCoordinate: (item: T) => GeoCoordinate
): Array<DistanceResult<T>> {
  return items
    .map((item) => ({ item, distanceKm: calculateDistanceKm(origin, getCoordinate(item)) }))
    .sort((current, next) => current.distanceKm - next.distanceKm);
}

export interface CheckoutLineInput {
  quantity: number;
  unitPriceUsd: number;
  requiresQuote?: boolean;
  requiresTechnicalValidation?: boolean;
}

export interface CheckoutCalculation {
  subtotalUsd: number;
  totalUsd: number;
  totalVes?: number;
  requiresOperatorReview: boolean;
  blockingReasons: string[];
}

export function calculateCheckout(lines: CheckoutLineInput[], exchangeRateUsdVes?: number): CheckoutCalculation {
  const subtotalUsd = Number(
    lines.reduce((total, line) => total + line.quantity * line.unitPriceUsd, 0).toFixed(2)
  );
  const blockingReasons = [
    ...new Set(
      lines.flatMap((line) => {
        const reasons: string[] = [];

        if (line.requiresQuote) {
          reasons.push("requires_quote");
        }

        if (line.requiresTechnicalValidation) {
          reasons.push("requires_technical_validation");
        }

        return reasons;
      })
    )
  ];

  const calculation: CheckoutCalculation = {
    subtotalUsd,
    totalUsd: subtotalUsd,
    requiresOperatorReview: blockingReasons.length > 0,
    blockingReasons
  };

  if (exchangeRateUsdVes) {
    calculation.totalVes = convertUsdToVes(subtotalUsd, exchangeRateUsdVes);
  }

  return calculation;
}
