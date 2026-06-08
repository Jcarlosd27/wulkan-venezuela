"use server";

import { firebaseCollections } from "@wulkan/config";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { writeFirestoreDocument } from "../../lib/firestore-writer";

function getString(formData: FormData, key: string): string {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function normalizeId(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export async function createServiceCaseAction(formData: FormData) {
  const technicalServiceId = getString(formData, "technicalServiceId");
  const customerName = getString(formData, "customerName");
  const customerContact = getString(formData, "customerContact");
  const symptoms = getString(formData, "symptoms");
  const now = new Date().toISOString();

  if (!technicalServiceId || !customerName || !customerContact || !symptoms) {
    redirect("/servicios/nuevo?status=invalid");
  }

  const serviceCaseId = normalizeId(`svc-${customerName}-${Date.now()}`);
  const diagnosis = getString(formData, "diagnosis");

  await writeFirestoreDocument(firebaseCollections.serviceCases, serviceCaseId, {
    technicalServiceId,
    customerName,
    customerContact,
    machineId: getString(formData, "machineId"),
    serialNumber: getString(formData, "serialNumber"),
    symptoms,
    diagnosis,
    photoUrls: [],
    requestedParts: [],
    usedParts: [],
    status: getString(formData, "status") || "received",
    warrantyRelated: false,
    createdAt: now,
    updatedAt: now
  });

  await writeFirestoreDocument(firebaseCollections.serviceCaseEvents, `event-${serviceCaseId}-created`, {
    serviceCaseId,
    type: diagnosis ? "diagnosis_added" : "created",
    message: diagnosis || "Caso tecnico creado desde admin.",
    actorUserId: "admin-form",
    createdAt: now,
    statusAfter: getString(formData, "status") || "received"
  });

  revalidatePath("/servicios");
  redirect("/servicios?status=service-case-created");
}
