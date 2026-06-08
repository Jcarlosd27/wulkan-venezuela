const projectId =
  process.env.FIREBASE_PROJECT_ID ?? process.env.GOOGLE_CLOUD_PROJECT ?? process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
const emulatorHost = process.env.FIRESTORE_EMULATOR_HOST;
const bearerToken = process.env.FIRESTORE_REST_BEARER_TOKEN;
const authorizationToken = bearerToken || (emulatorHost ? "owner" : "");

if (!projectId) {
  throw new Error("FIREBASE_PROJECT_ID is required.");
}

if (!emulatorHost && !bearerToken) {
  throw new Error("FIRESTORE_EMULATOR_HOST or FIRESTORE_REST_BEARER_TOKEN is required.");
}

const baseUrl = emulatorHost
  ? `http://${emulatorHost}/v1/projects/${projectId}/databases/(default)/documents`
  : `https://firestore.googleapis.com/v1/projects/${projectId}/databases/(default)/documents`;

const requiredCollections = {
  users: 1,
  business_verticals: 1,
  companies: 1,
  products: 1,
  product_stock: 1,
  product_compatibilities: 1,
  orders: 1,
  payments: 1,
  purchase_orders: 1,
  service_cases: 1,
  locations: 1,
  app_settings: 1,
  audit_logs: 1
};

async function countCollection(collection) {
  const response = await fetch(`${baseUrl}/${collection}`, {
    headers: {
      "Content-Type": "application/json",
      ...(authorizationToken ? { Authorization: `Bearer ${authorizationToken}` } : {})
    }
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Verify failed for ${collection}: ${response.status} ${body}`);
  }

  const payload = await response.json();
  return payload.documents?.length ?? 0;
}

const counts = {};

for (const [collection, minimum] of Object.entries(requiredCollections)) {
  const count = await countCollection(collection);
  counts[collection] = count;

  if (count < minimum) {
    throw new Error(`Expected at least ${minimum} document(s) in ${collection}, found ${count}.`);
  }
}

console.log("Firestore verification passed:");
console.table(counts);
