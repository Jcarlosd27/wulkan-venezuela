import 'dart:convert';
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fventas_mobile/src/auth/mobile_auth.dart';

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  test('MockMobileAuthRepository requires sign in before active session',
      () async {
    final repository = MockMobileAuthRepository();
    final initialSession = await repository.getCurrentSession();

    expect(initialSession.isAuthenticated, isFalse);

    final session = await repository.signIn(
      email: 'cliente@fventas.local',
      password: 'clave-segura-local',
    );

    expect(session.isAuthenticated, isTrue);
    expect(session.id, 'client-local-fventas');
    expect(session.roleLabel, 'Cliente B2B');
    expect(session.mustChangePassword, isFalse);
    expect(session.defaultSaleType, 'term_credit');
    expect(session.allowedPaymentTermsDays, contains(15));
    expect(
        session.purchaseConditions.paymentTermsLabel, 'Contado / 15, 30 dias');
    expect(session.purchaseConditions.scopeLabel, 'Solo datos de tu empresa');
    expect(session.name, 'Ferreteria Alameda');
    expect(session.assignedSeller.name, 'Carolina Reyes');
    expect(session.marketCountry, 'CL');
    expect(session.effectiveDisplayCurrency, 'CLP');

    await repository.recoverPassword(email: 'cliente@fventas.local');
    expect(
      repository.recoverPassword(email: ''),
      throwsA(isA<StateError>()),
    );
  });

  test('MockMobileAuthRepository can start as seller for demo flows', () async {
    final repository = MockMobileAuthRepository(initialSessionRole: 'seller');
    final session = await repository.getCurrentSession();

    expect(session.isAuthenticated, isTrue);
    expect(session.id, 'seller-local-fventas');
    expect(session.roleLabel, 'Vendedor');
    expect(session.isMobileSalesUser, isTrue);
  });

  test('MockMobileAuthRepository keeps logout after demo seller session',
      () async {
    final repository = MockMobileAuthRepository(initialSessionRole: 'seller');

    expect((await repository.getCurrentSession()).isMobileSalesUser, isTrue);

    await repository.signOut();
    final signedOutSession = await repository.getCurrentSession();

    expect(signedOutSession.isAuthenticated, isFalse);
    expect(signedOutSession.id, 'anonymous');

    final clientSession = await repository.signIn(
      email: 'cliente@fventas.local',
      password: 'clave-segura-local',
    );

    expect(clientSession.isClient, isTrue);
    expect(clientSession.id, 'client-local-fventas');
  });

  test('MobileUserSession uses subscription market currency', () {
    const session = MobileUserSession(
      id: 'client-ve',
      name: 'Cliente Venezuela',
      email: 'cliente@venezuela.test',
      roleLabel: 'Cliente B2B',
      isAuthenticated: true,
      companyId: 'company-ve',
      marketCountry: 'VE',
      salesCurrency: 'USD',
      localCurrency: 'USD',
      exchangeRateUsdLocal: 950,
    );

    expect(session.effectiveCountry, 'VE');
    expect(session.effectiveDisplayCurrency, 'USD');
    expect(session.effectiveExchangeRateUsdLocal, 1);
    expect(session.purchaseConditions.title, 'Condiciones de compra');
  });

  test('ApiMobileAuthRepository stores refreshed token after password change',
      () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final requests = <String>[];
    server.listen((request) async {
      requests.add(request.uri.path);
      await request.drain<void>();
      request.response.headers.contentType = ContentType.json;

      if (request.uri.path.endsWith('/auth/login')) {
        request.response.write(jsonEncode({
          'accessToken': 'token-old',
          'tokenType': 'Bearer',
          'customer': {
            'id': 'client-api',
            'businessName': 'Cliente API',
            'email': 'cliente@fventas.test',
            'accountRole': 'client',
            'roleLabel': 'Cliente B2B',
            'companyId': 'company-api',
            'market': {
              'companyId': 'company-api',
              'country': 'CL',
              'salesCurrency': 'USD',
              'localCurrency': 'CLP',
              'exchangeRateBaseToLocal': 950,
            },
            'allowedPaymentTermsDays': [0],
            'defaultSaleType': 'cash',
          },
        }));
      } else if (request.uri.path.endsWith('/auth/change-password')) {
        expect(request.headers.value(HttpHeaders.authorizationHeader),
            'Bearer token-old');
        request.response.write(jsonEncode({
          'status': 'updated',
          'mustChangePassword': false,
          'accessToken': 'token-new',
          'tokenType': 'Bearer',
        }));
      } else {
        request.response.statusCode = HttpStatus.notFound;
        request.response.write(jsonEncode({'error': 'not found'}));
      }

      await request.response.close();
    });

    try {
      final repository = ApiMobileAuthRepository(
        baseUrl: 'http://127.0.0.1:${server.port}/api/v1/mobile',
      );

      final session = await repository.signIn(
        email: 'cliente@fventas.test',
        password: 'ClaveActual2026',
      );
      expect(session.accessToken, 'token-old');

      await repository.changePassword(
        currentPassword: 'ClaveActual2026',
        newPassword: 'ClaveNueva2026',
      );

      final updated = await repository.getCurrentSession();
      expect(updated.accessToken, 'token-new');
      expect(requests, contains('/api/v1/mobile/auth/change-password'));
    } finally {
      await server.close(force: true);
    }
  });
}
