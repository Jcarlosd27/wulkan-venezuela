import type { AppSettings, BusinessVertical, UserRole, WulkanUser } from "@wulkan/domain";

export const initialRoles: UserRole[] = [
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

export const initialVerticals: BusinessVertical[] = [
  {
    id: "machinery-garden",
    name: "Maquinaria y jardin",
    slug: "maquinaria-jardin",
    status: "active",
    countries: ["VE"],
    requiresTechnicalAttributes: true,
    availableProductTypes: ["machine", "accessory", "spare_part"],
    attributeSchema: []
  },
  {
    id: "spare-parts",
    name: "Repuestos",
    slug: "repuestos",
    status: "active",
    countries: ["VE"],
    requiresTechnicalAttributes: true,
    availableProductTypes: ["spare_part"],
    attributeSchema: []
  },
  {
    id: "technical-hardware",
    name: "Ferreteria tecnica",
    slug: "ferreteria-tecnica",
    status: "active",
    countries: ["VE"],
    requiresTechnicalAttributes: false,
    availableProductTypes: ["accessory"],
    attributeSchema: []
  },
  {
    id: "lighting",
    name: "Iluminacion",
    slug: "iluminacion",
    status: "active",
    countries: ["VE"],
    requiresTechnicalAttributes: true,
    availableProductTypes: ["accessory", "project"],
    attributeSchema: []
  }
];

export const initialUsers: WulkanUser[] = [
  {
    id: "usr-super-admin",
    name: "Admin Maestro",
    email: "admin@wulkan.local",
    role: "super_admin",
    permissions: ["user.manage", "permission.manage", "vertical.manage", "product.approve", "payment.confirm"],
    status: "active",
    country: "VE"
  }
];

export const initialAppSettings: AppSettings = {
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
