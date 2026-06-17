import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:fventas_mobile/src/cart/mobile_cart_service.dart';
import 'package:fventas_mobile/src/data/mobile_repository.dart';
import 'package:fventas_mobile/src/domain/mobile_models.dart';
import 'package:fventas_mobile/src/orders/mobile_order_service.dart';

void main() {
  group('MobileCartService', () {
    final service = MobileCartService(repository: MockMobileRepository());

    test('starts local cart empty until the user selects products', () async {
      final items = await service.loadLocalCart();

      expect(items, isEmpty);
    });

    test('calculates checkout preview in base and local currencies', () {
      final preview = service.calculatePreview(
        const [
          MobileCartItem(
            productId: 'prod-motosierra-45cc',
            sku: 'FVT-MOT-45CC',
            title: 'Motosierra 45cc',
            quantity: 2,
            unitPriceUsd: 185,
            requiresQuote: false,
            requiresTechnicalValidation: false,
            imageUrl: null,
          ),
        ],
        exchangeRateUsdLocal: 950,
      );

      expect(preview.subtotalUsd, 370);
      expect(preview.totalLocal, 351500);
      expect(preview.requiresOperatorReview, isFalse);
    });

    test('flags technical validation as operator review', () {
      final preview = service.calculatePreview(
        const [
          MobileCartItem(
            productId: 'prod-cadena-18',
            sku: 'FVT-REP-CAD18',
            title: 'Cadena 18 pulgadas compatible',
            quantity: 1,
            unitPriceUsd: 18,
            requiresQuote: false,
            requiresTechnicalValidation: true,
            imageUrl: null,
          ),
        ],
      );

      expect(preview.requiresOperatorReview, isTrue);
      expect(
          preview.blockingReasons, contains('requires_technical_validation'));
    });

    test('controller adds quantities, increments and removes live cart items',
        () {
      final controller = MobileCartController();
      const product = MobileProduct(
        id: 'prod-motosierra-45cc',
        sku: 'FVT-MOT-45CC',
        name: 'Motosierra 45cc',
        verticalName: 'Maquinaria y jardin',
        description: 'Equipo de corte',
        publicPriceUsd: 185,
        b2bPriceUsd: 162,
        availableStock: 8,
        badge: 'Comprar',
        requiresQuote: false,
        requiresTechnicalValidation: false,
        compatibilityNotes: [],
        imageUrl: 'https://cdn.example.com/motosierra.jpg',
      );

      controller.addProduct(product, quantity: 2);
      controller.addProduct(product, quantity: 3);
      controller.increment(product.id);

      expect(controller.value, hasLength(1));
      expect(controller.itemCount, 6);
      expect(controller.contains(product.id), isTrue);
      expect(controller.value.first.unitPriceUsd, 162);
      expect(controller.value.first.imageUrl, product.imageUrl);

      controller.decrement(product.id);
      expect(controller.itemCount, 5);

      controller.remove(product.id);
      expect(controller.value, isEmpty);
    });

    test('controller restores and persists local cart securely', () async {
      final storage = _MemoryCartStorage();
      const seedItem = MobileCartItem(
        productId: 'prod-motosierra-45cc',
        sku: 'FVT-MOT-45CC',
        title: 'Motosierra 45cc',
        quantity: 2,
        unitPriceUsd: 162,
        requiresQuote: false,
        requiresTechnicalValidation: false,
        imageUrl: 'https://cdn.example.com/motosierra.jpg',
      );
      await storage.writeCart(jsonEncode([seedItem.toJson()]));

      final service = MobileCartService(
        repository: MockMobileRepository(),
        storage: storage,
      );
      final restoredFromService = await service.loadLocalCart();
      expect(restoredFromService, hasLength(1));
      expect(restoredFromService.first.quantity, 2);

      final controller = MobileCartController(storage: storage);
      await controller.load();
      expect(controller.itemCount, 2);

      controller.increment(seedItem.productId);
      await pumpEventQueue();
      final updated = jsonDecode(storage.raw!) as List<dynamic>;
      expect(updated.first["quantity"], 3);

      controller.clear();
      await pumpEventQueue();
      expect(storage.raw, isNull);
    });
  });

  test('MobileSecureOrderDraft builds callable payload', () {
    const draft = MobileSecureOrderDraft(
      items: [
        MobileCartItem(
          productId: 'prod-motosierra-45cc',
          sku: 'FVT-MOT-45CC',
          title: 'Motosierra 45cc',
          quantity: 1,
          unitPriceUsd: 185,
          requiresQuote: false,
          requiresTechnicalValidation: false,
          imageUrl: null,
        ),
      ],
      preview: MobileCheckoutPreview(
        subtotalUsd: 185,
        totalUsd: 185,
        totalLocal: 175750,
        exchangeRateUsdLocal: 950,
        requiresOperatorReview: false,
        blockingReasons: [],
      ),
      saleType: 'term_credit',
      paymentTermDays: 15,
    );

    expect(draft.toCallablePayload(), {
      'items': [
        {
          'productId': 'prod-motosierra-45cc',
          'sku': 'FVT-MOT-45CC',
          'quantity': 1,
        },
      ],
      'exchangeRateUsdLocal': 950,
      'exchangeRateUsdClp': 950,
      'exchangeRateUsdVes': 950,
      'saleType': 'term_credit',
      'paymentTermDays': 15,
    });
  });

  test('PreparedMobileOrderService explains that checkout needs a backend', () {
    const draft = MobileSecureOrderDraft(
      items: [
        MobileCartItem(
          productId: 'prod-motosierra-45cc',
          sku: 'FVT-MOT-45CC',
          title: 'Motosierra 45cc',
          quantity: 1,
          unitPriceUsd: 185,
          requiresQuote: false,
          requiresTechnicalValidation: false,
          imageUrl: null,
        ),
      ],
      preview: MobileCheckoutPreview(
        subtotalUsd: 185,
        totalUsd: 185,
        totalLocal: 175750,
        exchangeRateUsdLocal: 950,
        requiresOperatorReview: false,
        blockingReasons: [],
      ),
    );

    expect(
      PreparedMobileOrderService().createSecureOrder(draft),
      throwsA(
        isA<StateError>().having(
          (error) => error.message,
          'message',
          contains('FVENTAS_MOBILE_ORDER_API_URL'),
        ),
      ),
    );
  });
}

class _MemoryCartStorage implements MobileCartStorage {
  String? raw;

  @override
  Future<void> clearCart() async {
    raw = null;
  }

  @override
  Future<String?> readCart() async => raw;

  @override
  Future<void> writeCart(String value) async {
    raw = value;
  }
}
