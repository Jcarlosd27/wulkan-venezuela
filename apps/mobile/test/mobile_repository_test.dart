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

      expect(products.length, greaterThan(50));
      expect(products.map((product) => product.sku), contains('WUL-MOT-45CC'));
      expect(products.map((product) => product.sku), contains('WK-BL-43'));
      expect(products.any((product) => product.requiresTechnicalValidation),
          isTrue);
    });

    test('paginates catalog without loading the full product set', () async {
      final firstPage = await repository.listProductPage(
        const MobileProductQuery(limit: 10),
      );
      final secondPage = await repository.listProductPage(
        MobileProductQuery(limit: 10, cursor: firstPage.nextCursor),
      );

      expect(firstPage.products, hasLength(10));
      expect(firstPage.hasMore, isTrue);
      expect(firstPage.nextCursor, isNotNull);
      expect(secondPage.products, hasLength(10));
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
    });

    test('returns B2B credit and order summaries', () async {
      final credit = await repository.getCredit('client-ferreteria-valencia');
      final orders = await repository.listOrders('client-ferreteria-valencia');

      expect(credit.creditAvailableUsd, 915);
      expect(credit.status, 'in_use');
      expect(credit.defaultSaleType, 'term_credit');
      expect(credit.allowedPaymentTermsDays, contains(30));
      expect(credit.assignedSeller.name, 'Vendedor Wulkan');
      expect(orders, isNotEmpty);
      expect(orders.first.status, 'partial_paid');
    });
  });

  group('Firestore mappers', () {
    test('maps seeded product shape into mobile product', () {
      final product = mapFirestoreProduct('prod-motosierra-45cc', {
        'sku': 'WUL-MOT-45CC',
        'title': 'Motosierra 45cc',
        'description': 'Equipo de corte para uso tecnico y jardin.',
        'verticalId': 'machinery-garden',
        'publicPrice': {'amount': 185, 'currency': 'USD'},
        'b2bPrice': {'amount': 162, 'currency': 'USD'},
        'stock': 12,
        'requiresQuote': false,
        'requiresTechnicalValidation': false,
      });

      expect(product.name, 'Motosierra 45cc');
      expect(product.publicPriceUsd, 185);
      expect(product.b2bPriceUsd, 162);
      expect(product.availableStock, 12);
      expect(product.badge, 'Comprar');
    });

    test('marks technical validation products with validar badge', () {
      final product = mapFirestoreProduct('prod-cadena-18', {
        'sku': 'WUL-REP-CAD18',
        'title': 'Cadena 18 pulgadas compatible',
        'publicPrice': {'amount': 18, 'currency': 'USD'},
        'b2bPrice': {'amount': 15, 'currency': 'USD'},
        'stock': 4,
        'requiresTechnicalValidation': true,
      });

      expect(product.badge, 'Validar');
      expect(product.requiresTechnicalValidation, isTrue);
    });
  });
}
