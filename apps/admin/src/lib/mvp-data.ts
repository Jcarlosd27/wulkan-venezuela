import type {
  AppSettings,
  AuditLog,
  AuthorizedLocation,
  BusinessVertical,
  Company,
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
  CompanyPerformanceReport,
  TechnicalProject,
  WulkanUser,
  UserRole
} from "@wulkan/domain";
import { calculateCheckout } from "@wulkan/shared";
import { avalonGardenProductPrices, avalonGardenProducts, avalonGardenProductStock } from "./avalon-garden-catalog";

export const adminRoles: UserRole[] = [
  "super_admin",
  "wulkan_admin",
  "wulkan_operator",
  "company_owner",
  "company_seller",
  "hardware_store_owner",
  "hardware_store_buyer",
  "technical_service_owner",
  "technical_service_operator",
  "installer",
  "customer"
];

export const users: WulkanUser[] = [
  {
    id: "usr-super-admin",
    name: "Admin Maestro",
    email: "admin@wulkan.local",
    phone: "+58 000-0000000",
    role: "super_admin",
    permissions: ["user.manage", "permission.manage", "vertical.manage", "product.approve", "payment.confirm"],
    status: "active",
    country: "VE",
    lastLoginAt: "2026-05-19T18:00:00.000Z"
  },
  {
    id: "usr-operador",
    name: "Operador Wulkan",
    email: "operador@wulkan.local",
    role: "wulkan_operator",
    permissions: [
      "catalog.view",
      "order.view",
      "order.status.change",
      "purchase_order.approve",
      "payment.view",
      "payment.confirm",
      "service_case.update",
      "location.manage",
      "report.view"
    ],
    status: "active",
    country: "VE",
    lastLoginAt: "2026-05-19T18:20:00.000Z"
  },
  {
    id: "usr-ferretero",
    name: "Comprador Ferretero",
    email: "compras@ferreteria.local",
    role: "hardware_store_buyer",
    permissions: ["catalog.view", "purchase_order.create"],
    status: "pending",
    country: "VE",
    companyId: "ferreteria-demo"
  }
];

export const verticals: BusinessVertical[] = [
  {
    id: "machinery-garden",
    name: "Maquinaria y jardin",
    slug: "maquinaria-jardin",
    description: "Equipos, accesorios y repuestos para trabajo tecnico y jardin.",
    status: "active",
    countries: ["VE"],
    requiresTechnicalAttributes: true,
    availableProductTypes: ["machine", "spare_part", "accessory"],
    attributeSchema: [
      {
        id: "power",
        verticalId: "machinery-garden",
        name: "Potencia",
        type: "text",
        required: false,
        visibleInFilters: true,
        visibleInProductDetail: true,
        appliesToProductTypes: ["machine"]
      },
      {
        id: "fuel",
        verticalId: "machinery-garden",
        name: "Combustible",
        type: "select",
        options: ["Gasolina", "Electrico", "Bateria"],
        required: false,
        visibleInFilters: true,
        visibleInProductDetail: true,
        appliesToProductTypes: ["machine"]
      }
    ]
  },
  {
    id: "spare-parts",
    name: "Repuestos",
    slug: "repuestos",
    description: "Compatibilidades, SKU y piezas de reposicion.",
    status: "active",
    countries: ["VE"],
    requiresTechnicalAttributes: true,
    availableProductTypes: ["spare_part"],
    attributeSchema: [
      {
        id: "compatible-model",
        verticalId: "spare-parts",
        name: "Modelo compatible",
        type: "text",
        required: true,
        visibleInFilters: true,
        visibleInProductDetail: true,
        appliesToProductTypes: ["spare_part"]
      }
    ]
  },
  {
    id: "lighting",
    name: "Iluminacion",
    slug: "iluminacion",
    description: "Luminarias, proyectos y soluciones tecnicas.",
    status: "active",
    countries: ["VE"],
    requiresTechnicalAttributes: true,
    availableProductTypes: ["accessory", "project"],
    attributeSchema: [
      {
        id: "lumens",
        verticalId: "lighting",
        name: "Lumenes",
        type: "number",
        required: false,
        visibleInFilters: true,
        visibleInProductDetail: true,
        appliesToProductTypes: ["accessory"]
      }
    ]
  },
  {
    id: "technical-services",
    name: "Servicios tecnicos",
    slug: "servicios-tecnicos",
    description: "Diagnostico, reparacion, garantia e instalacion autorizada.",
    status: "active",
    countries: ["VE"],
    requiresTechnicalAttributes: false,
    availableProductTypes: ["service"],
    attributeSchema: []
  }
];

export const companies: Company[] = [
  {
    id: "avalon-group",
    legalName: "Avalon Group",
    commercialName: "Wulkan Venezuela",
    type: "seller",
    status: "active",
    contacts: [{ name: "Operacion Wulkan", phone: "+58 000-0000000" }],
    address: {
      country: "VE",
      state: "Distrito Capital",
      city: "Caracas",
      line1: "Base operativa Wulkan",
      phone: "+58 000-0000000"
    },
    commercialTerms: { b2bEnabled: true, creditEnabled: false, minimumPurchaseUsd: 100, paymentTermsDays: 0, priceListId: "public-ve" },
    activeVerticalIds: ["machinery-garden", "spare-parts", "lighting"]
  },
  {
    id: "ferreteria-demo",
    legalName: "Ferreteria Demo C.A.",
    commercialName: "Ferreteria Demo",
    type: "hardware_store",
    status: "pending",
    contacts: [{ name: "Compras", phone: "+58 000-1111111" }],
    address: {
      country: "VE",
      state: "Carabobo",
      city: "Valencia",
      line1: "Zona comercial demo",
      phone: "+58 000-1111111"
    },
    commercialTerms: {
      b2bEnabled: true,
      creditEnabled: false,
      defaultDiscountPercent: 8,
      minimumPurchaseUsd: 150,
      paymentTermsDays: 0,
      priceListId: "hardware-store-ve"
    },
    activeVerticalIds: ["machinery-garden", "spare-parts"]
  },
  {
    id: "seller-lighting-demo",
    legalName: "Iluminacion Demo C.A.",
    commercialName: "Iluminacion Demo",
    type: "seller",
    status: "pending",
    contacts: [{ name: "Ventas", phone: "+58 000-6666666", email: "ventas@iluminacion.local" }],
    address: {
      country: "VE",
      state: "Miranda",
      city: "Los Teques",
      line1: "Zona industrial demo",
      phone: "+58 000-6666666"
    },
    commercialTerms: {
      b2bEnabled: false,
      creditEnabled: false,
      minimumPurchaseUsd: 0,
      paymentTermsDays: 0,
      priceListId: "seller-lighting-ve"
    },
    activeVerticalIds: ["lighting"]
  }
];

export const products: Product[] = [
  {
    id: "prod-motosierra-45cc",
    sku: "WUL-MOT-45CC",
    title: "Motosierra 45cc",
    description: "Equipo de corte para uso tecnico y jardin.",
    verticalId: "machinery-garden",
    type: "machine",
    categoryId: "motosierras",
    sellerId: "avalon-group",
    publicPrice: { amount: 185, currency: "USD" },
    b2bPrice: { amount: 162, currency: "USD" },
    baseCurrency: "USD",
    stock: 12,
    countryAvailability: ["VE"],
    imageUrls: [],
    warranty: "6 meses",
    compatibilityIds: ["prod-cadena-18"],
    requiresQuote: false,
    requiresInstallation: false,
    requiresTechnicalValidation: false,
    status: "active"
  },
  {
    id: "prod-cadena-18",
    sku: "WUL-REP-CAD18",
    title: "Cadena 18 pulgadas compatible",
    description: "Repuesto compatible con motosierras seleccionadas.",
    verticalId: "spare-parts",
    type: "spare_part",
    categoryId: "cadenas",
    sellerId: "avalon-group",
    publicPrice: { amount: 18, currency: "USD" },
    b2bPrice: { amount: 15, currency: "USD" },
    baseCurrency: "USD",
    stock: 4,
    countryAvailability: ["VE"],
    imageUrls: [],
    warranty: "30 dias",
    compatibilityIds: ["prod-motosierra-45cc"],
    requiresQuote: false,
    requiresInstallation: false,
    requiresTechnicalValidation: true,
    status: "active"
  },
  {
    id: "prod-panel-led",
    sku: "WUL-ILU-LED60",
    title: "Panel LED tecnico 60W",
    description: "Luminaria para comercios y espacios tecnicos.",
    verticalId: "lighting",
    type: "accessory",
    categoryId: "paneles-led",
    sellerId: "avalon-group",
    publicPrice: { amount: 32, currency: "USD" },
    baseCurrency: "USD",
    stock: 0,
    countryAvailability: ["VE"],
    imageUrls: [],
    compatibilityIds: [],
    requiresQuote: true,
    requiresInstallation: true,
    requiresTechnicalValidation: true,
    status: "pending"
  },
  ...avalonGardenProducts
];

export const productVariants: ProductVariant[] = [
  {
    id: "var-motosierra-45cc-standard",
    productId: "prod-motosierra-45cc",
    sku: "WUL-MOT-45CC-STD",
    title: "Motosierra 45cc estandar",
    attributes: { espada: "18 pulgadas", combustible: "Gasolina" },
    status: "active"
  }
];

export const productPrices: ProductPrice[] = [
  {
    id: "price-motosierra-public",
    productId: "prod-motosierra-45cc",
    type: "public",
    amount: 185,
    currency: "USD",
    validFrom: "2026-05-19T00:00:00.000Z",
    changedBy: "usr-super-admin"
  },
  {
    id: "price-motosierra-b2b",
    productId: "prod-motosierra-45cc",
    type: "b2b",
    amount: 162,
    currency: "USD",
    validFrom: "2026-05-19T00:00:00.000Z",
    changedBy: "usr-super-admin"
  },
  {
    id: "price-cadena-public",
    productId: "prod-cadena-18",
    type: "public",
    amount: 18,
    currency: "USD",
    validFrom: "2026-05-19T00:00:00.000Z",
    changedBy: "usr-super-admin"
  },
  ...avalonGardenProductPrices
];

export const productStock: ProductStock[] = [
  {
    id: "stock-motosierra-caracas",
    productId: "prod-motosierra-45cc",
    companyId: "avalon-group",
    locationId: "loc-caracas-001",
    available: 12,
    reserved: 0,
    lowStockThreshold: 3,
    updatedAt: "2026-05-19T18:00:00.000Z"
  },
  {
    id: "stock-cadena-caracas",
    productId: "prod-cadena-18",
    companyId: "avalon-group",
    locationId: "loc-caracas-001",
    available: 4,
    reserved: 1,
    lowStockThreshold: 5,
    updatedAt: "2026-05-19T18:00:00.000Z"
  },
  {
    id: "stock-panel-caracas",
    productId: "prod-panel-led",
    companyId: "avalon-group",
    locationId: "loc-caracas-001",
    available: 0,
    reserved: 0,
    lowStockThreshold: 5,
    updatedAt: "2026-05-19T18:00:00.000Z"
  },
  ...avalonGardenProductStock
];

export const productCompatibilities: ProductCompatibility[] = [
  {
    id: "compat-cadena-motosierra",
    sourceProductId: "prod-cadena-18",
    compatibleProductId: "prod-motosierra-45cc",
    machineModel: "Motosierra 45cc",
    engineModel: "45cc gasolina",
    notes: "Validar largo de espada antes de entregar.",
    requiresTechnicalValidation: true,
    status: "active"
  }
];

export const marketplaceApplications: MarketplaceApplication[] = [
  {
    id: "mkt-app-001",
    companyId: "seller-lighting-demo",
    companyType: "seller",
    requestedVerticalIds: ["lighting"],
    status: "under_review",
    submittedBy: "usr-operador",
    createdAt: "2026-05-19T21:00:00.000Z",
    updatedAt: "2026-05-19T21:20:00.000Z"
  }
];

export const mobileAnnouncements: MobileAnnouncement[] = [
  {
    id: "ann-home-launch",
    title: "Lanzamiento Wulkan Venezuela",
    body: "Compra equipos Wulkan en USD con referencia en bolivares y soporte tecnico autorizado.",
    placement: "home",
    priority: 100,
    ctaLabel: "Ver catalogo",
    ctaUrl: "wulkan://catalog",
    imageUrl: "/brand/wulkan-logo.svg",
    startsAt: "2026-06-01T00:00:00.000Z",
    status: "active",
    createdBy: "usr-super-admin",
    updatedAt: "2026-06-08T00:00:00.000Z"
  },
  {
    id: "ann-catalog-stock",
    title: "Stock disponible",
    body: "Revisa maquinaria, repuestos y productos que no requieren cotizacion antes de comprar.",
    placement: "catalog",
    priority: 80,
    ctaLabel: "Comprar",
    ctaUrl: "wulkan://catalog?filter=available",
    startsAt: "2026-06-01T00:00:00.000Z",
    status: "active",
    createdBy: "usr-operador",
    updatedAt: "2026-06-08T00:00:00.000Z"
  },
  {
    id: "ann-checkout-review",
    title: "Validacion de pagos",
    body: "Las transferencias y pagos en bolivares quedan bajo revision del equipo Wulkan antes del despacho.",
    placement: "checkout",
    priority: 60,
    startsAt: "2026-06-01T00:00:00.000Z",
    status: "active",
    createdBy: "usr-operador",
    updatedAt: "2026-06-08T00:00:00.000Z"
  }
];

export const productApprovals: ProductApproval[] = [
  {
    id: "prod-appr-001",
    productId: "prod-panel-led",
    sellerId: "seller-lighting-demo",
    status: "changes_requested",
    submittedBy: "usr-operador",
    reviewedBy: "usr-super-admin",
    reviewedAt: "2026-05-19T21:40:00.000Z",
    notes: "Falta ficha tecnica y garantia comercial.",
    requiredChanges: ["Adjuntar ficha tecnica", "Definir garantia", "Confirmar stock"],
    createdAt: "2026-05-19T21:10:00.000Z",
    updatedAt: "2026-05-19T21:40:00.000Z"
  }
];

export const sellerQualityScores: SellerQualityScore[] = [
  {
    id: "seller-score-lighting-2026-05",
    companyId: "seller-lighting-demo",
    period: "2026-05",
    fulfillmentRate: 0,
    cancellationRate: 0,
    averageDispatchHours: 0,
    openIncidents: 0,
    status: "pending"
  }
];

export const orders: Order[] = [
  {
    id: "ord-1001",
    customerId: "customer-demo",
    items: [
      {
        productId: "prod-motosierra-45cc",
        sku: "WUL-MOT-45CC",
        title: "Motosierra 45cc",
        quantity: 1,
        unitPrice: { amount: 185, currency: "USD" },
        total: { amount: 185, currency: "USD" }
      }
    ],
    subtotal: { amount: 185, currency: "USD" },
    total: { amount: 185, currency: "USD" },
    currency: "USD",
    exchangeRateUsdVes: 38.5,
    status: "payment_under_review",
    paymentId: "pay-1001"
  }
];

export const checkoutDemo = calculateCheckout(
  [
    {
      quantity: 1,
      unitPriceUsd: 185,
      requiresQuote: false,
      requiresTechnicalValidation: false
    }
  ],
  38.5
);

export const purchaseOrders: PurchaseOrder[] = [
  {
    id: "po-2001",
    requesterCompanyId: "ferreteria-demo",
    requesterUserId: "buyer-demo",
    items: [
      {
        productId: "prod-cadena-18",
        sku: "WUL-REP-CAD18",
        title: "Cadena 18 pulgadas compatible",
        quantity: 10,
        unitPrice: { amount: 15, currency: "USD" },
        total: { amount: 150, currency: "USD" }
      }
    ],
    subtotal: { amount: 150, currency: "USD" },
    total: { amount: 150, currency: "USD" },
    currency: "USD",
    status: "under_wulkan_review",
    requestedDeliveryDate: "2026-05-24",
    notes: "Reposicion de cadenas por baja existencia."
  }
];

export const replenishmentRequests: ReplenishmentRequest[] = [
  {
    id: "rr-2101",
    requesterCompanyId: "ferreteria-demo",
    requesterUserId: "buyer-demo",
    productId: "prod-panel-led",
    sku: "WUL-ILU-LED60",
    description: "Solicitud de paneles LED para evaluar venta por proyecto.",
    requestedQuantity: 20,
    status: "quoted",
    quoteId: "quo-4001",
    createdAt: "2026-05-19T20:00:00.000Z",
    updatedAt: "2026-05-19T20:30:00.000Z"
  }
];

export const serviceCases: ServiceCase[] = [
  {
    id: "svc-3001",
    technicalServiceId: "service-demo",
    customerName: "Cliente Demo",
    customerContact: "+58 000-2222222",
    machineId: "prod-motosierra-45cc",
    serialNumber: "SN-DEMO-001",
    symptoms: "No enciende y requiere revision de cadena.",
    diagnosisDetail: {
      summary: "Falla probable en sistema de arranque y cadena con desgaste.",
      failureCode: "STARTER_CHAIN_REVIEW",
      recommendedAction: "replace_part",
      estimatedLaborUsd: 25,
      diagnosedBy: "usr-operador",
      diagnosedAt: "2026-05-19T19:10:00.000Z"
    },
    photoUrls: [],
    requestedParts: [{ productId: "prod-cadena-18", sku: "WUL-REP-CAD18", description: "Cadena 18 pulgadas", quantity: 1 }],
    usedParts: [],
    status: "diagnosed",
    warrantyRelated: false
  }
];

export const serviceCaseEvents: ServiceCaseEvent[] = [
  {
    id: "svc-event-001",
    serviceCaseId: "svc-3001",
    type: "created",
    message: "Caso tecnico creado por servicio autorizado.",
    actorUserId: "usr-operador",
    createdAt: "2026-05-19T19:00:00.000Z",
    statusAfter: "received"
  },
  {
    id: "svc-event-002",
    serviceCaseId: "svc-3001",
    type: "diagnosis_added",
    message: "Se registra diagnostico inicial y solicitud de cadena compatible.",
    actorUserId: "usr-operador",
    createdAt: "2026-05-19T19:10:00.000Z",
    statusAfter: "diagnosed"
  },
  {
    id: "svc-event-003",
    serviceCaseId: "svc-3001",
    type: "part_requested",
    message: "Repuesto solicitado para aprobacion Wulkan.",
    actorUserId: "usr-operador",
    createdAt: "2026-05-19T19:15:00.000Z",
    statusAfter: "waiting_part",
    part: { productId: "prod-cadena-18", sku: "WUL-REP-CAD18", description: "Cadena 18 pulgadas", quantity: 1 }
  }
];

export const payments: Payment[] = [
  {
    id: "pay-1001",
    orderId: "ord-1001",
    method: "bank_transfer",
    amountUsd: 185,
    amountVes: 7122.5,
    currency: "USD",
    exchangeRate: 38.5,
    referenceNumber: "REF-DEMO-1001",
    status: "under_review"
  }
];

export const quotes: Quote[] = [
  {
    id: "quo-4001",
    requesterType: "customer",
    requesterId: "customer-demo",
    items: [
      {
        productId: "prod-panel-led",
        sku: "WUL-ILU-LED60",
        title: "Panel LED tecnico 60W",
        quantity: 12,
        unitPrice: { amount: 32, currency: "USD" },
        total: { amount: 384, currency: "USD" }
      }
    ],
    message: "Cliente solicita instalacion para local comercial.",
    status: "under_review"
  }
];

export const locations: AuthorizedLocation[] = [
  {
    id: "loc-caracas-001",
    name: "Punto autorizado Caracas",
    type: "pickup_point",
    address: {
      country: "VE",
      state: "Distrito Capital",
      city: "Caracas",
      municipality: "Chacao",
      line1: "Zona comercial demo",
      phone: "+58 000-3333333"
    },
    coordinates: { lat: 10.498, lng: -66.853 },
    phone: "+58 000-3333333",
    whatsapp: "+58 000-3333333",
    schedule: "Lunes a viernes, 9:00 a 17:00",
    availableServices: ["pickup", "technical_support", "case_reception"],
    coverageAreas: [{ country: "VE", state: "Distrito Capital", city: "Caracas", municipality: "Chacao", radiusKm: 12 }],
    acceptsWalkIns: true,
    status: "active",
    companyId: "avalon-group"
  },
  {
    id: "loc-valencia-001",
    name: "Ferreteria Demo Valencia",
    type: "hardware_store",
    address: {
      country: "VE",
      state: "Carabobo",
      city: "Valencia",
      line1: "Zona comercial demo",
      phone: "+58 000-1111111"
    },
    coordinates: { lat: 10.162, lng: -68.008 },
    phone: "+58 000-1111111",
    whatsapp: "+58 000-1111111",
    schedule: "Lunes a sabado, 8:00 a 16:00",
    availableServices: ["b2b_sale", "pickup", "retail_sale"],
    coverageAreas: [{ country: "VE", state: "Carabobo", city: "Valencia", radiusKm: 18 }],
    acceptsWalkIns: true,
    status: "pending",
    companyId: "ferreteria-demo"
  }
];

export const technicalProjects: TechnicalProject[] = [
  {
    id: "prj-5001",
    verticalId: "lighting",
    requesterId: "customer-demo",
    requesterType: "customer",
    location: {
      country: "VE",
      state: "Distrito Capital",
      city: "Caracas",
      municipality: "Chacao",
      line1: "Local comercial demo",
      reference: "Frente a avenida principal",
      phone: "+58 000-5555555"
    },
    requirements: "Evaluar instalacion de 12 paneles LED para local comercial.",
    photoUrls: [],
    measurements: [
      { name: "Area", value: "80", unit: "m2" },
      { name: "Altura", value: "3", unit: "m" }
    ],
    assignedOperatorId: "usr-operador",
    assignedInstallerId: "usr-instalador-demo",
    quoteId: "quo-4001",
    status: "visit_scheduled",
    scheduledAt: "2026-05-22T14:00:00.000Z",
    createdAt: "2026-05-19T19:00:00.000Z",
    updatedAt: "2026-05-19T19:30:00.000Z"
  }
];

export const companyReports: CompanyPerformanceReport[] = [
  {
    id: "rep-avalon-2026-05",
    companyId: "avalon-group",
    period: "2026-05",
    grossRevenueUsd: 335,
    orderCount: 1,
    purchaseOrderCount: 1,
    averageTicketUsd: 167.5,
    pendingPayments: 1,
    openServiceCases: 1,
    status: "active"
  },
  {
    id: "rep-ferreteria-2026-05",
    companyId: "ferreteria-demo",
    period: "2026-05",
    grossRevenueUsd: 150,
    orderCount: 0,
    purchaseOrderCount: 1,
    averageTicketUsd: 150,
    pendingPayments: 0,
    openServiceCases: 0,
    status: "pending"
  }
];

export const platformCharges: PlatformCharge[] = [
  {
    id: "charge-avalon-2026-05",
    companyId: "avalon-group",
    period: "2026-05",
    concept: "commission",
    amountUsd: 10.05,
    status: "pending",
    createdAt: "2026-05-19T22:00:00.000Z"
  }
];

export const auditLogs: AuditLog[] = [
  {
    id: "aud-001",
    action: "product_created",
    actorUserId: "usr-operador",
    targetCollection: "products",
    targetId: "prod-panel-led",
    after: { status: "pending" },
    createdAt: "2026-05-19T18:15:00.000Z",
    origin: "admin_web"
  },
  {
    id: "aud-002",
    action: "payment_confirmed",
    actorUserId: "usr-super-admin",
    targetCollection: "payments",
    targetId: "pay-1001",
    after: { status: "under_review" },
    createdAt: "2026-05-19T18:30:00.000Z",
    origin: "cloud_function"
  }
];

export const appSettings: AppSettings = {
  id: "wulkan-ve",
  country: "VE",
  primaryCurrency: "USD",
  secondaryCurrency: "VES",
  maintenanceMode: false,
  whatsappSupportNumber: "+58 000-4444444",
  exchangeRate: {
    id: "rate-usd-ves",
    baseCurrency: "USD",
    targetCurrency: "VES",
    rate: 38.5,
    source: "manual",
    activeFrom: "2026-05-19T00:00:00.000Z",
    updatedBy: "usr-super-admin"
  }
};
