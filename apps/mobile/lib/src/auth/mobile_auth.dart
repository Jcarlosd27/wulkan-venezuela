import 'dart:convert';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';

import '../config/mobile_environment.dart';

class MobileUserSession {
  const MobileUserSession({
    required this.id,
    required this.name,
    required this.email,
    required this.roleLabel,
    required this.isAuthenticated,
    this.accessToken = "",
    this.mustChangePassword = false,
  });

  final String id;
  final String name;
  final String email;
  final String roleLabel;
  final bool isAuthenticated;
  final String accessToken;
  final bool mustChangePassword;
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

    _session = MobileUserSession(
      id: "client-ferreteria-valencia",
      name: email.trim().toLowerCase() == "ferreteria@wulkan.local"
          ? "Ferreteria Demo Valencia"
          : "Cliente Wulkan",
      email: email.trim().toLowerCase(),
      roleLabel: "Ferretero B2B",
      isAuthenticated: true,
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
  ApiMobileAuthRepository({required String baseUrl})
      : _baseUri = Uri.parse(baseUrl);

  final Uri _baseUri;
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

      _session = MobileUserSession(
        id: data["id"]?.toString() ?? "",
        name: data["businessName"]?.toString() ?? "Cliente Wulkan",
        email: data["email"]?.toString() ?? email,
        roleLabel: "Ferretero B2B",
        isAuthenticated: true,
        accessToken: token,
        mustChangePassword: data["mustChangePassword"] == true,
      );
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
        accessToken: session.accessToken,
        mustChangePassword: false,
      );
    } finally {
      client.close(force: true);
    }
  }

  @override
  Future<void> signOut() async {
    _session = null;
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
  if (mobileEnvironment.usesApiAuth) {
    return ApiMobileAuthRepository(baseUrl: mobileEnvironment.adminApiUrl);
  }

  if (mobileEnvironment.usesFirebaseAuth) {
    return FirebaseMobileAuthRepository();
  }

  return MockMobileAuthRepository();
}

final mobileAuthRepository = createMobileAuthRepository();
