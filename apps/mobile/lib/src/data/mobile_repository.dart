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
  Future<List<MobileNotification>> listNotifications();
  Future<void> markNotificationRead(String notificationId);
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
      description: "Equipos, accesorios y repuestos FVENTAS",
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
      sku: "FVT-MOT-45CC",
      name: "Motosierra FVENTAS 45cc",
      verticalName: "Maquinaria y jardin",
      description: "Equipo de corte para uso tecnico, finca y jardin.",
      publicPriceUsd: 185,
      b2bPriceUsd: 162,
      availableStock: 12,
      badge: "Comprar",
      requiresQuote: false,
      requiresTechnicalValidation: false,
      compatibilityNotes: [
        "Compatible con cadena FVT-REP-CAD18",
        "Validar largo de espada antes de entregar",
      ],
      productType: "machine",
      discountPercent: 12,
      originalPriceUsd: 185,
      imageUrl: "asset:assets/products/motosierra-45cc.png",
      specifications: {
        "Motor": "45cc",
        "Combustible": "Gasolina",
      },
    ),
    MobileProduct(
      id: "prod-cadena-18",
      sku: "FVT-REP-CAD18",
      name: "Cadena 18 pulgadas compatible",
      verticalName: "Repuestos",
      description: "Repuesto compatible con motosierras seleccionadas FVENTAS.",
      publicPriceUsd: 18,
      b2bPriceUsd: 15,
      availableStock: 4,
      badge: "Validar",
      requiresQuote: false,
      requiresTechnicalValidation: true,
      compatibilityNotes: [
        "Compatible con FVT-MOT-45CC",
        "Validar serie antes de despachar",
      ],
      productType: "spare_part",
      discountPercent: 17,
      imageUrl: "asset:assets/products/cadena-18.png",
    ),
    MobileProduct(
      id: "prod-motobomba-3x3",
      sku: "FVT-MB-3X3",
      name: "Motobomba 3x3 alta presion FVENTAS",
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
      imageUrl: "asset:assets/products/motobomba-3x3.png",
    ),
    MobileProduct(
      id: "prod-desbrozadora-52cc",
      sku: "FVT-DES-52CC",
      name: "Desbrozadora 52cc profesional",
      verticalName: "Maquinaria y jardin",
      description: "Equipo para mantencion de parcelas, condominios y faenas.",
      publicPriceUsd: 230,
      b2bPriceUsd: 198,
      availableStock: 9,
      badge: "Comprar",
      requiresQuote: false,
      requiresTechnicalValidation: false,
      compatibilityNotes: [
        "Incluye arnes y cabezal",
        "Validar disco segun tipo de maleza",
      ],
      productType: "machine",
      discountPercent: 14,
      originalPriceUsd: 230,
      imageUrl: "asset:assets/products/motosierra-45cc.png",
    ),
    MobileProduct(
      id: "prod-generador-7kva",
      sku: "FVT-GEN-7KVA",
      name: "Generador electrico 7 kVA",
      verticalName: "Industrial",
      description: "Respaldo electrico para talleres, terreno y obras.",
      publicPriceUsd: 890,
      b2bPriceUsd: 815,
      availableStock: 3,
      badge: "Validar",
      requiresQuote: false,
      requiresTechnicalValidation: true,
      compatibilityNotes: [
        "Validar carga requerida antes de despacho",
        "Requiere entrega asistida",
      ],
      productType: "machine",
      discountPercent: 8,
      originalPriceUsd: 890,
      imageUrl: "asset:assets/products/motobomba-3x3.png",
    ),
    MobileProduct(
      id: "prod-kit-manguera-3",
      sku: "FVT-KIT-MAN3",
      name: "Kit manguera descarga 3 pulgadas",
      verticalName: "Repuestos",
      description: "Accesorio para motobombas 3x3 con abrazaderas.",
      publicPriceUsd: 74,
      b2bPriceUsd: 62,
      availableStock: 18,
      badge: "Comprar",
      requiresQuote: false,
      requiresTechnicalValidation: false,
      compatibilityNotes: [
        "Compatible con FVT-MB-3X3",
        "Incluye abrazaderas reforzadas",
      ],
      productType: "spare_part",
      discountPercent: 16,
      originalPriceUsd: 74,
      imageUrl: "asset:assets/products/cadena-18.png",
    ),
    MobileProduct(
      id: "prod-aceite-2t",
      sku: "FVT-ACE-2T",
      name: "Aceite 2T premium caja 12 unidades",
      verticalName: "Consumibles",
      description: "Consumible para venta recurrente en cartera B2B.",
      publicPriceUsd: 96,
      b2bPriceUsd: 78,
      availableStock: 36,
      badge: "Comprar",
      requiresQuote: false,
      requiresTechnicalValidation: false,
      compatibilityNotes: [
        "Compatible con motores 2 tiempos",
        "Producto ideal para reposicion mensual",
      ],
      productType: "consumable",
      discountPercent: 19,
      originalPriceUsd: 96,
      imageUrl: "asset:assets/products/motosierra-45cc.png",
    ),
    MobileProduct(
      id: "prod-filtro-aire-45cc",
      sku: "FVT-FIL-AIR45",
      name: "Filtro de aire motosierra 45cc",
      verticalName: "Repuestos",
      description: "Repuesto de alta rotacion para servicio tecnico.",
      publicPriceUsd: 12,
      b2bPriceUsd: 9.5,
      availableStock: 48,
      badge: "Comprar",
      requiresQuote: false,
      requiresTechnicalValidation: false,
      compatibilityNotes: [
        "Compatible con FVT-MOT-45CC",
        "Sugerido en mantencion preventiva",
      ],
      productType: "spare_part",
      discountPercent: 21,
      originalPriceUsd: 12,
      imageUrl: "asset:assets/products/cadena-18.png",
    ),
  ];

  static const _locations = [
    MobileLocation(
      id: "loc-santiago-centro",
      name: "Punto autorizado principal",
      subtitle: "Retiro, soporte tecnico y recepcion de casos",
      phone: "+56 2 2000 0000",
      whatsapp: "+56 9 4000 0000",
      address: "Sucursal principal",
      specialties: ["Catalogo", "Garantia", "Retiro"],
    ),
    MobileLocation(
      id: "loc-valparaiso-service",
      name: "Servicio tecnico Valparaiso",
      subtitle: "Diagnostico, garantia y entrega asistida - Valparaiso",
      phone: "+56 32 200 0000",
      whatsapp: "+56 9 5000 0000",
      address: "Valparaiso, Valparaiso",
      specialties: ["Motobombas", "Repuestos", "Diagnostico"],
    ),
  ];

  static final _announcements = [
    MobileAnnouncement(
      id: "ann-home-local",
      title: "Reposicion B2B lista",
      body:
          "Compra maquinaria, repuestos y consumibles con stock vigente y condiciones comerciales activas.",
      placement: "home",
      priority: 100,
      ctaLabel: "Ver catalogo",
      ctaUrl: "fventas://catalog",
      startsAt: DateTime(2026, 1, 1),
      status: "active",
    ),
    MobileAnnouncement(
      id: "ann-checkout-local",
      title: "Orden revisada por FVENTAS",
      body:
          "El pedido queda registrado con tu vendedor asignado antes de despacho o retiro.",
      placement: "checkout",
      priority: 90,
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
      creditEnabled: true,
      creditLimitUsd: 12000,
      creditUsedUsd: 4200,
      creditOrdersUsd: 1850,
      creditExposureUsd: 6050,
      creditAvailableUsd: 5950,
      paymentTermsDays: 30,
      status: "approved",
      allowedPaymentTermsDays: const [0, 15, 30],
      defaultSaleType: "credit_line",
      assignedSeller: const MobileSellerSnapshot(
        id: "seller-local-fventas",
        name: "Carolina Reyes",
      ),
    );
  }

  @override
  Future<List<MobileOrderSummary>> listOrders(String customerId) async {
    return [
      MobileOrderSummary(
        id: "FVT-10318",
        status: "approved",
        totalUsd: 1620,
        paidUsd: 0,
        balanceUsd: 1620,
        itemsCount: 3,
        createdAt: DateTime(2026, 6, 17),
        paymentStatus: "pending",
        stockStatus: "reserved",
        customerId: customerId,
        customerName: "Ferreteria Alameda",
        sellerId: "seller-local-fventas",
        sellerName: "Carolina Reyes",
        saleType: "credit_line",
        saleTypeLabel: "Linea de credito",
        paymentTermDays: 30,
        dueDate: DateTime(2026, 7, 17),
        dueStatus: "current",
      ),
      MobileOrderSummary(
        id: "FVT-10291",
        status: "delivered",
        totalUsd: 840,
        paidUsd: 840,
        balanceUsd: 0,
        itemsCount: 2,
        createdAt: DateTime(2026, 6, 10),
        paymentStatus: "paid",
        stockStatus: "released",
        customerId: customerId,
        customerName: "Ferreteria Alameda",
        sellerId: "seller-local-fventas",
        sellerName: "Carolina Reyes",
        saleType: "term_credit",
        saleTypeLabel: "Credito 15 dias",
        paymentTermDays: 15,
        dueDate: DateTime(2026, 6, 25),
        dueStatus: "current",
      ),
      MobileOrderSummary(
        id: "FVT-10270",
        status: "review",
        totalUsd: 390,
        paidUsd: 0,
        balanceUsd: 390,
        itemsCount: 1,
        createdAt: DateTime(2026, 6, 5),
        paymentStatus: "pending",
        stockStatus: "pending",
        customerId: customerId,
        customerName: "Ferreteria Alameda",
        sellerId: "seller-local-fventas",
        sellerName: "Carolina Reyes",
        saleType: "cash",
        saleTypeLabel: "Contado",
      ),
    ];
  }

  @override
  Future<List<MobileNotification>> listNotifications() async => [
        MobileNotification(
          id: "notif-client-credit",
          title: "Cupo comercial activo",
          body: "Tienes linea aprobada y plazos 15/30 dias para compras B2B.",
          type: "credit",
          typeLabel: "Credito",
          priority: "normal",
          status: "unread",
          createdAt: DateTime(2026, 6, 17, 9, 30),
          module: "credit",
          entityType: "client",
          entityId: "client-local-fventas",
        ),
        MobileNotification(
          id: "notif-client-order",
          title: "Orden FVT-10318 en revision",
          body: "Stock reservado mientras FVENTAS valida despacho y condicion.",
          type: "order",
          typeLabel: "Orden",
          priority: "normal",
          status: "read",
          createdAt: DateTime(2026, 6, 17, 10, 15),
          module: "orders",
          entityType: "order",
          entityId: "FVT-10318",
        ),
      ];

  @override
  Future<void> markNotificationRead(String notificationId) async {}

  @override
  Future<MobileSellerSummary> getSellerSummary() async {
    return const MobileSellerSummary(
      sellerId: "seller-local-fventas",
      sellerName: "Vendedor FVENTAS",
      roleLabel: "Vendedor",
      sellerCode: "VEN-102",
      sellerZone: "Santiago norte",
      sellerTerritory: "Ferreterias y maquinaria",
      commissionRatePercent: 3.5,
      salesGoalUsd: 38000,
      salesMonthUsd: 23600,
      goalProgressPercent: 62,
      ticketAverageUsd: 2950,
      activeClientsCount: 3,
      newClientsMonth: 1,
      clientsCount: 4,
      ordersCount: 3,
      pendingCreditRequests: 1,
      salesUsd: 23600,
      openBalanceUsd: 5600,
      pendingCommissionUsd: 418,
      approvedCommissionUsd: 230,
      paidCommissionUsd: 610,
    );
  }

  @override
  Future<List<MobileSellerClient>> listSellerClients() async => const [
        MobileSellerClient(
          id: "client-ferreteria-alameda",
          businessName: "Ferreteria Alameda",
          email: "compras@alameda.cl",
          phone: "+56 9 6123 4567",
          city: "Santiago",
          state: "Metropolitana",
          creditEnabled: true,
          creditStatus: "approved",
          creditLimitUsd: 8000,
          creditAvailableUsd: 5200,
          creditExposureUsd: 2800,
          creditRequestStatus: "approved",
          taxId: "76.100.200-3",
          contactName: "Paula Morales",
          address: "Av. Libertador 1200",
          deliveryZone: "Centro",
          defaultSaleType: "credit_line",
          allowedPaymentTermsDays: [0, 15, 30],
        ),
        MobileSellerClient(
          id: "client-servitec-norte",
          businessName: "Servitec Norte",
          email: "operaciones@servitecnorte.cl",
          phone: "+56 9 7345 9012",
          city: "Quilicura",
          state: "Metropolitana",
          creditEnabled: false,
          creditStatus: "review",
          creditLimitUsd: 0,
          creditAvailableUsd: 0,
          creditExposureUsd: 0,
          creditRequestStatus: "pending",
          taxId: "77.200.300-4",
          contactName: "Marco Rojas",
          address: "Los Industriales 450",
          deliveryZone: "Norte",
          defaultSaleType: "credit_line",
          allowedPaymentTermsDays: [0],
          creditRequestedUsd: 4500,
        ),
        MobileSellerClient(
          id: "client-agro-maipo",
          businessName: "Agro Maipo SpA",
          email: "abastecimiento@agromaipo.cl",
          phone: "+56 9 8456 2211",
          city: "San Bernardo",
          state: "Metropolitana",
          creditEnabled: true,
          creditStatus: "approved",
          creditLimitUsd: 12000,
          creditAvailableUsd: 6400,
          creditExposureUsd: 5600,
          creditRequestStatus: "approved",
          taxId: "76.555.440-1",
          contactName: "Carolina Farias",
          address: "Camino Maipo 221",
          deliveryZone: "Sur",
          defaultSaleType: "credit_line",
          allowedPaymentTermsDays: [0, 15, 30, 40],
        ),
        MobileSellerClient(
          id: "client-rental-sur",
          businessName: "Rental Sur Equipos",
          email: "ventas@rentalsur.cl",
          phone: "+56 9 5561 4400",
          city: "Rancagua",
          state: "O'Higgins",
          creditEnabled: false,
          creditStatus: "cash",
          creditLimitUsd: 0,
          creditAvailableUsd: 0,
          creditExposureUsd: 0,
          creditRequestStatus: "none",
          taxId: "77.980.101-2",
          contactName: "Felipe Medina",
          address: "Ruta 5 Sur km 82",
          deliveryZone: "O'Higgins",
          defaultSaleType: "cash",
          allowedPaymentTermsDays: [0],
        ),
      ];

  @override
  Future<MobileSellerClientCreated> createSellerClient(
    MobileSellerClientDraft draft,
  ) async {
    final requestedCredit = draft.creditRequestedUsd;
    return MobileSellerClientCreated(
      temporaryPassword: "Temporal2026",
      message: "Cliente creado localmente.",
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
        taxId: draft.taxId,
        contactName: draft.contactName,
        address: draft.address,
        deliveryZone: draft.deliveryZone,
        defaultSaleType: draft.defaultSaleType,
        allowedPaymentTermsDays: draft.allowedPaymentTermsDays,
        creditRequestedUsd: requestedCredit,
      ),
    );
  }

  @override
  Future<List<MobileOrderSummary>> listSellerOrders() async =>
      _mockSellerOrders();

  @override
  Future<List<MobileOrderSummary>> listSellerCommissions() async =>
      _mockSellerOrders();
}

List<MobileOrderSummary> _mockSellerOrders() {
  return [
    MobileOrderSummary(
      id: "FVT-10291",
      status: "approved",
      totalUsd: 4860,
      paidUsd: 1800,
      balanceUsd: 3060,
      itemsCount: 6,
      createdAt: DateTime(2026, 6, 15),
      paymentStatus: "partial_paid",
      stockStatus: "reserved",
      customerId: "client-ferreteria-alameda",
      customerName: "Ferreteria Alameda",
      sellerId: "seller-local-fventas",
      sellerName: "Vendedor FVENTAS",
      saleType: "credit_line",
      saleTypeLabel: "Linea de credito",
      paymentTermDays: 30,
      dueDate: DateTime(2026, 7, 15),
      dueStatus: "current",
      commissionUsd: 170.1,
      commissionStatus: "commission_pending",
      commissionStatusLabel: "Pendiente",
    ),
    MobileOrderSummary(
      id: "FVT-10284",
      status: "delivered",
      totalUsd: 3220,
      paidUsd: 3220,
      balanceUsd: 0,
      itemsCount: 4,
      createdAt: DateTime(2026, 6, 12),
      paymentStatus: "paid",
      stockStatus: "released",
      customerId: "client-agro-maipo",
      customerName: "Agro Maipo SpA",
      sellerId: "seller-local-fventas",
      sellerName: "Vendedor FVENTAS",
      saleType: "term_credit",
      saleTypeLabel: "Credito 15 dias",
      paymentTermDays: 15,
      dueDate: DateTime(2026, 6, 27),
      dueStatus: "current",
      commissionUsd: 112.7,
      commissionStatus: "approved",
      commissionStatusLabel: "Aprobada",
    ),
    MobileOrderSummary(
      id: "FVT-10270",
      status: "paid",
      totalUsd: 2100,
      paidUsd: 2100,
      balanceUsd: 0,
      itemsCount: 3,
      createdAt: DateTime(2026, 6, 8),
      paymentStatus: "paid",
      stockStatus: "released",
      customerId: "client-rental-sur",
      customerName: "Rental Sur Equipos",
      sellerId: "seller-local-fventas",
      sellerName: "Vendedor FVENTAS",
      saleType: "cash",
      saleTypeLabel: "Contado",
      commissionUsd: 73.5,
      commissionStatus: "paid",
      commissionStatusLabel: "Pagada",
    ),
  ];
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
            name: _asString(item["name"], fallback: "Categoria FVENTAS"),
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
            name: _asString(item["name"], fallback: "Punto FVENTAS"),
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
  Future<List<MobileNotification>> listNotifications() async {
    final items = await _getItems("/notifications");
    return items.map(mapApiNotification).toList();
  }

  @override
  Future<void> markNotificationRead(String notificationId) async {
    await _postPayload("/notifications/$notificationId/read", const {});
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
    final payload = await _postPayload(
      "/seller/clients",
      draft.toJson(),
      idempotencyKey: draft.idempotencyKey,
    );
    final clientData = payload["client"];
    final data =
        clientData is Map<String, dynamic> ? clientData : <String, dynamic>{};

    return MobileSellerClientCreated(
      client: mapApiSellerClient(data),
      temporaryPassword:
          _asString(data["temporaryPassword"] ?? payload["temporaryPassword"]),
      alreadyExists: payload["alreadyExists"] == true,
      message: _asString(payload["message"]),
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
      await attachFventasMobileHeaders(request.headers, session: session);
      final response = await request.close();
      final body = await response.transform(utf8.decoder).join();

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw StateError(_apiErrorMessage(response.statusCode, body));
      }

      final payload = jsonDecode(body);
      return payload is Map<String, dynamic> ? payload : <String, dynamic>{};
    } finally {
      client.close(force: true);
    }
  }

  Future<Map<String, dynamic>> _postPayload(
    String path,
    Map<String, dynamic> body, {
    String idempotencyKey = "",
  }) async {
    final uri = _baseUri.replace(path: "${_baseUri.path}$path");
    final client = HttpClient();

    try {
      final request = await client.postUrl(uri);
      request.headers.contentType = ContentType.json;
      final session = await mobileAuthRepository.getCurrentSession();
      await attachFventasMobileHeaders(request.headers, session: session);
      if (idempotencyKey.trim().isNotEmpty) {
        request.headers.set("Idempotency-Key", idempotencyKey.trim());
      }
      request.write(jsonEncode(body));
      final response = await request.close();
      final responseBody = await response.transform(utf8.decoder).join();

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw StateError(_apiErrorMessage(response.statusCode, responseBody));
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

  String _apiErrorMessage(int statusCode, String responseBody) {
    var message = responseBody.trim();
    try {
      final decoded = jsonDecode(responseBody);
      if (decoded is Map<String, dynamic>) {
        final error = decoded["error"] ?? decoded["message"];
        if (error != null && error.toString().trim().isNotEmpty) {
          message = error.toString().trim();
        }
        final errors = decoded["errors"];
        if (errors is Map) {
          final details = errors.values
              .map((value) => value.toString().trim())
              .where((value) => value.isNotEmpty)
              .join(" ");
          if (details.isNotEmpty) {
            message = "$message $details";
          }
        }
      }
    } on FormatException {
      // The backend can return HTML for unexpected failures; keep a readable fallback.
    }

    if (message.isEmpty ||
        message.startsWith("<!doctype") ||
        message.startsWith("<html")) {
      return "No se pudo completar la solicitud. Intenta nuevamente.";
    }

    return message;
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
      fallback: "Categoria FVENTAS",
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
        : const ["Validar compatibilidad con FVENTAS"],
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
    title: _asString(data["title"], fallback: "Anuncio FVENTAS"),
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

MobileNotification mapApiNotification(Map<String, dynamic> data) {
  return MobileNotification(
    id: _asString(data["id"], fallback: "notification"),
    title: _asString(data["title"], fallback: "Notificacion FVENTAS"),
    body: _asString(data["body"]),
    type: _asString(data["type"], fallback: "info"),
    typeLabel: _asString(data["typeLabel"], fallback: "Informacion"),
    priority: _asString(data["priority"], fallback: "normal"),
    status: _asString(data["status"], fallback: "unread"),
    createdAt: _asDateTime(data["createdAt"]),
    module: _asString(data["module"]),
    entityType: _asString(data["entityType"]),
    entityId: _asString(data["entityId"]),
    deepLink: _asString(data["deepLink"]),
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
    sellerName: _asString(data["sellerName"], fallback: "Vendedor FVENTAS"),
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
    businessName: _asString(data["businessName"], fallback: "Cliente FVENTAS"),
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
    taxId: _asString(data["taxId"]),
    contactName: _asString(data["contactName"]),
    address: _asString(data["address"]),
    deliveryZone: _asString(data["deliveryZone"]),
    status: _asString(data["status"], fallback: "active"),
    defaultSaleType: _asString(data["defaultSaleType"], fallback: "cash"),
    allowedPaymentTermsDays: _asIntList(
      data["allowedPaymentTermsDays"],
      fallback: const [0],
    ),
    creditRequestedUsd: _asDouble(data["creditRequestedUsd"]),
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
