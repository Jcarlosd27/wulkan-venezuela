"use server";

import { firebaseCollections } from "@wulkan/config";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { writeFirestoreDocument } from "../../lib/firestore-writer";

function getString(formData: FormData, key: string): string {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function normalizeSlug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export async function createVerticalAction(formData: FormData) {
  const name = getString(formData, "name");
  const requestedSlug = getString(formData, "slug");
  const slug = normalizeSlug(requestedSlug || name);
  const rawStatus = getString(formData, "status") || "pending";
  const status = ["active", "pending", "suspended", "archived"].includes(rawStatus) ? rawStatus : "pending";
  const description = getString(formData, "description");
  const availableProductTypes = formData
    .getAll("availableProductTypes")
    .filter((value): value is string => typeof value === "string");

  if (!name || !slug || availableProductTypes.length === 0) {
    redirect("/verticales/nueva?status=invalid");
  }

  await writeFirestoreDocument(firebaseCollections.verticals, slug, {
    name,
    slug,
    description,
    status,
    countries: ["VE"],
    requiresTechnicalAttributes: true,
    availableProductTypes,
    attributeSchema: [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  });

  revalidatePath("/verticales");
  redirect("/verticales?status=vertical-created");
}
