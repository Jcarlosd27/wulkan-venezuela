const projectId =
  process.env.FIREBASE_PROJECT_ID ?? process.env.GOOGLE_CLOUD_PROJECT ?? process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
const emulatorHost = process.env.FIRESTORE_EMULATOR_HOST;
const bearerToken = process.env.FIRESTORE_REST_BEARER_TOKEN;
const authorizationToken = bearerToken || (emulatorHost ? "owner" : "");

if (!projectId) {
  throw new Error("FIREBASE_PROJECT_ID is required.");
}

const baseUrl = emulatorHost
  ? `http://${emulatorHost}/v1/projects/${projectId}/databases/(default)/documents`
  : `https://firestore.googleapis.com/v1/projects/${projectId}/databases/(default)/documents`;

const seedData = {
  users: [
    {
      id: "usr-super-admin",
      name: "Admin Maestro",
      email: "admin@wulkan.local",
      phone: "+58 000-0000000",
      role: "super_admin",
      permissions: ["user.manage", "permission.manage", "vertical.manage", "product.approve", "payment.confirm"],
      status: "active",
      country: "VE",
      lastLoginAt: "2026-05-19T18:00:00.000Z"
    },
    {
      id: "usr-operador",
      name: "Operador Wulkan",
      email: "operador@wulkan.local",
      role: "wulkan_operator",
      permissions: [
        "catalog.view",
        "order.view",
        "order.status.change",
        "purchase_order.approve",
        "payment.view",
        "payment.confirm",
        "service_case.update",
        "location.manage",
        "report.view"
      ],
      status: "active",
      country: "VE",
      lastLoginAt: "2026-05-19T18:20:00.000Z"
    }
  ],
  business_verticals: [
    {
      id: "machinery-garden",
      name: "Maquinaria y jardin",
      slug: "maquinaria-jardin",
      description: "Equipos, accesorios y repuestos para trabajo tecnico y jardin.",
      status: "active",
      countries: ["VE"],
      requiresTechnicalAttributes: true,
      availableProductTypes: ["machine", "spare_part", "accessory"],
      attributeSchema: []
    },
    {
      id: "spare-parts",
      name: "Repuestos",
      slug: "repuestos",
      description: "Compatibilidades, SKU y piezas de reposicion.",
      status: "active",
      countries: ["VE"],
      requiresTechnicalAttributes: true,
      availableProductTypes: ["spare_part"],
      attributeSchema: []
    }
  ],
  companies: [
    {
      id: "avalon-group",
      legalName: "Avalon Group",
      commercialName: "Wulkan Venezuela",
      type: "seller",
      status: "active",
      contacts: [{ name: "Operacion Wulkan", phone: "+58 000-0000000" }],
      address: {
        country: "VE",
        state: "Distrito Capital",
        city: "Caracas",
        line1: "Base operativa Wulkan",
        phone: "+58 000-0000000"
      },
      commercialTerms: { b2bEnabled: true, creditEnabled: false, minimumPurchaseUsd: 100, paymentTermsDays: 0, priceListId: "public-ve" },
      activeVerticalIds: ["machinery-garden", "spare-parts"]
    },
    {
      id: "ferreteria-demo",
      legalName: "Ferreteria Demo C.A.",
      commercialName: "Ferreteria Demo",
      type: "hardware_store",
      status: "pending",
      contacts: [{ name: "Compras", phone: "+58 000-1111111" }],
      address: {
        country: "VE",
        state: "Carabobo",
        city: "Valencia",
        line1: "Zona comercial demo",
        phone: "+58 000-1111111"
      },
      commercialTerms: {
        b2bEnabled: true,
        creditEnabled: false,
        defaultDiscountPercent: 8,
        minimumPurchaseUsd: 150,
        paymentTermsDays: 0,
        priceListId: "hardware-store-ve"
      },
      activeVerticalIds: ["machinery-garden", "spare-parts"]
    }
  ],
  products: [
    {
      id: "prod-motosierra-45cc",
      sku: "WUL-MOT-45CC",
      title: "Motosierra 45cc",
      description: "Equipo de corte para uso tecnico y jardin.",
      verticalId: "machinery-garden",
      type: "machine",
      categoryId: "motosierras",
      sellerId: "avalon-group",
      publicPrice: { amount: 185, currency: "USD" },
      b2bPrice: { amount: 162, currency: "USD" },
      baseCurrency: "USD",
      stock: 12,
      countryAvailability: ["VE"],
      imageUrls: [],
      warranty: "6 meses",
      compatibilityIds: ["prod-cadena-18"],
      requiresQuote: false,
      requiresInstallation: false,
      requiresTechnicalValidation: false,
      status: "active"
    },
    {
      id: "prod-cadena-18",
      sku: "WUL-REP-CAD18",
      title: "Cadena 18 pulgadas compatible",
      description: "Repuesto compatible con motosierras seleccionadas.",
      verticalId: "spare-parts",
      type: "spare_part",
      categoryId: "cadenas",
      sellerId: "avalon-group",
      publicPrice: { amount: 18, currency: "USD" },
      b2bPrice: { amount: 15, currency: "USD" },
      baseCurrency: "USD",
      stock: 4,
      countryAvailability: ["VE"],
      imageUrls: [],
      warranty: "30 dias",
      compatibilityIds: ["prod-motosierra-45cc"],
      requiresQuote: false,
      requiresInstallation: false,
      requiresTechnicalValidation: true,
      status: "active"
    }
  ],
  product_stock: [
    {
      id: "stock-motosierra-caracas",
      productId: "prod-motosierra-45cc",
      companyId: "avalon-group",
      locationId: "loc-caracas-001",
      available: 12,
      reserved: 0,
      lowStockThreshold: 3,
      updatedAt: "2026-05-19T18:00:00.000Z"
    }
  ],
  product_compatibilities: [
    {
      id: "compat-cadena-motosierra",
      sourceProductId: "prod-cadena-18",
      compatibleProductId: "prod-motosierra-45cc",
      machineModel: "Motosierra 45cc",
      engineModel: "45cc gasolina",
      notes: "Validar largo de espada antes de entregar.",
      requiresTechnicalValidation: true,
      status: "active"
    }
  ],
  orders: [
    {
      id: "ord-1001",
      customerId: "customer-demo",
      items: [
        {
          productId: "prod-motosierra-45cc",
          sku: "WUL-MOT-45CC",
          title: "Motosierra 45cc",
          quantity: 1,
          unitPrice: { amount: 185, currency: "USD" },
          total: { amount: 185, currency: "USD" }
        }
      ],
      subtotal: { amount: 185, currency: "USD" },
      total: { amount: 185, currency: "USD" },
      currency: "USD",
      exchangeRateUsdVes: 38.5,
      status: "payment_under_review",
      paymentId: "pay-1001",
      createdAt: "2026-05-19T18:00:00.000Z"
    }
  ],
  payments: [
    {
      id: "pay-1001",
      orderId: "ord-1001",
      method: "bank_transfer",
      amountUsd: 185,
      amountVes: 7122.5,
      currency: "USD",
      exchangeRate: 38.5,
      referenceNumber: "REF-DEMO-1001",
      status: "under_review"
    }
  ],
  purchase_orders: [
    {
      id: "po-2001",
      requesterCompanyId: "ferreteria-demo",
      requesterUserId: "buyer-demo",
      items: [
        {
          productId: "prod-cadena-18",
          sku: "WUL-REP-CAD18",
          title: "Cadena 18 pulgadas compatible",
          quantity: 10,
          unitPrice: { amount: 15, currency: "USD" },
          total: { amount: 150, currency: "USD" }
        }
      ],
      subtotal: { amount: 150, currency: "USD" },
      total: { amount: 150, currency: "USD" },
      currency: "USD",
      status: "under_wulkan_review",
      requestedDeliveryDate: "2026-05-24",
      notes: "Reposicion de cadenas por baja existencia."
    }
  ],
  service_cases: [
    {
      id: "svc-3001",
      technicalServiceId: "service-demo",
      customerName: "Cliente Demo",
      customerContact: "+58 000-2222222",
      machineId: "prod-motosierra-45cc",
      serialNumber: "SN-DEMO-001",
      symptoms: "No enciende y requiere revision de cadena.",
      photoUrls: [],
      requestedParts: [{ productId: "prod-cadena-18", sku: "WUL-REP-CAD18", description: "Cadena 18 pulgadas", quantity: 1 }],
      usedParts: [],
      status: "diagnosed",
      warrantyRelated: false,
      createdAt: "2026-05-19T19:00:00.000Z"
    }
  ],
  locations: [
    {
      id: "loc-caracas-001",
      name: "Punto autorizado Caracas",
      type: "pickup_point",
      address: {
        country: "VE",
        state: "Distrito Capital",
        city: "Caracas",
        municipality: "Chacao",
        line1: "Zona comercial demo",
        phone: "+58 000-3333333"
      },
      coordinates: { lat: 10.498, lng: -66.853 },
      phone: "+58 000-3333333",
      whatsapp: "+58 000-3333333",
      schedule: "Lunes a viernes, 9:00 a 17:00",
      availableServices: ["pickup", "technical_support", "case_reception"],
      coverageAreas: [{ country: "VE", state: "Distrito Capital", city: "Caracas", municipality: "Chacao", radiusKm: 12 }],
      acceptsWalkIns: true,
      status: "active",
      companyId: "avalon-group"
    }
  ],
  mobile_announcements: [
    {
      id: "ann-home-launch",
      title: "Lanzamiento Wulkan Venezuela",
      body: "Compra equipos Wulkan en USD con referencia en bolivares y soporte tecnico autorizado.",
      placement: "home",
      priority: 100,
      ctaLabel: "Ver catalogo",
      ctaUrl: "wulkan://catalog",
      imageUrl: "/brand/wulkan-logo.svg",
      startsAt: "2026-06-01T00:00:00.000Z",
      status: "active",
      createdBy: "usr-super-admin",
      updatedAt: "2026-06-08T00:00:00.000Z"
    },
    {
      id: "ann-catalog-stock",
      title: "Stock disponible",
      body: "Revisa maquinaria, repuestos y productos listos para venta directa.",
      placement: "catalog",
      priority: 80,
      ctaLabel: "Comprar",
      ctaUrl: "wulkan://catalog?filter=available",
      startsAt: "2026-06-01T00:00:00.000Z",
      status: "active",
      createdBy: "usr-operador",
      updatedAt: "2026-06-08T00:00:00.000Z"
    },
    {
      id: "ann-checkout-review",
      title: "Validacion de pagos",
      body: "Los pagos en bolivares quedan bajo revision Wulkan antes del despacho.",
      placement: "checkout",
      priority: 60,
      startsAt: "2026-06-01T00:00:00.000Z",
      status: "active",
      createdBy: "usr-operador",
      updatedAt: "2026-06-08T00:00:00.000Z"
    }
  ],
  app_settings: [
    {
      id: "wulkan-ve",
      country: "VE",
      primaryCurrency: "USD",
      secondaryCurrency: "VES",
      maintenanceMode: false,
      whatsappSupportNumber: "+58 000-4444444",
      exchangeRate: {
        id: "rate-usd-ves",
        baseCurrency: "USD",
        targetCurrency: "VES",
        rate: 38.5,
        source: "manual",
        activeFrom: "2026-05-19T00:00:00.000Z",
        updatedBy: "usr-super-admin"
      }
    }
  ],
  audit_logs: [
    {
      id: "aud-001",
      action: "seed_loaded",
      actorUserId: "system",
      targetCollection: "app_settings",
      targetId: "wulkan-ve",
      after: { status: "ready" },
      createdAt: "2026-05-20T00:00:00.000Z",
      origin: "seed"
    }
  ]
};

function encodeValue(value) {
  if (value === null || value === undefined) {
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

  return { stringValue: String(value) };
}

function encodeDocument(record) {
  const { id, ...fields } = record;
  return {
    fields: Object.fromEntries(Object.entries(fields).map(([key, value]) => [key, encodeValue(value)]))
  };
}

async function writeDocument(collection, record) {
  const response = await fetch(`${baseUrl}/${collection}/${record.id}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(authorizationToken ? { Authorization: `Bearer ${authorizationToken}` } : {})
    },
    body: JSON.stringify(encodeDocument(record))
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Seed failed for ${collection}/${record.id}: ${response.status} ${body}`);
  }
}

let total = 0;

for (const [collection, records] of Object.entries(seedData)) {
  for (const record of records) {
    await writeDocument(collection, record);
    total += 1;
  }
}

console.log(`Seeded ${total} Firestore documents into ${projectId}.`);
