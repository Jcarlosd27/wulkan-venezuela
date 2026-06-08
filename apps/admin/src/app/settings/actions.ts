"use server";

import { firebaseCollections } from "@wulkan/config";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { writeFirestoreDocument } from "../../lib/firestore-writer";

function getString(formData: FormData, key: string): string {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

export async function updateSettingsAction(formData: FormData) {
  const rate = Number(getString(formData, "exchangeRate"));

  if (!Number.isFinite(rate) || rate <= 0) {
    redirect("/settings?status=invalid");
  }

  await writeFirestoreDocument(firebaseCollections.appSettings, "wulkan-ve", {
    country: "VE",
    primaryCurrency: "USD",
    secondaryCurrency: "VES",
    maintenanceMode: formData.get("maintenanceMode") === "on",
    whatsappSupportNumber: getString(formData, "whatsappSupportNumber"),
    exchangeRate: {
      id: "rate-usd-ves",
      baseCurrency: "USD",
      targetCurrency: "VES",
      rate,
      source: "manual",
      activeFrom: new Date().toISOString(),
      updatedBy: "admin-form"
    },
    updatedAt: new Date().toISOString()
  });

  revalidatePath("/settings");
  redirect("/settings?status=settings-saved");
}
