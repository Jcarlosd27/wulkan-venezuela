import 'dart:convert';
import 'dart:io';

import 'package:cloud_firestore/cloud_firestore.dart';

import '../auth/mobile_auth.dart';
import '../config/mobile_environment.dart';
import '../domain/mobile_models.dart';

class MobileSecureOrderDraft {
  const MobileSecureOrderDraft({
    required this.items,
    required this.preview,
  });

  final List<MobileCartItem> items;
  final MobileCheckoutPreview preview;

  Map<String, dynamic> toCallablePayload() {
    return {
      "items": [
        for (final item in items)
          {
            "productId": item.productId,
            "sku": item.sku,
            "quantity": item.quantity,
          },
      ],
      "exchangeRateUsdVes": preview.exchangeRateUsdVes,
    };
  }
}

abstract class MobileOrderService {
  Future<String> createSecureOrder(MobileSecureOrderDraft draft);
}

class PreparedMobileOrderService implements MobileOrderService {
  @override
  Future<String> createSecureOrder(MobileSecureOrderDraft draft) async {
    throw StateError(
      "La app esta en modo Mock. Compilala con WULKAN_MOBILE_ORDER_API_URL o WULKAN_MOBILE_DATA_SOURCE=firestore para registrar ordenes en el admin.",
    );
  }
}

class ApiMobileOrderService implements MobileOrderService {
  ApiMobileOrderService({required this.endpoint});

  final Uri endpoint;

  @override
  Future<String> createSecureOrder(MobileSecureOrderDraft draft) async {
    if (draft.items.isEmpty) {
      throw StateError("El carrito no tiene productos.");
    }

    final client = HttpClient();

    try {
      final request = await client.postUrl(endpoint);
      request.headers.contentType = ContentType.json;
      final session = await mobileAuthRepository.getCurrentSession();
      if (session.accessToken.isNotEmpty) {
        request.headers.set("Authorization", "Bearer ${session.accessToken}");
      }
      request.write(jsonEncode(_toPayload(draft, session)));

      final response = await request.close();
      final body = await response.transform(utf8.decoder).join();

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw StateError(
          "No pudimos registrar la orden (${response.statusCode}): $body",
        );
      }

      final payload = jsonDecode(body);
      final orderId =
          payload is Map<String, dynamic> ? payload["orderId"] : null;

      if (orderId is! String || orderId.isEmpty) {
        throw StateError("El admin no devolvio un numero de orden valido.");
      }

      return orderId;
    } finally {
      client.close(force: true);
    }
  }

  Map<String, dynamic> _toPayload(
    MobileSecureOrderDraft draft,
    MobileUserSession session,
  ) {
    return {
      "source": "mobile_app",
      "customer": {
        "id": session.id,
        "name": session.name,
      },
      "items": [
        for (final item in draft.items)
          {
            "productId": item.productId,
            "sku": item.sku,
            "title": item.title,
            "quantity": item.quantity,
            "unitPriceUsd": item.unitPriceUsd,
            "imageUrl": item.imageUrl,
            "requiresQuote": item.requiresQuote,
            "requiresTechnicalValidation": item.requiresTechnicalValidation,
          },
      ],
      "preview": {
        "subtotalUsd": draft.preview.subtotalUsd,
        "totalUsd": draft.preview.totalUsd,
        "totalVes": draft.preview.totalVes,
        "exchangeRateUsdVes": draft.preview.exchangeRateUsdVes,
        "requiresOperatorReview": draft.preview.requiresOperatorReview,
        "blockingReasons": draft.preview.blockingReasons,
      },
    };
  }
}

class FirestoreMobileOrderService implements MobileOrderService {
  FirestoreMobileOrderService({FirebaseFirestore? firestore})
      : _firestore = firestore ?? FirebaseFirestore.instance;

  final FirebaseFirestore _firestore;

  @override
  Future<String> createSecureOrder(MobileSecureOrderDraft draft) async {
    if (draft.items.isEmpty) {
      throw StateError("El carrito no tiene productos.");
    }

    final orderId = "ord-mobile-${DateTime.now().millisecondsSinceEpoch}";
    final paymentId = "pay-$orderId";
    final now = FieldValue.serverTimestamp();
    final requiresOperatorReview = draft.preview.requiresOperatorReview;
    const firstSellerCompanyId = "wulkan-direct";

    final orderItems = [
      for (final item in draft.items)
        {
          "productId": item.productId,
          "sku": item.sku,
          "title": item.title,
          "quantity": item.quantity,
          "unitPrice": {
            "amount": item.unitPriceUsd,
            "currency": "USD",
          },
          "total": {
            "amount": double.parse(
              (item.quantity * item.unitPriceUsd).toStringAsFixed(2),
            ),
            "currency": "USD",
          },
        },
    ];

    final batch = _firestore.batch();
    final orderRef = _firestore.collection("orders").doc(orderId);
    final paymentRef = _firestore.collection("payments").doc(paymentId);
    final auditRef = _firestore.collection("audit_logs").doc(
          "audit-$orderId-created",
        );

    batch.set(paymentRef, {
      "orderId": orderId,
      "companyId": firstSellerCompanyId,
      "method": "whatsapp_assisted",
      "amountUsd": draft.preview.totalUsd,
      "amountVes": draft.preview.totalVes,
      "currency": "USD",
      "exchangeRate": draft.preview.exchangeRateUsdVes,
      "status": "under_review",
      "createdAt": now,
      "updatedAt": now,
    });

    batch.set(orderRef, {
      "customerId": "customer-mobile-demo",
      "companyId": firstSellerCompanyId,
      "items": orderItems,
      "subtotal": {
        "amount": draft.preview.subtotalUsd,
        "currency": "USD",
      },
      "total": {
        "amount": draft.preview.totalUsd,
        "currency": "USD",
      },
      "currency": "USD",
      "exchangeRateUsdVes": draft.preview.exchangeRateUsdVes,
      "status":
          requiresOperatorReview ? "payment_under_review" : "pending_payment",
      "paymentId": paymentId,
      "notes": "Orden creada desde app movil Wulkan.",
      "createdAt": now,
      "updatedAt": now,
    });

    batch.set(auditRef, {
      "actorUserId": "customer-mobile-demo",
      "actorRole": "customer",
      "action": "order_created",
      "targetCollection": "orders",
      "targetId": orderId,
      "metadata": {
        "source": "mobile_app",
        "paymentId": paymentId,
        "requiresOperatorReview": requiresOperatorReview,
      },
      "createdAt": now,
    });

    await batch.commit();
    return orderId;
  }
}

MobileOrderService createMobileOrderService() {
  if (mobileEnvironment.usesOrderApi) {
    return ApiMobileOrderService(
        endpoint: Uri.parse(mobileEnvironment.orderApiUrl));
  }

  if (mobileEnvironment.usesFirestore) {
    return FirestoreMobileOrderService();
  }

  return PreparedMobileOrderService();
}

final mobileOrderService = createMobileOrderService();
