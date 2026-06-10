import 'dart:convert';
import 'dart:io';

import '../auth/mobile_auth.dart';
import '../config/mobile_environment.dart';
import '../domain/mobile_models.dart';

class MobileSecureOrderDraft {
  const MobileSecureOrderDraft({
    required this.items,
    required this.preview,
    this.customerId = "",
    this.saleType = "cash",
    this.paymentTermDays = 0,
  });

  final List<MobileCartItem> items;
  final MobileCheckoutPreview preview;
  final String customerId;
  final String saleType;
  final int paymentTermDays;

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
      if (customerId.isNotEmpty) "customerId": customerId,
      "saleType": saleType,
      "paymentTermDays": paymentTermDays,
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
      "La app esta en modo Mock. Compilala con WULKAN_MOBILE_ORDER_API_URL y WULKAN_MOBILE_DATA_SOURCE=api para registrar ordenes en el admin.",
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
      final session = await mobileAuthRepository.getCurrentSession();
      final targetEndpoint = session.isMobileSalesUser
          ? endpoint.replace(
              path: endpoint.path.replaceFirst('/orders', '/seller/orders'))
          : endpoint;
      if (session.isMobileSalesUser && draft.customerId.isEmpty) {
        throw StateError("Selecciona el cliente antes de crear el pedido.");
      }

      final request = await client.postUrl(targetEndpoint);
      request.headers.contentType = ContentType.json;
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
      "salesChannel": session.isMobileSalesUser ? "seller_mobile" : "mobile",
      if (draft.customerId.isNotEmpty) "customerId": draft.customerId,
      "saleType": draft.saleType,
      "paymentTermDays": draft.paymentTermDays,
      "customer": {
        "id": draft.customerId.isNotEmpty ? draft.customerId : session.id,
        "name": session.name,
        "sellerId": session.assignedSeller.id,
        "sellerName": session.assignedSeller.name,
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

MobileOrderService createMobileOrderService() {
  if (mobileEnvironment.usesOrderApi) {
    return ApiMobileOrderService(
        endpoint: Uri.parse(mobileEnvironment.orderApiUrl));
  }

  return PreparedMobileOrderService();
}

final mobileOrderService = createMobileOrderService();
