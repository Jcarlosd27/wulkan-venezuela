"use server";

import { firebaseCollections } from "@wulkan/config";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { writeFirestoreDocument } from "../../lib/firestore-writer";

function getString(formData: FormData, key: string): string {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function getNumber(formData: FormData, key: string): number {
  const value = Number(getString(formData, key));
  return Number.isFinite(value) ? value : 0;
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

export async function createLocationAction(formData: FormData) {
  const name = getString(formData, "name");
  const state = getString(formData, "state");
  const city = getString(formData, "city");
  const line1 = getString(formData, "line1");
  const availableServices = formData.getAll("services").filter((value): value is string => typeof value === "string");

  if (!name || !state || !city || !line1 || availableServices.length === 0) {
    redirect("/ubicaciones/nueva?status=invalid");
  }

  const locationId = normalizeId(`loc-${city}-${name}`);

  await writeFirestoreDocument(firebaseCollections.locations, locationId, {
    name,
    type: getString(formData, "type") || "pickup_point",
    address: {
      country: "VE",
      state,
      city,
      line1,
      phone: getString(formData, "phone") || "+58 000-0000000"
    },
    coordinates: {
      lat: getNumber(formData, "lat"),
      lng: getNumber(formData, "lng")
    },
    phone: getString(formData, "phone") || "+58 000-0000000",
    availableServices,
    coverageAreas: [{ country: "VE", state, city, radiusKm: 10 }],
    acceptsWalkIns: true,
    status: "pending",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  });

  revalidatePath("/ubicaciones");
  redirect("/ubicaciones?status=location-created");
}
