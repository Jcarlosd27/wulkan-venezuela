import 'package:flutter_test/flutter_test.dart';
import 'package:fventas_mobile/src/data/mobile_repository.dart';
import 'package:fventas_mobile/src/domain/mobile_models.dart';

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

      expect(products.length, greaterThanOrEqualTo(8));
      expect(products.map((product) => product.sku), contains('FVT-MOT-45CC'));
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
      expect(secondPage.products, hasLength(2));
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
          contains('FVT-MOT-45CC'));
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
      expect(product?.publicPriceUsd, 175750);
      expect(product?.compatibilityNotes, isNotEmpty);
    });

    test('adapts mock amounts for Venezuela without leaking CLP values',
        () async {
      final venezuelaRepository = MockMobileRepository(countryCode: 'VE');

      final product =
          await venezuelaRepository.getProduct('prod-motosierra-45cc');
      final credit = await venezuelaRepository.getCredit('client-local');

      expect(product?.publicPriceUsd, 185);
      expect(product?.b2bPriceUsd, 162);
      expect(credit.creditLimitUsd, 12000);
    });

    test('returns authorized locations', () async {
      final locations = await repository.listLocations();

      expect(locations, hasLength(2));
      expect(locations.first.name, contains('Punto autorizado'));
      expect(locations.first.address, 'Sucursal principal');
      expect(locations.first.whatsapp, isNotEmpty);
      expect(locations.first.specialties, contains('Garantia'));
    });

    test('returns B2B credit and order summaries', () async {
      final credit = await repository.getCredit('client-local-fventas');
      final orders = await repository.listOrders('client-local-fventas');

      expect(credit.creditEnabled, isTrue);
      expect(credit.creditAvailableUsd, greaterThan(0));
      expect(credit.status, 'approved');
      expect(credit.defaultSaleType, 'credit_line');
      expect(credit.allowedPaymentTermsDays, contains(30));
      expect(credit.assignedSeller.name, 'Carolina Reyes');
      expect(orders, hasLength(greaterThanOrEqualTo(3)));
      expect(orders.first.customerId, 'client-local-fventas');
      expect(orders.first.sellerName, 'Carolina Reyes');
    });

    test('returns a commercial seller mock board', () async {
      final summary = await repository.getSellerSummary();
      final clients = await repository.listSellerClients();
      final orders = await repository.listSellerOrders();
      final commissions = await repository.listSellerCommissions();

      expect(summary.salesMonthUsd, greaterThan(0));
      expect(summary.clientsCount, greaterThanOrEqualTo(4));
      expect(clients, hasLength(greaterThanOrEqualTo(4)));
      expect(clients.any((client) => client.creditRequestStatus == 'pending'),
          isTrue);
      expect(
        clients
            .where((client) => client.canUseCreditLine)
            .map((client) => client.defaultSaleType),
        contains('credit_line'),
      );
      expect(
        clients
            .firstWhere((client) => client.creditRequestStatus == 'pending')
            .creditRequestedUsd,
        greaterThan(0),
      );
      final pendingClient = clients
          .firstWhere((client) => client.creditRequestStatus == 'pending');
      expect(pendingClient.defaultSaleType, 'credit_line');
      expect(pendingClient.positivePaymentTerms, isEmpty);
      expect(pendingClient.canUseCreditLine, isFalse);
      expect(orders, hasLength(greaterThanOrEqualTo(3)));
      expect(
          commissions.map((order) => order.commissionStatus), contains('paid'));
    });
  });

  group('API mappers', () {
    test('maps API product shape into mobile product', () {
      final product = mapApiProduct('prod-motosierra-45cc', {
        'sku': 'FVT-MOT-45CC',
        'name': 'Motosierra 45cc',
        'description': 'Equipo de corte para uso tecnico y jardin.',
        'categoryName': 'Maquinaria y jardin',
        'publicPriceUsd': 185,
        'b2bPriceUsd': 162,
        'availableStock': 12,
        'requiresQuote': false,
        'requiresTechnicalValidation': false,
        'pdfUrls': ['https://cdn.fventas.cl/ficha-motosierra.pdf'],
      });

      expect(product.name, 'Motosierra 45cc');
      expect(product.publicPriceUsd, 185);
      expect(product.b2bPriceUsd, 162);
      expect(product.availableStock, 12);
      expect(product.badge, 'Comprar');
      expect(product.pdfUrls,
          contains('https://cdn.fventas.cl/ficha-motosierra.pdf'));
    });

    test('marks technical validation products with validar badge', () {
      final product = mapApiProduct('prod-cadena-18', {
        'sku': 'FVT-REP-CAD18',
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
        'customerName': 'Cliente B2B Central',
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
      expect(order.customerName, 'Cliente B2B Central');
      expect(order.saleType, 'credit_line');
      expect(order.saleTypeLabel, 'Linea de credito');
      expect(order.balanceUsd, 150);
      expect(order.commissionUsd, 12.5);
      expect(order.commissionStatus, 'commission_pending');
      expect(order.commissionStatusLabel, 'Pendiente');
    });

    test('maps seller client commercial conditions from admin payload', () {
      final client = mapApiSellerClient({
        'id': 'client-central',
        'businessName': 'Cliente Central',
        'email': 'compras@central.cl',
        'phone': '+56 9 1234 5678',
        'city': 'Santiago',
        'state': 'Metropolitana',
        'creditEnabled': true,
        'creditStatus': 'approved',
        'creditLimitUsd': 5000,
        'creditAvailableUsd': 3200,
        'creditExposureUsd': 1800,
        'creditRequestStatus': 'approved',
        'creditRequestedUsd': 5000,
        'defaultSaleType': 'credit_line',
        'allowedPaymentTermsDays': [0, 15, 30],
        'taxId': '76.000.000-0',
        'contactName': 'Comprador Central',
        'deliveryZone': 'Centro',
      });

      expect(client.defaultSaleType, 'credit_line');
      expect(client.allowedPaymentTermsDays, [0, 15, 30]);
      expect(client.positivePaymentTerms, [15, 30]);
      expect(client.canUseCreditLine, isTrue);
      expect(client.creditRequestedUsd, 5000);
      expect(client.taxId, '76.000.000-0');
    });
  });
}
