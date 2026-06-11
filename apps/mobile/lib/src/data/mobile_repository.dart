import 'dart:convert';
import 'dart:io';

import '../auth/mobile_auth.dart';
import '../config/mobile_environment.dart';
import '../domain/mobile_models.dart';

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
  Future<MobileSellerClientCreated> createSellerClient(
    MobileSellerClientDraft draft,
  );
  Future<List<MobileOrderSummary>> listSellerOrders();
  Future<List<MobileOrderSummary>> listSellerCommissions();
}

class MockMobileRepository implements MobileRepository {
  static const _categories = [
    MobileCategory(
      id: "machinery-garden",
      name: "Maquinaria y jardin",
      description: "Equipos, accesorios y repuestos Wulkan",
      icon: "bi-tools",
      sortOrder: 10,
    ),
    MobileCategory(
      id: "spare-parts",
      name: "Repuestos",
      description: "Piezas por SKU, modelo o compatibilidad",
      icon: "bi-gear",
      sortOrder: 20,
    ),
    MobileCategory(
      id: "technical-services",
      name: "Servicios tecnicos",
      description: "Soporte autorizado por zona y especialidad",
      icon: "bi-wrench",
      sortOrder: 30,
    ),
  ];

  static const _products = [
    MobileProduct(
      id: "prod-motosierra-45cc",
      sku: "WUL-MOT-45CC",
      name: "Motosierra Wulkan 45cc",
      verticalName: "Maquinaria y jardin",
      description: "Equipo de corte para uso tecnico, finca y jardin.",
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
      productType: "machine",
      discountPercent: 12,
      originalPriceUsd: 185,
      specifications: {
        "Motor": "45cc",
        "Combustible": "Gasolina",
      },
    ),
    MobileProduct(
      id: "prod-cadena-18",
      sku: "WUL-REP-CAD18",
      name: "Cadena 18 pulgadas compatible",
      verticalName: "Repuestos",
      description: "Repuesto compatible con motosierras seleccionadas Wulkan.",
      publicPriceUsd: 18,
      b2bPriceUsd: 15,
      availableStock: 4,
      badge: "Validar",
      requiresQuote: false,
      requiresTechnicalValidation: true,
      compatibilityNotes: [
        "Compatible con WUL-MOT-45CC",
        "Validar serie antes de despachar",
      ],
      productType: "spare_part",
      discountPercent: 17,
    ),
    MobileProduct(
      id: "prod-motobomba-3x3",
      sku: "WUL-MB-3X3",
      name: "Motobomba 3x3 alta presion Wulkan",
      verticalName: "Industrial",
      description: "Motobomba para trabajo agricola e industrial.",
      publicPriceUsd: 535,
      b2bPriceUsd: 498,
      availableStock: 7,
      badge: "Comprar",
      requiresQuote: false,
      requiresTechnicalValidation: false,
      compatibilityNotes: [
        "Validar mangueras y accesorios requeridos por cliente",
      ],
      productType: "machine",
      discountPercent: 7,
    ),
  ];

  static const _locations = [
    MobileLocation(
      id: "loc-caracas-chacao",
      name: "Punto autorizado Caracas",
      subtitle: "Retiro, soporte tecnico y recepcion de casos - Chacao",
      phone: "+58 212 000 0000",
      whatsapp: "+58 412 000 0000",
      address: "Chacao, Caracas",
      specialties: ["Motosierras", "Garantia", "Retiro"],
    ),
    MobileLocation(
      id: "loc-valencia-service",
      name: "Servicio tecnico Valencia",
      subtitle: "Diagnostico, garantia y entrega asistida - Carabobo",
      phone: "+58 241 000 0000",
      whatsapp: "+58 414 000 0000",
      address: "Valencia, Carabobo",
      specialties: ["Motobombas", "Repuestos", "Diagnostico"],
    ),
  ];

  static final _announcements = [
    MobileAnnouncement(
      id: "ann-home-local",
      title: "Catalogo Wulkan",
      body:
          "Conecta la app al backend productivo para ver productos reales del admin.",
      placement: "home",
      priority: 100,
      ctaLabel: "Ver catalogo",
      ctaUrl: "wulkan://catalog",
      startsAt: DateTime(2026, 1, 1),
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

    return MobileProductPage(
      products: filtered.sublist(start, end),
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
      assignedSeller: const MobileSellerSnapshot(
        id: "seller-local-wulkan",
        name: "Vendedor Wulkan",
      ),
    );
  }

  @override
  Future<List<MobileOrderSummary>> listOrders(String customerId) async {
    return const [];
  }

  @override
  Future<MobileSellerSummary> getSellerSummary() async {
    return const MobileSellerSummary(
      sellerId: "seller-local-wulkan",
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
  Future<MobileSellerClientCreated> createSellerClient(
    MobileSellerClientDraft draft,
  ) async {
    final requestedCredit = draft.creditRequestedUsd;
    return MobileSellerClientCreated(
      temporaryPassword: "Temporal2026",
      client: MobileSellerClient(
        id: "client-${draft.email.replaceAll(RegExp(r'[^a-zA-Z0-9]+'), '-')}",
        businessName: draft.businessName,
        email: draft.email,
        phone: draft.phone,
        city: draft.city,
        state: draft.state,
        creditEnabled: false,
        creditStatus: "without_credit",
        creditLimitUsd: 0,
        creditAvailableUsd: 0,
        creditExposureUsd: 0,
        creditRequestStatus: requestedCredit > 0 ? "pending" : "none",
      ),
    );
  }

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
            slug: _asString(item["slug"]),
            imageUrl: _asString(item["imageUrl"]),
            icon: _asString(item["icon"]),
            sortOrder: _asInt(item["sortOrder"]),
            parentId: _asString(item["parentId"]),
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
    final payload = await _getPayload(
      "/products",
      queryParameters: _productQueryParameters(query),
    );
    final items = _itemsFromPayload(payload);
    final products = items
        .map((item) => mapApiProduct(_asString(item["id"]), item))
        .toList();
    final pagination = _paginationFromPayload(payload);
    if (pagination != null) {
      final nextCursor = _asString(pagination["nextCursor"]);
      return MobileProductPage(
        products: products,
        hasMore: pagination["hasMore"] == true,
        nextCursor: nextCursor.isEmpty ? null : nextCursor,
      );
    }

    final filteredProducts =
        products.where((product) => _matchesQuery(product, query)).toList();
    final start = int.tryParse(query.cursor ?? "") ?? 0;
    final limit = query.limit.clamp(1, 100).toInt();
    final end = (start + limit).clamp(0, filteredProducts.length).toInt();

    return MobileProductPage(
      products: filteredProducts.sublist(start, end),
      hasMore: end < filteredProducts.length,
      nextCursor: end < filteredProducts.length ? end.toString() : null,
    );
  }

  @override
  Future<MobileProduct?> getProduct(String id) async {
    try {
      final payload = await _getPayload("/products/$id");
      final product = payload["product"];
      if (product is Map<String, dynamic>) {
        return mapApiProduct(_asString(product["id"], fallback: id), product);
      }
    } catch (_) {
      // Legacy backends without product-detail endpoint still work via catalog.
    }

    final products = await listProducts();
    for (final product in products) {
      if (product.id == id || product.sku == id) {
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
            phone: _asString(item["phone"]),
            whatsapp: _asString(item["whatsapp"]),
            address: _asString(item["address"]),
            specialties: _asStringList(item["specialties"]),
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
  Future<MobileSellerClientCreated> createSellerClient(
    MobileSellerClientDraft draft,
  ) async {
    final payload = await _postPayload("/seller/clients", draft.toJson());
    final clientData = payload["client"];
    final data =
        clientData is Map<String, dynamic> ? clientData : <String, dynamic>{};

    return MobileSellerClientCreated(
      client: mapApiSellerClient(data),
      temporaryPassword:
          _asString(data["temporaryPassword"] ?? payload["temporaryPassword"]),
    );
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

  Future<Map<String, dynamic>> _postPayload(
    String path,
    Map<String, dynamic> body,
  ) async {
    final uri = _baseUri.replace(path: "${_baseUri.path}$path");
    final client = HttpClient();

    try {
      final request = await client.postUrl(uri);
      request.headers.contentType = ContentType.json;
      final session = await mobileAuthRepository.getCurrentSession();
      if (session.accessToken.isNotEmpty) {
        request.headers.set("Authorization", "Bearer ${session.accessToken}");
      }
      request.write(jsonEncode(body));
      final response = await request.close();
      final responseBody = await response.transform(utf8.decoder).join();

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw StateError("Flask API ${response.statusCode}: $responseBody");
      }

      final payload = jsonDecode(responseBody);
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
    return _itemsFromPayload(payload);
  }

  List<Map<String, dynamic>> _itemsFromPayload(Map<String, dynamic> payload) {
    final items = payload["items"];

    if (items is! List) {
      return const [];
    }

    return [
      for (final item in items)
        if (item is Map<String, dynamic>) item,
    ];
  }

  Map<String, dynamic>? _paginationFromPayload(Map<String, dynamic> payload) {
    final meta = payload["meta"];
    if (meta is! Map<String, dynamic>) {
      return null;
    }
    final pagination = meta["pagination"];
    return pagination is Map<String, dynamic> ? pagination : null;
  }

  Map<String, String> _productQueryParameters(MobileProductQuery query) {
    final parameters = <String, String>{
      "limit": query.limit.clamp(1, 100).toString(),
    };
    if (query.cursor != null && query.cursor!.isNotEmpty) {
      parameters["cursor"] = query.cursor!;
    }
    if (query.text.trim().isNotEmpty) {
      parameters["q"] = query.text.trim();
    }
    if (query.verticalName != null && query.verticalName!.trim().isNotEmpty) {
      parameters["verticalName"] = query.verticalName!.trim();
    }
    if (query.categoryId != null && query.categoryId!.trim().isNotEmpty) {
      parameters["categoryId"] = query.categoryId!.trim();
    }
    if (query.onlyAvailable) {
      parameters["onlyAvailable"] = "1";
    }
    if (query.onlyNeedsValidation) {
      parameters["onlyNeedsValidation"] = "1";
    }
    return parameters;
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
    pdfUrls: _asStringList(data["pdfUrls"]),
    imageUrl: _asString(data["imageUrl"]),
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
    sellerCode: _asString(data["sellerCode"]),
    sellerZone: _asString(data["sellerZone"]),
    sellerTerritory: _asString(data["sellerTerritory"]),
    commissionRatePercent: _asDouble(data["commissionRatePercent"]),
    salesGoalUsd: _asDouble(data["salesGoalUsd"]),
    salesMonthUsd: _asDouble(data["salesMonthUsd"]),
    goalProgressPercent: _asDouble(data["goalProgressPercent"]),
    ticketAverageUsd: _asDouble(data["ticketAverageUsd"]),
    activeClientsCount: _asInt(data["activeClientsCount"]),
    newClientsMonth: _asInt(data["newClientsMonth"]),
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

  return MockMobileRepository();
}

final mobileRepository = createMobileRepository();
