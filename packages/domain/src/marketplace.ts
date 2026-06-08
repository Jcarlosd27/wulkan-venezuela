import type { EntityStatus } from "./base";
import type { CompanyType } from "./companies";

export type MarketplaceApplicationStatus = "submitted" | "under_review" | "approved" | "rejected";
export type ProductApprovalStatus = "draft" | "submitted" | "approved" | "rejected" | "changes_requested";
export type MobileAnnouncementPlacement = "home" | "catalog" | "checkout";

export interface MarketplaceApplication {
  id: string;
  companyId: string;
  companyType: CompanyType;
  requestedVerticalIds: string[];
  status: MarketplaceApplicationStatus;
  submittedBy: string;
  reviewedBy?: string;
  reviewedAt?: string;
  rejectionReason?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ProductApproval {
  id: string;
  productId: string;
  sellerId: string;
  status: ProductApprovalStatus;
  submittedBy: string;
  reviewedBy?: string;
  reviewedAt?: string;
  notes?: string;
  requiredChanges?: string[];
  createdAt: string;
  updatedAt: string;
}

export interface SellerQualityScore {
  id: string;
  companyId: string;
  period: string;
  fulfillmentRate: number;
  cancellationRate: number;
  averageDispatchHours: number;
  openIncidents: number;
  status: EntityStatus;
}

export interface MobileAnnouncement {
  id: string;
  title: string;
  body: string;
  placement: MobileAnnouncementPlacement;
  priority: number;
  ctaLabel?: string;
  ctaUrl?: string;
  imageUrl?: string;
  startsAt: string;
  endsAt?: string;
  status: EntityStatus;
  createdBy: string;
  updatedAt: string;
}
