import 'package:flutter_test/flutter_test.dart';
import 'package:wulkan_mobile/src/auth/mobile_auth.dart';

void main() {
  test('MockMobileAuthRepository requires sign in before active session',
      () async {
    final repository = MockMobileAuthRepository();
    final initialSession = await repository.getCurrentSession();

    expect(initialSession.isAuthenticated, isFalse);

    final session = await repository.signIn(
      email: 'ferreteria@wulkan.local',
      password: 'clave-segura-local',
    );

    expect(session.isAuthenticated, isTrue);
    expect(session.id, 'client-ferreteria-valencia');
    expect(session.roleLabel, 'Ferretero B2B');
    expect(session.mustChangePassword, isFalse);
    expect(session.defaultSaleType, 'term_credit');
    expect(session.allowedPaymentTermsDays, contains(15));
    expect(session.assignedSeller.name, 'Vendedor Wulkan');
  });
}
