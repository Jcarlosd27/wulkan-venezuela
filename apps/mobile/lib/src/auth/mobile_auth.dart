import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../config/mobile_environment.dart';
import '../domain/mobile_models.dart';

class MobilePurchaseConditions {
  const MobilePurchaseConditions({
    this.title = "Condiciones de compra",
    this.currencyLabel = "",
    this.exchangeRateLabel = "",
    this.allowedPaymentTermsDays = const [0],
    this.paymentTermsLabel = "",
    this.defaultSaleType = "cash",
    this.defaultSaleTypeLabel = "Contado",
    this.scopeLabel = "Solo datos de tu empresa",
    this.note = "",
  });

  final String title;
  final String currencyLabel;
  final String exchangeRateLabel;
  final List<int> allowedPaymentTermsDays;
  final String paymentTermsLabel;
  final String defaultSaleType;
  final String defaultSaleTypeLabel;
  final String scopeLabel;
  final String note;
}

class MobileUserSession {
  const MobileUserSession({
    required this.id,
    required this.name,
    required this.email,
    required this.roleLabel,
    required this.isAuthenticated,
    this.accountRole = "client",
    this.accessToken = "",
    this.mustChangePassword = false,
    this.allowedPaymentTermsDays = const [0],
    this.defaultSaleType = "cash",
    this.assignedSeller = const MobileSellerSnapshot(id: "", name: ""),
    this.companyId = "",
    this.marketCountry = "",
    this.salesCurrency = "",
    this.localCurrency = "",
    this.exchangeRateUsdLocal,
    this.purchaseConditions = const MobilePurchaseConditions(),
  });

  final String id;
  final String name;
  final String email;
  final String roleLabel;
  final bool isAuthenticated;
  final String accountRole;
  final String accessToken;
  final bool mustChangePassword;
  final List<int> allowedPaymentTermsDays;
  final String defaultSaleType;
  final MobileSellerSnapshot assignedSeller;
  final String companyId;
  final String marketCountry;
  final String salesCurrency;
  final String localCurrency;
  final double? exchangeRateUsdLocal;
  final MobilePurchaseConditions purchaseConditions;

  bool get isClient => accountRole == "client";
  bool get isSeller => accountRole == "sales";
  bool get isCommercialManager => accountRole == "commercial_manager";
  bool get isMobileSalesUser =>
      isSeller || isCommercialManager || accountRole == "super_admin";
  String get effectiveCountry => marketCountry.trim().isNotEmpty
      ? marketCountry.trim().toUpperCase()
      : mobileEnvironment.countryCode;
  String get effectiveDisplayCurrency =>
      mobileEnvironment.displayCurrencyForMarket(
        countryCode: effectiveCountry,
        localCurrency: localCurrency,
        primaryCurrency: salesCurrency,
      );
  String get effectivePrimaryCurrency => mobileEnvironment
      .primaryCurrencyForMarket(primaryCurrency: salesCurrency);
  double get effectiveExchangeRateUsdLocal =>
      effectiveDisplayCurrency == effectivePrimaryCurrency
          ? 1
          : mobileEnvironment.exchangeRateForMarket(exchangeRateUsdLocal);
}

const _mobileDeviceIdKey = "fventas_mobile_device_id";

Future<String> fventasMobileDeviceId({
  FlutterSecureStorage storage = const FlutterSecureStorage(),
}) async {
  final stored = await storage.read(key: _mobileDeviceIdKey);
  if (stored != null && stored.trim().isNotEmpty) {
    return stored.trim();
  }

  final random = Random.secure();
  final bytes = List<int>.generate(24, (_) => random.nextInt(256));
  final deviceId = "fventas-${base64UrlEncode(bytes).replaceAll("=", "")}";
  await storage.write(key: _mobileDeviceIdKey, value: deviceId);
  return deviceId;
}

Future<void> attachFventasMobileHeaders(
  HttpHeaders headers, {
  MobileUserSession? session,
  FlutterSecureStorage storage = const FlutterSecureStorage(),
}) async {
  headers.set(
      "X-FVENTAS-Device-Id", await fventasMobileDeviceId(storage: storage));
  final token = session?.accessToken ?? "";
  if (token.isNotEmpty) {
    headers.set("Authorization", "Bearer $token");
  }
}

abstract class MobileAuthRepository {
  Future<MobileUserSession> getCurrentSession();
  Future<MobileUserSession> signIn({
    required String email,
    required String password,
  });
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  });
  Future<void> recoverPassword({required String email});
  Future<void> requestAccountDeletion({String reason = ""});
  Future<void> signOut();
}

class MockMobileAuthRepository implements MobileAuthRepository {
  MockMobileAuthRepository({String? initialSessionRole})
      : _initialSessionRole =
            initialSessionRole ?? mobileEnvironment.mockSessionRole;

  MobileUserSession? _session;
  final String _initialSessionRole;
  bool _initialSessionConsumed = false;

  @override
  Future<MobileUserSession> getCurrentSession() async {
    final session = _session;
    if (session != null) {
      return session;
    }

    final initialRole =
        _initialSessionConsumed ? "" : _initialSessionRole.trim().toLowerCase();
    if (initialRole == "seller" ||
        initialRole == "sales" ||
        initialRole == "vendedor") {
      _initialSessionConsumed = true;
      _session = _mockSession(
        email: "vendedor@fventas.local",
        isSeller: true,
      );
      return _session!;
    }
    if (initialRole == "client" || initialRole == "cliente") {
      _initialSessionConsumed = true;
      _session = _mockSession(
        email: "cliente@fventas.local",
        isSeller: false,
      );
      return _session!;
    }

    return const MobileUserSession(
      id: "anonymous",
      name: "Invitado",
      email: "",
      roleLabel: "Sin sesion",
      isAuthenticated: false,
    );
  }

  @override
  Future<MobileUserSession> signIn({
    required String email,
    required String password,
  }) async {
    if (email.trim().isEmpty || password.isEmpty) {
      throw StateError("Ingresa correo y contrasena.");
    }

    final normalizedEmail = email.trim().toLowerCase();
    final localPart = normalizedEmail.split("@").first;
    final isSeller = localPart.contains("vendedor") ||
        localPart.contains("seller") ||
        localPart.contains("ventas");

    _session = _mockSession(
      email: normalizedEmail,
      isSeller: isSeller,
    );
    _initialSessionConsumed = true;
    return _session!;
  }

  MobileUserSession _mockSession({
    required String email,
    required bool isSeller,
  }) {
    return MobileUserSession(
      id: isSeller ? "seller-local-fventas" : "client-local-fventas",
      name: isSeller ? "Vendedor FVENTAS" : "Ferreteria Alameda",
      email: email,
      roleLabel: isSeller ? "Vendedor" : "Cliente B2B",
      isAuthenticated: true,
      accountRole: isSeller ? "sales" : "client",
      allowedPaymentTermsDays: const [0, 15, 30],
      defaultSaleType: isSeller ? "cash" : "term_credit",
      assignedSeller: MobileSellerSnapshot(
        id: "seller-local-fventas",
        name: isSeller ? "Vendedor FVENTAS" : "Carolina Reyes",
      ),
      companyId: "company-local-fventas",
      marketCountry: mobileEnvironment.countryCode,
      salesCurrency: mobileEnvironment.primaryCurrency,
      localCurrency: mobileEnvironment.localCurrency,
      exchangeRateUsdLocal: mobileEnvironment.exchangeRateUsdLocal,
      purchaseConditions: MobilePurchaseConditions(
        currencyLabel: mobileEnvironment.currencySymbolForCurrency(
                  mobileEnvironment.displayCurrency,
                ) ==
                mobileEnvironment.displayCurrency
            ? mobileEnvironment.displayCurrency
            : '${mobileEnvironment.currencySymbolForCurrency(mobileEnvironment.displayCurrency)} ${mobileEnvironment.displayCurrency}',
        exchangeRateLabel: mobileEnvironment.displaysPrimaryCurrency
            ? ""
            : mobileEnvironment.exchangeRateLabel,
        allowedPaymentTermsDays: const [0, 15, 30],
        paymentTermsLabel: "Contado / 15, 30 dias",
        defaultSaleType: isSeller ? "cash" : "term_credit",
        defaultSaleTypeLabel: isSeller ? "Contado" : "Credito por dias",
        note: "Pedidos sujetos a validacion de stock, credito y despacho.",
      ),
    );
  }

  @override
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {}

  @override
  Future<void> recoverPassword({required String email}) async {
    if (email.trim().isEmpty) {
      throw StateError("Ingresa el correo registrado.");
    }
  }

  @override
  Future<void> requestAccountDeletion({String reason = ""}) async {
    _session = null;
    _initialSessionConsumed = true;
  }

  @override
  Future<void> signOut() async {
    _session = null;
    _initialSessionConsumed = true;
  }
}

class ApiMobileAuthRepository implements MobileAuthRepository {
  ApiMobileAuthRepository({
    required String baseUrl,
    FlutterSecureStorage? storage,
  })  : _baseUri = Uri.parse(baseUrl),
        _storage = storage ?? const FlutterSecureStorage();

  static const _sessionKey = "fventas_mobile_session";
  final Uri _baseUri;
  final FlutterSecureStorage _storage;
  MobileUserSession? _session;

  Future<String> _deviceId() => fventasMobileDeviceId(storage: _storage);

  Future<void> _attachSessionHeaders(
    HttpHeaders headers,
    MobileUserSession session,
  ) {
    return attachFventasMobileHeaders(
      headers,
      session: session,
      storage: _storage,
    );
  }

  @override
  Future<MobileUserSession> getCurrentSession() async {
    if (_session != null) {
      return _session!;
    }

    final stored = await _readStoredSession();
    if (stored != null) {
      _session = stored;
      final refreshed = await _refreshStoredSession(stored);
      if (refreshed != null) {
        return refreshed;
      }
      return await getCurrentSession();
    }

    return const MobileUserSession(
      id: "anonymous",
      name: "Invitado",
      email: "",
      roleLabel: "Sin sesion",
      isAuthenticated: false,
    );
  }

  @override
  Future<MobileUserSession> signIn({
    required String email,
    required String password,
  }) async {
    final uri = _baseUri.replace(path: "${_baseUri.path}/auth/login");
    final client = HttpClient();

    try {
      final request = await client.postUrl(uri);
      request.headers.contentType = ContentType.json;
      final deviceId = await _deviceId();
      request.headers.set("X-FVENTAS-Device-Id", deviceId);
      request.write(jsonEncode({
        "email": email,
        "password": password,
        "deviceId": deviceId,
      }));
      final response = await request.close();
      final body = await response.transform(utf8.decoder).join();

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw StateError("Credenciales invalidas o cliente no habilitado.");
      }

      final payload = jsonDecode(body);
      final parsed =
          payload is Map<String, dynamic> ? payload : <String, dynamic>{};
      _session = _sessionFromAuthPayload(parsed, fallbackEmail: email);
      await _persistSession(_session!);
      return _session!;
    } finally {
      client.close(force: true);
    }
  }

  Future<MobileUserSession?> _refreshStoredSession(
    MobileUserSession stored,
  ) async {
    if (stored.accessToken.isEmpty) {
      return stored;
    }

    final uri = _baseUri.replace(path: "${_baseUri.path}/auth/refresh");
    final client = HttpClient();

    try {
      final request = await client.postUrl(uri);
      request.headers.contentType = ContentType.json;
      await _attachSessionHeaders(request.headers, stored);
      final response = await request.close();
      final body = await response.transform(utf8.decoder).join();

      if (response.statusCode == HttpStatus.unauthorized ||
          response.statusCode == HttpStatus.forbidden) {
        _session = null;
        await _storage.delete(key: _sessionKey);
        return null;
      }

      if (response.statusCode < 200 || response.statusCode >= 300) {
        return stored;
      }

      final payload = jsonDecode(body);
      final parsed =
          payload is Map<String, dynamic> ? payload : <String, dynamic>{};
      _session = _sessionFromAuthPayload(
        parsed,
        fallbackEmail: stored.email,
        fallbackToken: stored.accessToken,
      );
      await _persistSession(_session!);
      return _session;
    } catch (_) {
      return stored;
    } finally {
      client.close(force: true);
    }
  }

  MobileUserSession _sessionFromAuthPayload(
    Map<String, dynamic> payload, {
    required String fallbackEmail,
    String fallbackToken = "",
  }) {
    final customer = payload["customer"];
    final data =
        customer is Map<String, dynamic> ? customer : <String, dynamic>{};
    final token = payload["accessToken"]?.toString() ?? fallbackToken;
    final assignedSeller = data["assignedSeller"];
    final sellerData = assignedSeller is Map<String, dynamic>
        ? assignedSeller
        : <String, dynamic>{};
    final market = data["market"];
    final marketData = market is Map ? market : const {};
    final purchaseConditions = _purchaseConditionsFromPayload(
      data["purchaseConditions"],
      fallbackTerms: _asIntList(
        data["allowedPaymentTermsDays"],
        fallback: const [0],
      ),
    );
    final accountRole = data["accountRole"]?.toString() ??
        data["clientType"]?.toString() ??
        "client";
    final roleLabel = data["roleLabel"]?.toString() ??
        (accountRole == "sales" ? "Vendedor" : "Cliente B2B");

    return MobileUserSession(
      id: data["id"]?.toString() ?? "",
      name: data["businessName"]?.toString() ?? "Cliente FVENTAS",
      email: data["email"]?.toString() ?? fallbackEmail,
      roleLabel: roleLabel,
      isAuthenticated: true,
      accountRole: accountRole,
      accessToken: token,
      mustChangePassword: data["mustChangePassword"] == true,
      allowedPaymentTermsDays:
          _asIntList(data["allowedPaymentTermsDays"], fallback: const [0]),
      defaultSaleType: data["defaultSaleType"]?.toString() ?? "cash",
      assignedSeller: MobileSellerSnapshot(
        id: sellerData["id"]?.toString() ?? "",
        name: sellerData["name"]?.toString() ?? "",
      ),
      companyId: _firstNonEmpty([data["companyId"], marketData["companyId"]]),
      marketCountry: _firstNonEmpty([
        marketData["country"],
        data["marketCountry"],
        data["country"],
      ]),
      salesCurrency: _firstNonEmpty([
        marketData["salesCurrency"],
        data["salesCurrency"],
        data["baseCurrency"],
      ]),
      localCurrency: _firstNonEmpty([
        marketData["localCurrency"],
        data["localCurrency"],
        data["currency"],
      ]),
      exchangeRateUsdLocal: _firstDouble([
        marketData["exchangeRateBaseToLocal"],
        marketData["exchangeRate"],
        data["exchangeRateBaseToLocal"],
        data["exchangeRateUsdLocal"],
        data["exchangeRate"],
      ]),
      purchaseConditions: purchaseConditions,
    );
  }

  @override
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    final session = _session;
    if (session == null || session.accessToken.isEmpty) {
      throw StateError("Debes iniciar sesion para cambiar la contrasena.");
    }

    final uri = _baseUri.replace(path: "${_baseUri.path}/auth/change-password");
    final client = HttpClient();

    try {
      final request = await client.postUrl(uri);
      request.headers.contentType = ContentType.json;
      await _attachSessionHeaders(request.headers, session);
      request.write(jsonEncode({
        "currentPassword": currentPassword,
        "newPassword": newPassword,
      }));
      final response = await request.close();
      final body = await response.transform(utf8.decoder).join();

      if (response.statusCode < 200 || response.statusCode >= 300) {
        final payload = body.isNotEmpty ? jsonDecode(body) : null;
        final message = payload is Map<String, dynamic>
            ? payload["error"]?.toString()
            : null;
        throw StateError(message ?? "No se pudo cambiar la contrasena.");
      }
      final payload = body.isNotEmpty ? jsonDecode(body) : null;
      final newAccessToken = payload is Map<String, dynamic>
          ? _firstNonEmpty([payload["accessToken"], session.accessToken])
          : session.accessToken;

      _session = MobileUserSession(
        id: session.id,
        name: session.name,
        email: session.email,
        roleLabel: session.roleLabel,
        isAuthenticated: session.isAuthenticated,
        accountRole: session.accountRole,
        accessToken: newAccessToken,
        mustChangePassword: false,
        allowedPaymentTermsDays: session.allowedPaymentTermsDays,
        defaultSaleType: session.defaultSaleType,
        assignedSeller: session.assignedSeller,
        companyId: session.companyId,
        marketCountry: session.marketCountry,
        salesCurrency: session.salesCurrency,
        localCurrency: session.localCurrency,
        exchangeRateUsdLocal: session.exchangeRateUsdLocal,
        purchaseConditions: session.purchaseConditions,
      );
      await _persistSession(_session!);
    } finally {
      client.close(force: true);
    }
  }

  @override
  Future<void> recoverPassword({required String email}) async {
    final uri =
        _baseUri.replace(path: "${_baseUri.path}/auth/recover-password");
    final client = HttpClient();

    try {
      final request = await client.postUrl(uri);
      request.headers.contentType = ContentType.json;
      request.write(jsonEncode({"email": email}));
      final response = await request.close();
      final body = await response.transform(utf8.decoder).join();

      if (response.statusCode < 200 || response.statusCode >= 300) {
        final payload = body.isNotEmpty ? jsonDecode(body) : null;
        final message = payload is Map<String, dynamic>
            ? payload["error"]?.toString()
            : null;
        throw StateError(message ?? "No se pudo solicitar recuperacion.");
      }
    } finally {
      client.close(force: true);
    }
  }

  @override
  Future<void> requestAccountDeletion({String reason = ""}) async {
    final session = _session ?? await _readStoredSession();
    if (session == null || session.accessToken.isEmpty) {
      throw StateError("Debes iniciar sesion para solicitar la eliminacion.");
    }

    final uri = _baseUri.replace(
      path: "${_baseUri.path}/account/deletion-request",
    );
    final client = HttpClient();

    try {
      final request = await client.postUrl(uri);
      request.headers.contentType = ContentType.json;
      await _attachSessionHeaders(request.headers, session);
      request.write(jsonEncode({"reason": reason}));
      final response = await request.close();
      final body = await response.transform(utf8.decoder).join();

      if (response.statusCode < 200 || response.statusCode >= 300) {
        final payload = body.isNotEmpty ? jsonDecode(body) : null;
        final message = payload is Map<String, dynamic>
            ? payload["error"]?.toString()
            : null;
        throw StateError(message ?? "No se pudo registrar la solicitud.");
      }

      _session = null;
      await _storage.delete(key: _sessionKey);
    } finally {
      client.close(force: true);
    }
  }

  @override
  Future<void> signOut() async {
    final session = _session ?? await _readStoredSession();

    if (session != null && session.accessToken.isNotEmpty) {
      final uri = _baseUri.replace(path: "${_baseUri.path}/auth/logout");
      final client = HttpClient();

      try {
        final request = await client.postUrl(uri);
        request.headers.contentType = ContentType.json;
        await _attachSessionHeaders(request.headers, session);
        final response = await request.close();
        await response.drain<void>();
      } catch (_) {
        // Local session cleanup must succeed even if the token was already
        // expired or the backend rejected the logout call.
      } finally {
        client.close(force: true);
      }
    }

    _session = null;
    await _storage.delete(key: _sessionKey);
  }

  Future<void> _persistSession(MobileUserSession session) {
    return _storage.write(
      key: _sessionKey,
      value: jsonEncode({
        "id": session.id,
        "name": session.name,
        "email": session.email,
        "roleLabel": session.roleLabel,
        "accountRole": session.accountRole,
        "accessToken": session.accessToken,
        "mustChangePassword": session.mustChangePassword,
        "allowedPaymentTermsDays": session.allowedPaymentTermsDays,
        "defaultSaleType": session.defaultSaleType,
        "assignedSeller": {
          "id": session.assignedSeller.id,
          "name": session.assignedSeller.name,
        },
        "companyId": session.companyId,
        "marketCountry": session.marketCountry,
        "salesCurrency": session.salesCurrency,
        "localCurrency": session.localCurrency,
        "exchangeRateUsdLocal": session.exchangeRateUsdLocal,
        "purchaseConditions": {
          "title": session.purchaseConditions.title,
          "currencyLabel": session.purchaseConditions.currencyLabel,
          "exchangeRateLabel": session.purchaseConditions.exchangeRateLabel,
          "allowedPaymentTermsDays":
              session.purchaseConditions.allowedPaymentTermsDays,
          "paymentTermsLabel": session.purchaseConditions.paymentTermsLabel,
          "defaultSaleType": session.purchaseConditions.defaultSaleType,
          "defaultSaleTypeLabel":
              session.purchaseConditions.defaultSaleTypeLabel,
          "scopeLabel": session.purchaseConditions.scopeLabel,
          "note": session.purchaseConditions.note,
        },
      }),
    );
  }

  Future<MobileUserSession?> _readStoredSession() async {
    final raw = await _storage.read(key: _sessionKey);
    if (raw == null || raw.isEmpty) {
      return null;
    }

    try {
      final payload = jsonDecode(raw);
      if (payload is! Map<String, dynamic>) {
        return null;
      }

      final token = payload["accessToken"]?.toString() ?? "";
      final id = payload["id"]?.toString() ?? "";
      if (token.isEmpty || id.isEmpty) {
        return null;
      }
      final assignedSeller = payload["assignedSeller"];
      final sellerData = assignedSeller is Map<String, dynamic>
          ? assignedSeller
          : <String, dynamic>{};

      return MobileUserSession(
        id: id,
        name: payload["name"]?.toString() ?? "Cliente FVENTAS",
        email: payload["email"]?.toString() ?? "",
        roleLabel: payload["roleLabel"]?.toString() ?? "Cliente B2B",
        isAuthenticated: true,
        accountRole: payload["accountRole"]?.toString() ?? "client",
        accessToken: token,
        mustChangePassword: payload["mustChangePassword"] == true,
        allowedPaymentTermsDays: _asIntList(
          payload["allowedPaymentTermsDays"],
          fallback: const [0],
        ),
        defaultSaleType: payload["defaultSaleType"]?.toString() ?? "cash",
        assignedSeller: MobileSellerSnapshot(
          id: sellerData["id"]?.toString() ?? "",
          name: sellerData["name"]?.toString() ?? "",
        ),
        companyId: payload["companyId"]?.toString() ?? "",
        marketCountry: payload["marketCountry"]?.toString() ?? "",
        salesCurrency: payload["salesCurrency"]?.toString() ?? "",
        localCurrency: payload["localCurrency"]?.toString() ?? "",
        exchangeRateUsdLocal: _asDoubleOrNull(
          payload["exchangeRateUsdLocal"],
        ),
        purchaseConditions: _purchaseConditionsFromPayload(
          payload["purchaseConditions"],
          fallbackTerms: _asIntList(
            payload["allowedPaymentTermsDays"],
            fallback: const [0],
          ),
        ),
      );
    } catch (_) {
      await _storage.delete(key: _sessionKey);
      return null;
    }
  }
}

MobileAuthRepository createMobileAuthRepository() {
  mobileEnvironment.validateRuntime();

  if (mobileEnvironment.usesApiAuth) {
    return ApiMobileAuthRepository(baseUrl: mobileEnvironment.adminApiUrl);
  }

  return MockMobileAuthRepository();
}

final mobileAuthRepository = createMobileAuthRepository();

List<int> _asIntList(Object? value, {required List<int> fallback}) {
  if (value is List) {
    final items = value
        .map((item) => int.tryParse(item.toString()))
        .whereType<int>()
        .toSet()
        .toList()
      ..sort();

    return items.isEmpty ? fallback : items;
  }

  return fallback;
}

MobilePurchaseConditions _purchaseConditionsFromPayload(
  Object? value, {
  required List<int> fallbackTerms,
}) {
  final data = value is Map ? value : const {};
  final terms = _asIntList(
    data["allowedPaymentTermsDays"],
    fallback: fallbackTerms,
  );
  return MobilePurchaseConditions(
    title: _firstNonEmpty([data["title"], "Condiciones de compra"]),
    currencyLabel: _firstNonEmpty([data["currencyLabel"]]),
    exchangeRateLabel: _firstNonEmpty([data["exchangeRateLabel"]]),
    allowedPaymentTermsDays: terms,
    paymentTermsLabel: _firstNonEmpty([data["paymentTermsLabel"]]),
    defaultSaleType: _firstNonEmpty([data["defaultSaleType"], "cash"]),
    defaultSaleTypeLabel: _firstNonEmpty([
      data["defaultSaleTypeLabel"],
      "Contado",
    ]),
    scopeLabel: _firstNonEmpty([
      data["scopeLabel"],
      "Solo datos de tu empresa",
    ]),
    note: _firstNonEmpty([data["note"]]),
  );
}

String _firstNonEmpty(Iterable<Object?> values) {
  for (final value in values) {
    final text = value?.toString().trim() ?? "";
    if (text.isNotEmpty) {
      return text;
    }
  }
  return "";
}

double? _firstDouble(Iterable<Object?> values) {
  for (final value in values) {
    final parsed = _asDoubleOrNull(value);
    if (parsed != null) {
      return parsed;
    }
  }
  return null;
}

double? _asDoubleOrNull(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is num) {
    return value.toDouble();
  }
  return double.tryParse(value.toString());
}
