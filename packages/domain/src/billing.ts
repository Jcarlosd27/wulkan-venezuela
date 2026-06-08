export interface PlatformFeeRule {
  id: string;
  name: string;
  minRevenueUsd: number;
  maxRevenueUsd?: number;
  commissionPercent: number;
  status: "active" | "inactive";
}

export interface CompanyRevenuePeriod {
  id: string;
  companyId: string;
  period: string;
  grossRevenueUsd: number;
  estimatedCommissionUsd: number;
  confirmedCommissionUsd: number;
  status: "open" | "closed" | "charged" | "paid";
}

export interface PlatformCharge {
  id: string;
  companyId: string;
  period: string;
  concept: "commission" | "premium_service" | "adjustment";
  amountUsd: number;
  status: "pending" | "confirmed" | "paid" | "void";
  createdAt: string;
}
