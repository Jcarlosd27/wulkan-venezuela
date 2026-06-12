import 'package:flutter_test/flutter_test.dart';
import 'package:wulkan_mobile/src/data/mobile_repository.dart';
import 'package:wulkan_mobile/src/domain/mobile_models.dart';

void main() {
  group('MockMobileRepository', () {
    final repository = MockMobileRepository();

    test('returns initial categories', () async {
      final categories = await repository.listCategories();

      expect(categories, isNotEmpty);
      expect(categories.first.name, 'Maquinaria y jardin');
    });

    test('returns technical catalog products', () async {
      final products = await repository.listProducts();

      expect(products.length, 3);
      expect(products.map((product) => product.sku), contains('WUL-MOT-45CC'));
      expect(products.any((product) => product.requiresTechnicalValidation),
          isTrue);
    });

    test('paginates catalog without loading the full product set', () async {
      final firstPage = await repository.listProductPage(
        const MobileProductQuery(limit: 2),
      );
      final secondPage = await repository.listProductPage(
        MobileProductQuery(limit: 2, cursor: firstPage.nextCursor),
      );

      expect(firstPage.products, hasLength(2));
      expect(firstPage.hasMore, isTrue);
      expect(firstPage.nextCursor, isNotNull);
      expect(secondPage.products, hasLength(1));
      expect(
        firstPage.products.map((product) => product.id).toSet().intersection(
              secondPage.products.map((product) => product.id).toSet(),
            ),
        isEmpty,
      );
    });

    test('filters paginated catalog by search and operational state', () async {
      final chainsawPage = await repository.listProductPage(
        const MobileProductQuery(text: 'motosierra', limit: 20),
      );
      final validationPage = await repository.listProductPage(
        const MobileProductQuery(onlyNeedsValidation: true, limit: 20),
      );

      expect(chainsawPage.products.map((product) => product.sku),
          contains('WUL-MOT-45CC'));
      expect(
        validationPage.products.any(
          (product) =>
              product.requiresQuote || product.requiresTechnicalValidation,
        ),
        isTrue,
      );
    });

    test('finds product detail by id', () async {
      final product = await repository.getProduct('prod-motosierra-45cc');

      expect(product, isNotNull);
      expect(product?.publicPriceUsd, 185);
      expect(product?.compatibilityNotes, isNotEmpty);
    });

    test('returns authorized locations', () async {
      final locations = await repository.listLocations();

      expect(locations, hasLength(2));
      expect(locations.first.name, contains('Caracas'));
      expect(locations.first.whatsapp, isNotEmpty);
      expect(locations.first.specialties, contains('Garantia'));
    });

    test('returns B2B credit and order summaries', () async {
      final credit = await repository.getCredit('client-local-wulkan');
      final orders = await repository.listOrders('client-local-wulkan');

      expect(credit.creditAvailableUsd, 0);
      expect(credit.status, 'without_credit');
      expect(credit.defaultSaleType, 'cash');
      expect(credit.allowedPaymentTermsDays, contains(0));
      expect(credit.assignedSeller.name, 'Vendedor Wulkan');
      expect(orders, isEmpty);
    });
  });

  group('API mappers', () {
    test('maps API product shape into mobile product', () {
      final product = mapApiProduct('prod-motosierra-45cc', {
        'sku': 'WUL-MOT-45CC',
        'name': 'Motosierra 45cc',
        'description': 'Equipo de corte para uso tecnico y jardin.',
        'categoryName': 'Maquinaria y jardin',
        'publicPriceUsd': 185,
        'b2bPriceUsd': 162,
        'availableStock': 12,
        'requiresQuote': false,
        'requiresTechnicalValidation': false,
        'pdfUrls': ['https://cdn.wulkan/ficha-motosierra.pdf'],
      });

      expect(product.name, 'Motosierra 45cc');
      expect(product.publicPriceUsd, 185);
      expect(product.b2bPriceUsd, 162);
      expect(product.availableStock, 12);
      expect(product.badge, 'Comprar');
      expect(
          product.pdfUrls, contains('https://cdn.wulkan/ficha-motosierra.pdf'));
    });

    test('marks technical validation products with validar badge', () {
      final product = mapApiProduct('prod-cadena-18', {
        'sku': 'WUL-REP-CAD18',
        'name': 'Cadena 18 pulgadas compatible',
        'publicPriceUsd': 18,
        'b2bPriceUsd': 15,
        'availableStock': 4,
        'requiresTechnicalValidation': true,
      });

      expect(product.badge, 'Validar');
      expect(product.requiresTechnicalValidation, isTrue);
    });

    test('maps order commission fields for seller mobile view', () {
      final order = mapApiOrder({
        'orderId': 'ord-mobile-100',
        'customerName': 'Ferreteria Central',
        'saleType': 'credit_line',
        'saleTypeLabel': 'Linea de credito',
        'status': 'approved',
        'paymentStatus': 'partial_paid',
        'stockStatus': 'reserved',
        'totalUsd': 250,
        'paidUsd': 100,
        'balanceUsd': 150,
        'itemsCount': 3,
        'commissionUsd': 12.5,
        'commissionStatus': 'commission_pending',
        'commissionStatusLabel': 'Pendiente',
      });

      expect(order.id, 'ord-mobile-100');
      expect(order.customerName, 'Ferreteria Central');
      expect(order.saleType, 'credit_line');
      expect(order.saleTypeLabel, 'Linea de credito');
      expect(order.balanceUsd, 150);
      expect(order.commissionUsd, 12.5);
      expect(order.commissionStatus, 'commission_pending');
      expect(order.commissionStatusLabel, 'Pendiente');
    });
  });
}
