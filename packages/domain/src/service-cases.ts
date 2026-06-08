export type ServiceCaseStatus =
  | "received"
  | "diagnosed"
  | "waiting_approval"
  | "waiting_part"
  | "in_repair"
  | "repaired"
  | "delivered"
  | "closed"
  | "warranty_rejected";

export interface RequestedPart {
  productId?: string;
  sku?: string;
  description: string;
  quantity: number;
}

export interface ServiceDiagnosis {
  summary: string;
  failureCode?: string;
  recommendedAction: "repair" | "replace_part" | "quote" | "warranty_review" | "no_repair";
  estimatedLaborUsd?: number;
  diagnosedBy: string;
  diagnosedAt: string;
}

export type ServiceCaseEventType =
  | "created"
  | "diagnosis_added"
  | "part_requested"
  | "part_used"
  | "status_changed"
  | "photo_added"
  | "case_closed";

export interface ServiceCaseEvent {
  id: string;
  serviceCaseId: string;
  type: ServiceCaseEventType;
  message: string;
  actorUserId: string;
  createdAt: string;
  statusAfter?: ServiceCaseStatus;
  part?: RequestedPart;
  photoUrl?: string;
}

export interface ServiceCase {
  id: string;
  technicalServiceId: string;
  customerName: string;
  customerContact: string;
  machineId?: string;
  serialNumber?: string;
  symptoms: string;
  diagnosis?: string;
  diagnosisDetail?: ServiceDiagnosis;
  photoUrls: string[];
  requestedParts: RequestedPart[];
  usedParts: RequestedPart[];
  laborNotes?: string;
  status: ServiceCaseStatus;
  warrantyRelated: boolean;
  closedAt?: string;
}
