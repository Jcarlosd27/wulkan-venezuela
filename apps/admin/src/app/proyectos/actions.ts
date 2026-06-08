"use server";

import { firebaseCollections } from "@wulkan/config";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { writeFirestoreDocument } from "../../lib/firestore-writer";

function getString(formData: FormData, key: string): string {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

export async function createTechnicalProjectAction(formData: FormData) {
  const verticalId = getString(formData, "verticalId");
  const requesterId = getString(formData, "requesterId");
  const requirements = getString(formData, "requirements");

  if (!verticalId || !requesterId || !requirements) {
    redirect("/proyectos/nuevo?status=invalid");
  }

  const projectId = `prj-${Date.now()}`;
  const now = new Date().toISOString();

  await writeFirestoreDocument(firebaseCollections.technicalProjects, projectId, {
    verticalId,
    requesterId,
    requesterType: "customer",
    location: {
      country: "VE",
      state: getString(formData, "state"),
      city: getString(formData, "city"),
      line1: "Pendiente por validar",
      phone: "+58 000-0000000"
    },
    requirements,
    photoUrls: [],
    measurements: [],
    assignedInstallerId: getString(formData, "assignedInstallerId"),
    status: getString(formData, "status") || "requested",
    createdAt: now,
    updatedAt: now
  });

  revalidatePath("/proyectos");
  redirect("/proyectos?status=project-created");
}
