import 'package:flutter_test/flutter_test.dart';
import 'package:wulkan_mobile/src/auth/mobile_auth.dart';

void main() {
  test('MockMobileAuthRepository returns active customer session', () async {
    final repository = MockMobileAuthRepository();
    final session = await repository.getCurrentSession();

    expect(session.isAuthenticated, isTrue);
    expect(session.id, 'client-ferreteria-valencia');
    expect(session.roleLabel, 'Ferretero B2B');
  });
}
