export type AuditAction =
  | "product_created"
  | "product_approved"
  | "price_changed"
  | "order_status_changed"
  | "purchase_order_status_changed"
  | "payment_confirmed"
  | "payment_rejected"
  | "service_case_updated"
  | "company_approved"
  | "company_suspended";

export interface AuditLog {
  id: string;
  action: AuditAction;
  actorUserId: string;
  targetCollection: string;
  targetId: string;
  before?: unknown;
  after?: unknown;
  createdAt: string;
  origin: "admin_web" | "mobile_app" | "cloud_function" | "system";
}

