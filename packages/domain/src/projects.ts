import type { Address, EntityStatus } from "./base";

export type TechnicalProjectStatus =
  | "requested"
  | "under_evaluation"
  | "visit_scheduled"
  | "quoted"
  | "approved"
  | "in_installation"
  | "installed"
  | "closed"
  | "cancelled";

export type ProjectRequesterType = "customer" | "hardware_store" | "company";

export interface ProjectMeasurement {
  name: string;
  value: string;
  unit?: string;
}

export interface TechnicalProject {
  id: string;
  verticalId: string;
  requesterId: string;
  requesterType: ProjectRequesterType;
  location: Address;
  requirements: string;
  photoUrls: string[];
  measurements: ProjectMeasurement[];
  assignedOperatorId?: string;
  assignedInstallerId?: string;
  quoteId?: string;
  status: TechnicalProjectStatus;
  scheduledAt?: string;
  installedAt?: string;
  warrantyStartAt?: string;
  warrantyEndAt?: string;
  closingNotes?: string;
  createdAt: string;
  updatedAt: string;
}

export interface CompanyPerformanceReport {
  id: string;
  companyId: string;
  period: string;
  grossRevenueUsd: number;
  orderCount: number;
  purchaseOrderCount: number;
  averageTicketUsd: number;
  pendingPayments: number;
  openServiceCases: number;
  status: EntityStatus;
}

