import 'package:flutter/foundation.dart';

import '../config/mobile_environment.dart';
import '../data/mobile_repository.dart';
import '../domain/mobile_models.dart';

class MobileCartService {
  const MobileCartService({required this.repository});

  final MobileRepository repository;

  Future<List<MobileCartItem>> loadLocalCart() async {
    final product = await repository.getProduct("prod-motosierra-45cc");

    if (product == null) {
      return const [];
    }

    return [
      MobileCartItem(
        productId: product.id,
        sku: product.sku,
        title: product.name,
        quantity: 1,
        unitPriceUsd: product.ferreteroPriceUsd,
        requiresQuote: product.requiresQuote,
        requiresTechnicalValidation: product.requiresTechnicalValidation,
        imageUrl: product.primaryImageUrl,
      ),
    ];
  }

  MobileCheckoutPreview calculatePreview(
    List<MobileCartItem> items, {
    double? exchangeRateUsdVes,
  }) {
    final subtotalUsd = _roundMoney(
      items.fold<double>(
          0, (total, item) => total + item.quantity * item.unitPriceUsd),
    );
    final exchangeRate =
        exchangeRateUsdVes ?? mobileEnvironment.exchangeRateUsdVes;
    final blockingReasons = <String>{
      for (final item in items)
        if (item.requiresQuote) "requires_quote",
      for (final item in items)
        if (item.requiresTechnicalValidation) "requires_technical_validation",
    }.toList();

    return MobileCheckoutPreview(
      subtotalUsd: subtotalUsd,
      totalUsd: subtotalUsd,
      totalVes: _roundMoney(subtotalUsd * exchangeRate),
      exchangeRateUsdVes: exchangeRate,
      requiresOperatorReview: blockingReasons.isNotEmpty,
      blockingReasons: blockingReasons,
    );
  }

  double _roundMoney(double value) => double.parse(value.toStringAsFixed(2));
}

class MobileCartController extends ValueNotifier<List<MobileCartItem>> {
  MobileCartController() : super(const []);

  int get itemCount =>
      value.fold<int>(0, (total, item) => total + item.quantity);

  bool contains(String productId) {
    return value.any((item) => item.productId == productId);
  }

  void addProduct(MobileProduct product, {int quantity = 1}) {
    if (product.ferreteroPriceUsd <= 0) {
      return;
    }
    final normalizedQuantity = quantity < 1 ? 1 : quantity;

    final existingIndex =
        value.indexWhere((item) => item.productId == product.id);

    if (existingIndex >= 0) {
      final updated = [...value];
      final current = updated[existingIndex];
      updated[existingIndex] = current.copyWith(
        quantity: current.quantity + normalizedQuantity,
      );
      value = updated;
      return;
    }

    value = [
      ...value,
      MobileCartItem(
        productId: product.id,
        sku: product.sku,
        title: product.name,
        quantity: normalizedQuantity,
        unitPriceUsd: product.ferreteroPriceUsd,
        requiresQuote: product.requiresQuote,
        requiresTechnicalValidation: product.requiresTechnicalValidation,
        imageUrl: product.primaryImageUrl,
      ),
    ];
  }

  void increment(String productId) {
    value = [
      for (final item in value)
        item.productId == productId
            ? item.copyWith(quantity: item.quantity + 1)
            : item,
    ];
  }

  void decrement(String productId) {
    final updated = <MobileCartItem>[];

    for (final item in value) {
      if (item.productId != productId) {
        updated.add(item);
        continue;
      }

      if (item.quantity > 1) {
        updated.add(item.copyWith(quantity: item.quantity - 1));
      }
    }

    value = updated;
  }

  void remove(String productId) {
    value = value.where((item) => item.productId != productId).toList();
  }

  void clear() {
    value = const [];
  }
}

final mobileCartService = MobileCartService(repository: mobileRepository);
final mobileCartController = MobileCartController();
