import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:wulkan_mobile/main.dart';

void main() {
  testWidgets('Wulkan app renders mobile shell', (WidgetTester tester) async {
    await tester.pumpWidget(const WulkanApp());
    await tester.pumpAndSettle();

    expect(find.text('Wulkan B2B'), findsOneWidget);
    expect(find.text('Iniciar sesion'), findsOneWidget);

    await tester.enterText(
      find.byKey(const Key('mobile-login-email')),
      'ferreteria@wulkan.local',
    );
    await tester.enterText(
      find.byKey(const Key('mobile-login-password')),
      'ferretero2026',
    );
    await tester.tap(find.byKey(const Key('mobile-login-submit')));
    await tester.pumpAndSettle();

    expect(find.text('Ferreteria Demo Valencia'), findsWidgets);
    expect(find.text('Buscar maquinaria, repuestos o SKU'), findsOneWidget);

    await tester.drag(find.byType(ListView).first, const Offset(0, -420));
    await tester.pumpAndSettle();

    expect(find.text('Maquinaria lista para trabajar'), findsOneWidget);
    expect(find.text('Explorar catalogo'), findsOneWidget);
    expect(find.textContaining('Compra equipos, repuestos'), findsOneWidget);
  });
}
