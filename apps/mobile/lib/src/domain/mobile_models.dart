class MobileCategory {
  const MobileCategory({
    required this.id,
    required this.name,
    required this.description,
    this.slug = "",
    this.imageUrl = "",
    this.icon = "",
    this.sortOrder = 0,
    this.parentId = "",
  });

  final String id;
  final String name;
  final String description;
  final String slug;
  final String imageUrl;
  final String icon;
  final int sortOrder;
  final String parentId;
}

class MobileProduct {
  const MobileProduct({
    required this.id,
    required this.sku,
    required this.name,
    required this.verticalName,
    required this.description,
    required this.publicPriceUsd,
    required this.b2bPriceUsd,
    required this.availableStock,
    required this.badge,
    required this.requiresQuote,
    required this.requiresTechnicalValidation,
    required this.compatibilityNotes,
    this.productType = "machine",
    this.imageUrls = const [],
    this.discountPercent = 0,
    this.originalPriceUsd,
    this.variants = const [],
    this.specifications = const {},
    this.pdfUrls = const [],
    this.imageUrl,
  });

  final String id;
  final String sku;
  final String name;
  final String verticalName;
  final String description;
  final double publicPriceUsd;
  final double b2bPriceUsd;
  final int availableStock;
  final String badge;
  final bool requiresQuote;
  final bool requiresTechnicalValidation;
  final List<String> compatibilityNotes;
  final String productType;
  final List<String> imageUrls;
  final double discountPercent;
  final double? originalPriceUsd;
  final List<String> variants;
  final Map<String, String> specifications;
  final List<String> pdfUrls;
  final String? imageUrl;

  String get categoryName => verticalName;
  bool get hasDiscount =>
      discountPercent > 0 || (originalPriceUsd ?? 0) > publicPriceUsd;
  double get effectiveB2bPriceUsd =>
      b2bPriceUsd > 0 ? b2bPriceUsd : publicPriceUsd;
  double? get b2bReferencePriceUsd {
    if (publicPriceUsd > effectiveB2bPriceUsd) {
      return publicPriceUsd;
    }
    if ((originalPriceUsd ?? 0) > effectiveB2bPriceUsd) {
      return originalPriceUsd;
    }
    return null;
  }

  double get b2bDiscountPercent {
    final reference = b2bReferencePriceUsd;
    if (reference == null || reference <= 0) {
      return discountPercent;
    }
    return ((reference - effectiveB2bPriceUsd) / reference * 100).clamp(0, 100);
  }

  String? get primaryImageUrl {
    if (imageUrl != null && imageUrl!.isNotEmpty) {
      return imageUrl;
    }
    return imageUrls.isNotEmpty ? imageUrls.first : null;
  }

  List<String> get galleryImageUrls {
    final urls = <String>[];
    final primary = primaryImageUrl;
    if (primary != null && primary.isNotEmpty) {
      urls.add(primary);
    }
    for (final url in imageUrls) {
      if (url.isNotEmpty && !urls.contains(url)) {
        urls.add(url);
      }
    }
    return urls;
  }
}

class MobileProductQuery {
  const MobileProductQuery({
    this.text = "",
    this.verticalName,
    this.categoryId,
    this.sellerId,
    this.onlyAvailable = false,
    this.onlyNeedsValidation = false,
    this.limit = 24,
    this.cursor,
  });

  final String text;
  final String? verticalName;
  final String? categoryId;
  final String? sellerId;
  final bool onlyAvailable;
  final bool onlyNeedsValidation;
  final int limit;
  final String? cursor;

  MobileProductQuery copyWith({
    String? text,
    String? verticalName,
    String? categoryId,
    String? sellerId,
    bool? onlyAvailable,
    bool? onlyNeedsValidation,
    int? limit,
    String? cursor,
  }) {
    return MobileProductQuery(
      text: text ?? this.text,
      verticalName: verticalName ?? this.verticalName,
      categoryId: categoryId ?? this.categoryId,
      sellerId: sellerId ?? this.sellerId,
      onlyAvailable: onlyAvailable ?? this.onlyAvailable,
      onlyNeedsValidation: onlyNeedsValidation ?? this.onlyNeedsValidation,
      limit: limit ?? this.limit,
      cursor: cursor,
    );
  }
}

class MobileProductPage {
  const MobileProductPage({
    required this.products,
    required this.hasMore,
    this.nextCursor,
  });

  final List<MobileProduct> products;
  final bool hasMore;
  final String? nextCursor;
}

class MobileLocation {
  const MobileLocation({
    required this.id,
    required this.name,
    required this.subtitle,
    this.phone = "",
    this.whatsapp = "",
    this.address = "",
    this.specialties = const [],
  });

  final String id;
  final String name;
  final String subtitle;
  final String phone;
  final String whatsapp;
  final String address;
  final List<String> specialties;
}

class MobileSellerSnapshot {
  const MobileSellerSnapshot({
    required this.id,
    required this.name,
  });

  final String id;
  final String name;
}

class MobileAnnouncement {
  const MobileAnnouncement({
    required this.id,
    required this.title,
    required this.body,
    required this.placement,
    required this.priority,
    required this.startsAt,
    required this.status,
    this.ctaLabel,
    this.ctaUrl,
    this.imageUrl,
    this.endsAt,
  });

  final String id;
  final String title;
  final String body;
  final String placement;
  final int priority;
  final DateTime startsAt;
  final String status;
  final String? ctaLabel;
  final String? ctaUrl;
  final String? imageUrl;
  final DateTime? endsAt;

  bool get isActive {
    final now = DateTime.now();
    return status == "active" &&
        !startsAt.isAfter(now) &&
        (endsAt == null || endsAt!.isAfter(now));
  }
}

class MobileNotification {
  const MobileNotification({
    required this.id,
    required this.title,
    required this.body,
    required this.type,
    required this.typeLabel,
    required this.priority,
    required this.status,
    required this.createdAt,
    this.module = "",
    this.entityType = "",
    this.entityId = "",
    this.deepLink = "",
  });

  final String id;
  final String title;
  final String body;
  final String type;
  final String typeLabel;
  final String priority;
  final String status;
  final DateTime createdAt;
  final String module;
  final String entityType;
  final String entityId;
  final String deepLink;

  bool get isUnread => status == "unread";
  bool get isCritical => priority == "critical" || priority == "high";
}

class MobileCartItem {
  const MobileCartItem({
    required this.productId,
    required this.sku,
    required this.title,
    required this.quantity,
    required this.unitPriceUsd,
    required this.requiresQuote,
    required this.requiresTechnicalValidation,
    this.imageUrl,
  });

  final String productId;
  final String sku;
  final String title;
  final int quantity;
  final double unitPriceUsd;
  final bool requiresQuote;
  final bool requiresTechnicalValidation;
  final String? imageUrl;

  factory MobileCartItem.fromJson(Map<String, dynamic> json) {
    return MobileCartItem(
      productId: json["productId"]?.toString() ?? "",
      sku: json["sku"]?.toString() ?? "",
      title: json["title"]?.toString() ?? "",
      quantity: _readInt(json["quantity"], fallback: 1),
      unitPriceUsd: _readDouble(json["unitPriceUsd"]),
      requiresQuote: json["requiresQuote"] == true,
      requiresTechnicalValidation: json["requiresTechnicalValidation"] == true,
      imageUrl: json["imageUrl"]?.toString(),
    );
  }

  MobileCartItem copyWith({
    int? quantity,
  }) {
    return MobileCartItem(
      productId: productId,
      sku: sku,
      title: title,
      quantity: quantity ?? this.quantity,
      unitPriceUsd: unitPriceUsd,
      requiresQuote: requiresQuote,
      requiresTechnicalValidation: requiresTechnicalValidation,
      imageUrl: imageUrl,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      "productId": productId,
      "sku": sku,
      "title": title,
      "quantity": quantity,
      "unitPriceUsd": unitPriceUsd,
      "requiresQuote": requiresQuote,
      "requiresTechnicalValidation": requiresTechnicalValidation,
      "imageUrl": imageUrl,
    };
  }

  static int _readInt(dynamic value, {int fallback = 0}) {
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.toInt();
    }
    return int.tryParse(value?.toString() ?? "") ?? fallback;
  }

  static double _readDouble(dynamic value, {double fallback = 0}) {
    if (value is double) {
      return value;
    }
    if (value is num) {
      return value.toDouble();
    }
    return double.tryParse(value?.toString() ?? "") ?? fallback;
  }
}

class MobileCheckoutPreview {
  const MobileCheckoutPreview({
    required this.subtotalUsd,
    required this.totalUsd,
    required this.totalLocal,
    required this.exchangeRateUsdLocal,
    required this.requiresOperatorReview,
    required this.blockingReasons,
  });

  final double subtotalUsd;
  final double totalUsd;
  final double totalLocal;
  final double exchangeRateUsdLocal;
  final bool requiresOperatorReview;
  final List<String> blockingReasons;
}

class MobileCreditSnapshot {
  const MobileCreditSnapshot({
    required this.customerId,
    required this.creditEnabled,
    required this.creditLimitUsd,
    required this.creditUsedUsd,
    required this.creditOrdersUsd,
    required this.creditExposureUsd,
    required this.creditAvailableUsd,
    required this.paymentTermsDays,
    required this.status,
    this.allowedPaymentTermsDays = const [0],
    this.defaultSaleType = "cash",
    this.assignedSeller = const MobileSellerSnapshot(id: "", name: ""),
  });

  final String customerId;
  final bool creditEnabled;
  final double creditLimitUsd;
  final double creditUsedUsd;
  final double creditOrdersUsd;
  final double creditExposureUsd;
  final double creditAvailableUsd;
  final int paymentTermsDays;
  final String status;
  final List<int> allowedPaymentTermsDays;
  final String defaultSaleType;
  final MobileSellerSnapshot assignedSeller;
}

class MobileOrderSummary {
  const MobileOrderSummary({
    required this.id,
    required this.status,
    required this.totalUsd,
    required this.paidUsd,
    required this.balanceUsd,
    required this.itemsCount,
    required this.createdAt,
    required this.paymentStatus,
    required this.stockStatus,
    this.customerId = "",
    this.customerName = "",
    this.sellerId = "",
    this.sellerName = "",
    this.saleType = "cash",
    this.saleTypeLabel = "Contado",
    this.paymentTermDays = 0,
    this.dueDate,
    this.dueStatus = "without_due_date",
    this.commissionUsd = 0,
    this.commissionStatus = "",
    this.commissionStatusLabel = "",
  });

  final String id;
  final String status;
  final double totalUsd;
  final double paidUsd;
  final double balanceUsd;
  final int itemsCount;
  final DateTime createdAt;
  final String paymentStatus;
  final String stockStatus;
  final String customerId;
  final String customerName;
  final String sellerId;
  final String sellerName;
  final String saleType;
  final String saleTypeLabel;
  final int paymentTermDays;
  final DateTime? dueDate;
  final String dueStatus;
  final double commissionUsd;
  final String commissionStatus;
  final String commissionStatusLabel;
}

class MobileSellerSummary {
  const MobileSellerSummary({
    required this.sellerId,
    required this.sellerName,
    required this.roleLabel,
    this.sellerCode = "",
    this.sellerZone = "",
    this.sellerTerritory = "",
    this.commissionRatePercent = 0,
    this.salesGoalUsd = 0,
    this.salesMonthUsd = 0,
    this.goalProgressPercent = 0,
    this.ticketAverageUsd = 0,
    this.activeClientsCount = 0,
    this.newClientsMonth = 0,
    required this.clientsCount,
    required this.ordersCount,
    required this.pendingCreditRequests,
    required this.salesUsd,
    required this.openBalanceUsd,
    required this.pendingCommissionUsd,
    required this.approvedCommissionUsd,
    required this.paidCommissionUsd,
  });

  final String sellerId;
  final String sellerName;
  final String roleLabel;
  final String sellerCode;
  final String sellerZone;
  final String sellerTerritory;
  final double commissionRatePercent;
  final double salesGoalUsd;
  final double salesMonthUsd;
  final double goalProgressPercent;
  final double ticketAverageUsd;
  final int activeClientsCount;
  final int newClientsMonth;
  final int clientsCount;
  final int ordersCount;
  final int pendingCreditRequests;
  final double salesUsd;
  final double openBalanceUsd;
  final double pendingCommissionUsd;
  final double approvedCommissionUsd;
  final double paidCommissionUsd;
}

class MobileSellerClient {
  const MobileSellerClient({
    required this.id,
    required this.businessName,
    required this.email,
    required this.phone,
    required this.city,
    required this.state,
    required this.creditEnabled,
    required this.creditStatus,
    required this.creditLimitUsd,
    required this.creditAvailableUsd,
    required this.creditExposureUsd,
    required this.creditRequestStatus,
    this.taxId = "",
    this.contactName = "",
    this.address = "",
    this.deliveryZone = "",
    this.status = "active",
    this.defaultSaleType = "cash",
    this.allowedPaymentTermsDays = const [0],
    this.creditRequestedUsd = 0,
  });

  final String id;
  final String businessName;
  final String email;
  final String phone;
  final String city;
  final String state;
  final bool creditEnabled;
  final String creditStatus;
  final double creditLimitUsd;
  final double creditAvailableUsd;
  final double creditExposureUsd;
  final String creditRequestStatus;
  final String taxId;
  final String contactName;
  final String address;
  final String deliveryZone;
  final String status;
  final String defaultSaleType;
  final List<int> allowedPaymentTermsDays;
  final double creditRequestedUsd;

  List<int> get positivePaymentTerms =>
      allowedPaymentTermsDays.where((term) => term > 0).toList(growable: false);
  bool get canUseTermCredit => positivePaymentTerms.isNotEmpty;
  bool get canUseCreditLine => creditEnabled && creditAvailableUsd > 0;
}

class MobileSellerClientDraft {
  const MobileSellerClientDraft({
    required this.businessName,
    required this.email,
    this.phone = "",
    this.taxId = "",
    this.contactName = "",
    this.address = "",
    this.state = "",
    this.city = "",
    this.deliveryZone = "",
    this.notes = "",
    this.defaultSaleType = "cash",
    this.creditRequestedUsd = 0,
    this.allowedPaymentTermsDays = const [0],
    this.idempotencyKey = "",
  });

  final String businessName;
  final String email;
  final String phone;
  final String taxId;
  final String contactName;
  final String address;
  final String state;
  final String city;
  final String deliveryZone;
  final String notes;
  final String defaultSaleType;
  final double creditRequestedUsd;
  final List<int> allowedPaymentTermsDays;
  final String idempotencyKey;

  Map<String, dynamic> toJson() {
    return {
      "businessName": businessName,
      "email": email,
      "phone": phone,
      "taxId": taxId,
      "contactName": contactName,
      "address": address,
      "state": state,
      "city": city,
      "deliveryZone": deliveryZone,
      "notes": notes,
      "defaultSaleType": defaultSaleType,
      "creditRequestedUsd": creditRequestedUsd,
      "allowedPaymentTermsDays": allowedPaymentTermsDays,
      if (idempotencyKey.isNotEmpty) "idempotencyKey": idempotencyKey,
    };
  }
}

class MobileSellerClientCreated {
  const MobileSellerClientCreated({
    required this.client,
    required this.temporaryPassword,
    this.alreadyExists = false,
    this.message = "",
  });

  final MobileSellerClient client;
  final String temporaryPassword;
  final bool alreadyExists;
  final String message;
}
