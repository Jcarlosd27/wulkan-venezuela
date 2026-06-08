import 'package:flutter_test/flutter_test.dart';

import 'package:wulkan_mobile/main.dart';

void main() {
  testWidgets('Wulkan app renders mobile shell', (WidgetTester tester) async {
    await tester.pumpWidget(const WulkanApp());
    await tester.pumpAndSettle();

    expect(find.text('Maquinaria lista para trabajar'), findsOneWidget);
    expect(find.text('Explorar catalogo'), findsOneWidget);
    expect(find.textContaining('Compra equipos, repuestos'), findsOneWidget);
  });
}
