import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:wulkan_mobile/main.dart';

void main() {
  testWidgets('Wulkan app renders mobile shell', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: WulkanLoginScreen(onAuthenticated: (_) {}),
      ),
    );
    await tester.pump(const Duration(milliseconds: 200));

    expect(find.text('Wulkan B2B'), findsOneWidget);
    expect(find.text('Iniciar sesion'), findsOneWidget);
    expect(find.byKey(const Key('mobile-login-email')), findsOneWidget);
    expect(find.byKey(const Key('mobile-login-password')), findsOneWidget);
  });
}
