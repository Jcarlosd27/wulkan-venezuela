import type {
  AppSettings,
  AuditLog,
  AuthorizedLocation,
  BusinessVertical,
  Company,
  CompanyPerformanceReport,
  Order,
  Payment,
  MarketplaceApplication,
  MobileAnnouncement,
  PlatformCharge,
  Product,
  ProductApproval,
  ProductCompatibility,
  ProductPrice,
  ProductStock,
  ProductVariant,
  PurchaseOrder,
  ReplenishmentRequest,
  Quote,
  ServiceCase,
  ServiceCaseEvent,
  SellerQualityScore,
  TechnicalProject,
  WulkanUser
} from "@wulkan/domain";
import type { LocationService, LocationType } from "@wulkan/domain";
import type { GeoCoordinate } from "@wulkan/shared";
import { sortByDistance } from "@wulkan/shared";
import { createFirestoreAdminRepository, shouldUseFirestoreRepository } from "./firestore-repository";
import {
  appSettings,
  auditLogs,
  companies,
  companyReports,
  locations,
  marketplaceApplications,
  mobileAnnouncements,
  orders,
  payments,
  platformCharges,
  productCompatibilities,
  productPrices,
  productStock,
  productVariants,
  products,
  productApprovals,
  purchaseOrders,
  replenishmentRequests,
  quotes,
  serviceCases,
  serviceCaseEvents,
  sellerQualityScores,
  technicalProjects,
  users,
  verticals
} from "./mvp-data";

export interface AdminRepository {
  listVerticals(): Promise<BusinessVertical[]>;
  getVertical(id: string): Promise<BusinessVertical | undefined>;
  listProducts(): Promise<Product[]>;
  getProduct(id: string): Promise<Product | undefined>;
  listProductVariants(productId?: string): Promise<ProductVariant[]>;
  listProductPrices(productId?: string): Promise<ProductPrice[]>;
  listProductStock(productId?: string): Promise<ProductStock[]>;
  listProductCompatibilities(productId?: string): Promise<ProductCompatibility[]>;
  listCompanies(): Promise<Company[]>;
  listOrders(): Promise<Order[]>;
  getOrder(id: string): Promise<Order | undefined>;
  listPurchaseOrders(): Promise<PurchaseOrder[]>;
  getPurchaseOrder(id: string): Promise<PurchaseOrder | undefined>;
  listReplenishmentRequests(): Promise<ReplenishmentRequest[]>;
  listServiceCases(): Promise<ServiceCase[]>;
  getServiceCase(id: string): Promise<ServiceCase | undefined>;
  listServiceCaseEvents(serviceCaseId?: string): Promise<ServiceCaseEvent[]>;
  listPayments(): Promise<Payment[]>;
  listQuotes(): Promise<Quote[]>;
  listLocations(filters?: { type?: LocationType; service?: LocationService }): Promise<AuthorizedLocation[]>;
  listNearbyLocations(
    origin: GeoCoordinate,
    filters?: { type?: LocationType; service?: LocationService; limit?: number }
  ): Promise<Array<{ location: AuthorizedLocation; distanceKm: number }>>;
  getLocation(id: string): Promise<AuthorizedLocation | undefined>;
  listTechnicalProjects(): Promise<TechnicalProject[]>;
  listCompanyReports(): Promise<CompanyPerformanceReport[]>;
  listMarketplaceApplications(): Promise<MarketplaceApplication[]>;
  listMobileAnnouncements(): Promise<MobileAnnouncement[]>;
  listProductApprovals(): Promise<ProductApproval[]>;
  listSellerQualityScores(): Promise<SellerQualityScore[]>;
  listPlatformCharges(): Promise<PlatformCharge[]>;
  listUsers(): Promise<WulkanUser[]>;
  listAuditLogs(): Promise<AuditLog[]>;
  getAppSettings(): Promise<AppSettings>;
}

export class MockAdminRepository implements AdminRepository {
  async listVerticals() {
    return verticals;
  }

  async getVertical(id: string) {
    return verticals.find((vertical) => vertical.id === id);
  }

  async listProducts() {
    return products;
  }

  async getProduct(id: string) {
    return products.find((product) => product.id === id);
  }

  async listProductVariants(productId?: string) {
    return productId ? productVariants.filter((variant) => variant.productId === productId) : productVariants;
  }

  async listProductPrices(productId?: string) {
    return productId ? productPrices.filter((price) => price.productId === productId) : productPrices;
  }

  async listProductStock(productId?: string) {
    return productId ? productStock.filter((stock) => stock.productId === productId) : productStock;
  }

  async listProductCompatibilities(productId?: string) {
    return productId
      ? productCompatibilities.filter(
          (compatibility) => compatibility.sourceProductId === productId || compatibility.compatibleProductId === productId
        )
      : productCompatibilities;
  }

  async listCompanies() {
    return companies;
  }

  async listOrders() {
    return orders;
  }

  async getOrder(id: string) {
    return orders.find((order) => order.id === id);
  }

  async listPurchaseOrders() {
    return purchaseOrders;
  }

  async getPurchaseOrder(id: string) {
    return purchaseOrders.find((order) => order.id === id);
  }

  async listReplenishmentRequests() {
    return replenishmentRequests;
  }

  async listServiceCases() {
    return serviceCases;
  }

  async getServiceCase(id: string) {
    return serviceCases.find((serviceCase) => serviceCase.id === id);
  }

  async listServiceCaseEvents(serviceCaseId?: string) {
    return serviceCaseId
      ? serviceCaseEvents.filter((event) => event.serviceCaseId === serviceCaseId)
      : serviceCaseEvents;
  }

  async listPayments() {
    return payments;
  }

  async listQuotes() {
    return quotes;
  }

  async listLocations(filters?: { type?: LocationType; service?: LocationService }) {
    return locations.filter((location) => {
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

  async getLocation(id: string) {
    return locations.find((location) => location.id === id);
  }

  async listTechnicalProjects() {
    return technicalProjects;
  }

  async listCompanyReports() {
    return companyReports;
  }

  async listMarketplaceApplications() {
    return marketplaceApplications;
  }

  async listMobileAnnouncements() {
    return mobileAnnouncements;
  }

  async listProductApprovals() {
    return productApprovals;
  }

  async listSellerQualityScores() {
    return sellerQualityScores;
  }

  async listPlatformCharges() {
    return platformCharges;
  }

  async listUsers() {
    return users;
  }

  async listAuditLogs() {
    return auditLogs;
  }

  async getAppSettings() {
    return appSettings;
  }
}

export const adminRepository: AdminRepository = shouldUseFirestoreRepository()
  ? createFirestoreAdminRepository()
  : new MockAdminRepository();
