import 'package:flutter_test/flutter_test.dart';
import 'package:wulkan_mobile/src/cart/mobile_cart_service.dart';
import 'package:wulkan_mobile/src/data/mobile_repository.dart';
import 'package:wulkan_mobile/src/domain/mobile_models.dart';
import 'package:wulkan_mobile/src/orders/mobile_order_service.dart';

void main() {
  group('MobileCartService', () {
    final service = MobileCartService(repository: MockMobileRepository());

    test('loads demo cart from product repository', () async {
      final items = await service.loadDemoCart();

      expect(items, hasLength(1));
      expect(items.first.sku, 'WUL-MOT-45CC');
      expect(items.first.unitPriceUsd, 162);
    });

    test('calculates checkout preview in USD and VES', () {
      final preview = service.calculatePreview(
        const [
          MobileCartItem(
            productId: 'prod-motosierra-45cc',
            sku: 'WUL-MOT-45CC',
            title: 'Motosierra 45cc',
            quantity: 2,
            unitPriceUsd: 185,
            requiresQuote: false,
            requiresTechnicalValidation: false,
            imageUrl: null,
          ),
        ],
        exchangeRateUsdVes: 38.5,
      );

      expect(preview.subtotalUsd, 370);
      expect(preview.totalVes, 14245);
      expect(preview.requiresOperatorReview, isFalse);
    });

    test('flags technical validation as operator review', () {
      final preview = service.calculatePreview(
        const [
          MobileCartItem(
            productId: 'prod-cadena-18',
            sku: 'WUL-REP-CAD18',
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
        sku: 'WUL-MOT-45CC',
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
  });

  test('MobileSecureOrderDraft builds callable payload', () {
    const draft = MobileSecureOrderDraft(
      items: [
        MobileCartItem(
          productId: 'prod-motosierra-45cc',
          sku: 'WUL-MOT-45CC',
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
        totalVes: 7122.5,
        exchangeRateUsdVes: 38.5,
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
          'sku': 'WUL-MOT-45CC',
          'quantity': 1,
        },
      ],
      'exchangeRateUsdVes': 38.5,
      'saleType': 'term_credit',
      'paymentTermDays': 15,
    });
  });

  test('PreparedMobileOrderService explains that checkout needs a backend', () {
    const draft = MobileSecureOrderDraft(
      items: [
        MobileCartItem(
          productId: 'prod-motosierra-45cc',
          sku: 'WUL-MOT-45CC',
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
        totalVes: 7122.5,
        exchangeRateUsdVes: 38.5,
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
          contains('WULKAN_MOBILE_ORDER_API_URL'),
        ),
      ),
    );
  });
}
