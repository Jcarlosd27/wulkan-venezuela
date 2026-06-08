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
  return Number.isFinite(value) && value >= 0 ? value : 0;
}

function getStringList(formData: FormData, key: string): string[] {
  return getString(formData, key)
    .split(/[\n,]+/)
    .map((value) => value.trim())
    .filter(Boolean);
}

function normalizeSku(value: string): string {
  return value.trim().toUpperCase().replace(/\s+/g, "-");
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

export async function createProductAction(formData: FormData) {
  const title = getString(formData, "title");
  const sku = normalizeSku(getString(formData, "sku"));
  const verticalId = getString(formData, "verticalId");
  const type = getString(formData, "type") || "machine";
  const status = getString(formData, "status") || "active";
  const description = getString(formData, "description");
  const categoryId = getString(formData, "categoryId") || verticalId;
  const sellerId = getString(formData, "sellerId") || "avalon-group";
  const warranty = getString(formData, "warranty");
  const technicalSheetUrl = getString(formData, "technicalSheetUrl");
  const manualUrl = getString(formData, "manualUrl");
  const imageUrls = getStringList(formData, "imageUrls");
  const publicPrice = getNumber(formData, "publicPrice");
  const b2bPrice = getNumber(formData, "b2bPrice");
  const stock = Math.floor(getNumber(formData, "stock"));
  const now = new Date().toISOString();

  if (!title || !sku || !verticalId) {
    redirect("/productos/nuevo?status=invalid");
  }

  const productId = normalizeId(`prod-${sku}`);

  const productWrite = await writeFirestoreDocument(firebaseCollections.products, productId, {
    sku,
    title,
    description,
    verticalId,
    type,
    categoryId,
    sellerId,
    publicPrice: publicPrice > 0 ? { amount: publicPrice, currency: "USD" } : null,
    b2bPrice: b2bPrice > 0 ? { amount: b2bPrice, currency: "USD" } : null,
    baseCurrency: "USD",
    stock,
    countryAvailability: ["VE"],
    imageUrls,
    technicalSheetUrl: technicalSheetUrl || null,
    manualUrl: manualUrl || null,
    warranty: warranty || null,
    compatibilityIds: [],
    requiresQuote: formData.get("requiresQuote") === "on",
    requiresInstallation: formData.get("requiresInstallation") === "on",
    requiresTechnicalValidation: formData.get("requiresTechnicalValidation") === "on",
    status,
    createdAt: now,
    updatedAt: now
  });

  if (publicPrice > 0) {
    await writeFirestoreDocument(firebaseCollections.productPrices, `price-${productId}-public`, {
      productId,
      type: "public",
      amount: publicPrice,
      currency: "USD",
      validFrom: now,
      changedBy: "admin-form"
    });
  }

  if (b2bPrice > 0) {
    await writeFirestoreDocument(firebaseCollections.productPrices, `price-${productId}-b2b`, {
      productId,
      type: "b2b",
      amount: b2bPrice,
      currency: "USD",
      validFrom: now,
      changedBy: "admin-form"
    });
  }

  await writeFirestoreDocument(firebaseCollections.productStock, `stock-${productId}-main`, {
    productId,
    companyId: "avalon-group",
    locationId: "loc-caracas-001",
    available: stock,
    reserved: 0,
    lowStockThreshold: 5,
    updatedAt: now
  });

  revalidatePath("/productos");
  redirect(productWrite.persisted ? `/productos/${productId}` : "/productos?status=product-created");
}

export async function updateProductPricingAction(formData: FormData) {
  const productId = getString(formData, "productId");
  const publicPrice = getNumber(formData, "publicPrice");
  const b2bPrice = getNumber(formData, "b2bPrice");
  const changedBy = getString(formData, "changedBy") || "admin-price-form";
  const now = new Date().toISOString();

  if (!productId || publicPrice <= 0) {
    redirect(productId ? `/productos/${productId}?status=invalid-price` : "/productos?status=invalid-price");
  }

  await writeFirestoreDocument(firebaseCollections.products, productId, {
    publicPrice: { amount: publicPrice, currency: "USD" },
    b2bPrice: b2bPrice > 0 ? { amount: b2bPrice, currency: "USD" } : null,
    updatedAt: now
  });

  await writeFirestoreDocument(firebaseCollections.productPrices, `price-${productId}-public-${Date.now()}`, {
    productId,
    type: "public",
    amount: publicPrice,
    currency: "USD",
    validFrom: now,
    changedBy
  });

  if (b2bPrice > 0) {
    await writeFirestoreDocument(firebaseCollections.productPrices, `price-${productId}-b2b-${Date.now()}`, {
      productId,
      type: "b2b",
      amount: b2bPrice,
      currency: "USD",
      validFrom: now,
      changedBy
    });
  }

  revalidatePath("/productos");
  revalidatePath(`/productos/${productId}`);
  redirect(`/productos/${productId}?status=price-updated`);
}
