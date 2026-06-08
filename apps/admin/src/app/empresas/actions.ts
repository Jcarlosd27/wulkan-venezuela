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

export async function createCompanyAction(formData: FormData) {
  const legalName = getString(formData, "legalName");
  const commercialName = getString(formData, "commercialName");
  const phone = getString(formData, "phone");
  const state = getString(formData, "state");
  const city = getString(formData, "city");

  if (!legalName || !commercialName || !phone || !state || !city) {
    redirect("/empresas/nueva?status=invalid");
  }

  const companyId = normalizeId(commercialName);

  await writeFirestoreDocument(firebaseCollections.companies, companyId, {
    legalName,
    commercialName,
    taxId: getString(formData, "taxId"),
    type: getString(formData, "type") || "seller",
    status: "pending",
    contacts: [
      {
        name: getString(formData, "contactName") || "Contacto principal",
        email: getString(formData, "email"),
        phone,
        whatsapp: getString(formData, "whatsapp") || phone
      }
    ],
    address: {
      country: "VE",
      state,
      city,
      line1: getString(formData, "line1") || "Pendiente por validar",
      phone
    },
    commercialTerms: {
      b2bEnabled: formData.get("b2bEnabled") === "on",
      creditEnabled: false,
      minimumPurchaseUsd: 0,
      paymentTermsDays: 0,
      priceListId: "public-ve"
    },
    activeVerticalIds: [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  });

  revalidatePath("/empresas");
  redirect("/empresas?status=company-created");
}
