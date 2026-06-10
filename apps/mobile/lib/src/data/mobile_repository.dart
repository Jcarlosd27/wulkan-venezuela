import 'dart:convert';
import 'dart:io';

import 'package:cloud_firestore/cloud_firestore.dart';

import '../auth/mobile_auth.dart';
import '../config/mobile_environment.dart';
import '../domain/mobile_models.dart';
import 'avalon_garden_catalog.dart';

abstract class MobileRepository {
  Future<List<MobileCategory>> listCategories();
  Future<List<MobileProduct>> listProducts();
  Future<MobileProductPage> listProductPage(MobileProductQuery query);
  Future<MobileProduct?> getProduct(String id);
  Future<List<MobileLocation>> listLocations();
  Future<List<MobileAnnouncement>> listAnnouncements(String placement);
  Future<MobileCreditSnapshot> getCredit(String customerId);
  Future<List<MobileOrderSummary>> listOrders(String customerId);
  Future<MobileSellerSummary> getSellerSummary();
  Future<List<MobileSellerClient>> listSellerClients();
  Future<List<MobileOrderSummary>> listSellerOrders();
  Future<List<MobileOrderSummary>> listSellerCommissions();
}

class MockMobileRepository implements MobileRepository {
  static const _categories = [
    MobileCategory(
      id: "machinery-garden",
      name: "Maquinaria y jardin",
      description: "Equipos, accesorios y repuestos",
    ),
    MobileCategory(
      id: "spare-parts",
      name: "Repuestos",
      description: "Busca por SKU, modelo o compatibilidad",
    ),
    MobileCategory(
      id: "lighting",
      name: "Iluminacion",
      description: "Productos y proyectos con instalacion",
    ),
    MobileCategory(
      id: "technical-services",
      name: "Servicios tecnicos",
      description: "Diagnostico, reparacion y garantia",
    ),
  ];

  static const _products = [
    MobileProduct(
      id: "prod-motosierra-45cc",
      sku: "WUL-MOT-45CC",
      name: "Motosierra 45cc",
      verticalName: "Maquinaria y jardin",
      description: "Equipo principal para venta directa y red ferretera.",
      publicPriceUsd: 185,
      b2bPriceUsd: 162,
      availableStock: 12,
      badge: "Comprar",
      requiresQuote: false,
      requiresTechnicalValidation: false,
      compatibilityNotes: [
        "Compatible con cadena WUL-REP-CAD18",
        "Validar largo de espada antes de entregar",
      ],
    ),
    MobileProduct(
      id: "prod-cadena-18",
      sku: "WUL-REP-CAD18",
      name: "Cadena 18 pulgadas compatible",
      verticalName: "Repuestos",
      description: "Repuesto compatible con motosierra 45cc.",
      publicPriceUsd: 18,
      b2bPriceUsd: 15,
      availableStock: 3,
      badge: "Validar",
      requiresQuote: false,
      requiresTechnicalValidation: true,
      compatibilityNotes: [
        "Compatible con WUL-MOT-45CC",
        "Stock critico, validar antes de prometer entrega",
      ],
    ),
    MobileProduct(
      id: "prod-panel-led-60w",
      sku: "WUL-ILU-LED60",
      name: "Panel LED tecnico 60W",
      verticalName: "Iluminacion",
      description: "Producto para cotizacion e instalacion tecnica.",
      publicPriceUsd: 42,
      b2bPriceUsd: 36,
      availableStock: 0,
      badge: "Cotizar",
      requiresQuote: true,
      requiresTechnicalValidation: false,
      compatibilityNotes: [
        "Requiere validacion de metraje y punto de instalacion",
      ],
    ),
    ...avalonGardenProducts,
  ];

  static const _locations = [
    MobileLocation(
      id: "loc-caracas-chacao",
      name: "Punto autorizado Caracas",
      subtitle: "Retiro, soporte tecnico y recepcion de casos - Chacao",
    ),
    MobileLocation(
      id: "loc-valencia-demo",
      name: "Ferreteria Demo Valencia",
      subtitle: "Venta B2B, retail y retiro - radio 18 km",
    ),
  ];

  static final _announcements = [
    MobileAnnouncement(
      id: "ann-home-launch",
      title: "Lanzamiento Wulkan Venezuela",
      body:
          "Compra equipos Wulkan en USD con referencia en bolivares y soporte tecnico autorizado.",
      placement: "home",
      priority: 100,
      ctaLabel: "Ver catalogo",
      ctaUrl: "wulkan://catalog",
      startsAt: DateTime(2026, 6, 1),
      status: "active",
    ),
    MobileAnnouncement(
      id: "ann-catalog-stock",
      title: "Stock disponible",
      body:
          "Revisa maquinaria, repuestos y productos listos para venta directa.",
      placement: "catalog",
      priority: 80,
      ctaLabel: "Comprar",
      ctaUrl: "wulkan://catalog?filter=available",
      startsAt: DateTime(2026, 6, 1),
      status: "active",
    ),
    MobileAnnouncement(
      id: "ann-checkout-review",
      title: "Validacion de pagos",
      body:
          "Los pagos en bolivares quedan bajo revision Wulkan antes del despacho.",
      placement: "checkout",
      priority: 60,
      startsAt: DateTime(2026, 6, 1),
      status: "active",
    ),
  ];

  @override
  Future<List<MobileCategory>> listCategories() async => _categories;

  @override
  Future<List<MobileProduct>> listProducts() async => _products;

  @override
  Future<MobileProductPage> listProductPage(MobileProductQuery query) async {
    final start = int.tryParse(query.cursor ?? "") ?? 0;
    final pageLimit = query.limit.clamp(1, 100).toInt();
    final filtered =
        _products.where((product) => _matchesQuery(product, query)).toList();
    final end = (start + pageLimit).clamp(0, filtered.length).toInt();
    final page = filtered.sublist(start, end);

    return MobileProductPage(
      products: page,
      hasMore: end < filtered.length,
      nextCursor: end < filtered.length ? end.toString() : null,
    );
  }

  @override
  Future<MobileProduct?> getProduct(String id) async {
    for (final product in _products) {
      if (product.id == id) {
        return product;
      }
    }

    return null;
  }

  @override
  Future<List<MobileLocation>> listLocations() async => _locations;

  @override
  Future<List<MobileAnnouncement>> listAnnouncements(String placement) async {
    return _announcements
        .where((announcement) =>
            announcement.placement == placement && announcement.isActive)
        .toList()
      ..sort(_sortAnnouncements);
  }

  @override
  Future<MobileCreditSnapshot> getCredit(String customerId) async {
    return MobileCreditSnapshot(
      customerId: customerId,
      creditEnabled: true,
      creditLimitUsd: 1000,
      creditUsedUsd: 0,
      creditOrdersUsd: 85,
      creditExposureUsd: 85,
      creditAvailableUsd: 915,
      paymentTermsDays: 15,
      status: "in_use",
      allowedPaymentTermsDays: const [0, 15, 30],
      defaultSaleType: "term_credit",
      assignedSeller: const MobileSellerSnapshot(
        id: "seller-demo",
        name: "Vendedor Wulkan",
      ),
    );
  }

  @override
  Future<List<MobileOrderSummary>> listOrders(String customerId) async {
    return [
      MobileOrderSummary(
        id: "ord-mobile-demo",
        status: "partial_paid",
        totalUsd: 185,
        paidUsd: 100,
        balanceUsd: 85,
        itemsCount: 1,
        createdAt: DateTime(2026, 6, 8),
        paymentStatus: "partial",
        stockStatus: "reserved",
      ),
    ];
  }

  @override
  Future<MobileSellerSummary> getSellerSummary() async {
    return const MobileSellerSummary(
      sellerId: "admin-seller-demo",
      sellerName: "Vendedor Wulkan",
      roleLabel: "Vendedor",
      clientsCount: 1,
      ordersCount: 1,
      pendingCreditRequests: 1,
      salesUsd: 185,
      openBalanceUsd: 85,
      pendingCommissionUsd: 7.4,
      approvedCommissionUsd: 0,
      paidCommissionUsd: 0,
    );
  }

  @override
  Future<List<MobileSellerClient>> listSellerClients() async {
    return const [
      MobileSellerClient(
        id: "client-ferreteria-valencia",
        businessName: "Ferreteria Demo Valencia",
        email: "ferreteria@wulkan.local",
        phone: "+58 000-0000000",
        city: "Valencia",
        state: "Carabobo",
        creditEnabled: true,
        creditStatus: "in_use",
        creditLimitUsd: 1000,
        creditAvailableUsd: 915,
        creditExposureUsd: 85,
        creditRequestStatus: "approved",
      ),
    ];
  }

  @override
  Future<List<MobileOrderSummary>> listSellerOrders() async {
    return listOrders("client-ferreteria-valencia");
  }

  @override
  Future<List<MobileOrderSummary>> listSellerCommissions() async {
    return listSellerOrders();
  }
}

class FirestoreMobileRepository implements MobileRepository {
  FirestoreMobileRepository({FirebaseFirestore? firestore})
      : _firestore = firestore ?? FirebaseFirestore.instance;

  final FirebaseFirestore _firestore;

  @override
  Future<List<MobileCategory>> listCategories() async {
    final snapshot = await _firestore
        .collection("business_verticals")
        .where("status", isEqualTo: "active")
        .get();

    return snapshot.docs.map((doc) {
      final data = doc.data();

      return MobileCategory(
        id: doc.id,
        name: _asString(data["name"], fallback: doc.id),
        description:
            _asString(data["description"], fallback: "Categoria Wulkan"),
      );
    }).toList();
  }

  @override
  Future<List<MobileProduct>> listProducts() async {
    final page = await listProductPage(const MobileProductQuery(limit: 100));
    return page.products;
  }

  @override
  Future<MobileProductPage> listProductPage(MobileProductQuery query) async {
    final requestedLimit = query.limit.clamp(1, 50).toInt();
    Query<Map<String, dynamic>> firestoreQuery = _firestore
        .collection("products")
        .where("status", isEqualTo: "active")
        .orderBy(FieldPath.documentId)
        .limit(requestedLimit);

    if (query.cursor?.isNotEmpty == true) {
      firestoreQuery = firestoreQuery.startAfter([query.cursor]);
    }

    final snapshot = await firestoreQuery.get();

    final products = snapshot.docs
        .map((doc) => mapFirestoreProduct(doc.id, doc.data()))
        .where((product) => _matchesQuery(product, query))
        .toList();
    final nextCursor = snapshot.docs.isNotEmpty ? snapshot.docs.last.id : null;

    return MobileProductPage(
      products: products,
      hasMore: snapshot.docs.length == requestedLimit,
      nextCursor: nextCursor,
    );
  }

  @override
  Future<MobileProduct?> getProduct(String id) async {
    final doc = await _firestore.collection("products").doc(id).get();

    if (!doc.exists) {
      return null;
    }

    return mapFirestoreProduct(doc.id, doc.data() ?? {});
  }

  @override
  Future<List<MobileLocation>> listLocations() async {
    final snapshot = await _firestore.collection("locations").limit(30).get();

    return snapshot.docs.map((doc) {
      final data = doc.data();
      final address = _asMap(data["address"]);
      final city = _asString(address["city"]);
      final services =
          (data["availableServices"] as List<dynamic>? ?? []).join(", ");

      return MobileLocation(
        id: doc.id,
        name: _asString(data["name"], fallback: doc.id),
        subtitle: [services, city].where((item) => item.isNotEmpty).join(" - "),
      );
    }).toList();
  }

  @override
  Future<List<MobileAnnouncement>> listAnnouncements(String placement) async {
    final snapshot = await _firestore
        .collection("mobile_announcements")
        .where("status", isEqualTo: "active")
        .where("placement", isEqualTo: placement)
        .get();
    final announcements = snapshot.docs
        .map((doc) => mapFirestoreAnnouncement(doc.id, doc.data()))
        .where((announcement) => announcement.isActive)
        .toList()
      ..sort(_sortAnnouncements);

    return announcements;
  }

  @override
  Future<MobileCreditSnapshot> getCredit(String customerId) async {
    return MobileCreditSnapshot(
      customerId: customerId,
      creditEnabled: false,
      creditLimitUsd: 0,
      creditUsedUsd: 0,
      creditOrdersUsd: 0,
      creditExposureUsd: 0,
      creditAvailableUsd: 0,
      paymentTermsDays: 0,
      status: "without_credit",
      allowedPaymentTermsDays: const [0],
      defaultSaleType: "cash",
    );
  }

  @override
  Future<List<MobileOrderSummary>> listOrders(String customerId) async {
    return const [];
  }

  @override
  Future<MobileSellerSummary> getSellerSummary() async {
    return const MobileSellerSummary(
      sellerId: "",
      sellerName: "Vendedor Wulkan",
      roleLabel: "Vendedor",
      clientsCount: 0,
      ordersCount: 0,
      pendingCreditRequests: 0,
      salesUsd: 0,
      openBalanceUsd: 0,
      pendingCommissionUsd: 0,
      approvedCommissionUsd: 0,
      paidCommissionUsd: 0,
    );
  }

  @override
  Future<List<MobileSellerClient>> listSellerClients() async => const [];

  @override
  Future<List<MobileOrderSummary>> listSellerOrders() async => const [];

  @override
  Future<List<MobileOrderSummary>> listSellerCommissions() async => const [];
}

class ApiMobileRepository implements MobileRepository {
  ApiMobileRepository({required String baseUrl})
      : _baseUri = Uri.parse(baseUrl);

  final Uri _baseUri;

  @override
  Future<List<MobileCategory>> listCategories() async {
    final items = await _getItems("/categories");
    return items
        .map(
          (item) => MobileCategory(
            id: _asString(item["id"]),
            name: _asString(item["name"], fallback: "Categoria Wulkan"),
            description: _asString(item["description"]),
          ),
        )
        .toList();
  }

  @override
  Future<List<MobileProduct>> listProducts() async {
    final page = await listProductPage(const MobileProductQuery(limit: 100));
    return page.products;
  }

  @override
  Future<MobileProductPage> listProductPage(MobileProductQuery query) async {
    final items = await _getItems("/products");
    final products = items
        .map((item) => mapApiProduct(_asString(item["id"]), item))
        .where((product) => _matchesQuery(product, query))
        .toList();
    final start = int.tryParse(query.cursor ?? "") ?? 0;
    final limit = query.limit.clamp(1, 100).toInt();
    final end = (start + limit).clamp(0, products.length).toInt();

    return MobileProductPage(
      products: products.sublist(start, end),
      hasMore: end < products.length,
      nextCursor: end < products.length ? end.toString() : null,
    );
  }

  @override
  Future<MobileProduct?> getProduct(String id) async {
    final products = await listProducts();
    for (final product in products) {
      if (product.id == id) {
        return product;
      }
    }
    return null;
  }

  @override
  Future<List<MobileLocation>> listLocations() async {
    final items = await _getItems("/locations");
    return items
        .map(
          (item) => MobileLocation(
            id: _asString(item["id"]),
            name: _asString(item["name"], fallback: "Punto Wulkan"),
            subtitle: _asString(item["subtitle"]),
          ),
        )
        .toList();
  }

  @override
  Future<List<MobileAnnouncement>> listAnnouncements(String placement) async {
    final items = await _getItems(
      "/announcements",
      queryParameters: {"placement": placement},
    );
    final announcements = items
        .map((item) => mapApiAnnouncement(_asString(item["id"]), item))
        .where((announcement) => announcement.isActive)
        .toList()
      ..sort(_sortAnnouncements);
    return announcements;
  }

  @override
  Future<MobileCreditSnapshot> getCredit(String customerId) async {
    final payload = await _getPayload(
      "/credit",
      queryParameters: {"customerId": customerId},
    );
    final credit = payload["credit"];
    final data = credit is Map<String, dynamic> ? credit : <String, dynamic>{};
    final seller = data["assignedSeller"];
    final sellerData =
        seller is Map<String, dynamic> ? seller : <String, dynamic>{};

    return MobileCreditSnapshot(
      customerId: _asString(data["customerId"], fallback: customerId),
      creditEnabled: data["creditEnabled"] == true,
      creditLimitUsd: _asDouble(data["creditLimitUsd"]),
      creditUsedUsd: _asDouble(data["creditUsedUsd"]),
      creditOrdersUsd: _asDouble(data["creditOrdersUsd"]),
      creditExposureUsd: _asDouble(data["creditExposureUsd"]),
      creditAvailableUsd: _asDouble(data["creditAvailableUsd"]),
      paymentTermsDays: _asInt(data["paymentTermsDays"]),
      status: _asString(data["status"], fallback: "without_credit"),
      allowedPaymentTermsDays: _asIntList(
        data["allowedPaymentTermsDays"],
        fallback: const [0],
      ),
      defaultSaleType: _asString(data["defaultSaleType"], fallback: "cash"),
      assignedSeller: MobileSellerSnapshot(
        id: _asString(sellerData["id"]),
        name: _asString(sellerData["name"]),
      ),
    );
  }

  @override
  Future<List<MobileOrderSummary>> listOrders(String customerId) async {
    final items = await _getItems(
      "/orders",
      queryParameters: {"customerId": customerId},
    );
    return items.map(mapApiOrder).toList();
  }

  @override
  Future<MobileSellerSummary> getSellerSummary() async {
    final payload = await _getPayload("/seller/summary");
    final data = payload["summary"];
    return mapApiSellerSummary(
      data is Map<String, dynamic> ? data : <String, dynamic>{},
    );
  }

  @override
  Future<List<MobileSellerClient>> listSellerClients() async {
    final items = await _getItems("/seller/clients");
    return items.map(mapApiSellerClient).toList();
  }

  @override
  Future<List<MobileOrderSummary>> listSellerOrders() async {
    final items = await _getItems("/seller/orders");
    return items.map(mapApiOrder).toList();
  }

  @override
  Future<List<MobileOrderSummary>> listSellerCommissions() async {
    final items = await _getItems("/seller/commissions");
    return items.map(mapApiOrder).toList();
  }

  Future<Map<String, dynamic>> _getPayload(
    String path, {
    Map<String, String>? queryParameters,
  }) async {
    final uri = _baseUri.replace(
      path: "${_baseUri.path}$path",
      queryParameters: queryParameters,
    );
    final client = HttpClient();

    try {
      final request = await client.getUrl(uri);
      final session = await mobileAuthRepository.getCurrentSession();
      if (session.accessToken.isNotEmpty) {
        request.headers.set("Authorization", "Bearer ${session.accessToken}");
      }
      final response = await request.close();
      final body = await response.transform(utf8.decoder).join();

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw StateError("Flask API ${response.statusCode}: $body");
      }

      final payload = jsonDecode(body);
      return payload is Map<String, dynamic> ? payload : <String, dynamic>{};
    } finally {
      client.close(force: true);
    }
  }

  Future<List<Map<String, dynamic>>> _getItems(
    String path, {
    Map<String, String>? queryParameters,
  }) async {
    final payload = await _getPayload(path, queryParameters: queryParameters);
    final items = payload["items"];

    if (items is! List) {
      return const [];
    }

    return [
      for (final item in items)
        if (item is Map<String, dynamic>) item,
    ];
  }
}

int _sortAnnouncements(
  MobileAnnouncement current,
  MobileAnnouncement next,
) {
  return next.priority.compareTo(current.priority);
}

bool _matchesQuery(MobileProduct product, MobileProductQuery query) {
  final normalizedText = query.text.trim().toLowerCase();
  final haystack =
      "${product.name} ${product.sku} ${product.description} ${product.categoryName} ${product.variants.join(" ")} ${product.specifications.values.join(" ")}"
          .toLowerCase();
  final matchesText =
      normalizedText.isEmpty || haystack.contains(normalizedText);
  final matchesVertical = query.verticalName == null ||
      product.verticalName
          .toLowerCase()
          .contains(query.verticalName!.toLowerCase());
  final matchesAvailable = !query.onlyAvailable ||
      (product.availableStock > 0 && !product.requiresQuote);
  final matchesValidation = !query.onlyNeedsValidation ||
      product.requiresQuote ||
      product.requiresTechnicalValidation;

  return matchesText &&
      matchesVertical &&
      matchesAvailable &&
      matchesValidation;
}

MobileProduct mapFirestoreProduct(String id, Map<String, dynamic> data) {
  final publicPrice = _asMap(data["publicPrice"]);
  final b2bPriceData = _asMap(data["b2bPrice"]);
  final price = _asDouble(
    data["publicPriceUsd"] ?? data["priceUsd"] ?? publicPrice["amount"],
  );
  final b2bPrice = _asDouble(
    data["b2bPriceUsd"] ?? b2bPriceData["amount"],
    fallback: price,
  );
  final stock = _asInt(data["availableStock"] ?? data["stock"]);
  final requiresQuote = data["requiresQuote"] == true;
  final requiresTechnicalValidation =
      data["requiresTechnicalValidation"] == true;
  final imageUrls = data["imageUrls"];

  return MobileProduct(
    id: id,
    sku: _asString(data["sku"], fallback: id),
    name: _asString(data["name"] ?? data["title"], fallback: id),
    verticalName: _asString(
      data["verticalName"] ?? data["verticalId"],
      fallback: "Categoria Wulkan",
    ),
    description: _asString(
      data["description"],
      fallback: "Producto tecnico Wulkan",
    ),
    publicPriceUsd: price,
    b2bPriceUsd: b2bPrice,
    availableStock: stock,
    badge: requiresQuote
        ? "Cotizar"
        : (requiresTechnicalValidation ? "Validar" : "Comprar"),
    requiresQuote: requiresQuote,
    requiresTechnicalValidation: requiresTechnicalValidation,
    compatibilityNotes: const [
      "Compatibilidad pendiente de cargar desde Firestore",
    ],
    productType:
        _asString(data["productType"] ?? data["type"], fallback: "machine"),
    imageUrls: _asStringList(imageUrls),
    discountPercent: _asDouble(data["discountPercent"]),
    originalPriceUsd: _asDouble(data["originalPriceUsd"], fallback: price),
    variants: _asStringList(data["variants"]),
    specifications: _asStringMap(data["specifications"]),
    imageUrl: imageUrls is List && imageUrls.isNotEmpty
        ? _asString(imageUrls.first)
        : _asString(data["imageUrl"]),
    sourceUrl: _asString(data["sourceUrl"] ?? data["permalink"]),
  );
}

MobileProduct mapApiProduct(String id, Map<String, dynamic> data) {
  final requiresQuote = data["requiresQuote"] == true;
  final requiresTechnicalValidation =
      data["requiresTechnicalValidation"] == true;
  final notes = data["compatibilityNotes"];
  final imageUrls = _asStringList(data["imageUrls"]);
  final price = _asDouble(data["publicPriceUsd"]);

  return MobileProduct(
    id: id,
    sku: _asString(data["sku"], fallback: id),
    name: _asString(data["name"] ?? data["title"], fallback: id),
    verticalName: _asString(
      data["verticalName"] ?? data["categoryName"],
      fallback: "Categoria Wulkan",
    ),
    description: _asString(data["description"]),
    publicPriceUsd: price,
    b2bPriceUsd: _asDouble(data["b2bPriceUsd"]),
    availableStock: _asInt(data["availableStock"] ?? data["stock"]),
    badge: _asString(
      data["badge"],
      fallback: requiresQuote
          ? "Cotizar"
          : (requiresTechnicalValidation ? "Validar" : "Comprar"),
    ),
    requiresQuote: requiresQuote,
    requiresTechnicalValidation: requiresTechnicalValidation,
    compatibilityNotes: notes is List
        ? notes.map((note) => note.toString()).toList()
        : const ["Validar compatibilidad con Wulkan"],
    productType: _asString(data["productType"], fallback: "machine"),
    imageUrls: imageUrls,
    discountPercent: _asDouble(data["discountPercent"]),
    originalPriceUsd: _asDouble(data["originalPriceUsd"], fallback: price),
    variants: _asStringList(data["variants"]),
    specifications: _asStringMap(data["specifications"]),
    imageUrl: _asString(data["imageUrl"]),
  );
}

MobileAnnouncement mapFirestoreAnnouncement(
  String id,
  Map<String, dynamic> data,
) {
  return MobileAnnouncement(
    id: id,
    title: _asString(data["title"], fallback: "Anuncio Wulkan"),
    body: _asString(data["body"], fallback: "Promocion activa"),
    placement: _asString(data["placement"], fallback: "home"),
    priority: _asInt(data["priority"], fallback: 50),
    ctaLabel: _asString(data["ctaLabel"]),
    ctaUrl: _asString(data["ctaUrl"]),
    imageUrl: _asString(data["imageUrl"]),
    startsAt: _asDateTime(data["startsAt"]),
    endsAt: _asNullableDateTime(data["endsAt"]),
    status: _asString(data["status"], fallback: "pending"),
  );
}

MobileAnnouncement mapApiAnnouncement(String id, Map<String, dynamic> data) {
  return MobileAnnouncement(
    id: id,
    title: _asString(data["title"], fallback: "Anuncio Wulkan"),
    body: _asString(data["body"]),
    placement: _asString(data["placement"], fallback: "home"),
    priority: _asInt(data["priority"], fallback: 50),
    ctaLabel: _asString(data["ctaLabel"]),
    ctaUrl: _asString(data["ctaUrl"]),
    imageUrl: _asString(data["imageUrl"]),
    startsAt: _asDateTime(data["startsAt"]),
    endsAt: _asNullableDateTime(data["endsAt"]),
    status: _asString(data["status"], fallback: "pending"),
  );
}

MobileOrderSummary mapApiOrder(Map<String, dynamic> data) {
  return MobileOrderSummary(
    id: _asString(data["orderId"] ?? data["id"], fallback: "orden"),
    status: _asString(data["status"], fallback: "credit_review"),
    totalUsd: _asDouble(data["totalUsd"]),
    paidUsd: _asDouble(data["paidUsd"]),
    balanceUsd: _asDouble(data["balanceUsd"]),
    itemsCount: _asInt(data["itemsCount"]),
    createdAt: _asDateTime(data["createdAt"]),
    paymentStatus: _asString(data["paymentStatus"], fallback: "pending"),
    stockStatus: _asString(data["stockStatus"], fallback: "pending"),
    customerId: _asString(data["customerId"]),
    customerName: _asString(data["customerName"]),
    sellerId: _asString(data["sellerId"]),
    sellerName: _asString(data["sellerName"]),
    saleType: _asString(data["saleType"], fallback: "cash"),
    saleTypeLabel: _asString(data["saleTypeLabel"], fallback: "Contado"),
    paymentTermDays: _asInt(data["paymentTermDays"]),
    dueDate: _asNullableDateTime(data["dueDate"]),
    dueStatus: _asString(data["dueStatus"], fallback: "without_due_date"),
    commissionUsd: _asDouble(data["commissionUsd"]),
    commissionStatus: _asString(data["commissionStatus"]),
    commissionStatusLabel: _asString(data["commissionStatusLabel"]),
  );
}

MobileSellerSummary mapApiSellerSummary(Map<String, dynamic> data) {
  return MobileSellerSummary(
    sellerId: _asString(data["sellerId"]),
    sellerName: _asString(data["sellerName"], fallback: "Vendedor Wulkan"),
    roleLabel: _asString(data["roleLabel"], fallback: "Vendedor"),
    clientsCount: _asInt(data["clientsCount"]),
    ordersCount: _asInt(data["ordersCount"]),
    pendingCreditRequests: _asInt(data["pendingCreditRequests"]),
    salesUsd: _asDouble(data["salesUsd"]),
    openBalanceUsd: _asDouble(data["openBalanceUsd"]),
    pendingCommissionUsd: _asDouble(data["pendingCommissionUsd"]),
    approvedCommissionUsd: _asDouble(data["approvedCommissionUsd"]),
    paidCommissionUsd: _asDouble(data["paidCommissionUsd"]),
  );
}

MobileSellerClient mapApiSellerClient(Map<String, dynamic> data) {
  return MobileSellerClient(
    id: _asString(data["id"]),
    businessName: _asString(data["businessName"], fallback: "Cliente Wulkan"),
    email: _asString(data["email"]),
    phone: _asString(data["phone"]),
    city: _asString(data["city"]),
    state: _asString(data["state"]),
    creditEnabled: data["creditEnabled"] == true,
    creditStatus: _asString(data["creditStatus"], fallback: "without_credit"),
    creditLimitUsd: _asDouble(data["creditLimitUsd"]),
    creditAvailableUsd: _asDouble(data["creditAvailableUsd"]),
    creditExposureUsd: _asDouble(data["creditExposureUsd"]),
    creditRequestStatus:
        _asString(data["creditRequestStatus"], fallback: "none"),
  );
}

Map<String, dynamic> _asMap(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }

  if (value is Map) {
    return value.map((key, mapValue) => MapEntry(key.toString(), mapValue));
  }

  return {};
}

String _asString(Object? value, {String fallback = ""}) {
  return value is String && value.isNotEmpty ? value : fallback;
}

List<String> _asStringList(Object? value) {
  if (value is List) {
    return value
        .map((item) => item.toString())
        .where((item) => item.isNotEmpty)
        .toList();
  }
  return const [];
}

Map<String, String> _asStringMap(Object? value) {
  if (value is Map) {
    return value
        .map((key, mapValue) => MapEntry(key.toString(), mapValue.toString()));
  }
  return const {};
}

List<int> _asIntList(Object? value, {required List<int> fallback}) {
  if (value is List) {
    final items = value
        .map((item) => int.tryParse(item.toString()))
        .whereType<int>()
        .toSet()
        .toList()
      ..sort();

    return items.isEmpty ? fallback : items;
  }

  return fallback;
}

double _asDouble(Object? value, {double fallback = 0}) {
  return switch (value) {
    int number => number.toDouble(),
    double number => number,
    String text => double.tryParse(text) ?? fallback,
    _ => fallback,
  };
}

int _asInt(Object? value, {int fallback = 0}) {
  return switch (value) {
    int number => number,
    double number => number.round(),
    String text => int.tryParse(text) ?? fallback,
    _ => fallback,
  };
}

DateTime _asDateTime(Object? value) {
  return _asNullableDateTime(value) ?? DateTime.fromMillisecondsSinceEpoch(0);
}

DateTime? _asNullableDateTime(Object? value) {
  if (value is Timestamp) {
    return value.toDate();
  }

  if (value is String && value.isNotEmpty) {
    return DateTime.tryParse(value);
  }

  return null;
}

MobileRepository createMobileRepository() {
  mobileEnvironment.validateRuntime();

  if (mobileEnvironment.usesApi) {
    return ApiMobileRepository(baseUrl: mobileEnvironment.adminApiUrl);
  }

  if (mobileEnvironment.usesFirestore) {
    return FirestoreMobileRepository();
  }

  return MockMobileRepository();
}

final mobileRepository = createMobileRepository();
