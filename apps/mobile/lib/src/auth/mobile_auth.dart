import 'dart:convert';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../config/mobile_environment.dart';
import '../domain/mobile_models.dart';

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

  bool get isClient => accountRole == "client";
  bool get isSeller => accountRole == "sales";
  bool get isCommercialManager => accountRole == "commercial_manager";
  bool get isMobileSalesUser => isSeller || isCommercialManager || accountRole == "super_admin";
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
  Future<void> signOut();
}

class MockMobileAuthRepository implements MobileAuthRepository {
  MobileUserSession? _session;

  @override
  Future<MobileUserSession> getCurrentSession() async {
    return _session ??
        const MobileUserSession(
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
    final isSeller = normalizedEmail.contains("vendedor") ||
        normalizedEmail.contains("seller") ||
        normalizedEmail.contains("ventas");

    _session = MobileUserSession(
      id: isSeller ? "admin-seller-demo" : "client-ferreteria-valencia",
      name: isSeller
          ? "Vendedor Wulkan"
          : (normalizedEmail == "ferreteria@wulkan.local"
              ? "Ferreteria Demo Valencia"
              : "Cliente Wulkan"),
      email: normalizedEmail,
      roleLabel: isSeller ? "Vendedor" : "Ferretero B2B",
      isAuthenticated: true,
      accountRole: isSeller ? "sales" : "client",
      allowedPaymentTermsDays: const [0, 15, 30],
      defaultSaleType: isSeller ? "cash" : "term_credit",
      assignedSeller: const MobileSellerSnapshot(
        id: "seller-demo",
        name: "Vendedor Wulkan",
      ),
    );
    return _session!;
  }

  @override
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {}

  @override
  Future<void> signOut() async {
    _session = null;
  }
}

class ApiMobileAuthRepository implements MobileAuthRepository {
  ApiMobileAuthRepository({
    required String baseUrl,
    FlutterSecureStorage? storage,
  })  : _baseUri = Uri.parse(baseUrl),
        _storage = storage ?? const FlutterSecureStorage();

  static const _sessionKey = "wulkan_mobile_session";
  final Uri _baseUri;
  final FlutterSecureStorage _storage;
  MobileUserSession? _session;

  @override
  Future<MobileUserSession> getCurrentSession() async {
    if (_session != null) {
      return _session!;
    }

    final stored = await _readStoredSession();
    if (stored != null) {
      _session = stored;
      return stored;
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
      request.write(jsonEncode({"email": email, "password": password}));
      final response = await request.close();
      final body = await response.transform(utf8.decoder).join();

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw StateError("Credenciales invalidas o cliente no habilitado.");
      }

      final payload = jsonDecode(body);
      final customer =
          payload is Map<String, dynamic> ? payload["customer"] : null;
      final data =
          customer is Map<String, dynamic> ? customer : <String, dynamic>{};
      final token = payload is Map<String, dynamic>
          ? payload["accessToken"]?.toString() ?? ""
          : "";
      final assignedSeller = data["assignedSeller"];
      final sellerData = assignedSeller is Map<String, dynamic>
          ? assignedSeller
          : <String, dynamic>{};
      final accountRole = data["accountRole"]?.toString() ??
          data["clientType"]?.toString() ??
          "client";
      final roleLabel = data["roleLabel"]?.toString() ??
          (accountRole == "sales" ? "Vendedor" : "Ferretero B2B");

      _session = MobileUserSession(
        id: data["id"]?.toString() ?? "",
        name: data["businessName"]?.toString() ?? "Cliente Wulkan",
        email: data["email"]?.toString() ?? email,
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
      );
      await _persistSession(_session!);
      return _session!;
    } finally {
      client.close(force: true);
    }
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
      request.headers.set("Authorization", "Bearer ${session.accessToken}");
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

      _session = MobileUserSession(
        id: session.id,
        name: session.name,
        email: session.email,
        roleLabel: session.roleLabel,
        isAuthenticated: session.isAuthenticated,
        accountRole: session.accountRole,
        accessToken: session.accessToken,
        mustChangePassword: false,
        allowedPaymentTermsDays: session.allowedPaymentTermsDays,
        defaultSaleType: session.defaultSaleType,
        assignedSeller: session.assignedSeller,
      );
      await _persistSession(_session!);
    } finally {
      client.close(force: true);
    }
  }

  @override
  Future<void> signOut() async {
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
        name: payload["name"]?.toString() ?? "Cliente Wulkan",
        email: payload["email"]?.toString() ?? "",
        roleLabel: payload["roleLabel"]?.toString() ?? "Ferretero B2B",
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
      );
    } catch (_) {
      await _storage.delete(key: _sessionKey);
      return null;
    }
  }
}

class FirebaseMobileAuthRepository implements MobileAuthRepository {
  FirebaseMobileAuthRepository({FirebaseAuth? firebaseAuth})
      : _firebaseAuth = firebaseAuth ?? FirebaseAuth.instance;

  final FirebaseAuth _firebaseAuth;

  @override
  Future<MobileUserSession> getCurrentSession() async {
    final user = _firebaseAuth.currentUser;

    if (user == null) {
      return const MobileUserSession(
        id: "anonymous",
        name: "Invitado",
        email: "",
        roleLabel: "Sin sesion",
        isAuthenticated: false,
      );
    }

    final token = await user.getIdTokenResult();
    final role = token.claims?["role"]?.toString();

    return MobileUserSession(
      id: user.uid,
      name: user.displayName ?? user.email ?? "Usuario Wulkan",
      email: user.email ?? "",
      roleLabel: role ?? "Usuario autenticado",
      isAuthenticated: true,
      accountRole: role ?? "client",
    );
  }

  @override
  Future<MobileUserSession> signIn({
    required String email,
    required String password,
  }) async {
    await _firebaseAuth.signInWithEmailAndPassword(
      email: email,
      password: password,
    );
    return getCurrentSession();
  }

  @override
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) {
    throw UnsupportedError("Cambio de contrasena disponible en modo API.");
  }

  @override
  Future<void> signOut() async {
    await _firebaseAuth.signOut();
  }
}

MobileAuthRepository createMobileAuthRepository() {
  mobileEnvironment.validateRuntime();

  if (mobileEnvironment.usesApiAuth) {
    return ApiMobileAuthRepository(baseUrl: mobileEnvironment.adminApiUrl);
  }

  if (mobileEnvironment.usesFirebaseAuth) {
    return FirebaseMobileAuthRepository();
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
