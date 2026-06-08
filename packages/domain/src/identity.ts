import type { CountryCode, EntityStatus } from "./base";

export type UserRole =
  | "super_admin"
  | "wulkan_admin"
  | "wulkan_operator"
  | "company_owner"
  | "company_seller"
  | "hardware_store_owner"
  | "hardware_store_buyer"
  | "technical_service_owner"
  | "technical_service_operator"
  | "installer"
  | "customer";

export type Permission =
  | "catalog.view"
  | "product.create"
  | "product.edit"
  | "product.approve"
  | "price.change"
  | "order.view"
  | "order.status.change"
  | "purchase_order.create"
  | "purchase_order.approve"
  | "payment.view"
  | "payment.confirm"
  | "service_case.create"
  | "service_case.update"
  | "service_case.close"
  | "vertical.manage"
  | "technical_attribute.manage"
  | "location.manage"
  | "report.view"
  | "user.manage"
  | "permission.manage";

export interface WulkanUser {
  id: string;
  name: string;
  email: string;
  phone?: string;
  role: UserRole;
  permissions: Permission[];
  status: EntityStatus;
  country: CountryCode;
  companyId?: string;
  lastLoginAt?: string;
}

