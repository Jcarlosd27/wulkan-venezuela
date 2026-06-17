import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../config/mobile_environment.dart';
import '../data/mobile_repository.dart';
import '../domain/mobile_models.dart';

class MobileCartService {
  const MobileCartService({
    required this.repository,
    MobileCartStorage storage = const SecureMobileCartStorage(),
  }) : _storage = storage;

  final MobileRepository repository;
  final MobileCartStorage _storage;

  Future<List<MobileCartItem>> loadLocalCart() async {
    try {
      return _decodeCartItems(await _storage.readCart());
    } catch (_) {
      return const [];
    }
  }

  MobileCheckoutPreview calculatePreview(
    List<MobileCartItem> items, {
    double? exchangeRateUsdLocal,
  }) {
    final subtotalUsd = _roundMoney(
      items.fold<double>(
          0, (total, item) => total + item.quantity * item.unitPriceUsd),
    );
    final exchangeRate =
        exchangeRateUsdLocal ?? mobileEnvironment.exchangeRateUsdLocal;
    final blockingReasons = <String>{
      for (final item in items)
        if (item.requiresQuote) "requires_quote",
      for (final item in items)
        if (item.requiresTechnicalValidation) "requires_technical_validation",
    }.toList();

    return MobileCheckoutPreview(
      subtotalUsd: subtotalUsd,
      totalUsd: subtotalUsd,
      totalLocal: _roundMoney(subtotalUsd * exchangeRate),
      exchangeRateUsdLocal: exchangeRate,
      requiresOperatorReview: blockingReasons.isNotEmpty,
      blockingReasons: blockingReasons,
    );
  }

  double _roundMoney(double value) => double.parse(value.toStringAsFixed(2));
}

abstract class MobileCartStorage {
  Future<String?> readCart();

  Future<void> writeCart(String value);

  Future<void> clearCart();
}

class SecureMobileCartStorage implements MobileCartStorage {
  const SecureMobileCartStorage({
    FlutterSecureStorage storage = const FlutterSecureStorage(),
  }) : _storage = storage;

  static const _cartKey = "fventas_mobile_cart_v1";

  final FlutterSecureStorage _storage;

  @override
  Future<String?> readCart() {
    return _storage.read(key: _cartKey);
  }

  @override
  Future<void> writeCart(String value) {
    return _storage.write(key: _cartKey, value: value);
  }

  @override
  Future<void> clearCart() {
    return _storage.delete(key: _cartKey);
  }
}

class MobileCartController extends ValueNotifier<List<MobileCartItem>> {
  MobileCartController({
    MobileCartStorage storage = const SecureMobileCartStorage(),
  })  : _storage = storage,
        super(const []);

  final MobileCartStorage _storage;

  int get itemCount =>
      value.fold<int>(0, (total, item) => total + item.quantity);

  Future<void> load() async {
    try {
      value = _decodeCartItems(await _storage.readCart());
    } catch (_) {
      value = const [];
    }
  }

  bool contains(String productId) {
    return value.any((item) => item.productId == productId);
  }

  void addProduct(MobileProduct product, {int quantity = 1}) {
    if (product.effectiveB2bPriceUsd <= 0) {
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
      _setItems(updated);
      return;
    }

    _setItems([
      ...value,
      MobileCartItem(
        productId: product.id,
        sku: product.sku,
        title: product.name,
        quantity: normalizedQuantity,
        unitPriceUsd: product.effectiveB2bPriceUsd,
        requiresQuote: product.requiresQuote,
        requiresTechnicalValidation: product.requiresTechnicalValidation,
        imageUrl: product.primaryImageUrl,
      ),
    ]);
  }

  void increment(String productId) {
    _setItems([
      for (final item in value)
        item.productId == productId
            ? item.copyWith(quantity: item.quantity + 1)
            : item,
    ]);
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

    _setItems(updated);
  }

  void remove(String productId) {
    _setItems(value.where((item) => item.productId != productId).toList());
  }

  void clear() {
    _setItems(const []);
  }

  void _setItems(List<MobileCartItem> items) {
    value = List.unmodifiable(items);
    unawaited(_persist());
  }

  Future<void> _persist() async {
    try {
      if (value.isEmpty) {
        await _storage.clearCart();
        return;
      }
      await _storage.writeCart(jsonEncode([
        for (final item in value) item.toJson(),
      ]));
    } catch (_) {
      // The cart remains usable in memory even if secure storage is unavailable.
    }
  }
}

List<MobileCartItem> _decodeCartItems(String? rawCart) {
  if (rawCart == null || rawCart.trim().isEmpty) {
    return const [];
  }
  final decoded = jsonDecode(rawCart);
  if (decoded is! List) {
    return const [];
  }
  return decoded
      .whereType<Map<String, dynamic>>()
      .map(MobileCartItem.fromJson)
      .where((item) =>
          item.productId.isNotEmpty &&
          item.sku.isNotEmpty &&
          item.quantity > 0 &&
          item.unitPriceUsd > 0)
      .toList();
}

final mobileCartService = MobileCartService(repository: mobileRepository);
final mobileCartController = MobileCartController();
