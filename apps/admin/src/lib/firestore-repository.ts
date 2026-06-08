import type {
  AppSettings,
  AuditLog,
  AuthorizedLocation,
  BusinessVertical,
  Company,
  CompanyPerformanceReport,
  MarketplaceApplication,
  MobileAnnouncement,
  Order,
  Payment,
  PlatformCharge,
  Product,
  ProductApproval,
  ProductCompatibility,
  ProductPrice,
  ProductStock,
  ProductVariant,
  PurchaseOrder,
  Quote,
  ReplenishmentRequest,
  SellerQualityScore,
  ServiceCase,
  ServiceCaseEvent,
  TechnicalProject,
  WulkanUser
} from "@wulkan/domain";
import type { LocationService, LocationType } from "@wulkan/domain";
import { firebaseCollections } from "@wulkan/config";
import type { GeoCoordinate } from "@wulkan/shared";
import { sortByDistance } from "@wulkan/shared";
import type { AdminRepository } from "./repositories";

type FirestorePrimitive = string | number | boolean | null;
interface FirestoreRecord {
  [key: string]: FirestoreValue;
}
interface FirestoreArray extends Array<FirestoreValue> {}
type FirestoreValue = FirestorePrimitive | FirestoreRecord | FirestoreArray;

interface FirestoreApiDocument {
  name: string;
  fields?: Record<string, FirestoreEncodedValue>;
}

interface FirestoreEncodedValue {
  nullValue?: null;
  booleanValue?: boolean;
  integerValue?: string;
  doubleValue?: number;
  timestampValue?: string;
  stringValue?: string;
  bytesValue?: string;
  referenceValue?: string;
  geoPointValue?: { latitude: number; longitude: number };
  arrayValue?: { values?: FirestoreEncodedValue[] };
  mapValue?: { fields?: Record<string, FirestoreEncodedValue> };
}

interface FirestoreListResponse {
  documents?: FirestoreApiDocument[];
}

export function shouldUseFirestoreRepository(): boolean {
  return process.env.WULKAN_ADMIN_DATA_SOURCE === "firestore" && Boolean(getFirestoreProjectId());
}

export function createFirestoreAdminRepository(): AdminRepository {
  return new FirestoreRestAdminRepository();
}

function getFirestoreProjectId(): string {
  return process.env.FIREBASE_PROJECT_ID ?? process.env.GOOGLE_CLOUD_PROJECT ?? process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "";
}

function getFirestoreBaseUrl(): string {
  const emulatorHost = process.env.FIRESTORE_EMULATOR_HOST;

  if (emulatorHost) {
    return `http://${emulatorHost}/v1/projects/${getFirestoreProjectId()}/databases/(default)/documents`;
  }

  return `https://firestore.googleapis.com/v1/projects/${getFirestoreProjectId()}/databases/(default)/documents`;
}

function getRequestHeaders(): HeadersInit {
  const token = process.env.FIRESTORE_REST_BEARER_TOKEN;
  const emulatorToken = process.env.FIRESTORE_EMULATOR_HOST ? "owner" : "";
  const headers: HeadersInit = { "Content-Type": "application/json" };

  if (token || emulatorToken) {
    headers.Authorization = `Bearer ${token || emulatorToken}`;
  }

  return headers;
}

function documentId(name: string): string {
  return name.split("/").at(-1) ?? name;
}

function decodeValue(value: FirestoreEncodedValue): FirestoreValue {
  if ("nullValue" in value) {
    return null;
  }

  if (typeof value.booleanValue === "boolean") {
    return value.booleanValue;
  }

  if (typeof value.integerValue === "string") {
    return Number(value.integerValue);
  }

  if (typeof value.doubleValue === "number") {
    return value.doubleValue;
  }

  if (typeof value.timestampValue === "string") {
    return value.timestampValue;
  }

  if (typeof value.stringValue === "string") {
    return value.stringValue;
  }

  if (typeof value.bytesValue === "string") {
    return value.bytesValue;
  }

  if (typeof value.referenceValue === "string") {
    return value.referenceValue;
  }

  if (value.geoPointValue) {
    return { lat: value.geoPointValue.latitude, lng: value.geoPointValue.longitude };
  }

  if (value.arrayValue) {
    return value.arrayValue.values?.map(decodeValue) ?? [];
  }

  if (value.mapValue) {
    return decodeFields(value.mapValue.fields ?? {});
  }

  return null;
}

function decodeFields(fields: Record<string, FirestoreEncodedValue>): FirestoreRecord {
  return Object.fromEntries(Object.entries(fields).map(([key, value]) => [key, decodeValue(value)]));
}

function decodeDocument<T extends { id: string }>(document: FirestoreApiDocument): T {
  return {
    id: documentId(document.name),
    ...decodeFields(document.fields ?? {})
  } as T;
}

class FirestoreRestAdminRepository implements AdminRepository {
  private async listCollection<T extends { id: string }>(collection: string): Promise<T[]> {
    const response = await fetch(`${getFirestoreBaseUrl()}/${collection}`, {
      headers: getRequestHeaders(),
      next: { revalidate: 0 }
    });

    if (!response.ok) {
      throw new Error(`Firestore list failed for ${collection}: ${response.status}`);
    }

    const payload = (await response.json()) as FirestoreListResponse;
    return payload.documents?.map((document) => decodeDocument<T>(document)) ?? [];
  }

  private async getDocument<T extends { id: string }>(collection: string, id: string): Promise<T | undefined> {
    const response = await fetch(`${getFirestoreBaseUrl()}/${collection}/${id}`, {
      headers: getRequestHeaders(),
      next: { revalidate: 0 }
    });

    if (response.status === 404) {
      return undefined;
    }

    if (!response.ok) {
      throw new Error(`Firestore get failed for ${collection}/${id}: ${response.status}`);
    }

    return decodeDocument<T>((await response.json()) as FirestoreApiDocument);
  }

  listVerticals() {
    return this.listCollection<BusinessVertical>(firebaseCollections.verticals);
  }

  getVertical(id: string) {
    return this.getDocument<BusinessVertical>(firebaseCollections.verticals, id);
  }

  listProducts() {
    return this.listCollection<Product>(firebaseCollections.products);
  }

  getProduct(id: string) {
    return this.getDocument<Product>(firebaseCollections.products, id);
  }

  listProductVariants(productId?: string) {
    return this.listFiltered<ProductVariant>(firebaseCollections.productVariants, (variant) => variant.productId === productId, productId);
  }

  listProductPrices(productId?: string) {
    return this.listFiltered<ProductPrice>(firebaseCollections.productPrices, (price) => price.productId === productId, productId);
  }

  listProductStock(productId?: string) {
    return this.listFiltered<ProductStock>(firebaseCollections.productStock, (stock) => stock.productId === productId, productId);
  }

  async listProductCompatibilities(productId?: string) {
    return this.listFiltered<ProductCompatibility>(
      firebaseCollections.productCompatibilities,
      (compatibility) =>
        compatibility.sourceProductId === productId || compatibility.compatibleProductId === productId,
      productId
    );
  }

  listCompanies() {
    return this.listCollection<Company>(firebaseCollections.companies);
  }

  listOrders() {
    return this.listCollection<Order>(firebaseCollections.orders);
  }

  getOrder(id: string) {
    return this.getDocument<Order>(firebaseCollections.orders, id);
  }

  listPurchaseOrders() {
    return this.listCollection<PurchaseOrder>(firebaseCollections.purchaseOrders);
  }

  getPurchaseOrder(id: string) {
    return this.getDocument<PurchaseOrder>(firebaseCollections.purchaseOrders, id);
  }

  listReplenishmentRequests() {
    return this.listCollection<ReplenishmentRequest>(firebaseCollections.replenishmentRequests);
  }

  listServiceCases() {
    return this.listCollection<ServiceCase>(firebaseCollections.serviceCases);
  }

  getServiceCase(id: string) {
    return this.getDocument<ServiceCase>(firebaseCollections.serviceCases, id);
  }

  listServiceCaseEvents(serviceCaseId?: string) {
    return this.listFiltered<ServiceCaseEvent>(
      firebaseCollections.serviceCaseEvents,
      (event) => event.serviceCaseId === serviceCaseId,
      serviceCaseId
    );
  }

  listPayments() {
    return this.listCollection<Payment>(firebaseCollections.payments);
  }

  listQuotes() {
    return this.listCollection<Quote>(firebaseCollections.quotes);
  }

  async listLocations(filters?: { type?: LocationType; service?: LocationService }) {
    const allLocations = await this.listCollection<AuthorizedLocation>(firebaseCollections.locations);

    return allLocations.filter((location) => {
      const matchesType = !filters?.type || location.type === filters.type;
      const matchesService = !filters?.service || location.availableServices.includes(filters.service);

      return matchesType && matchesService;
    });
  }

  async listNearbyLocations(
    origin: GeoCoordinate,
    filters?: { type?: LocationType; service?: LocationService; limit?: number }
  ) {
    const filteredLocations = await this.listLocations(filters);
    const nearbyLocations = sortByDistance(filteredLocations, origin, (location) => location.coordinates).map(
      ({ item, distanceKm }) => ({ location: item, distanceKm })
    );

    return typeof filters?.limit === "number" ? nearbyLocations.slice(0, filters.limit) : nearbyLocations;
  }

  getLocation(id: string) {
    return this.getDocument<AuthorizedLocation>(firebaseCollections.locations, id);
  }

  listTechnicalProjects() {
    return this.listCollection<TechnicalProject>(firebaseCollections.technicalProjects);
  }

  listCompanyReports() {
    return this.listCollection<CompanyPerformanceReport>(firebaseCollections.companyReports);
  }

  listMarketplaceApplications() {
    return this.listCollection<MarketplaceApplication>(firebaseCollections.marketplaceApplications);
  }

  listMobileAnnouncements() {
    return this.listCollection<MobileAnnouncement>(firebaseCollections.mobileAnnouncements);
  }

  listProductApprovals() {
    return this.listCollection<ProductApproval>(firebaseCollections.productApprovals);
  }

  listSellerQualityScores() {
    return this.listCollection<SellerQualityScore>(firebaseCollections.sellerQualityScores);
  }

  listPlatformCharges() {
    return this.listCollection<PlatformCharge>(firebaseCollections.platformCharges);
  }

  listUsers() {
    return this.listCollection<WulkanUser>(firebaseCollections.users);
  }

  listAuditLogs() {
    return this.listCollection<AuditLog>(firebaseCollections.auditLogs);
  }

  async getAppSettings() {
    return (await this.getDocument<AppSettings>(firebaseCollections.appSettings, "wulkan-ve")) ?? {
      id: "wulkan-ve",
      country: "VE",
      primaryCurrency: "USD",
      secondaryCurrency: "VES",
      exchangeRate: {
        id: "rate-usd-ves",
        baseCurrency: "USD",
        targetCurrency: "VES",
        rate: 0,
        source: "manual",
        activeFrom: new Date(0).toISOString(),
        updatedBy: "system"
      },
      maintenanceMode: true
    };
  }

  private async listFiltered<T extends { id: string }>(
    collection: string,
    predicate: (item: T) => boolean,
    filterValue?: string
  ): Promise<T[]> {
    const items = await this.listCollection<T>(collection);
    return filterValue ? items.filter(predicate) : items;
  }
}
