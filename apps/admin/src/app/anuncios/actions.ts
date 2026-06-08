"use server";

import { firebaseCollections } from "@wulkan/config";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { writeFirestoreDocument } from "../../lib/firestore-writer";

function getString(formData: FormData, key: string): string {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function getNumber(formData: FormData, key: string, fallback: number): number {
  const value = Number(getString(formData, key));
  return Number.isFinite(value) ? value : fallback;
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

export async function createMobileAnnouncementAction(formData: FormData) {
  const title = getString(formData, "title");
  const body = getString(formData, "body");
  const placement = getString(formData, "placement") || "home";
  const startsAt = getString(formData, "startsAt");
  const now = new Date().toISOString();

  if (!title || !body || !startsAt) {
    redirect("/anuncios?status=invalid");
  }

  const announcementId = normalizeId(`ann-${title}-${Date.now()}`);

  await writeFirestoreDocument(firebaseCollections.mobileAnnouncements, announcementId, {
    title,
    body,
    placement,
    priority: Math.max(0, Math.floor(getNumber(formData, "priority", 50))),
    ctaLabel: getString(formData, "ctaLabel") || null,
    ctaUrl: getString(formData, "ctaUrl") || null,
    imageUrl: getString(formData, "imageUrl") || null,
    startsAt,
    endsAt: getString(formData, "endsAt") || null,
    status: getString(formData, "status") || "active",
    createdBy: "admin-announcements",
    updatedAt: now
  });

  revalidatePath("/anuncios");
  redirect("/anuncios?status=created");
}
