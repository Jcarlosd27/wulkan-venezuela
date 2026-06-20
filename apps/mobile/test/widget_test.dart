import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fventas_mobile/main.dart';
import 'package:fventas_mobile/src/auth/mobile_auth.dart';
import 'package:fventas_mobile/src/config/mobile_environment.dart';
import 'package:fventas_mobile/src/domain/mobile_models.dart';

const _clientSession = MobileUserSession(
  id: 'client-local-fventas',
  name: 'Ferreteria Alameda',
  email: 'cliente@fventas.local',
  roleLabel: 'Cliente B2B',
  isAuthenticated: true,
  accountRole: 'client',
  allowedPaymentTermsDays: [0, 15, 30],
  defaultSaleType: 'term_credit',
  assignedSeller: MobileSellerSnapshot(
    id: 'seller-local-fventas',
    name: 'Carolina Reyes',
  ),
  companyId: 'company-local-fventas',
  marketCountry: 'CL',
  salesCurrency: 'USD',
  localCurrency: 'CLP',
  exchangeRateUsdLocal: 950,
  purchaseConditions: MobilePurchaseConditions(
    currencyLabel: r'$ CLP',
    exchangeRateLabel: '950 CLP/USD',
    allowedPaymentTermsDays: [0, 15, 30],
    paymentTermsLabel: 'Contado / 15, 30 dias',
    defaultSaleTypeLabel: 'Contado',
    scopeLabel: 'Solo datos de tu empresa',
    note: 'Pedidos sujetos a validacion de stock, credito y despacho.',
  ),
);

void main() {
  testWidgets('FVENTAS app renders mobile shell', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: FVENTASLoginScreen(onAuthenticated: (_) {}),
      ),
    );
    await tester.pump(const Duration(milliseconds: 200));

    expect(find.text('FVENTAS B2B'), findsOneWidget);
    expect(find.text('Iniciar sesion'), findsOneWidget);
    expect(find.byKey(const Key('mobile-login-email')), findsOneWidget);
    expect(find.byKey(const Key('mobile-login-password')), findsOneWidget);
  });

  testWidgets(
    'client shell smoke renders all primary sections without layout overflow',
    (WidgetTester tester) async {
      await tester.binding.setSurfaceSize(const Size(375, 667));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData(
            splashFactory: NoSplash.splashFactory,
            useMaterial3: true,
          ),
          home: FVENTASShell(
            session: _clientSession,
            onSessionChanged: () async {},
            onSignOut: () async {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      expect(find.text('Ferreteria Alameda'), findsWidgets);
      await tester.scrollUntilVisible(
        find.text('Categorias'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Categorias'), findsOneWidget);
      expect(find.text('Maquinaria y jardin'), findsWidgets);
      expect(find.text('Productos destacados'), findsOneWidget);

      await tester.tap(find.text('Catalogo').last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.textContaining('productos disponibles'), findsOneWidget);

      await tester.tap(find.text('Carrito').last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(
        find.text('Agrega productos del catalogo para crear una orden'),
        findsOneWidget,
      );

      await tester.tap(find.text('Puntos').last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Puntos de entrega'), findsOneWidget);

      await tester.tap(find.text('Perfil').last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Cuenta comercial'), findsOneWidget);
    },
    skip: !mobileEnvironment.usesMock,
  );
}
