import { shouldUseFirestoreRepository } from "./firestore-repository";

type WritableValue = string | number | boolean | null | WritableRecord | WritableValue[];

interface WritableRecord {
  [key: string]: WritableValue;
}

function getFirestoreProjectId(): string {
  return process.env.FIREBASE_PROJECT_ID ?? process.env.GOOGLE_CLOUD_PROJECT ?? process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "";
}

function getFirestoreBaseUrl(): string {
  const emulatorHost = process.env.FIRESTORE_EMULATOR_HOST;

  if (emulatorHost) {
    return `http://${emulatorHost}/v1/projects/${getFirestoreProjectId()}/databases/(default)/documents`;
  }

  return `https://firestore.googleapis.com/v1/projects/${getFirestoreProjectId()}/databases/(default)/documents`;
}

function encodeValue(value: WritableValue): object {
  if (value === null) {
    return { nullValue: null };
  }

  if (Array.isArray(value)) {
    return { arrayValue: { values: value.map(encodeValue) } };
  }

  if (typeof value === "boolean") {
    return { booleanValue: value };
  }

  if (typeof value === "number") {
    return Number.isInteger(value) ? { integerValue: String(value) } : { doubleValue: value };
  }

  if (typeof value === "object") {
    return {
      mapValue: {
        fields: Object.fromEntries(Object.entries(value).map(([key, nestedValue]) => [key, encodeValue(nestedValue)]))
      }
    };
  }

  return { stringValue: value };
}

function encodeDocument(record: WritableRecord) {
  return {
    fields: Object.fromEntries(Object.entries(record).map(([key, value]) => [key, encodeValue(value)]))
  };
}

export async function writeFirestoreDocument(
  collection: string,
  documentId: string,
  record: WritableRecord
): Promise<{ persisted: boolean }> {
  if (!shouldUseFirestoreRepository()) {
    return { persisted: false };
  }

  const token = process.env.FIRESTORE_REST_BEARER_TOKEN;
  const emulatorToken = process.env.FIRESTORE_EMULATOR_HOST ? "owner" : "";
  const response = await fetch(`${getFirestoreBaseUrl()}/${collection}/${documentId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(token || emulatorToken ? { Authorization: `Bearer ${token || emulatorToken}` } : {})
    },
    body: JSON.stringify(encodeDocument(record))
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Firestore write failed for ${collection}/${documentId}: ${response.status} ${body}`);
  }

  return { persisted: true };
}
