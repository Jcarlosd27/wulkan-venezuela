export const wulkanEnvironment = {
  defaultCountry: "VE",
  primaryCurrency: "USD",
  secondaryCurrency: "VES",
  authMode: "mock"
} as const;

export const firebaseCollections = {
  users: "users",
  companies: "companies",
  verticals: "business_verticals",
  products: "products",
  productVariants: "product_variants",
  productPrices: "product_prices",
  productStock: "product_stock",
  productCompatibilities: "product_compatibilities",
  orders: "orders",
  purchaseOrders: "purchase_orders",
  replenishmentRequests: "replenishment_requests",
  serviceCases: "service_cases",
  serviceCaseEvents: "service_case_events",
  quotes: "quotes",
  payments: "payments",
  locations: "locations",
  technicalProjects: "technical_projects",
  companyReports: "company_performance_reports",
  marketplaceApplications: "marketplace_applications",
  mobileAnnouncements: "mobile_announcements",
  productApprovals: "product_approvals",
  sellerQualityScores: "seller_quality_scores",
  platformCharges: "platform_charges",
  auditLogs: "audit_logs",
  appSettings: "app_settings"
} as const;
