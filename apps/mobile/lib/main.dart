import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'src/auth/mobile_auth.dart';
import 'src/brand/fventas_logo.dart';
import 'src/bootstrap/mobile_bootstrap.dart';
import 'src/cart/mobile_cart_service.dart';
import 'src/config/mobile_environment.dart';
import 'src/data/mobile_repository.dart';
import 'src/domain/country_locations.dart';
import 'src/domain/mobile_models.dart';
import 'src/domain/chile_locations.dart';
import 'src/orders/mobile_order_service.dart';

const _fventasBlue = Color(0xFF0D6EFD);
const _fventasBlack = Color(0xFF0B1220);
const _fventasInk = Color(0xFF1F2937);
const _fventasMuted = Color(0xFF667085);
const _fventasCanvas = Color(0xFFF4F7FB);
const _fventasSurface = Color(0xFFFFFFFF);
const _fventasLine = Color(0xFFE6EEF8);

String _newOperationId(String prefix) =>
    '$prefix-${DateTime.now().microsecondsSinceEpoch}';

MobileUserSession? _activeMoneySession;

String _displayCurrency() {
  final session = _activeMoneySession;
  if (session == null) {
    return mobileEnvironment.displayCurrency;
  }
  return session.effectiveDisplayCurrency;
}

String _displayCurrencySymbol() {
  final session = _activeMoneySession;
  if (session == null) {
    return mobileEnvironment.currencySymbolForCurrency(
      mobileEnvironment.displayCurrency,
    );
  }
  return mobileEnvironment.currencySymbolForMarket(
    countryCode: session.effectiveCountry,
    localCurrency: session.localCurrency,
    primaryCurrency: session.salesCurrency,
  );
}

String _displayCurrencyLabel() {
  final currency = _displayCurrency();
  final symbol = _displayCurrencySymbol();
  return symbol.trim() == currency ? currency : '$symbol $currency';
}

String _marketCountryCode() {
  return _activeMoneySession?.effectiveCountry ?? mobileEnvironment.countryCode;
}

bool _usesChileFormat() => _marketCountryCode() == "CL";

String _taxLabel() => mobileEnvironment.taxLabelForMarket(
      countryCode: _marketCountryCode(),
    );

String _taxPlaceholder() => mobileEnvironment.taxPlaceholderForMarket(
      countryCode: _marketCountryCode(),
    );

String _phonePlaceholder() => mobileEnvironment.phonePlaceholderForMarket(
      countryCode: _marketCountryCode(),
    );

bool _displaysPrimaryCurrency() {
  final session = _activeMoneySession;
  if (session == null) {
    return mobileEnvironment.displaysPrimaryCurrency;
  }
  return mobileEnvironment.displaysPrimaryCurrencyForMarket(
    countryCode: session.effectiveCountry,
    localCurrency: session.localCurrency,
    primaryCurrency: session.salesCurrency,
  );
}

double _exchangeRateUsdLocal() {
  return _activeMoneySession?.effectiveExchangeRateUsdLocal ??
      mobileEnvironment.exchangeRateUsdLocal;
}

String _exchangeRateLabel() {
  final session = _activeMoneySession;
  if (session == null) {
    return mobileEnvironment.exchangeRateLabel;
  }
  return mobileEnvironment.exchangeRateLabelForMarket(
    countryCode: session.effectiveCountry,
    localCurrency: session.localCurrency,
    primaryCurrency: session.salesCurrency,
  );
}

String _exchangeRateValueLabel() {
  final value = _exchangeRateUsdLocal();
  return value == value.roundToDouble()
      ? value.toStringAsFixed(0)
      : value.toStringAsFixed(2);
}

String _moneyFromUsd(double amount, {int? fractionDigits}) {
  final session = _activeMoneySession;
  if (session == null) {
    return mobileEnvironment.moneyFromUsd(
      amount,
      fractionDigits: fractionDigits,
    );
  }
  return mobileEnvironment.moneyFromUsdForMarket(
    amount,
    countryCode: session.effectiveCountry,
    localCurrency: session.localCurrency,
    primaryCurrency: session.salesCurrency,
    exchangeRateUsdLocal: session.exchangeRateUsdLocal,
    fractionDigits: fractionDigits,
  );
}

String _parseableAmountText(String raw) {
  final compact = raw.trim().replaceAll(RegExp(r'\s+'), '');
  if (_displayCurrency() != "USD") {
    return compact.replaceAll('.', '').replaceAll(',', '.');
  }
  return compact.replaceAll(',', '');
}

double _visibleMoneyInputToUsd(String raw) {
  final visibleAmount = double.tryParse(_parseableAmountText(raw)) ?? 0;
  final session = _activeMoneySession;
  if (session == null) {
    return mobileEnvironment.visibleAmountToUsd(visibleAmount);
  }
  return mobileEnvironment.visibleAmountToUsdForMarket(
    visibleAmount,
    countryCode: session.effectiveCountry,
    localCurrency: session.localCurrency,
    primaryCurrency: session.salesCurrency,
    exchangeRateUsdLocal: session.exchangeRateUsdLocal,
  );
}

class _ChileanPhoneInputFormatter extends TextInputFormatter {
  const _ChileanPhoneInputFormatter();

  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    var digits = newValue.text.replaceAll(RegExp(r'\D+'), '');
    if (digits.startsWith('0056')) {
      digits = digits.substring(4);
    } else if (digits.startsWith('56')) {
      digits = digits.substring(2);
    }
    if (digits.startsWith('0')) {
      digits = digits.substring(1);
    }
    if (digits.length == 8) {
      digits = '9$digits';
    }
    if (digits.length > 9) {
      digits = digits.substring(0, 9);
    }

    final formatted = switch (digits.length) {
      0 => '',
      1 => '+56 $digits',
      <= 5 => '+56 ${digits.substring(0, 1)} ${digits.substring(1)}',
      _ =>
        '+56 ${digits.substring(0, 1)} ${digits.substring(1, 5)} ${digits.substring(5)}',
    };
    return TextEditingValue(
      text: formatted,
      selection: TextSelection.collapsed(offset: formatted.length),
    );
  }
}

class _ChileanTaxIdInputFormatter extends TextInputFormatter {
  const _ChileanTaxIdInputFormatter();

  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    var compact =
        newValue.text.toUpperCase().replaceAll(RegExp(r'[^0-9K]+'), '');
    if (compact.isEmpty) {
      return const TextEditingValue();
    }
    if (compact.length > 9) {
      compact = compact.substring(0, 9);
    }

    final body =
        compact.length > 1 ? compact.substring(0, compact.length - 1) : compact;
    final verifier =
        compact.length > 1 ? compact.substring(compact.length - 1) : '';
    final chunks = <String>[];
    var remaining = body;
    while (remaining.length > 3) {
      chunks.insert(0, remaining.substring(remaining.length - 3));
      remaining = remaining.substring(0, remaining.length - 3);
    }
    if (remaining.isNotEmpty) {
      chunks.insert(0, remaining);
    }
    final formatted =
        verifier.isEmpty ? chunks.join('.') : '${chunks.join('.')}-$verifier';

    return TextEditingValue(
      text: formatted,
      selection: TextSelection.collapsed(offset: formatted.length),
    );
  }
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  mobileEnvironment.validateRuntime();
  await countryLocations.load();
  await configureMobileRuntime();
  await mobileCartController.load();
  runApp(const FVENTASApp());
}

class FVENTASApp extends StatelessWidget {
  const FVENTASApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'FVENTAS',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: _fventasBlue,
          primary: _fventasBlue,
          secondary: _fventasBlack,
          error: const Color(0xFFC83232),
          surface: _fventasSurface,
          onSurface: _fventasInk,
        ),
        scaffoldBackgroundColor: _fventasCanvas,
        appBarTheme: const AppBarTheme(
          backgroundColor: _fventasCanvas,
          foregroundColor: _fventasBlack,
          elevation: 0,
          scrolledUnderElevation: 0,
          centerTitle: false,
        ),
        cardTheme: CardThemeData(
          color: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(18),
            side: const BorderSide(color: _fventasLine),
          ),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            backgroundColor: _fventasBlue,
            foregroundColor: Colors.white,
            minimumSize: const Size(48, 48),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
            ),
          ),
        ),
        navigationBarTheme: NavigationBarThemeData(
          backgroundColor: Colors.white,
          indicatorColor: _fventasBlue.withValues(alpha: 0.12),
          labelTextStyle: WidgetStateProperty.resolveWith(
            (states) => TextStyle(
              color: states.contains(WidgetState.selected)
                  ? _fventasBlue
                  : _fventasMuted,
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
        useMaterial3: true,
      ),
      home: const FVENTASSessionGate(),
    );
  }
}

class FVENTASSessionGate extends StatefulWidget {
  const FVENTASSessionGate({super.key});

  @override
  State<FVENTASSessionGate> createState() => _FVENTASSessionGateState();
}

class _FVENTASSessionGateState extends State<FVENTASSessionGate> {
  late Future<MobileUserSession> _sessionFuture;

  @override
  void initState() {
    super.initState();
    _sessionFuture = mobileAuthRepository.getCurrentSession();
  }

  void _setSession(MobileUserSession session) {
    setState(() {
      _activeMoneySession = session;
      _sessionFuture = Future.value(session);
    });
  }

  Future<void> _refreshSession() async {
    setState(() {
      _sessionFuture = mobileAuthRepository.getCurrentSession();
    });
  }

  Future<void> _signOut() async {
    await mobileAuthRepository.signOut();
    if (!mounted) {
      return;
    }
    setState(() {
      _activeMoneySession = null;
      _sessionFuture = mobileAuthRepository.getCurrentSession();
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<MobileUserSession>(
      future: _sessionFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Scaffold(body: _LoadingState());
        }

        final session = snapshot.data;
        if (session == null || !session.isAuthenticated) {
          _activeMoneySession = null;
          return FVENTASLoginScreen(onAuthenticated: _setSession);
        }

        _activeMoneySession = session;
        return FVENTASShell(
          session: session,
          onSessionChanged: _refreshSession,
          onSignOut: _signOut,
        );
      },
    );
  }
}

class FVENTASLoginScreen extends StatefulWidget {
  const FVENTASLoginScreen({super.key, required this.onAuthenticated});

  final ValueChanged<MobileUserSession> onAuthenticated;

  @override
  State<FVENTASLoginScreen> createState() => _FVENTASLoginScreenState();
}

class _FVENTASLoginScreenState extends State<FVENTASLoginScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isSigningIn = false;
  bool _isRecovering = false;
  bool _showPassword = false;
  String _errorMessage = "";

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _signIn() async {
    if (_isSigningIn) {
      return;
    }

    setState(() {
      _isSigningIn = true;
      _errorMessage = "";
    });

    try {
      final session = await mobileAuthRepository.signIn(
        email: _emailController.text.trim(),
        password: _passwordController.text,
      );
      if (!mounted) {
        return;
      }
      widget.onAuthenticated(session);
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isSigningIn = false;
        _errorMessage = error.toString().replaceFirst("Bad state: ", "");
      });
    }
  }

  Future<void> _recoverPassword() async {
    if (_isRecovering) {
      return;
    }

    setState(() {
      _isRecovering = true;
      _errorMessage = "";
    });

    try {
      await mobileAuthRepository.recoverPassword(
        email: _emailController.text.trim(),
      );
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content:
              Text('Solicitud recibida. FVENTAS validara tu acceso movil.'),
        ),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _errorMessage = error.toString().replaceFirst("Bad state: ", "");
      });
    } finally {
      if (mounted) {
        setState(() {
          _isRecovering = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(22, 24, 22, 24),
          children: [
            const SizedBox(height: 12),
            Center(
              child: Container(
                width: 92,
                height: 92,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(26),
                  boxShadow: [
                    BoxShadow(
                      color: _fventasBlue.withValues(alpha: 0.22),
                      blurRadius: 26,
                      offset: const Offset(0, 14),
                    ),
                  ],
                ),
                child: const Center(
                  child: FVENTASLogo(compact: true, size: 92),
                ),
              ),
            ),
            const SizedBox(height: 22),
            Text(
              'FVENTAS B2B',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w900,
                    color: _fventasBlack,
                  ),
            ),
            const SizedBox(height: 6),
            const Text(
              'Acceso para clientes B2B autorizados',
              textAlign: TextAlign.center,
              style:
                  TextStyle(color: _fventasMuted, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 24),
            _LoginAccessCard(
              emailController: _emailController,
              passwordController: _passwordController,
              errorMessage: _errorMessage,
              isSigningIn: _isSigningIn,
              isRecovering: _isRecovering,
              showPassword: _showPassword,
              onTogglePassword: () {
                setState(() {
                  _showPassword = !_showPassword;
                });
              },
              onSubmit: _signIn,
              onRecoverPassword: _recoverPassword,
            ),
            const SizedBox(height: 18),
            const _LoginTrustGrid(),
          ],
        ),
      ),
    );
  }
}

class _LoginAccessCard extends StatelessWidget {
  const _LoginAccessCard({
    required this.emailController,
    required this.passwordController,
    required this.errorMessage,
    required this.isSigningIn,
    required this.isRecovering,
    required this.showPassword,
    required this.onTogglePassword,
    required this.onSubmit,
    required this.onRecoverPassword,
  });

  final TextEditingController emailController;
  final TextEditingController passwordController;
  final String errorMessage;
  final bool isSigningIn;
  final bool isRecovering;
  final bool showPassword;
  final VoidCallback onTogglePassword;
  final VoidCallback onSubmit;
  final VoidCallback onRecoverPassword;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const _SoftIcon(
                  icon: Icons.lock_person_outlined,
                  color: _fventasBlue,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Iniciar sesion',
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.w900),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            TextField(
              key: const Key('mobile-login-email'),
              controller: emailController,
              keyboardType: TextInputType.emailAddress,
              textInputAction: TextInputAction.next,
              decoration: const InputDecoration(
                labelText: 'Correo',
                prefixIcon: Icon(Icons.mail_outline),
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              key: const Key('mobile-login-password'),
              controller: passwordController,
              obscureText: !showPassword,
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => onSubmit(),
              decoration: InputDecoration(
                labelText: 'Clave',
                prefixIcon: const Icon(Icons.key_outlined),
                suffixIcon: IconButton(
                  tooltip: showPassword ? 'Ocultar clave' : 'Ver clave',
                  onPressed: onTogglePassword,
                  icon: Icon(
                    showPassword
                        ? Icons.visibility_off_outlined
                        : Icons.visibility_outlined,
                  ),
                ),
                border: const OutlineInputBorder(),
              ),
            ),
            if (errorMessage.isNotEmpty) ...[
              const SizedBox(height: 12),
              _InlineNotice(
                icon: Icons.error_outline,
                title: 'No pudimos iniciar sesion',
                message: errorMessage,
                color: const Color(0xFFDC3545),
              ),
            ],
            const SizedBox(height: 16),
            FilledButton.icon(
              key: const Key('mobile-login-submit'),
              onPressed: isSigningIn ? null : onSubmit,
              icon: isSigningIn
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.login_outlined),
              label: Text(isSigningIn ? 'Validando acceso' : 'Entrar'),
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.center,
              child: TextButton.icon(
                onPressed:
                    isSigningIn || isRecovering ? null : onRecoverPassword,
                icon: isRecovering
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.help_outline),
                label: Text(
                  isRecovering ? 'Enviando solicitud' : 'Recuperar acceso',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoginTrustGrid extends StatelessWidget {
  const _LoginTrustGrid();

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisCount: 2,
      mainAxisSpacing: 10,
      crossAxisSpacing: 10,
      childAspectRatio: 1.55,
      children: const [
        _TrustTile(icon: Icons.inventory_2_outlined, label: 'Stock al dia'),
        _TrustTile(icon: Icons.credit_card_outlined, label: 'Credito B2B'),
        _TrustTile(icon: Icons.receipt_long_outlined, label: 'Ordenes'),
        _TrustTile(icon: Icons.local_shipping_outlined, label: 'Despacho'),
      ],
    );
  }
}

class _TrustTile extends StatelessWidget {
  const _TrustTile({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: _fventasLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _SoftIcon(icon: icon, color: _fventasBlue),
          Text(
            label,
            style: const TextStyle(
              color: _fventasBlack,
              fontWeight: FontWeight.w900,
            ),
          ),
        ],
      ),
    );
  }
}

class FVENTASShell extends StatefulWidget {
  const FVENTASShell({
    super.key,
    required this.session,
    required this.onSessionChanged,
    required this.onSignOut,
  });

  final MobileUserSession session;
  final Future<void> Function() onSessionChanged;
  final Future<void> Function() onSignOut;

  @override
  State<FVENTASShell> createState() => _FVENTASShellState();
}

class _FVENTASShellState extends State<FVENTASShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    if (widget.session.mustChangePassword) {
      return _PasswordChangeRequiredScreen(
        session: widget.session,
        onSessionChanged: widget.onSessionChanged,
        onSignOut: widget.onSignOut,
      );
    }

    if (widget.session.isMobileSalesUser) {
      return _SellerShell(
        session: widget.session,
        onSignOut: widget.onSignOut,
      );
    }

    final screens = [
      HomeScreen(
        session: widget.session,
        onOpenCatalog: () => setState(() => _index = 1),
        onOpenCart: () => setState(() => _index = 2),
      ),
      const CatalogScreen(),
      CartScreen(
        session: widget.session,
        onOpenCatalog: () => setState(() => _index = 1),
      ),
      const LocationsScreen(),
      ProfileScreen(
        session: widget.session,
        onSessionChanged: widget.onSessionChanged,
        onSignOut: widget.onSignOut,
      ),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const FVENTASLogo(compact: true),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'FVENTAS',
                    style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16),
                  ),
                  Text(
                    widget.session.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: _fventasMuted,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        centerTitle: false,
        toolbarHeight: 64,
        actions: [
          const _NotificationsButton(),
          ValueListenableBuilder<List<MobileCartItem>>(
            valueListenable: mobileCartController,
            builder: (context, items, _) {
              final count =
                  items.fold<int>(0, (total, item) => total + item.quantity);

              return IconButton(
                tooltip: 'Carrito',
                onPressed: () => setState(() => _index = 2),
                icon: Badge(
                  isLabelVisible: count > 0,
                  backgroundColor: _fventasBlue,
                  label: Text(count.toString()),
                  child: const Icon(Icons.shopping_cart_outlined),
                ),
              );
            },
          ),
          IconButton(
            tooltip: 'Perfil',
            onPressed: () => setState(() => _index = 4),
            icon: const Icon(Icons.person_outline),
          ),
        ],
      ),
      body: screens[_index],
      bottomNavigationBar: NavigationBar(
        height: 72,
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.home_outlined), label: 'Inicio'),
          NavigationDestination(
              icon: Icon(Icons.grid_view_outlined), label: 'Catalogo'),
          NavigationDestination(
              icon: Icon(Icons.shopping_cart_outlined), label: 'Carrito'),
          NavigationDestination(
              icon: Icon(Icons.location_on_outlined), label: 'Puntos'),
          NavigationDestination(
              icon: Icon(Icons.person_outline), label: 'Perfil'),
        ],
      ),
    );
  }
}

class _PasswordChangeRequiredScreen extends StatefulWidget {
  const _PasswordChangeRequiredScreen({
    required this.session,
    required this.onSessionChanged,
    required this.onSignOut,
  });

  final MobileUserSession session;
  final Future<void> Function() onSessionChanged;
  final Future<void> Function() onSignOut;

  @override
  State<_PasswordChangeRequiredScreen> createState() =>
      _PasswordChangeRequiredScreenState();
}

class _PasswordChangeRequiredScreenState
    extends State<_PasswordChangeRequiredScreen> {
  final _currentPasswordController = TextEditingController();
  final _newPasswordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  bool _isSaving = false;

  @override
  void dispose() {
    _currentPasswordController.dispose();
    _newPasswordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  Future<void> _changePassword() async {
    if (_isSaving) {
      return;
    }
    if (_newPasswordController.text != _confirmPasswordController.text) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('La confirmacion no coincide.')),
      );
      return;
    }

    setState(() => _isSaving = true);

    try {
      await mobileAuthRepository.changePassword(
        currentPassword: _currentPasswordController.text,
        newPassword: _newPasswordController.text,
      );
      if (!mounted) {
        return;
      }
      _currentPasswordController.clear();
      _newPasswordController.clear();
      _confirmPasswordController.clear();
      await widget.onSessionChanged();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Clave actualizada.')),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text(error.toString().replaceFirst('Bad state: ', ''))),
      );
    } finally {
      if (mounted) {
        setState(() => _isSaving = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const FVENTASLogo(compact: true),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                widget.session.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w900),
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Cerrar sesion',
            onPressed: widget.onSignOut,
            icon: const Icon(Icons.logout_outlined),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          const _InlineNotice(
            icon: Icons.security_outlined,
            title: 'Clave temporal obligatoria',
            message:
                'Antes de comprar, tomar pedidos o ver cartera debes crear una clave privada.',
            color: _fventasBlue,
          ),
          const SizedBox(height: 12),
          _PasswordChangePanel(
            currentPasswordController: _currentPasswordController,
            newPasswordController: _newPasswordController,
            confirmPasswordController: _confirmPasswordController,
            isSaving: _isSaving,
            requiredChange: true,
            onSubmit: _changePassword,
          ),
        ],
      ),
    );
  }
}

class _SellerShell extends StatefulWidget {
  const _SellerShell({
    required this.session,
    required this.onSignOut,
  });

  final MobileUserSession session;
  final Future<void> Function() onSignOut;

  @override
  State<_SellerShell> createState() => _SellerShellState();
}

class _SellerShellState extends State<_SellerShell> {
  int _index = 1;

  @override
  Widget build(BuildContext context) {
    final screens = [
      SellerHomeScreen(
        session: widget.session,
        onOpenCatalog: () => setState(() => _index = 1),
        onOpenOrder: () => setState(() => _index = 2),
        onOpenClients: () => setState(() => _index = 3),
      ),
      SellerCatalogScreen(
        onOpenOrder: () => setState(() => _index = 2),
      ),
      SellerCartScreen(
        session: widget.session,
        onOpenCatalog: () => setState(() => _index = 1),
      ),
      const SellerClientsScreen(),
      const SellerCommissionsScreen(),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const FVENTASLogo(compact: true),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'FVENTAS Ventas',
                    style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16),
                  ),
                  Text(
                    widget.session.roleLabel,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: _fventasMuted,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        centerTitle: false,
        toolbarHeight: 60,
        actions: [
          ValueListenableBuilder<List<MobileCartItem>>(
            valueListenable: mobileCartController,
            builder: (context, items, _) {
              final count =
                  items.fold<int>(0, (total, item) => total + item.quantity);
              return IconButton(
                tooltip: 'Pedido asistido',
                onPressed: () => setState(() => _index = 2),
                icon: Badge(
                  isLabelVisible: count > 0,
                  backgroundColor: _fventasBlue,
                  label: Text(count.toString()),
                  child: const Icon(Icons.assignment_add),
                ),
              );
            },
          ),
          IconButton(
            tooltip: 'Cerrar sesion',
            onPressed: widget.onSignOut,
            icon: const Icon(Icons.logout_outlined),
          ),
        ],
      ),
      body: screens[_index],
      bottomNavigationBar: NavigationBar(
        height: 72,
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.dashboard_outlined), label: 'Inicio'),
          NavigationDestination(
              icon: Icon(Icons.point_of_sale_outlined), label: 'Vender'),
          NavigationDestination(
              icon: Icon(Icons.assignment_add), label: 'Pedido'),
          NavigationDestination(
              icon: Icon(Icons.storefront_outlined), label: 'Clientes'),
          NavigationDestination(
              icon: Icon(Icons.payments_outlined), label: 'Comis.'),
        ],
      ),
    );
  }
}

class _NotificationsButton extends StatelessWidget {
  const _NotificationsButton();

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<MobileNotification>>(
      future: mobileRepository.listNotifications(),
      builder: (context, snapshot) {
        final count = (snapshot.data ?? const <MobileNotification>[])
            .where((notification) => notification.isUnread)
            .length;
        return IconButton(
          tooltip: 'Notificaciones',
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const NotificationsScreen()),
          ),
          icon: Badge(
            isLabelVisible: count > 0,
            backgroundColor: _fventasBlue,
            label: Text(count.toString()),
            child: const Icon(Icons.notifications_none),
          ),
        );
      },
    );
  }
}

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  late Future<List<MobileNotification>> _notificationsFuture;

  @override
  void initState() {
    super.initState();
    _notificationsFuture = mobileRepository.listNotifications();
  }

  Future<void> _refreshNotifications() async {
    final future = mobileRepository.listNotifications();
    setState(() {
      _notificationsFuture = future;
    });
    try {
      await future;
    } catch (_) {
      // The FutureBuilder below renders the error state.
    }
  }

  void _reloadNotifications() {
    setState(() {
      _notificationsFuture = mobileRepository.listNotifications();
    });
  }

  Future<void> _markAsRead(MobileNotification notification) async {
    if (!notification.isUnread) {
      return;
    }
    await mobileRepository.markNotificationRead(notification.id);
    await _refreshNotifications();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Notificaciones'),
        actions: [
          IconButton(
            tooltip: 'Actualizar',
            onPressed: _reloadNotifications,
            icon: const Icon(Icons.refresh_outlined),
          ),
        ],
      ),
      body: SafeArea(
        child: FutureBuilder<List<MobileNotification>>(
          future: _notificationsFuture,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const _NotificationsLoadingState();
            }
            if (snapshot.hasError) {
              return Padding(
                padding: const EdgeInsets.all(18),
                child: _ErrorState(
                  title: 'No pudimos cargar las notificaciones',
                  message: _friendlyMobileError(snapshot.error),
                  onRetry: _reloadNotifications,
                ),
              );
            }
            final notifications = snapshot.data ?? const <MobileNotification>[];
            if (notifications.isEmpty) {
              return _NotificationsEmptyState(
                onRefresh: _refreshNotifications,
              );
            }
            return RefreshIndicator(
              onRefresh: _refreshNotifications,
              child: ListView.separated(
                padding: const EdgeInsets.fromLTRB(18, 8, 18, 24),
                itemCount: notifications.length,
                separatorBuilder: (_, __) => const SizedBox(height: 12),
                itemBuilder: (context, index) => _NotificationCard(
                  notification: notifications[index],
                  onRead: () => _markAsRead(notifications[index]),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _NotificationsLoadingState extends StatelessWidget {
  const _NotificationsLoadingState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 360),
        child: Container(
          margin: const EdgeInsets.all(18),
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(
            color: _fventasSurface,
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: _fventasLine),
            boxShadow: const [
              BoxShadow(
                blurRadius: 24,
                offset: Offset(0, 12),
                color: Color(0x0F000000),
              ),
            ],
          ),
          child: const Row(
            children: [
              _SoftIcon(icon: Icons.sync_outlined),
              SizedBox(width: 14),
              Expanded(
                child: Text(
                  'Sincronizando alertas FVENTAS',
                  style: TextStyle(
                    color: _fventasBlack,
                    fontSize: 16,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2.4),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NotificationsEmptyState extends StatelessWidget {
  const _NotificationsEmptyState({required this.onRefresh});

  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(18, 34, 18, 24),
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 30),
            decoration: BoxDecoration(
              color: _fventasSurface,
              borderRadius: BorderRadius.circular(26),
              border: Border.all(color: _fventasLine),
              boxShadow: const [
                BoxShadow(
                  blurRadius: 24,
                  offset: Offset(0, 12),
                  color: Color(0x0D000000),
                ),
              ],
            ),
            child: Column(
              children: [
                const _SoftIcon(icon: Icons.notifications_none_outlined),
                const SizedBox(height: 16),
                Text(
                  'Sin alertas por revisar',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        color: _fventasBlack,
                        fontWeight: FontWeight.w900,
                      ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Las notificaciones de pedidos, credito, stock y comisiones apareceran aqui cuando exista una accion pendiente.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: _fventasMuted,
                    height: 1.35,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 18),
                OutlinedButton.icon(
                  onPressed: onRefresh,
                  icon: const Icon(Icons.refresh_outlined),
                  label: const Text('Actualizar'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _NotificationCard extends StatelessWidget {
  const _NotificationCard({
    required this.notification,
    required this.onRead,
  });

  final MobileNotification notification;
  final Future<void> Function() onRead;

  @override
  Widget build(BuildContext context) {
    final color = _notificationColor(notification);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _fventasSurface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: notification.isUnread
              ? color.withValues(alpha: .28)
              : _fventasLine,
        ),
        boxShadow: const [
          BoxShadow(
            blurRadius: 18,
            offset: Offset(0, 10),
            color: Color(0x10000000),
          ),
        ],
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
              color: color.withValues(alpha: .12),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Icon(_notificationIcon(notification), color: color),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        notification.title,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w900,
                          color: _fventasBlack,
                        ),
                      ),
                    ),
                    if (notification.isUnread)
                      Container(
                        width: 8,
                        height: 8,
                        decoration: const BoxDecoration(
                          color: _fventasBlue,
                          shape: BoxShape.circle,
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  notification.body.isEmpty
                      ? notification.typeLabel
                      : notification.body,
                  style: const TextStyle(
                    color: _fventasMuted,
                    height: 1.35,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    _MiniChip(
                      label: notification.typeLabel,
                      color: color,
                    ),
                    _MiniChip(
                      label: _shortDate(notification.createdAt),
                      color: _fventasInk,
                    ),
                    if (notification.entityId.isNotEmpty)
                      _MiniChip(
                        label: notification.entityId,
                        color: _fventasMuted,
                      ),
                  ],
                ),
                if (notification.isUnread) ...[
                  const SizedBox(height: 12),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      onPressed: onRead,
                      icon: const Icon(Icons.done_all_outlined, size: 18),
                      label: const Text('Marcar como leida'),
                      style: TextButton.styleFrom(
                        foregroundColor: color,
                        padding: EdgeInsets.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

Color _notificationColor(MobileNotification notification) {
  if (notification.priority == 'critical') {
    return const Color(0xFFDC3545);
  }
  if (notification.priority == 'high') {
    return const Color(0xFFFFB020);
  }
  if (notification.type.contains('credit')) {
    return const Color(0xFF0D6EFD);
  }
  return _fventasBlue;
}

IconData _notificationIcon(MobileNotification notification) {
  if (notification.type.contains('order')) {
    return Icons.receipt_long_outlined;
  }
  if (notification.type.contains('credit')) {
    return Icons.credit_card_outlined;
  }
  if (notification.type.contains('stock') ||
      notification.type.contains('out')) {
    return Icons.inventory_2_outlined;
  }
  if (notification.type.contains('commission')) {
    return Icons.payments_outlined;
  }
  return Icons.notifications_none;
}

String _shortDate(DateTime value) {
  return '${value.day.toString().padLeft(2, '0')}/${value.month.toString().padLeft(2, '0')}';
}

class _MiniChip extends StatelessWidget {
  const _MiniChip({
    required this.label,
    required this.color,
  });

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .1),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({
    super.key,
    required this.session,
    required this.onOpenCatalog,
    required this.onOpenCart,
  });

  final MobileUserSession session;
  final VoidCallback onOpenCatalog;
  final VoidCallback onOpenCart;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(18, 8, 18, 24),
      children: [
        _SearchBox(
          labelText: 'Buscar maquinaria, repuestos o SKU',
          readOnly: true,
          onTap: onOpenCatalog,
        ),
        const SizedBox(height: 14),
        _CustomerCommerceCard(
          session: session,
          onOpenCatalog: onOpenCatalog,
        ),
        const SizedBox(height: 18),
        _HeroPanel(onOpenCatalog: onOpenCatalog),
        const SizedBox(height: 18),
        _SectionTitle(
          title: 'Categorias',
          actionLabel: 'Ver todo',
          onAction: onOpenCatalog,
        ),
        _CategoryRail(onOpenCatalog: onOpenCatalog),
        const SizedBox(height: 18),
        _SectionTitle(
          title: 'Productos destacados',
          actionLabel: 'Catalogo',
          onAction: onOpenCatalog,
        ),
        _FeaturedProductGrid(
          onOpenCart: onOpenCart,
        ),
      ],
    );
  }
}

class SellerHomeScreen extends StatelessWidget {
  const SellerHomeScreen({
    super.key,
    required this.session,
    required this.onOpenCatalog,
    required this.onOpenOrder,
    required this.onOpenClients,
  });

  final MobileUserSession session;
  final VoidCallback onOpenCatalog;
  final VoidCallback onOpenOrder;
  final VoidCallback onOpenClients;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 24),
      children: [
        _SellerSummaryCard(
          session: session,
          onOpenCatalog: onOpenCatalog,
          onOpenOrder: onOpenOrder,
          onOpenClients: onOpenClients,
        ),
        const SizedBox(height: 16),
        _SectionTitle(
          title: 'Pedidos recientes',
          actionLabel: 'Nuevo',
          onAction: onOpenOrder,
        ),
        const _SellerOrdersPreview(),
      ],
    );
  }
}

class _SellerSummaryCard extends StatelessWidget {
  const _SellerSummaryCard({
    required this.session,
    required this.onOpenCatalog,
    required this.onOpenOrder,
    required this.onOpenClients,
  });

  final MobileUserSession session;
  final VoidCallback onOpenCatalog;
  final VoidCallback onOpenOrder;
  final VoidCallback onOpenClients;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<MobileSellerSummary>(
      future: mobileRepository.getSellerSummary(),
      builder: (context, snapshot) {
        final summary = snapshot.data;
        final isLoading = snapshot.connectionState != ConnectionState.done;
        final goalProgress =
            ((summary?.goalProgressPercent ?? 0).clamp(0, 100) / 100)
                .toDouble();
        final sellerMeta = [
          summary?.sellerCode ?? '',
          summary?.sellerZone ?? '',
        ].where((item) => item.isNotEmpty).join(' - ');

        return Card(
          margin: EdgeInsets.zero,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(18),
            side: const BorderSide(color: _fventasLine),
          ),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const _SoftIcon(icon: Icons.badge_outlined),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            session.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context)
                                .textTheme
                                .titleLarge
                                ?.copyWith(
                                  color: _fventasBlack,
                                  fontWeight: FontWeight.w900,
                                ),
                          ),
                          Text(
                            sellerMeta.isEmpty
                                ? (summary?.roleLabel ?? session.roleLabel)
                                : sellerMeta,
                            style: const TextStyle(
                              color: _fventasMuted,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ),
                    _StatusPill(
                      label: isLoading ? 'Sync' : 'Activo',
                      color: _fventasBlue,
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(14),
                    color: _fventasCanvas,
                    border: Border.all(
                      color: _fventasLine,
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'Meta mensual',
                            style: TextStyle(
                              color: _fventasInk,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                          Text(
                            isLoading
                                ? 'Sync'
                                : '${(summary?.goalProgressPercent ?? 0).toStringAsFixed(0)}%',
                            style: const TextStyle(
                              color: _fventasBlack,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(99),
                        child: LinearProgressIndicator(
                          minHeight: 8,
                          value: isLoading ? null : goalProgress,
                          backgroundColor: const Color(0xFFDCE7F7),
                          valueColor: const AlwaysStoppedAnimation<Color>(
                            _fventasBlue,
                          ),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        isLoading
                            ? 'Sincronizando cartera'
                            : '${_moneyFromUsd(summary?.salesMonthUsd ?? 0, fractionDigits: 0)} de ${_moneyFromUsd(summary?.salesGoalUsd ?? 0, fractionDigits: 0)}',
                        style: const TextStyle(
                          color: _fventasMuted,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: _SellerMetricTile(
                        label: 'Clientes',
                        value: isLoading
                            ? '...'
                            : '${summary?.activeClientsCount ?? summary?.clientsCount ?? 0}/${summary?.clientsCount ?? 0}',
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _SellerMetricTile(
                        label: 'Ticket',
                        value: isLoading
                            ? '...'
                            : _moneyFromUsd(
                                summary?.ticketAverageUsd ?? 0,
                                fractionDigits: 0,
                              ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: _SellerMetricTile(
                        label: 'Comision',
                        value: isLoading
                            ? '...'
                            : _moneyFromUsd(summary?.pendingCommissionUsd ?? 0),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _SellerMetricTile(
                        label: 'Cupos',
                        value: isLoading
                            ? '...'
                            : '${summary?.pendingCreditRequests ?? 0}',
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: onOpenCatalog,
                        icon: const Icon(Icons.search),
                        label: const Text('Vender'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: onOpenOrder,
                        icon: const Icon(Icons.assignment_add),
                        label: const Text('Pedido'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: TextButton.icon(
                    onPressed: onOpenClients,
                    icon: const Icon(Icons.person_add_alt_1),
                    label: const Text('Nuevo cliente o revisar cartera'),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _SellerMetricTile extends StatelessWidget {
  const _SellerMetricTile({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        color: Colors.white,
        border: Border.all(color: _fventasLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: _fventasMuted,
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  color: _fventasBlack,
                  fontWeight: FontWeight.w900,
                ),
          ),
        ],
      ),
    );
  }
}

class _DarkMetric extends StatelessWidget {
  const _DarkMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: Colors.white.withValues(alpha: 0.08),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: Color(0xFFD4D4D4),
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w900,
                ),
          ),
        ],
      ),
    );
  }
}

class _SellerOrdersPreview extends StatelessWidget {
  const _SellerOrdersPreview();

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<MobileOrderSummary>>(
      future: mobileRepository.listSellerOrders(),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const _SellerCommissionsLoadingView();
        }

        final orders = snapshot.data ?? [];
        if (orders.isEmpty) {
          return const _EmptyState(message: 'Sin ordenes de cartera todavia');
        }

        return Column(
          children: [
            for (final order in orders.take(4))
              _SellerOrderCard(order: order, showCommission: false),
          ],
        );
      },
    );
  }
}

class SellerCatalogScreen extends StatefulWidget {
  const SellerCatalogScreen({
    super.key,
    required this.onOpenOrder,
  });

  final VoidCallback onOpenOrder;

  @override
  State<SellerCatalogScreen> createState() => _SellerCatalogScreenState();
}

class _SellerCatalogScreenState extends State<SellerCatalogScreen> {
  final _searchController = TextEditingController();
  Timer? _searchDebounce;
  late Future<MobileProductPage> _future;
  _CatalogFilter _filter = _CatalogFilter.available;
  String _searchText = "";
  String? _selectedCategoryId;

  @override
  void initState() {
    super.initState();
    _future = _loadProducts();
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  MobileProductQuery _query() {
    return MobileProductQuery(
      text: _searchText,
      verticalName: switch (_filter) {
        _CatalogFilter.machinery => "maquinaria",
        _CatalogFilter.spareParts => "repuesto",
        _ => null,
      },
      categoryId: _selectedCategoryId,
      onlyAvailable: _filter == _CatalogFilter.available,
      onlyNeedsValidation: _filter == _CatalogFilter.validation,
      limit: 50,
    );
  }

  Future<MobileProductPage> _loadProducts() {
    return mobileRepository.listProductPage(_query());
  }

  void _refreshProducts() {
    setState(() {
      _future = _loadProducts();
    });
  }

  void _onSearchChanged(String value) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 220), () {
      _searchText = value.trim();
      _refreshProducts();
    });
  }

  void _onFilterChanged(_CatalogFilter filter) {
    if (_filter == filter) {
      return;
    }
    _filter = filter;
    _refreshProducts();
  }

  void _onCategoryChanged(MobileCategory? category) {
    final nextId = category?.id.trim();
    final normalized = nextId == null || nextId.isEmpty ? null : nextId;
    if (_selectedCategoryId == normalized) {
      return;
    }
    _selectedCategoryId = normalized;
    _refreshProducts();
  }

  bool _addToOrder(MobileProduct product, int quantity) {
    if (!_canAddProductQuantity(context, product, quantity)) {
      return false;
    }
    mobileCartController.addProduct(product, quantity: quantity);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          '$quantity uds de ${product.name} agregadas al pedido',
        ),
        action: SnackBarAction(
          label: 'Ver pedido',
          onPressed: widget.onOpenOrder,
        ),
      ),
    );
    return true;
  }

  void _openProduct(MobileProduct product) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => _ProductDetailSheet(
        product: product,
        onAddQuantity: (quantity) {
          if (_addToOrder(product, quantity)) {
            Navigator.of(context).pop();
          }
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async => _refreshProducts(),
      child: FutureBuilder<MobileProductPage>(
        future: _future,
        builder: (context, snapshot) {
          final products = snapshot.data?.products ?? const <MobileProduct>[];
          final isLoading = snapshot.connectionState != ConnectionState.done;

          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 24),
            children: [
              ValueListenableBuilder<List<MobileCartItem>>(
                valueListenable: mobileCartController,
                builder: (context, items, _) => _SellerOrderBar(
                  items: items,
                  onOpenOrder: widget.onOpenOrder,
                ),
              ),
              const SizedBox(height: 12),
              _SearchBox(
                controller: _searchController,
                onChanged: _onSearchChanged,
                labelText: 'Buscar para vender: SKU, producto o repuesto',
              ),
              const SizedBox(height: 10),
              _CatalogFilterBar(selected: _filter, onChanged: _onFilterChanged),
              const SizedBox(height: 10),
              _CategoryFilterStrip(
                selectedCategoryId: _selectedCategoryId,
                onChanged: _onCategoryChanged,
              ),
              const SizedBox(height: 12),
              if (snapshot.hasError)
                _ErrorState(
                  title: 'No pudimos cargar productos',
                  message: _friendlyMobileError(snapshot.error),
                  onRetry: _refreshProducts,
                )
              else if (isLoading)
                const _LoadingState(message: 'Cargando lista de venta')
              else if (products.isEmpty)
                _EmptyState(
                  icon: Icons.inventory_2_outlined,
                  title: 'Sin productos para vender',
                  message:
                      'Ajusta busqueda, familia o disponibilidad para volver a cargar la lista.',
                  actionLabel: 'Limpiar filtros',
                  onAction: () {
                    _searchController.clear();
                    _searchText = "";
                    _selectedCategoryId = null;
                    _filter = _CatalogFilter.available;
                    _refreshProducts();
                  },
                )
              else ...[
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Text(
                    '${products.length} productos comerciales',
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                          color: _fventasMuted,
                          fontWeight: FontWeight.w900,
                        ),
                  ),
                ),
                for (final product in products)
                  _SellerProductLineCard(
                    product: product,
                    onTap: () => _openProduct(product),
                    onAddQuantity: (quantity) => _addToOrder(product, quantity),
                  ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _SellerOrderBar extends StatelessWidget {
  const _SellerOrderBar({
    required this.items,
    required this.onOpenOrder,
  });

  final List<MobileCartItem> items;
  final VoidCallback onOpenOrder;

  @override
  Widget build(BuildContext context) {
    final quantity = items.fold<int>(0, (total, item) => total + item.quantity);
    final total = items.fold<double>(
      0,
      (sum, item) => sum + item.quantity * item.unitPriceUsd,
    );

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        color: _fventasBlack,
      ),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              color: Colors.white.withValues(alpha: 0.1),
            ),
            child:
                const Icon(Icons.point_of_sale_outlined, color: Colors.white),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  quantity == 0 ? 'Venta asistida' : '$quantity uds en pedido',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w900,
                      ),
                ),
                Text(
                  quantity == 0
                      ? 'Busca, agrega y asigna cliente B2B'
                      : 'Total ${_moneyFromUsd(total)}',
                  style: const TextStyle(
                    color: Color(0xFFD4D4D4),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
          FilledButton(
            onPressed: quantity == 0 ? null : onOpenOrder,
            child: const Text('Pedido'),
          ),
        ],
      ),
    );
  }
}

class _SellerProductLineCard extends StatefulWidget {
  const _SellerProductLineCard({
    required this.product,
    required this.onTap,
    required this.onAddQuantity,
  });

  final MobileProduct product;
  final VoidCallback onTap;
  final ValueChanged<int> onAddQuantity;

  @override
  State<_SellerProductLineCard> createState() => _SellerProductLineCardState();
}

class _SellerProductLineCardState extends State<_SellerProductLineCard> {
  int _quantity = 1;

  Future<void> _editQuantity() async {
    final selected = await _showQuantityPicker(
      context,
      initialQuantity: _quantity,
      stock: widget.product.availableStock,
      allowBeyondStock: widget.product.requiresQuote,
    );
    if (!mounted || selected == null) {
      return;
    }
    setState(() => _quantity = selected);
  }

  @override
  Widget build(BuildContext context) {
    final product = widget.product;
    final accentColor = _productAccentColor(product.categoryName);
    final canAdd = product.requiresQuote || product.availableStock > 0;
    final effectiveImageUrl = _effectiveProductImage(
      imageUrl: product.primaryImageUrl,
      title: product.name,
      category: product.categoryName,
    );

    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: _fventasLine),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: widget.onTap,
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _SellerProductThumb(
                imageUrl: effectiveImageUrl,
                accentColor: accentColor,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            product.sku,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context)
                                .textTheme
                                .labelSmall
                                ?.copyWith(
                                  color: _fventasMuted,
                                  fontWeight: FontWeight.w900,
                                ),
                          ),
                        ),
                        _MiniChip(
                          label: product.requiresTechnicalValidation
                              ? 'Validar'
                              : '${product.availableStock} disp.',
                          color: product.requiresTechnicalValidation
                              ? const Color(0xFFFF6A1A)
                              : _fventasBlue,
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      product.name,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            color: _fventasBlack,
                            fontWeight: FontWeight.w900,
                            height: 1.08,
                          ),
                    ),
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        _MiniChip(
                            label: product.categoryName, color: accentColor),
                        if (product.b2bDiscountPercent > 0)
                          _MiniChip(
                            label:
                                '-${product.b2bDiscountPercent.toStringAsFixed(0)}%',
                            color: const Color(0xFF198754),
                          ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            product.requiresQuote
                                ? 'Cotizar'
                                : _moneyFromUsd(product.effectiveB2bPriceUsd),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context)
                                .textTheme
                                .titleMedium
                                ?.copyWith(
                                  color: _fventasBlack,
                                  fontWeight: FontWeight.w900,
                                ),
                          ),
                        ),
                        SizedBox(
                          width: 52,
                          height: 34,
                          child: OutlinedButton(
                            onPressed: canAdd ? _editQuantity : null,
                            style: OutlinedButton.styleFrom(
                              padding: EdgeInsets.zero,
                              foregroundColor: accentColor,
                              side: BorderSide(
                                color: accentColor.withValues(alpha: 0.35),
                              ),
                            ),
                            child: Text(
                              '$_quantity',
                              style:
                                  const TextStyle(fontWeight: FontWeight.w900),
                            ),
                          ),
                        ),
                        const SizedBox(width: 6),
                        FilledButton(
                          onPressed: canAdd
                              ? () => widget.onAddQuantity(_quantity)
                              : null,
                          style: FilledButton.styleFrom(
                            minimumSize: const Size(82, 34),
                            padding: const EdgeInsets.symmetric(horizontal: 10),
                            backgroundColor: accentColor,
                          ),
                          child: Text(canAdd ? 'Agregar' : 'Sin stock'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SellerProductThumb extends StatelessWidget {
  const _SellerProductThumb({
    required this.imageUrl,
    required this.accentColor,
  });

  final String? imageUrl;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(14),
      child: SizedBox(
        width: 78,
        height: 94,
        child: ColoredBox(
          color: accentColor.withValues(alpha: 0.08),
          child: imageUrl == null || imageUrl!.isEmpty
              ? _FVENTASProductPlaceholder(accentColor: accentColor)
              : Padding(
                  padding: const EdgeInsets.all(7),
                  child: _catalogImage(
                    imageUrl: imageUrl!,
                    fit: BoxFit.contain,
                    semanticLabel: 'Imagen de producto',
                    fallbackBuilder: () => _FVENTASProductPlaceholder(
                      accentColor: accentColor,
                    ),
                  ),
                ),
        ),
      ),
    );
  }
}

class SellerCartScreen extends StatefulWidget {
  const SellerCartScreen({
    super.key,
    required this.session,
    required this.onOpenCatalog,
  });

  final MobileUserSession session;
  final VoidCallback onOpenCatalog;

  @override
  State<SellerCartScreen> createState() => _SellerCartScreenState();
}

class _SellerCartScreenState extends State<SellerCartScreen> {
  String _selectedClientId = "";
  String _saleType = "cash";
  int _paymentTermDays = 15;

  MobileSellerClient? _selectedClient(List<MobileSellerClient> clients) {
    if (clients.isEmpty) {
      _selectedClientId = "";
      return null;
    }
    final existing = clients.where((client) => client.id == _selectedClientId);
    final selected = existing.isNotEmpty ? existing.first : clients.first;
    _selectedClientId = selected.id;
    return selected;
  }

  Set<String> _availableSaleTypes(
    MobileSellerClient client,
    double orderTotalUsd,
  ) {
    return {
      "cash",
      if (client.canUseTermCredit) "term_credit",
      if (client.canUseCreditLine && client.creditAvailableUsd >= orderTotalUsd)
        "credit_line",
    };
  }

  String _normalizeSaleType(
    MobileSellerClient client,
    double orderTotalUsd,
  ) {
    final available = _availableSaleTypes(client, orderTotalUsd);
    if (available.contains(_saleType)) {
      return _saleType;
    }
    if (available.contains(client.defaultSaleType)) {
      return client.defaultSaleType;
    }
    if (available.contains("term_credit")) {
      return "term_credit";
    }
    return "cash";
  }

  int _normalizePaymentTerm(MobileSellerClient client) {
    final terms = _positiveTerms(client.allowedPaymentTermsDays);
    if (terms.isEmpty) {
      return 0;
    }
    if (terms.contains(_paymentTermDays)) {
      return _paymentTermDays;
    }
    return terms.first;
  }

  String? _orderBlocker(
    MobileSellerClient? client,
    MobileCheckoutPreview preview,
    int selectedTerm,
  ) {
    if (client == null) {
      return "Selecciona un cliente B2B antes de crear el pedido.";
    }
    if (client.status.isNotEmpty && client.status != "active") {
      return "Cliente no habilitado para comprar desde la app.";
    }
    if (_saleType == "term_credit" &&
        !client.positivePaymentTerms.contains(selectedTerm)) {
      return "El plazo seleccionado no esta autorizado para este cliente.";
    }
    if (_saleType == "credit_line" && !client.creditEnabled) {
      return "El cliente no tiene linea de credito aprobada.";
    }
    if (_saleType == "credit_line" &&
        client.creditAvailableUsd < preview.totalUsd) {
      return "Cupo insuficiente: disponible ${_moneyFromUsd(client.creditAvailableUsd)}.";
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<List<MobileCartItem>>(
      valueListenable: mobileCartController,
      builder: (context, items, _) {
        if (items.isEmpty) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const _SectionTitle(title: 'Pedido'),
              const _EmptyState(
                title: 'Arma un pedido desde Vender',
                message:
                    'Busca productos, define cantidades y asigna el cliente B2B.',
                icon: Icons.assignment_add,
              ),
              FilledButton.icon(
                onPressed: widget.onOpenCatalog,
                icon: const Icon(Icons.search),
                label: const Text('Vender productos'),
              ),
            ],
          );
        }

        final preview = mobileCartService.calculatePreview(
          items,
          exchangeRateUsdLocal: _exchangeRateUsdLocal(),
        );

        return FutureBuilder<List<MobileSellerClient>>(
          future: mobileRepository.listSellerClients(),
          builder: (context, snapshot) {
            final clients = snapshot.data ?? [];
            final selectedClient = _selectedClient(clients);
            if (selectedClient != null) {
              _saleType = _normalizeSaleType(selectedClient, preview.totalUsd);
              _paymentTermDays = _normalizePaymentTerm(selectedClient);
            }

            final selectedTerm =
                _saleType == "term_credit" ? _paymentTermDays : 0;
            final orderBlocker =
                _orderBlocker(selectedClient, preview, selectedTerm);
            final draft = MobileSecureOrderDraft(
              items: items,
              preview: preview,
              customerId: _selectedClientId,
              saleType: _saleType,
              paymentTermDays: selectedTerm,
            );

            return ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Row(
                  children: [
                    const Expanded(child: _SectionTitle(title: 'Pedido')),
                    TextButton.icon(
                      onPressed: mobileCartController.clear,
                      icon: const Icon(Icons.delete_outline),
                      label: const Text('Vaciar'),
                    ),
                  ],
                ),
                if (snapshot.connectionState != ConnectionState.done)
                  const _InfoPanel(
                    title: 'Cliente',
                    lines: ['Cargando cartera comercial...'],
                  )
                else if (clients.isEmpty)
                  const _InfoPanel(
                    title: 'Cliente',
                    lines: ['No tienes clientes asignados para tomar pedidos.'],
                  )
                else
                  Card(
                    margin: const EdgeInsets.only(bottom: 12),
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Cliente B2B',
                            style: Theme.of(context)
                                .textTheme
                                .titleMedium
                                ?.copyWith(fontWeight: FontWeight.w900),
                          ),
                          const SizedBox(height: 12),
                          DropdownButtonFormField<String>(
                            initialValue: _selectedClientId,
                            decoration: const InputDecoration(
                              border: OutlineInputBorder(),
                              prefixIcon: Icon(Icons.storefront_outlined),
                            ),
                            items: [
                              for (final client in clients)
                                DropdownMenuItem(
                                  value: client.id,
                                  child: Text(client.businessName),
                                ),
                            ],
                            onChanged: (value) => setState(() {
                              _selectedClientId = value ?? "";
                              final nextClient = _selectedClient(clients);
                              if (nextClient == null) {
                                return;
                              }
                              _saleType = _normalizeSaleType(
                                nextClient,
                                preview.totalUsd,
                              );
                              _paymentTermDays =
                                  _normalizePaymentTerm(nextClient);
                            }),
                          ),
                          if (selectedClient != null) ...[
                            const SizedBox(height: 10),
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: [
                                _MiniChip(
                                  label:
                                      'Cupo ${_moneyFromUsd(selectedClient.creditAvailableUsd)}',
                                  color: selectedClient.canUseCreditLine
                                      ? const Color(0xFF198754)
                                      : _fventasMuted,
                                ),
                                if (selectedClient.creditRequestedUsd > 0)
                                  _MiniChip(
                                    label:
                                        'Solicitado ${_moneyFromUsd(selectedClient.creditRequestedUsd)}',
                                    color: const Color(0xFFFFC107),
                                  ),
                                if (selectedClient
                                    .positivePaymentTerms.isNotEmpty)
                                  _MiniChip(
                                    label:
                                        'Plazos ${selectedClient.positivePaymentTerms.join(", ")} dias',
                                    color: _fventasBlue,
                                  ),
                              ],
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                for (final item in items)
                  _CartItemTile(
                    item: item,
                    onIncrement: () =>
                        mobileCartController.increment(item.productId),
                    onDecrement: () =>
                        mobileCartController.decrement(item.productId),
                    onRemove: () => mobileCartController.remove(item.productId),
                  ),
                Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Condicion de venta',
                          style: Theme.of(context)
                              .textTheme
                              .titleMedium
                              ?.copyWith(fontWeight: FontWeight.w900),
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            _SaleTypeChip(
                              label: 'Efectivo',
                              selected: _saleType == "cash",
                              onSelected: () =>
                                  setState(() => _saleType = "cash"),
                            ),
                            _SaleTypeChip(
                              label: 'Credito dias',
                              selected: _saleType == "term_credit",
                              enabled: selectedClient?.canUseTermCredit == true,
                              onSelected: () => setState(() {
                                _saleType = "term_credit";
                                if (selectedClient != null) {
                                  _paymentTermDays =
                                      _normalizePaymentTerm(selectedClient);
                                }
                              }),
                            ),
                            _SaleTypeChip(
                              label: 'Linea de credito',
                              selected: _saleType == "credit_line",
                              enabled: selectedClient != null &&
                                  selectedClient.canUseCreditLine &&
                                  selectedClient.creditAvailableUsd >=
                                      preview.totalUsd,
                              onSelected: () =>
                                  setState(() => _saleType = "credit_line"),
                            ),
                          ],
                        ),
                        if (_saleType == "term_credit") ...[
                          const SizedBox(height: 12),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              for (final term
                                  in selectedClient?.positivePaymentTerms ??
                                      const <int>[])
                                _SaleTypeChip(
                                  label: '$term dias',
                                  selected: _paymentTermDays == term,
                                  onSelected: () => setState(
                                    () => _paymentTermDays = term,
                                  ),
                                ),
                            ],
                          ),
                        ],
                        const SizedBox(height: 14),
                        _InfoPanel(
                          title: 'Resumen',
                          compact: true,
                          lines: [
                            'Total ${_moneyFromUsd(preview.totalUsd)}',
                            'Condicion: ${_saleTypeLabel(_saleType, selectedTerm)}',
                            if (preview.requiresOperatorReview)
                              'Requiere revision por producto tecnico o cotizable.',
                            if (orderBlocker != null) orderBlocker,
                          ],
                        ),
                        const SizedBox(height: 10),
                        _CreateOrderButton(
                          draft: draft,
                          session: widget.session,
                          blocker: orderBlocker,
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            );
          },
        );
      },
    );
  }
}

class SellerClientsScreen extends StatefulWidget {
  const SellerClientsScreen({super.key});

  @override
  State<SellerClientsScreen> createState() => _SellerClientsScreenState();
}

class _SellerClientsScreenState extends State<SellerClientsScreen> {
  late Future<List<MobileSellerClient>> _clientsFuture;

  @override
  void initState() {
    super.initState();
    _clientsFuture = mobileRepository.listSellerClients();
  }

  void _reloadClients() {
    setState(() {
      _clientsFuture = mobileRepository.listSellerClients();
    });
  }

  Future<void> _showCreateClientSheet() async {
    final formKey = GlobalKey<FormState>();
    final businessNameController = TextEditingController();
    final emailController = TextEditingController();
    final phoneController = TextEditingController();
    final taxIdController = TextEditingController();
    final contactNameController = TextEditingController();
    final addressController = TextEditingController();
    final creditController = TextEditingController();
    final notesController = TextEditingController();
    String? selectedState;
    String? selectedCity;
    final idempotencyKey = _newOperationId('seller-client');

    void disposeControllers() {
      businessNameController.dispose();
      emailController.dispose();
      phoneController.dispose();
      taxIdController.dispose();
      contactNameController.dispose();
      addressController.dispose();
      creditController.dispose();
      notesController.dispose();
    }

    final created = await showModalBottomSheet<MobileSellerClientCreated>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (sheetContext) {
        var isSaving = false;
        String? formError;

        Future<void> submit(StateSetter setSheetState) async {
          if (isSaving || formKey.currentState?.validate() != true) {
            return;
          }
          FocusScope.of(sheetContext).unfocus();
          setSheetState(() {
            isSaving = true;
            formError = null;
          });
          try {
            final requestedCredit =
                _visibleMoneyInputToUsd(creditController.text);
            final rawPhone = phoneController.text.trim();
            final rawTaxId = taxIdController.text.trim();
            final usesChileFormat = _usesChileFormat();
            final normalizedPhone = usesChileFormat
                ? normalizeChileanPhone(rawPhone)
                : rawPhone.replaceAll(RegExp(r'\s+'), ' ').trim();
            final normalizedTaxId = usesChileFormat
                ? normalizeChileanRut(rawTaxId)
                : rawTaxId.toUpperCase().trim();
            final result = await mobileRepository.createSellerClient(
              MobileSellerClientDraft(
                businessName: businessNameController.text.trim(),
                email: emailController.text.trim().toLowerCase(),
                phone: normalizedPhone,
                taxId: normalizedTaxId,
                contactName: contactNameController.text.trim(),
                state: selectedState ?? '',
                city: selectedCity ?? '',
                address: addressController.text.trim(),
                notes: notesController.text.trim(),
                creditRequestedUsd: requestedCredit,
                defaultSaleType: requestedCredit > 0 ? 'credit_line' : 'cash',
                allowedPaymentTermsDays: const [0],
                idempotencyKey: idempotencyKey,
              ),
            );
            FocusManager.instance.primaryFocus?.unfocus();
            await Future<void>.delayed(Duration.zero);
            if (sheetContext.mounted) {
              Navigator.of(sheetContext).pop(result);
            }
          } catch (error) {
            if (!sheetContext.mounted) {
              return;
            }
            final readableError = _friendlyMobileError(error);
            setSheetState(() {
              isSaving = false;
              formError = readableError;
            });
            ScaffoldMessenger.of(sheetContext).showSnackBar(
              SnackBar(content: Text(readableError)),
            );
          }
        }

        return StatefulBuilder(
          builder: (context, setSheetState) {
            final locationProfile =
                countryLocations.profileFor(_marketCountryCode());
            final stateOptions = locationProfile.states;
            final cityOptions = locationProfile.citiesFor(selectedState);
            final selectedRegion =
                stateOptions.contains(selectedState) ? selectedState : null;
            final selectedCommune =
                cityOptions.contains(selectedCity) ? selectedCity : null;
            final usesChileFormat = _usesChileFormat();
            final taxLabel = _taxLabel();
            final taxPlaceholder = _taxPlaceholder();
            final phonePlaceholder = _phonePlaceholder();
            return Padding(
              padding: EdgeInsets.only(
                left: 18,
                right: 18,
                top: 12,
                bottom: MediaQuery.of(context).viewInsets.bottom + 18,
              ),
              child: SingleChildScrollView(
                child: Form(
                  key: formKey,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Center(
                        child: Container(
                          width: 42,
                          height: 4,
                          decoration: BoxDecoration(
                            color: _fventasLine,
                            borderRadius: BorderRadius.circular(99),
                          ),
                        ),
                      ),
                      const SizedBox(height: 18),
                      Text(
                        'Nuevo cliente B2B',
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.w900,
                            ),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Quedara asignado a tu cartera y el credito pasara a aprobacion comercial.',
                        style: TextStyle(
                          color: _fventasMuted,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 16),
                      TextFormField(
                        controller: businessNameController,
                        textInputAction: TextInputAction.next,
                        decoration: const InputDecoration(
                          labelText: 'Razon social / empresa',
                          prefixIcon: Icon(Icons.storefront_outlined),
                          border: OutlineInputBorder(),
                        ),
                        validator: (value) =>
                            value == null || value.trim().isEmpty
                                ? 'Ingresa el nombre comercial'
                                : null,
                      ),
                      const SizedBox(height: 10),
                      TextFormField(
                        controller: emailController,
                        keyboardType: TextInputType.emailAddress,
                        textInputAction: TextInputAction.next,
                        decoration: const InputDecoration(
                          labelText: 'Correo de acceso',
                          prefixIcon: Icon(Icons.mail_outline),
                          border: OutlineInputBorder(),
                        ),
                        validator: (value) {
                          final email = (value?.trim() ?? '').toLowerCase();
                          if (email.isEmpty) {
                            return 'Ingresa el correo';
                          }
                          if (!RegExp(
                            r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$',
                          ).hasMatch(email)) {
                            return 'Correo no valido';
                          }
                          if (email.endsWith('@fventas.local')) {
                            return 'Usa correo real del cliente';
                          }
                          return null;
                        },
                      ),
                      const SizedBox(height: 10),
                      Row(
                        children: [
                          Expanded(
                            child: TextFormField(
                              controller: phoneController,
                              keyboardType: TextInputType.phone,
                              textInputAction: TextInputAction.next,
                              inputFormatters: usesChileFormat
                                  ? [
                                      FilteringTextInputFormatter.digitsOnly,
                                      const _ChileanPhoneInputFormatter(),
                                    ]
                                  : [
                                      FilteringTextInputFormatter.allow(
                                        RegExp(r'[0-9+ -]'),
                                      ),
                                      LengthLimitingTextInputFormatter(24),
                                    ],
                              decoration: InputDecoration(
                                labelText: 'Telefono',
                                hintText: phonePlaceholder,
                                border: const OutlineInputBorder(),
                              ),
                              validator: (value) {
                                final phone = value?.trim() ?? '';
                                if (phone.isEmpty) {
                                  return 'Ingresa telefono';
                                }
                                if (usesChileFormat &&
                                    !isValidChileanPhone(phone)) {
                                  return 'Formato telefonico invalido';
                                }
                                if (!usesChileFormat &&
                                    phone
                                            .replaceAll(RegExp(r'[^0-9]'), '')
                                            .length <
                                        7) {
                                  return 'Formato telefonico invalido';
                                }
                                return null;
                              },
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: TextFormField(
                              controller: taxIdController,
                              textInputAction: TextInputAction.next,
                              textCapitalization: TextCapitalization.characters,
                              inputFormatters: usesChileFormat
                                  ? const [
                                      _ChileanTaxIdInputFormatter(),
                                    ]
                                  : [
                                      FilteringTextInputFormatter.allow(
                                        RegExp(r'[A-Za-z0-9.-]'),
                                      ),
                                      LengthLimitingTextInputFormatter(30),
                                    ],
                              decoration: InputDecoration(
                                labelText: taxLabel,
                                hintText: taxPlaceholder,
                                border: const OutlineInputBorder(),
                              ),
                              validator: (value) {
                                final rif = value?.trim() ?? '';
                                if (rif.isEmpty) {
                                  return 'Ingresa ${taxLabel.toLowerCase()}';
                                }
                                if (usesChileFormat &&
                                    !isValidChileanRut(rif)) {
                                  return '$taxLabel invalido';
                                }
                                return null;
                              },
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      TextFormField(
                        controller: contactNameController,
                        textInputAction: TextInputAction.next,
                        decoration: const InputDecoration(
                          labelText: 'Contacto principal',
                          prefixIcon: Icon(Icons.person_outline),
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 10),
                      if (locationProfile.hasLocations)
                        Row(
                          children: [
                            Expanded(
                              child: DropdownButtonFormField<String>(
                                initialValue: selectedRegion,
                                isExpanded: true,
                                decoration: InputDecoration(
                                  labelText: locationProfile.stateLabel,
                                  border: const OutlineInputBorder(),
                                ),
                                hint: Text(locationProfile.statePlaceholder),
                                validator: (value) =>
                                    value == null || value.trim().isEmpty
                                        ? locationProfile.statePlaceholder
                                        : null,
                                items: stateOptions
                                    .map(
                                      (state) => DropdownMenuItem<String>(
                                        value: state,
                                        child: Text(
                                          state,
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                    )
                                    .toList(growable: false),
                                onChanged: isSaving
                                    ? null
                                    : (value) => setSheetState(() {
                                          selectedState = value;
                                          selectedCity = null;
                                        }),
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: DropdownButtonFormField<String>(
                                initialValue: selectedCommune,
                                isExpanded: true,
                                decoration: InputDecoration(
                                  labelText: locationProfile.cityLabel,
                                  border: const OutlineInputBorder(),
                                ),
                                hint: Text(locationProfile.cityPlaceholder),
                                validator: (value) =>
                                    value == null || value.trim().isEmpty
                                        ? locationProfile.cityPlaceholder
                                        : null,
                                items: cityOptions
                                    .map(
                                      (city) => DropdownMenuItem<String>(
                                        value: city,
                                        child: Text(
                                          city,
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                    )
                                    .toList(growable: false),
                                onChanged: cityOptions.isEmpty || isSaving
                                    ? null
                                    : (value) => setSheetState(() {
                                          selectedCity = value;
                                        }),
                              ),
                            ),
                          ],
                        )
                      else
                        Row(
                          children: [
                            Expanded(
                              child: TextFormField(
                                initialValue: selectedState,
                                textInputAction: TextInputAction.next,
                                decoration: InputDecoration(
                                  labelText: locationProfile.stateLabel,
                                  border: const OutlineInputBorder(),
                                ),
                                onChanged: (value) {
                                  selectedState = value.trim();
                                },
                                validator: (value) =>
                                    value == null || value.trim().isEmpty
                                        ? locationProfile.statePlaceholder
                                        : null,
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: TextFormField(
                                initialValue: selectedCity,
                                textInputAction: TextInputAction.next,
                                decoration: InputDecoration(
                                  labelText: locationProfile.cityLabel,
                                  border: const OutlineInputBorder(),
                                ),
                                onChanged: (value) {
                                  selectedCity = value.trim();
                                },
                                validator: (value) =>
                                    value == null || value.trim().isEmpty
                                        ? locationProfile.cityPlaceholder
                                        : null,
                              ),
                            ),
                          ],
                        ),
                      const SizedBox(height: 10),
                      TextFormField(
                        controller: addressController,
                        minLines: 2,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: 'Direccion comercial',
                          prefixIcon: Icon(Icons.location_on_outlined),
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 10),
                      TextFormField(
                        controller: creditController,
                        keyboardType: const TextInputType.numberWithOptions(
                          decimal: true,
                        ),
                        textInputAction: TextInputAction.next,
                        inputFormatters: [
                          FilteringTextInputFormatter.allow(
                            RegExp(r'[0-9.,]'),
                          ),
                        ],
                        decoration: InputDecoration(
                          labelText:
                              'Cupo solicitado (${_displayCurrencySymbol()})',
                          helperText:
                              'Opcional. El gerente lo aprueba en el panel.',
                          prefixIcon: const Icon(Icons.credit_card_outlined),
                          border: const OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 10),
                      TextFormField(
                        controller: notesController,
                        minLines: 2,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: 'Notas comerciales',
                          border: OutlineInputBorder(),
                        ),
                      ),
                      if (formError != null) ...[
                        const SizedBox(height: 12),
                        _InlineNotice(
                          icon: Icons.error_outline,
                          title: 'No se pudo crear el cliente',
                          message: formError!,
                          color: Colors.red,
                        ),
                      ],
                      const SizedBox(height: 16),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          onPressed:
                              isSaving ? null : () => submit(setSheetState),
                          icon: isSaving
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.person_add_alt_1),
                          label: Text(
                            isSaving ? 'Creando...' : 'Crear cliente',
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        );
      },
    ).whenComplete(disposeControllers);

    if (created == null || !mounted) {
      return;
    }

    _reloadClients();
    final showTemporaryPassword =
        !created.alreadyExists && created.temporaryPassword.trim().isNotEmpty;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(
            created.alreadyExists ? 'Cliente sincronizado' : 'Cliente creado'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(created.client.businessName),
            const SizedBox(height: 10),
            if (created.message.trim().isNotEmpty) Text(created.message),
            if (showTemporaryPassword) ...[
              const SizedBox(height: 10),
              const Text(
                'Clave temporal',
                style: TextStyle(fontWeight: FontWeight.w900),
              ),
              SelectableText(created.temporaryPassword),
            ],
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Entendido'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<MobileSellerClient>>(
      future: _clientsFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const _SellerClientsLoadingView();
        }

        final clients = snapshot.data ?? [];
        final creditClients =
            clients.where((client) => client.creditEnabled).length;
        final pendingCredit = clients
            .where((client) => client.creditRequestStatus == "pending")
            .length;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Row(
              children: [
                const Expanded(child: _SectionTitle(title: 'Clientes')),
                FilledButton.icon(
                  onPressed: _showCreateClientSheet,
                  icon: const Icon(Icons.person_add_alt_1),
                  label: const Text('Nuevo cliente'),
                ),
              ],
            ),
            _SellerClientStatsRow(
              total: clients.length,
              withCredit: creditClients,
              pendingCredit: pendingCredit,
            ),
            const SizedBox(height: 12),
            if (clients.isEmpty)
              const _EmptyState(message: 'Sin clientes asignados')
            else
              for (final client in clients) _SellerClientCard(client: client),
          ],
        );
      },
    );
  }
}

class _SellerClientsLoadingView extends StatelessWidget {
  const _SellerClientsLoadingView();

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: const [
        Row(
          children: [
            Expanded(child: _SectionTitle(title: 'Clientes')),
            _SkeletonBox(width: 92, height: 44, radius: 14),
          ],
        ),
        SizedBox(height: 8),
        _SellerClientsSyncCard(),
        SizedBox(height: 12),
        _SellerClientSkeletonCard(),
        _SellerClientSkeletonCard(),
        _SellerClientSkeletonCard(),
      ],
    );
  }
}

class _SellerClientStatsRow extends StatelessWidget {
  const _SellerClientStatsRow({
    required this.total,
    required this.withCredit,
    required this.pendingCredit,
  });

  final int total;
  final int withCredit;
  final int pendingCredit;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _SellerMetricTile(
            label: 'Cartera',
            value: '$total',
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _SellerMetricTile(
            label: 'Con cupo',
            value: '$withCredit',
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _SellerMetricTile(
            label: 'Por aprobar',
            value: '$pendingCredit',
          ),
        ),
      ],
    );
  }
}

class _SellerClientsSyncCard extends StatelessWidget {
  const _SellerClientsSyncCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _fventasLine),
        boxShadow: [
          BoxShadow(
            color: _fventasBlack.withValues(alpha: 0.04),
            blurRadius: 18,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: _fventasBlue.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Padding(
              padding: EdgeInsets.all(10),
              child: CircularProgressIndicator(
                strokeWidth: 2.5,
                color: _fventasBlue,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Actualizando cartera',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        color: _fventasBlack,
                        fontWeight: FontWeight.w900,
                      ),
                ),
                const SizedBox(height: 2),
                const Text(
                  'Sincronizando clientes asignados, cupo y estado comercial.',
                  style: TextStyle(
                    color: _fventasMuted,
                    fontWeight: FontWeight.w700,
                    height: 1.25,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SellerClientSkeletonCard extends StatelessWidget {
  const _SellerClientSkeletonCard();

  @override
  Widget build(BuildContext context) {
    return const Card(
      margin: EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _SkeletonBox(width: 46, height: 46, radius: 16),
            SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _SkeletonBox(width: 160, height: 16, radius: 8),
                  SizedBox(height: 8),
                  _SkeletonBox(width: 120, height: 12, radius: 8),
                  SizedBox(height: 14),
                  _SkeletonBox(width: 150, height: 14, radius: 8),
                  SizedBox(height: 8),
                  _SkeletonBox(width: 190, height: 12, radius: 8),
                ],
              ),
            ),
            SizedBox(width: 10),
            _SkeletonBox(width: 72, height: 30, radius: 999),
          ],
        ),
      ),
    );
  }
}

class _SkeletonBox extends StatelessWidget {
  const _SkeletonBox({
    required this.width,
    required this.height,
    this.radius = 12,
  });

  final double width;
  final double height;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(radius),
        gradient: const LinearGradient(
          colors: [
            Color(0xFFEDE8E4),
            Color(0xFFF8FAFD),
            Color(0xFFEDE8E4),
          ],
          begin: Alignment.centerLeft,
          end: Alignment.centerRight,
        ),
      ),
    );
  }
}

class _SellerClientCard extends StatelessWidget {
  const _SellerClientCard({required this.client});

  final MobileSellerClient client;

  @override
  Widget build(BuildContext context) {
    final status = _sellerCreditStatus(client);
    final creditChipLabel =
        client.creditRequestStatus == "pending" && client.creditRequestedUsd > 0
            ? 'Solicitado ${_moneyFromUsd(client.creditRequestedUsd)}'
            : 'Cupo ${_moneyFromUsd(client.creditAvailableUsd)}';
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _SoftIcon(icon: Icons.storefront_outlined, color: status.color),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    client.businessName,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w900,
                        ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    [client.city, client.state]
                        .where((item) => item.isNotEmpty)
                        .join(' - '),
                    style: const TextStyle(
                      color: _fventasMuted,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 6,
                    children: [
                      _MiniChip(
                        label: creditChipLabel,
                        color: status.color,
                      ),
                      if (client.phone.isNotEmpty)
                        _MiniChip(label: client.phone, color: _fventasMuted),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    client.email,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: _fventasMuted),
                  ),
                ],
              ),
            ),
            _StatusPill(label: status.label, color: status.color),
          ],
        ),
      ),
    );
  }
}

({String label, Color color}) _sellerCreditStatus(MobileSellerClient client) {
  if (client.creditRequestStatus == "pending") {
    return (label: 'Por aprobar', color: const Color(0xFFFFC107));
  }
  if (!client.creditEnabled) {
    return (label: 'Contado', color: _fventasMuted);
  }
  if (client.creditAvailableUsd <= 0) {
    return (label: 'Sin cupo', color: const Color(0xFFDC3545));
  }
  return (label: 'Credito', color: const Color(0xFF198754));
}

class SellerCommissionsScreen extends StatefulWidget {
  const SellerCommissionsScreen({super.key});

  @override
  State<SellerCommissionsScreen> createState() =>
      _SellerCommissionsScreenState();
}

class _SellerCommissionsScreenState extends State<SellerCommissionsScreen> {
  late Future<
      ({
        MobileSellerSummary summary,
        List<MobileOrderSummary> orders,
      })> _future;
  _CommissionFilter _filter = _CommissionFilter.all;

  @override
  void initState() {
    super.initState();
    _future = _loadSellerCommissionBoard();
  }

  Future<
      ({
        MobileSellerSummary summary,
        List<MobileOrderSummary> orders,
      })> _loadSellerCommissionBoard() async {
    final results = await Future.wait([
      mobileRepository.getSellerSummary(),
      mobileRepository.listSellerCommissions(),
    ]);

    return (
      summary: results[0] as MobileSellerSummary,
      orders: results[1] as List<MobileOrderSummary>,
    );
  }

  Future<void> _refresh() async {
    final future = _loadSellerCommissionBoard();
    setState(() {
      _future = future;
    });
    await future;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<
        ({
          MobileSellerSummary summary,
          List<MobileOrderSummary> orders,
        })>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const _LoadingState();
        }

        if (snapshot.hasError) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const _SectionTitle(title: 'Comisiones'),
              _InlineNotice(
                icon: Icons.cloud_off_outlined,
                title: 'No pudimos sincronizar comisiones',
                message: snapshot.error.toString(),
                color: const Color(0xFFDC3545),
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: _refresh,
                icon: const Icon(Icons.sync),
                label: const Text('Reintentar'),
              ),
            ],
          );
        }

        final data = snapshot.data;
        final summary = data?.summary;
        final orders = data?.orders ?? const <MobileOrderSummary>[];
        final filteredOrders = orders
            .where((order) => _commissionMatches(order, _filter))
            .toList(growable: false);

        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const _SectionTitle(title: 'Comisiones'),
              if (summary != null) ...[
                _SellerCommissionHero(summary: summary, orders: orders),
                const SizedBox(height: 12),
              ],
              _CommissionFilterBar(
                selected: _filter,
                orders: orders,
                onChanged: (value) => setState(() => _filter = value),
              ),
              const SizedBox(height: 12),
              if (orders.isEmpty)
                const _EmptyState(
                  title: 'Sin comisiones',
                  message:
                      'Cuando tus pedidos sean registrados y evaluados por FVENTAS, veras aqui el estado de liquidacion.',
                  icon: Icons.payments_outlined,
                )
              else if (filteredOrders.isEmpty)
                _EmptyState(
                  title: 'Sin resultados',
                  message:
                      'No hay comisiones en el estado ${_commissionFilterLabel(_filter).toLowerCase()}.',
                  icon: Icons.filter_alt_off_outlined,
                )
              else
                for (final order in filteredOrders)
                  _SellerCommissionCard(order: order),
            ],
          ),
        );
      },
    );
  }
}

class _SellerCommissionsLoadingView extends StatelessWidget {
  const _SellerCommissionsLoadingView();

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: const [
        _SectionTitle(title: 'Comisiones'),
        _SellerCommissionsSyncHero(),
        SizedBox(height: 12),
        _CommissionFilterSkeletonBar(),
        SizedBox(height: 12),
        _CommissionSkeletonCard(),
        _CommissionSkeletonCard(),
      ],
    );
  }
}

class _SellerCommissionsSyncHero extends StatelessWidget {
  const _SellerCommissionsSyncHero();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: const LinearGradient(
          colors: [_fventasBlack, Color(0xFF102A43)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        boxShadow: [
          BoxShadow(
            color: _fventasBlack.withValues(alpha: 0.14),
            blurRadius: 22,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: _fventasBlue.withValues(alpha: 0.18),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Padding(
                  padding: EdgeInsets.all(12),
                  child: CircularProgressIndicator(
                    strokeWidth: 2.6,
                    color: _fventasBlue,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Actualizando comisiones',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w900,
                          ),
                    ),
                    const SizedBox(height: 2),
                    const Text(
                      'Leyendo ordenes, saldos y estados de liquidacion.',
                      style: TextStyle(
                        color: Color(0xFFD4D4D4),
                        fontWeight: FontWeight.w700,
                        height: 1.25,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          const _DarkSkeletonBox(width: 170, height: 24, radius: 10),
          const SizedBox(height: 8),
          const _DarkSkeletonBox(width: 220, height: 12, radius: 8),
          const SizedBox(height: 14),
          const Row(
            children: [
              Expanded(child: _DarkSkeletonMetric()),
              SizedBox(width: 10),
              Expanded(child: _DarkSkeletonMetric()),
              SizedBox(width: 10),
              Expanded(child: _DarkSkeletonMetric()),
            ],
          ),
        ],
      ),
    );
  }
}

class _CommissionFilterSkeletonBar extends StatelessWidget {
  const _CommissionFilterSkeletonBar();

  @override
  Widget build(BuildContext context) {
    return const SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          _SkeletonBox(width: 92, height: 36, radius: 999),
          SizedBox(width: 8),
          _SkeletonBox(width: 118, height: 36, radius: 999),
          SizedBox(width: 8),
          _SkeletonBox(width: 112, height: 36, radius: 999),
          SizedBox(width: 8),
          _SkeletonBox(width: 96, height: 36, radius: 999),
        ],
      ),
    );
  }
}

class _CommissionSkeletonCard extends StatelessWidget {
  const _CommissionSkeletonCard();

  @override
  Widget build(BuildContext context) {
    return const Card(
      margin: EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _SkeletonBox(width: 46, height: 46, radius: 16),
                SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _SkeletonBox(width: 170, height: 16, radius: 8),
                      SizedBox(height: 8),
                      _SkeletonBox(width: 210, height: 12, radius: 8),
                    ],
                  ),
                ),
                SizedBox(width: 10),
                _SkeletonBox(width: 78, height: 30, radius: 999),
              ],
            ),
            SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: _SkeletonBox(width: double.infinity, height: 62),
                ),
                SizedBox(width: 10),
                Expanded(
                  child: _SkeletonBox(width: double.infinity, height: 62),
                ),
              ],
            ),
            SizedBox(height: 12),
            _SkeletonBox(width: double.infinity, height: 44, radius: 16),
          ],
        ),
      ),
    );
  }
}

class _DarkSkeletonMetric extends StatelessWidget {
  const _DarkSkeletonMetric();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: Colors.white.withValues(alpha: 0.08),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _DarkSkeletonBox(width: 68, height: 10, radius: 8),
          SizedBox(height: 8),
          _DarkSkeletonBox(width: 92, height: 16, radius: 8),
        ],
      ),
    );
  }
}

class _DarkSkeletonBox extends StatelessWidget {
  const _DarkSkeletonBox({
    required this.width,
    required this.height,
    this.radius = 12,
  });

  final double width;
  final double height;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(radius),
        color: Colors.white.withValues(alpha: 0.16),
      ),
    );
  }
}

enum _CommissionFilter {
  all,
  pending,
  approved,
  paid,
  blocked,
}

class _SellerCommissionHero extends StatelessWidget {
  const _SellerCommissionHero({
    required this.summary,
    required this.orders,
  });

  final MobileSellerSummary summary;
  final List<MobileOrderSummary> orders;

  @override
  Widget build(BuildContext context) {
    final totalCommission = summary.pendingCommissionUsd +
        summary.approvedCommissionUsd +
        summary.paidCommissionUsd;

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: const LinearGradient(
          colors: [_fventasBlack, Color(0xFF102A43)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        boxShadow: [
          BoxShadow(
            color: _fventasBlack.withValues(alpha: 0.18),
            blurRadius: 24,
            offset: const Offset(0, 14),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: _fventasBlue.withValues(alpha: 0.18),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Icon(Icons.payments_outlined, color: _fventasBlue),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      summary.sellerName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w900,
                          ),
                    ),
                    Text(
                      '${summary.sellerCode.isEmpty ? summary.roleLabel : summary.sellerCode} - ${orders.length} ordenes',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Color(0xFFD4D4D4),
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
              _StatusPill(
                label: '${summary.commissionRatePercent.toStringAsFixed(1)}%',
                color: _fventasBlue,
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            _moneyFromUsd(totalCommission),
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w900,
                ),
          ),
          const Text(
            'Comision total registrada en cartera',
            style: TextStyle(
              color: Color(0xFFD4D4D4),
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: _DarkMetric(
                  label: 'Pendiente',
                  value: _moneyFromUsd(summary.pendingCommissionUsd),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _DarkMetric(
                  label: 'Aprobada',
                  value: _moneyFromUsd(summary.approvedCommissionUsd),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _DarkMetric(
                  label: 'Pagada',
                  value: _moneyFromUsd(summary.paidCommissionUsd),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _CommissionFilterBar extends StatelessWidget {
  const _CommissionFilterBar({
    required this.selected,
    required this.orders,
    required this.onChanged,
  });

  final _CommissionFilter selected;
  final List<MobileOrderSummary> orders;
  final ValueChanged<_CommissionFilter> onChanged;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final filter in _CommissionFilter.values)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ChoiceChip(
                selected: selected == filter,
                selectedColor: _fventasBlack,
                backgroundColor: Colors.white,
                side: BorderSide(
                  color: selected == filter ? _fventasBlack : _fventasLine,
                ),
                labelStyle: TextStyle(
                  color: selected == filter ? Colors.white : _fventasInk,
                  fontWeight: FontWeight.w900,
                ),
                avatar: Icon(
                  _commissionFilterIcon(filter),
                  size: 16,
                  color: selected == filter ? Colors.white : _fventasMuted,
                ),
                label: Text(
                  '${_commissionFilterLabel(filter)} ${_commissionFilterCount(orders, filter)}',
                ),
                onSelected: (_) => onChanged(filter),
              ),
            ),
        ],
      ),
    );
  }
}

class _SellerCommissionCard extends StatelessWidget {
  const _SellerCommissionCard({required this.order});

  final MobileOrderSummary order;

  @override
  Widget build(BuildContext context) {
    final commission = _sellerCommissionStatus(order);
    final orderStatus = _customerOrderStatus(order.status, order.paymentStatus);
    final rate = order.totalUsd <= 0 ? 0 : order.commissionUsd / order.totalUsd;
    final releaseReason = _commissionReleaseReason(order, commission.filter);

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _SoftIcon(icon: commission.icon, color: commission.color),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        order.customerName.isEmpty
                            ? 'Cliente por confirmar'
                            : order.customerName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style:
                            Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w900,
                                ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        order.id,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: _fventasMuted,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
                _StatusPill(label: commission.label, color: commission.color),
              ],
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: _CommissionAmountTile(
                    label: 'Comision',
                    value: _moneyFromUsd(order.commissionUsd),
                    color: commission.color,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _CommissionAmountTile(
                    label: 'Venta',
                    value: _moneyFromUsd(order.totalUsd),
                    color: _fventasInk,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _MiniChip(label: order.saleTypeLabel, color: _fventasBlue),
                _MiniChip(label: orderStatus.label, color: orderStatus.color),
                _MiniChip(
                  label: '${order.itemsCount} items',
                  color: _fventasMuted,
                ),
                if (rate > 0)
                  _MiniChip(
                    label: '${(rate * 100).toStringAsFixed(1)}%',
                    color: commission.color,
                  ),
                if (order.dueDate != null)
                  _MiniChip(
                    label: 'Vence ${_formatCustomerDate(order.dueDate!)}',
                    color: _fventasMuted,
                  ),
              ],
            ),
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: commission.color.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Text(
                releaseReason,
                style: TextStyle(
                  color: commission.color,
                  fontWeight: FontWeight.w800,
                  height: 1.3,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CommissionAmountTile extends StatelessWidget {
  const _CommissionAmountTile({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFD),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: _fventasLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: _fventasMuted,
              fontWeight: FontWeight.w800,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: color,
                  fontWeight: FontWeight.w900,
                ),
          ),
        ],
      ),
    );
  }
}

bool _commissionMatches(MobileOrderSummary order, _CommissionFilter filter) {
  if (filter == _CommissionFilter.all) {
    return true;
  }
  return _sellerCommissionStatus(order).filter == filter;
}

int _commissionFilterCount(
  List<MobileOrderSummary> orders,
  _CommissionFilter filter,
) {
  if (filter == _CommissionFilter.all) {
    return orders.length;
  }
  return orders
      .where((order) => _sellerCommissionStatus(order).filter == filter)
      .length;
}

String _commissionFilterLabel(_CommissionFilter filter) {
  switch (filter) {
    case _CommissionFilter.all:
      return 'Todas';
    case _CommissionFilter.pending:
      return 'Pendientes';
    case _CommissionFilter.approved:
      return 'Aprobadas';
    case _CommissionFilter.paid:
      return 'Pagadas';
    case _CommissionFilter.blocked:
      return 'Retenidas';
  }
}

IconData _commissionFilterIcon(_CommissionFilter filter) {
  switch (filter) {
    case _CommissionFilter.all:
      return Icons.list_alt_outlined;
    case _CommissionFilter.pending:
      return Icons.schedule_outlined;
    case _CommissionFilter.approved:
      return Icons.verified_outlined;
    case _CommissionFilter.paid:
      return Icons.paid_outlined;
    case _CommissionFilter.blocked:
      return Icons.block_outlined;
  }
}

({String label, IconData icon, Color color, _CommissionFilter filter})
    _sellerCommissionStatus(MobileOrderSummary order) {
  final raw =
      '${order.commissionStatus} ${order.commissionStatusLabel}'.toLowerCase();
  final orderRaw = '${order.status} ${order.paymentStatus}'.toLowerCase();

  if (raw.contains('paid') ||
      raw.contains('pagada') ||
      raw.contains('liquid')) {
    return (
      label: 'Pagada',
      icon: Icons.paid_outlined,
      color: const Color(0xFF198754),
      filter: _CommissionFilter.paid,
    );
  }
  if (raw.contains('approved') ||
      raw.contains('aprob') ||
      raw.contains('released')) {
    return (
      label: 'Aprobada',
      icon: Icons.verified_outlined,
      color: const Color(0xFF0D6EFD),
      filter: _CommissionFilter.approved,
    );
  }
  if (raw.contains('cancel') ||
      raw.contains('reject') ||
      raw.contains('anulad') ||
      raw.contains('hold') ||
      raw.contains('reten')) {
    return (
      label: 'Retenida',
      icon: Icons.block_outlined,
      color: const Color(0xFFDC3545),
      filter: _CommissionFilter.blocked,
    );
  }
  if (orderRaw.contains('cancel')) {
    return (
      label: 'Anulada',
      icon: Icons.cancel_outlined,
      color: const Color(0xFFDC3545),
      filter: _CommissionFilter.blocked,
    );
  }
  return (
    label: 'Pendiente',
    icon: Icons.schedule_outlined,
    color: const Color(0xFFFFB020),
    filter: _CommissionFilter.pending,
  );
}

String _commissionReleaseReason(
  MobileOrderSummary order,
  _CommissionFilter filter,
) {
  switch (filter) {
    case _CommissionFilter.paid:
      return 'Liquidada por FVENTAS. Esta comision ya forma parte del historial pagado.';
    case _CommissionFilter.approved:
      return 'Aprobada comercialmente. Queda lista para liquidacion segun el cierre interno.';
    case _CommissionFilter.blocked:
      return 'Retenida o anulada. Revisa con gerencia comercial antes de considerarla cobrable.';
    case _CommissionFilter.pending:
    case _CommissionFilter.all:
      if (order.balanceUsd > 0) {
        return 'Pendiente por saldo de cliente: ${_moneyFromUsd(order.balanceUsd)}.';
      }
      if (order.stockStatus.toLowerCase().contains('reserved')) {
        return 'Pedido con stock reservado. Falta validacion de entrega o cierre comercial.';
      }
      return 'Pendiente de validacion FVENTAS para liberar la comision.';
  }
}

class _SellerOrderCard extends StatelessWidget {
  const _SellerOrderCard({
    required this.order,
    required this.showCommission,
  });

  final MobileOrderSummary order;
  final bool showCommission;

  @override
  Widget build(BuildContext context) {
    final status = _customerOrderStatus(order.status, order.paymentStatus);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _SoftIcon(icon: status.icon, color: status.color),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    order.customerName.isEmpty ? order.id : order.customerName,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w900,
                        ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${order.saleTypeLabel} - ${status.label}',
                    style: const TextStyle(
                      color: _fventasMuted,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Total ${_moneyFromUsd(order.totalUsd)}',
                    style: const TextStyle(fontWeight: FontWeight.w900),
                  ),
                  if (showCommission)
                    Text(
                      'Comision ${_moneyFromUsd(order.commissionUsd)} - ${order.commissionStatusLabel}',
                      style: const TextStyle(
                        color: _fventasMuted,
                        fontWeight: FontWeight.w700,
                      ),
                    )
                  else
                    Text(
                      'Saldo ${_moneyFromUsd(order.balanceUsd)}',
                      style: const TextStyle(color: _fventasMuted),
                    ),
                ],
              ),
            ),
            _StatusPill(label: status.label, color: status.color),
          ],
        ),
      ),
    );
  }
}

enum _CatalogFilter {
  all,
  available,
  validation,
  machinery,
  spareParts,
}

class _CategoryRail extends StatelessWidget {
  const _CategoryRail({required this.onOpenCatalog});

  final VoidCallback onOpenCatalog;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<MobileCategory>>(
      future: mobileRepository.listCategories(),
      builder: (context, snapshot) {
        final categories = snapshot.data ?? [];

        if (snapshot.connectionState != ConnectionState.done) {
          return const SizedBox(
            height: 122,
            child: Center(child: CircularProgressIndicator()),
          );
        }

        return SizedBox(
          height: 122,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: categories.length,
            separatorBuilder: (_, __) => const SizedBox(width: 12),
            itemBuilder: (context, index) {
              final category = categories[index];
              return _CategoryPill(
                title: category.name,
                subtitle: category.description,
                imageUrl: category.imageUrl,
                icon: _categoryIcon(category.icon, index),
                onTap: onOpenCatalog,
              );
            },
          ),
        );
      },
    );
  }
}

IconData _categoryIcon(String iconName, int index) {
  final normalized = iconName.toLowerCase();
  if (normalized.contains('tool') || normalized.contains('wrench')) {
    return Icons.construction_outlined;
  }
  if (normalized.contains('gear') || normalized.contains('settings')) {
    return Icons.settings_suggest_outlined;
  }
  if (normalized.contains('image')) {
    return Icons.image_outlined;
  }
  if (normalized.contains('truck')) {
    return Icons.local_shipping_outlined;
  }
  return switch (index % 4) {
    0 => Icons.grass_outlined,
    1 => Icons.construction_outlined,
    2 => Icons.settings_suggest_outlined,
    _ => Icons.agriculture_outlined,
  };
}

class _CustomerCommerceCard extends StatelessWidget {
  const _CustomerCommerceCard({
    required this.session,
    required this.onOpenCatalog,
  });

  final MobileUserSession session;
  final VoidCallback onOpenCatalog;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<MobileCreditSnapshot>(
      future: mobileRepository.getCredit(session.id),
      builder: (context, snapshot) {
        final credit = snapshot.data;
        final isLoading = snapshot.connectionState != ConnectionState.done;
        final available = credit?.creditAvailableUsd ?? 0;
        final exposure = credit?.creditExposureUsd ?? 0;
        final limit = credit?.creditLimitUsd ?? 0;
        final enabled = credit?.creditEnabled == true;

        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(24),
            color: Colors.white,
            border: Border.all(color: _fventasLine),
            boxShadow: [
              BoxShadow(
                color: _fventasBlack.withValues(alpha: 0.05),
                blurRadius: 22,
                offset: const Offset(0, 12),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const _SoftIcon(icon: Icons.storefront_outlined),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          session.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context)
                              .textTheme
                              .titleMedium
                              ?.copyWith(fontWeight: FontWeight.w900),
                        ),
                        Text(
                          enabled ? 'Linea activa' : 'Compra bajo revision',
                          style: const TextStyle(
                            color: _fventasMuted,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
                  _StatusPill(
                    label:
                        isLoading ? 'Sync' : (enabled ? 'Credito' : 'Revision'),
                    color: enabled ? const Color(0xFF198754) : _fventasBlue,
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: _CommerceMetric(
                      label: 'Disponible',
                      value: isLoading ? '...' : _moneyFromUsd(available),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _CommerceMetric(
                      label: 'Comprometido',
                      value: isLoading ? '...' : _moneyFromUsd(exposure),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: LinearProgressIndicator(
                  minHeight: 8,
                  value: limit <= 0 ? 0 : (exposure / limit).clamp(0, 1),
                  backgroundColor: const Color(0xFFE9ECEF),
                  color: enabled ? _fventasBlue : const Color(0xFFADB5BD),
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      session.mustChangePassword
                          ? 'Clave temporal pendiente'
                          : 'Catalogo y cupo sincronizados',
                      style: const TextStyle(
                        color: _fventasMuted,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  TextButton(
                    onPressed: onOpenCatalog,
                    child: const Text(
                      'Comprar',
                      style: TextStyle(fontWeight: FontWeight.w900),
                    ),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}

class _CommerceMetric extends StatelessWidget {
  const _CommerceMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: const Color(0xFFF8F9FA),
        border: Border.all(color: _fventasLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: _fventasMuted,
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context)
                .textTheme
                .titleSmall
                ?.copyWith(fontWeight: FontWeight.w900),
          ),
        ],
      ),
    );
  }
}

class _CategoryPill extends StatelessWidget {
  const _CategoryPill({
    required this.title,
    required this.subtitle,
    required this.imageUrl,
    required this.icon,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final String imageUrl;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 156,
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            color: Colors.white,
            border: Border.all(color: _fventasLine),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (imageUrl.isNotEmpty)
                ClipRRect(
                  borderRadius: BorderRadius.circular(18),
                  child: Image.network(
                    imageUrl,
                    width: 44,
                    height: 44,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => CircleAvatar(
                      radius: 22,
                      backgroundColor: _fventasBlue.withValues(alpha: 0.1),
                      foregroundColor: _fventasBlue,
                      child: Icon(icon, size: 20),
                    ),
                  ),
                )
              else
                CircleAvatar(
                  radius: 22,
                  backgroundColor: _fventasBlue.withValues(alpha: 0.1),
                  foregroundColor: _fventasBlue,
                  child: Icon(icon, size: 20),
                ),
              const SizedBox(height: 10),
              Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w900),
              ),
              Text(
                subtitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: _fventasMuted, fontSize: 12),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FeaturedProductGrid extends StatelessWidget {
  const _FeaturedProductGrid({
    required this.onOpenCart,
  });

  final VoidCallback onOpenCart;

  bool _addFeaturedToCart(
    BuildContext context,
    MobileProduct product,
    int quantity,
  ) {
    if (!_canAddProductQuantity(context, product, quantity)) {
      return false;
    }

    mobileCartController.addProduct(product, quantity: quantity);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          '$quantity uds de ${product.name} agregadas al carrito',
        ),
      ),
    );
    return true;
  }

  void _openProductPreview(BuildContext context, MobileProduct product) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (sheetContext) => _ProductDetailSheet(
        product: product,
        onAddQuantity: (quantity) {
          if (_addFeaturedToCart(context, product, quantity)) {
            Navigator.of(sheetContext).pop();
            onOpenCart();
          }
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<MobileProductPage>(
      future: mobileRepository.listProductPage(
        const MobileProductQuery(onlyAvailable: true, limit: 4),
      ),
      builder: (context, snapshot) {
        final products = snapshot.data?.products ?? [];

        if (snapshot.connectionState != ConnectionState.done) {
          return const _LoadingState();
        }

        if (products.isEmpty) {
          return const _EmptyState(message: 'Sin productos destacados');
        }

        return GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: products.length,
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            mainAxisSpacing: 10,
            crossAxisSpacing: 10,
            childAspectRatio: 0.5,
          ),
          itemBuilder: (context, index) {
            final product = products[index];
            return _ProductTile(
              sku: product.sku,
              title: product.name,
              subtitle: _productSubtitle(product),
              badge: product.badge,
              imageUrl: product.primaryImageUrl,
              priceUsd: product.effectiveB2bPriceUsd,
              originalPriceUsd: product.b2bReferencePriceUsd,
              discountPercent: product.b2bDiscountPercent,
              category: product.categoryName,
              variants: product.variants,
              stock: product.availableStock,
              requiresQuote: product.requiresQuote,
              onTap: () => _openProductPreview(context, product),
              onAddQuantity: (quantity) {
                if (_addFeaturedToCart(context, product, quantity)) {
                  onOpenCart();
                }
              },
            );
          },
        );
      },
    );
  }
}

class CatalogScreen extends StatefulWidget {
  const CatalogScreen({super.key});

  @override
  State<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends State<CatalogScreen> {
  final _searchController = TextEditingController();
  final _scrollController = ScrollController();
  final _products = <MobileProduct>[];

  Timer? _searchDebounce;
  _CatalogFilter _filter = _CatalogFilter.all;
  String _searchText = "";
  String? _selectedCategoryId;
  String _selectedCategoryLabel = "Todas";
  String? _nextCursor;
  String? _errorMessage;
  bool _hasMore = true;
  bool _isLoading = true;
  bool _isLoadingMore = false;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_handleScroll);
    _loadFirstPage();
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _handleScroll() {
    if (!_scrollController.hasClients) {
      return;
    }

    final position = _scrollController.position;
    if (position.pixels >= position.maxScrollExtent - 360) {
      _loadMore();
    }
  }

  MobileProductQuery _query({String? cursor}) {
    return MobileProductQuery(
      text: _searchText,
      verticalName: switch (_filter) {
        _CatalogFilter.machinery => "maquinaria",
        _CatalogFilter.spareParts => "repuesto",
        _ => null,
      },
      categoryId: _selectedCategoryId,
      onlyAvailable: _filter == _CatalogFilter.available,
      onlyNeedsValidation: _filter == _CatalogFilter.validation,
      limit: 18,
      cursor: cursor,
    );
  }

  Future<void> _loadFirstPage() async {
    setState(() {
      _isLoading = true;
      _isLoadingMore = false;
      _errorMessage = null;
      _products.clear();
      _nextCursor = null;
      _hasMore = true;
    });

    try {
      final page = await mobileRepository.listProductPage(_query());
      if (!mounted) {
        return;
      }

      setState(() {
        _products.addAll(page.products);
        _nextCursor = page.nextCursor;
        _hasMore = page.hasMore;
        _isLoading = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _errorMessage = error.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _loadMore() async {
    if (_isLoading || _isLoadingMore || !_hasMore || _nextCursor == null) {
      return;
    }

    setState(() => _isLoadingMore = true);

    try {
      final page =
          await mobileRepository.listProductPage(_query(cursor: _nextCursor));
      if (!mounted) {
        return;
      }

      setState(() {
        _products.addAll(page.products);
        _nextCursor = page.nextCursor;
        _hasMore = page.hasMore;
        _isLoadingMore = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _errorMessage = error.toString();
        _isLoadingMore = false;
      });
    }
  }

  void _onSearchChanged(String value) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 280), () {
      _searchText = value;
      _loadFirstPage();
    });
  }

  void _onFilterChanged(_CatalogFilter filter) {
    if (_filter == filter) {
      return;
    }

    setState(() => _filter = filter);
    _loadFirstPage();
  }

  void _onCategoryChanged(MobileCategory? category) {
    final nextId = category?.id.trim();
    final normalizedId = nextId == null || nextId.isEmpty ? null : nextId;
    if (_selectedCategoryId == normalizedId) {
      return;
    }

    setState(() {
      _selectedCategoryId = normalizedId;
      _selectedCategoryLabel = category?.name ?? "Todas";
    });
    _loadFirstPage();
  }

  bool _addToCart(MobileProduct product, {int quantity = 1}) {
    if (!_canAddProductQuantity(context, product, quantity)) {
      return false;
    }

    mobileCartController.addProduct(product, quantity: quantity);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          '$quantity uds de ${product.name} agregadas al carrito',
        ),
      ),
    );
    return true;
  }

  void _openProduct(MobileProduct product) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => _ProductDetailSheet(
        product: product,
        onAddQuantity: (quantity) {
          if (_addToCart(product, quantity: quantity)) {
            Navigator.of(context).pop();
          }
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _loadFirstPage,
      child: ListView(
        controller: _scrollController,
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 24),
        children: [
          _SearchBox(
            controller: _searchController,
            onChanged: _onSearchChanged,
            labelText: 'Buscar producto, SKU o repuesto',
          ),
          const SizedBox(height: 10),
          _CatalogFilterBar(
            selected: _filter,
            onChanged: _onFilterChanged,
          ),
          const SizedBox(height: 10),
          _CategoryFilterStrip(
            selectedCategoryId: _selectedCategoryId,
            onChanged: _onCategoryChanged,
          ),
          const SizedBox(height: 12),
          if (!_isLoading && _errorMessage == null)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Text(
                _products.isEmpty
                    ? 'Sin productos para esta busqueda'
                    : _selectedCategoryLabel == "Todas"
                        ? '${_products.length} productos disponibles para compra'
                        : '${_products.length} productos en $_selectedCategoryLabel',
                style: Theme.of(context).textTheme.labelLarge?.copyWith(
                      color: _fventasMuted,
                      fontWeight: FontWeight.w900,
                    ),
              ),
            ),
          if (_errorMessage != null)
            _ErrorState(
              title: 'No pudimos cargar el catalogo',
              message: _friendlyMobileError(_errorMessage),
              onRetry: _loadFirstPage,
            )
          else if (_isLoading)
            const _LoadingState(message: 'Sincronizando catalogo FVENTAS')
          else if (_products.isEmpty)
            _EmptyState(
              icon: Icons.inventory_2_outlined,
              title: 'Sin productos visibles',
              message:
                  'No hay productos disponibles para esta busqueda o categoria. Ajusta los filtros o consulta con tu vendedor.',
              actionLabel: 'Limpiar filtros',
              onAction: () {
                _searchController.clear();
                _searchText = "";
                setState(() {
                  _filter = _CatalogFilter.all;
                  _selectedCategoryId = null;
                  _selectedCategoryLabel = "Todas";
                });
                _loadFirstPage();
              },
            )
          else
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: _products.length,
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                mainAxisSpacing: 10,
                crossAxisSpacing: 10,
                childAspectRatio: 0.5,
              ),
              itemBuilder: (context, index) {
                final product = _products[index];
                return _ProductTile(
                  sku: product.sku,
                  title: product.name,
                  subtitle: _productSubtitle(product),
                  badge: product.badge,
                  imageUrl: product.primaryImageUrl,
                  priceUsd: product.effectiveB2bPriceUsd,
                  originalPriceUsd: product.b2bReferencePriceUsd,
                  discountPercent: product.b2bDiscountPercent,
                  category: product.categoryName,
                  variants: product.variants,
                  stock: product.availableStock,
                  requiresQuote: product.requiresQuote,
                  onTap: () => _openProduct(product),
                  onAddQuantity: (quantity) =>
                      _addToCart(product, quantity: quantity),
                );
              },
            ),
          if (_isLoadingMore)
            const _LoadingState(
              compact: true,
              message: 'Cargando mas productos',
            ),
          if (!_isLoading &&
              !_isLoadingMore &&
              _hasMore &&
              _products.isNotEmpty)
            OutlinedButton.icon(
              onPressed: _loadMore,
              icon: const Icon(Icons.expand_more),
              label: const Text('Cargar mas productos'),
            ),
        ],
      ),
    );
  }
}

class _CatalogFilterBar extends StatelessWidget {
  const _CatalogFilterBar({
    required this.selected,
    required this.onChanged,
  });

  final _CatalogFilter selected;
  final ValueChanged<_CatalogFilter> onChanged;

  @override
  Widget build(BuildContext context) {
    const filters = [
      (_CatalogFilter.all, 'Todos'),
      (_CatalogFilter.available, 'Disponibles'),
      (_CatalogFilter.validation, 'Revision'),
    ];

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final (filter, label) in filters)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ChoiceChip(
                label: Text(label),
                selected: selected == filter,
                onSelected: (_) => onChanged(filter),
                selectedColor: _fventasBlack,
                backgroundColor: Colors.white,
                labelStyle: TextStyle(
                  color: selected == filter ? Colors.white : _fventasInk,
                  fontWeight: FontWeight.w800,
                ),
                side: BorderSide(
                  color: selected == filter ? _fventasBlack : _fventasLine,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _CategoryFilterStrip extends StatelessWidget {
  const _CategoryFilterStrip({
    required this.selectedCategoryId,
    required this.onChanged,
  });

  final String? selectedCategoryId;
  final ValueChanged<MobileCategory?> onChanged;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<MobileCategory>>(
      future: mobileRepository.listCategories(),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const _LoadingState(
            compact: true,
            message: 'Cargando familias',
          );
        }

        if (snapshot.hasError) {
          return const _InlineNotice(
            icon: Icons.cloud_off_outlined,
            title: 'Categorias no disponibles',
            message:
                'El catalogo sigue operativo, pero no pudimos leer las familias disponibles.',
            color: _fventasBlue,
          );
        }

        final categories = snapshot.data ?? [];
        if (categories.isEmpty) {
          return const SizedBox.shrink();
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Familias',
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: _fventasMuted,
                    fontWeight: FontWeight.w900,
                  ),
            ),
            const SizedBox(height: 8),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: const Text('Todas'),
                      avatar: const Icon(Icons.apps_outlined, size: 17),
                      selected: selectedCategoryId == null,
                      onSelected: (_) => onChanged(null),
                      selectedColor: _fventasBlack,
                      backgroundColor: Colors.white,
                      labelStyle: TextStyle(
                        color: selectedCategoryId == null
                            ? Colors.white
                            : _fventasInk,
                        fontWeight: FontWeight.w800,
                      ),
                      side: BorderSide(
                        color: selectedCategoryId == null
                            ? _fventasBlack
                            : _fventasLine,
                      ),
                    ),
                  ),
                  for (var index = 0; index < categories.length; index++)
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(
                        label: Text(categories[index].name),
                        avatar: Icon(
                          _categoryIcon(categories[index].icon, index),
                          size: 17,
                        ),
                        selected: selectedCategoryId == categories[index].id,
                        onSelected: (_) => onChanged(categories[index]),
                        selectedColor: _fventasBlack,
                        backgroundColor: Colors.white,
                        labelStyle: TextStyle(
                          color: selectedCategoryId == categories[index].id
                              ? Colors.white
                              : _fventasInk,
                          fontWeight: FontWeight.w800,
                        ),
                        side: BorderSide(
                          color: selectedCategoryId == categories[index].id
                              ? _fventasBlack
                              : _fventasLine,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

class _ProductDetailSheet extends StatefulWidget {
  const _ProductDetailSheet({
    required this.product,
    required this.onAddQuantity,
  });

  final MobileProduct product;
  final ValueChanged<int> onAddQuantity;

  @override
  State<_ProductDetailSheet> createState() => _ProductDetailSheetState();
}

class _ProductDetailSheetState extends State<_ProductDetailSheet> {
  int _quantity = 1;
  int _imageIndex = 0;
  late final PageController _imageController;

  @override
  void initState() {
    super.initState();
    _imageController = PageController();
  }

  @override
  void dispose() {
    _imageController.dispose();
    super.dispose();
  }

  Future<void> _editQuantity() async {
    final selected = await _showQuantityPicker(
      context,
      initialQuantity: _quantity,
      stock: widget.product.availableStock,
      allowBeyondStock: widget.product.requiresQuote,
    );

    if (!mounted || selected == null) {
      return;
    }

    setState(() => _quantity = selected);
  }

  @override
  Widget build(BuildContext context) {
    final product = widget.product;
    final b2bPrice = product.effectiveB2bPriceUsd;
    final referencePrice = product.b2bReferencePriceUsd;
    final accentColor = _productAccentColor(product.categoryName);
    final canAdd = product.requiresQuote || product.availableStock > 0;
    final galleryImages = product.galleryImageUrls;

    return FractionallySizedBox(
      heightFactor: 0.88,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: [
          SizedBox(
            height: 36,
            child: Stack(
              alignment: Alignment.center,
              children: [
                Container(
                  width: 42,
                  height: 4,
                  decoration: BoxDecoration(
                    color: const Color(0xFFD3DAE5),
                    borderRadius: BorderRadius.circular(99),
                  ),
                ),
                Align(
                  alignment: Alignment.centerRight,
                  child: IconButton(
                    tooltip: 'Cerrar',
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _ProductImageCarousel(
            images: galleryImages,
            title: product.name,
            accentColor: accentColor,
            controller: _imageController,
            selectedIndex: _imageIndex,
            onChanged: (index) => setState(() => _imageIndex = index),
          ),
          const SizedBox(height: 14),
          Text(
            product.name,
            style: Theme.of(context)
                .textTheme
                .titleLarge
                ?.copyWith(fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 4),
          Text(product.sku, style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _InfoChip(
                icon: Icons.payments_outlined,
                label: 'B2B ${_moneyFromUsd(b2bPrice)}',
              ),
              if (product.b2bDiscountPercent > 0)
                _InfoChip(
                  icon: Icons.local_offer_outlined,
                  label: product.b2bDiscountPercent > 0
                      ? '${product.b2bDiscountPercent.toStringAsFixed(0)}% ahorro'
                      : 'Oferta',
                ),
              if (referencePrice != null)
                _InfoChip(
                  icon: Icons.storefront_outlined,
                  label: 'PVP ${_moneyFromUsd(referencePrice)}',
                ),
              _StockBadge(stock: product.availableStock),
              if (product.requiresTechnicalValidation)
                const _InfoChip(
                  icon: Icons.engineering_outlined,
                  label: 'Validacion',
                ),
              if (product.requiresQuote)
                const _InfoChip(
                  icon: Icons.request_quote_outlined,
                  label: 'Cotizacion',
                ),
            ],
          ),
          const SizedBox(height: 14),
          Text(product.description),
          if (product.variants.isNotEmpty) ...[
            const SizedBox(height: 14),
            _InfoPanel(
              title: 'Opciones disponibles',
              lines: product.variants,
            ),
          ],
          if (product.specifications.isNotEmpty) ...[
            const SizedBox(height: 2),
            _InfoPanel(
              title: 'Ficha tecnica',
              lines: [
                for (final entry in product.specifications.entries)
                  '${entry.key}: ${entry.value}',
              ],
            ),
          ],
          const SizedBox(height: 14),
          _InfoPanel(
            title: 'Compatibilidad',
            lines: product.compatibilityNotes,
          ),
          if (product.pdfUrls.isNotEmpty) ...[
            const SizedBox(height: 2),
            _DocumentLinksPanel(
              title: 'Documentos tecnicos',
              urls: product.pdfUrls,
            ),
          ],
          _QuantitySelectorButton(
            quantity: _quantity,
            stock: product.availableStock,
            requiresQuote: product.requiresQuote,
            onPressed: canAdd ? _editQuantity : null,
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: () => Navigator.of(context).pop(),
              icon: const Icon(Icons.visibility_outlined),
              label: const Text('Cerrar detalle'),
            ),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: canAdd ? () => widget.onAddQuantity(_quantity) : null,
              icon: const Icon(Icons.add_shopping_cart),
              label: Text(
                !canAdd
                    ? 'Sin stock disponible'
                    : product.requiresQuote
                        ? 'Agregar para cotizar'
                        : 'Agregar $_quantity al carrito',
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: _fventasBlue.withValues(alpha: 0.1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 15, color: _fventasBlue),
          const SizedBox(width: 6),
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: _fventasBlue,
                  fontWeight: FontWeight.w800,
                ),
          ),
        ],
      ),
    );
  }
}

class _StockBadge extends StatelessWidget {
  const _StockBadge({required this.stock});

  final int stock;

  @override
  Widget build(BuildContext context) {
    final isOut = stock <= 0;
    final color = isOut ? const Color(0xFFC83232) : _fventasBlack;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: Colors.white.withValues(alpha: 0.94),
        border: Border.all(color: color.withValues(alpha: 0.18)),
      ),
      child: Text(
        isOut ? 'Bajo pedido' : '$stock disp.',
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

class CartScreen extends StatelessWidget {
  const CartScreen({
    super.key,
    required this.session,
    required this.onOpenCatalog,
  });

  final MobileUserSession session;
  final VoidCallback onOpenCatalog;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<List<MobileCartItem>>(
      valueListenable: mobileCartController,
      builder: (context, items, _) {
        if (items.isEmpty) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const _SectionTitle(title: 'Carrito'),
              const _AnnouncementsStrip(placement: 'checkout'),
              const _EmptyState(
                message: 'Agrega productos del catalogo para crear una orden',
              ),
              FilledButton.icon(
                onPressed: onOpenCatalog,
                icon: const Icon(Icons.search),
                label: const Text('Explorar catalogo'),
              ),
            ],
          );
        }

        final preview = mobileCartService.calculatePreview(
          items,
          exchangeRateUsdLocal: _exchangeRateUsdLocal(),
        );

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Row(
              children: [
                const Expanded(child: _SectionTitle(title: 'Carrito')),
                TextButton.icon(
                  onPressed: mobileCartController.clear,
                  icon: const Icon(Icons.delete_outline),
                  label: const Text('Vaciar'),
                ),
              ],
            ),
            for (final item in items)
              _CartItemTile(
                item: item,
                onIncrement: () => mobileCartController.increment(
                  item.productId,
                ),
                onDecrement: () => mobileCartController.decrement(
                  item.productId,
                ),
                onRemove: () => mobileCartController.remove(item.productId),
              ),
            if (session.mustChangePassword)
              const _InlineNotice(
                icon: Icons.shield_outlined,
                title: 'Clave temporal pendiente',
                message: 'Cambia la clave temporal antes de crear ordenes B2B.',
                color: _fventasBlue,
              ),
            const _AnnouncementsStrip(placement: 'checkout'),
            _CheckoutCommercePanel(
              items: items,
              preview: preview,
              session: session,
            ),
          ],
        );
      },
    );
  }
}

class _CheckoutCommercePanel extends StatefulWidget {
  const _CheckoutCommercePanel({
    required this.items,
    required this.preview,
    required this.session,
  });

  final List<MobileCartItem> items;
  final MobileCheckoutPreview preview;
  final MobileUserSession session;

  @override
  State<_CheckoutCommercePanel> createState() => _CheckoutCommercePanelState();
}

class _CheckoutCommercePanelState extends State<_CheckoutCommercePanel> {
  bool _initialized = false;
  String _saleType = "cash";
  int _paymentTermDays = 0;

  void _initialize(MobileCreditSnapshot? credit) {
    if (_initialized) {
      return;
    }

    final terms = _positiveTerms(
      credit?.allowedPaymentTermsDays ?? widget.session.allowedPaymentTermsDays,
    );
    final defaultTerm =
        terms.isNotEmpty ? terms.first : (credit?.paymentTermsDays ?? 0);
    final preferredSaleType = credit?.defaultSaleType.isNotEmpty == true
        ? credit!.defaultSaleType
        : widget.session.defaultSaleType;
    final canUseLine =
        credit?.creditEnabled == true && (credit?.creditAvailableUsd ?? 0) > 0;
    final canUseTerm = terms.isNotEmpty;

    _saleType = switch (preferredSaleType) {
      "credit_line" when canUseLine => "credit_line",
      "term_credit" when canUseTerm => "term_credit",
      _ => "cash",
    };
    _paymentTermDays = defaultTerm;
    _initialized = true;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<MobileCreditSnapshot>(
      future: mobileRepository.getCredit(widget.session.id),
      builder: (context, snapshot) {
        final credit = snapshot.data;
        _initialize(credit);

        final terms = _positiveTerms(
          credit?.allowedPaymentTermsDays ??
              widget.session.allowedPaymentTermsDays,
        );
        if (_saleType == "term_credit" && terms.isNotEmpty) {
          _paymentTermDays =
              terms.contains(_paymentTermDays) ? _paymentTermDays : terms.first;
        }
        final canUseTerm = terms.isNotEmpty;
        final canUseLine = credit?.creditEnabled == true &&
            (credit?.creditAvailableUsd ?? 0) > 0;
        final sellerName = credit?.assignedSeller.name.isNotEmpty == true
            ? credit!.assignedSeller.name
            : widget.session.assignedSeller.name;
        final selectedTerm = _saleType == "term_credit" ? _paymentTermDays : 0;
        final draft = MobileSecureOrderDraft(
          items: widget.items,
          preview: widget.preview,
          saleType: _saleType,
          paymentTermDays: selectedTerm,
        );

        return Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const _SoftIcon(icon: Icons.assignment_turned_in_outlined),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Condicion comercial',
                            style: Theme.of(context)
                                .textTheme
                                .titleMedium
                                ?.copyWith(fontWeight: FontWeight.w900),
                          ),
                          Text(
                            sellerName.isEmpty
                                ? 'Orden revisada por FVENTAS'
                                : 'Vendedor asignado: $sellerName',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: _fventasMuted,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    _SaleTypeChip(
                      label: 'Efectivo',
                      selected: _saleType == "cash",
                      onSelected: () => setState(() => _saleType = "cash"),
                    ),
                    _SaleTypeChip(
                      label: terms.isNotEmpty
                          ? 'Credito ${terms.first} dias'
                          : 'Credito plazo',
                      selected: _saleType == "term_credit",
                      enabled: canUseTerm,
                      onSelected: () => setState(() {
                        _saleType = "term_credit";
                        _paymentTermDays = terms.contains(_paymentTermDays)
                            ? _paymentTermDays
                            : terms.first;
                      }),
                    ),
                    _SaleTypeChip(
                      label: 'Linea de credito',
                      selected: _saleType == "credit_line",
                      enabled: canUseLine,
                      onSelected: () =>
                          setState(() => _saleType = "credit_line"),
                    ),
                  ],
                ),
                if (snapshot.hasError) ...[
                  const SizedBox(height: 12),
                  const _InlineNotice(
                    icon: Icons.cloud_off_outlined,
                    title: 'Credito no sincronizado',
                    message:
                        'Puedes enviar la solicitud como efectivo o revision. FVENTAS validara credito, saldo y condiciones.',
                    color: _fventasBlue,
                  ),
                ],
                if (_saleType == "term_credit" && terms.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final term in terms)
                        _SaleTypeChip(
                          label: '$term dias',
                          selected: _paymentTermDays == term,
                          onSelected: () =>
                              setState(() => _paymentTermDays = term),
                        ),
                    ],
                  ),
                ],
                const SizedBox(height: 14),
                _InfoPanel(
                  title: 'Resumen de compra',
                  compact: true,
                  lines: [
                    'Subtotal: ${_moneyFromUsd(widget.preview.subtotalUsd)}',
                    'Total: ${_moneyFromUsd(widget.preview.totalUsd)}',
                    'Condicion: ${_saleTypeLabel(_saleType, selectedTerm)}',
                    if (credit != null && _saleType == "credit_line")
                      'Credito disponible: ${_moneyFromUsd(credit.creditAvailableUsd)}',
                    widget.preview.requiresOperatorReview
                        ? 'Requiere revision operativa antes de confirmar.'
                        : 'Validacion operativa FVENTAS antes del despacho.',
                  ],
                ),
                const SizedBox(height: 10),
                _CreateOrderButton(draft: draft, session: widget.session),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _SaleTypeChip extends StatelessWidget {
  const _SaleTypeChip({
    required this.label,
    required this.selected,
    required this.onSelected,
    this.enabled = true,
  });

  final String label;
  final bool selected;
  final bool enabled;
  final VoidCallback onSelected;

  @override
  Widget build(BuildContext context) {
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      onSelected: enabled ? (_) => onSelected() : null,
      selectedColor: _fventasBlack,
      backgroundColor: enabled ? Colors.white : const Color(0xFFF1F3F5),
      labelStyle: TextStyle(
        color: selected
            ? Colors.white
            : (enabled ? _fventasInk : const Color(0xFFADB5BD)),
        fontWeight: FontWeight.w900,
      ),
      side: BorderSide(
        color: selected ? _fventasBlack : _fventasLine,
      ),
    );
  }
}

List<int> _positiveTerms(List<int> terms) {
  return terms.where((term) => term > 0).toSet().toList()..sort();
}

String _saleTypeLabel(String saleType, int paymentTermDays) {
  return switch (saleType) {
    "credit_line" => "Linea de credito",
    "term_credit" =>
      "Credito ${paymentTermDays > 0 ? paymentTermDays : 0} dias",
    _ => "Efectivo",
  };
}

class _CreateOrderButton extends StatefulWidget {
  const _CreateOrderButton({
    required this.draft,
    required this.session,
    this.blocker,
  });

  final MobileSecureOrderDraft draft;
  final MobileUserSession session;
  final String? blocker;

  @override
  State<_CreateOrderButton> createState() => _CreateOrderButtonState();
}

class _CreateOrderButtonState extends State<_CreateOrderButton> {
  bool _isSubmitting = false;

  Future<void> _createOrder() async {
    if (_isSubmitting) {
      return;
    }

    setState(() => _isSubmitting = true);

    try {
      final orderId = await mobileOrderService.createSecureOrder(widget.draft);
      mobileCartController.clear();

      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Orden $orderId registrada para revision')),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_friendlyMobileError(error))),
      );
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isBlocked =
        widget.blocker != null && widget.blocker!.trim().isNotEmpty;
    final label = widget.session.mustChangePassword
        ? 'Actualiza tu clave'
        : isBlocked
            ? 'Revisa condicion comercial'
            : (_isSubmitting ? 'Registrando orden' : 'Crear orden segura');
    return FilledButton.icon(
      onPressed: _isSubmitting || widget.session.mustChangePassword || isBlocked
          ? null
          : _createOrder,
      icon: _isSubmitting
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.lock_outline),
      label: Text(label),
    );
  }
}

class LocationsScreen extends StatelessWidget {
  const LocationsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: const [
        _SectionTitle(title: 'Puntos de entrega'),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            FilterChip(label: Text('Retiro'), selected: true, onSelected: null),
            FilterChip(
                label: Text('Clientes B2B'), selected: false, onSelected: null),
            FilterChip(
                label: Text('Servicio tecnico'),
                selected: false,
                onSelected: null),
            FilterChip(
                label: Text('Instalacion'), selected: false, onSelected: null),
          ],
        ),
        SizedBox(height: 12),
        _MapPreview(),
        SizedBox(height: 12),
        _LocationsList(),
      ],
    );
  }
}

String _productSubtitle(MobileProduct product) {
  if (product.requiresQuote) {
    return "Cotizacion asistida por FVENTAS";
  }

  if (product.requiresTechnicalValidation) {
    return "${product.availableStock} disp. - validar FVENTAS";
  }

  return "${product.availableStock} disp. - precio B2B";
}

int _cartQuantityForProduct(String productId) {
  return mobileCartController.value
      .where((item) => item.productId == productId)
      .fold<int>(0, (total, item) => total + item.quantity);
}

bool _canAddProductQuantity(
  BuildContext context,
  MobileProduct product,
  int quantity,
) {
  if (product.requiresQuote) {
    return true;
  }

  if (product.availableStock <= 0) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('${product.name} no tiene stock disponible')),
    );
    return false;
  }

  final quantityInCart = _cartQuantityForProduct(product.id);
  final remainingStock = product.availableStock - quantityInCart;
  if (remainingStock <= 0) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Ya tienes todo el stock disponible de ${product.name} en el carrito',
        ),
      ),
    );
    return false;
  }

  if (quantity > remainingStock) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Puedes agregar maximo $remainingStock uds mas de ${product.name}',
        ),
      ),
    );
    return false;
  }

  return true;
}

class OrderHistoryScreen extends StatelessWidget {
  const OrderHistoryScreen({super.key, required this.customerId});

  final String customerId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Ordenes',
          style: TextStyle(fontWeight: FontWeight.w900),
        ),
      ),
      body: FutureBuilder<List<MobileOrderSummary>>(
        future: mobileRepository.listOrders(customerId),
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const _LoadingState();
          }

          final orders = snapshot.data ?? [];
          if (orders.isEmpty) {
            return const _EmptyState(message: 'Sin ordenes registradas');
          }

          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              _OrderHistoryHeader(orders: orders),
              const SizedBox(height: 12),
              for (final order in orders) _CustomerOrderHistoryCard(order),
            ],
          );
        },
      ),
    );
  }
}

class _CustomerOrderHistoryCard extends StatelessWidget {
  const _CustomerOrderHistoryCard(this.order);

  final MobileOrderSummary order;

  @override
  Widget build(BuildContext context) {
    final status = _customerOrderStatus(order.status, order.paymentStatus);
    final stock = _customerStockStatus(order.stockStatus);
    final dueLabel = order.dueDate == null
        ? 'Sin vencimiento'
        : 'Vence ${_formatCustomerDate(order.dueDate!)}';
    final statusLabel = _compactCustomerStatusLabel(status.label);
    final balanceIsOpen = order.balanceUsd > 0;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: _fventasLine),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _SoftIcon(icon: status.icon, color: status.color),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        order.id,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.w900,
                              color: _fventasBlack,
                              height: 1,
                            ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${order.saleTypeLabel} - ${_formatCustomerDate(order.createdAt)}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: _fventasMuted,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                _StatusPill(label: statusLabel, color: status.color),
              ],
            ),
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                color: _fventasCanvas,
                border: Border.all(color: _fventasLine),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: _OrderHistoryMetric(
                      label: 'Total',
                      value: _moneyFromUsd(order.totalUsd),
                      color: _fventasBlack,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _OrderHistoryMetric(
                      label: balanceIsOpen ? 'Saldo' : 'Pagado',
                      value: _moneyFromUsd(order.balanceUsd),
                      color: balanceIsOpen
                          ? status.color
                          : const Color(0xFF198754),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _MiniChip(label: dueLabel, color: _fventasMuted),
                _MiniChip(
                    label: '${order.itemsCount} items', color: _fventasBlue),
                _MiniChip(label: stock, color: status.color),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _OrderHistoryHeader extends StatelessWidget {
  const _OrderHistoryHeader({required this.orders});

  final List<MobileOrderSummary> orders;

  @override
  Widget build(BuildContext context) {
    final openBalance =
        orders.fold<double>(0, (total, order) => total + order.balanceUsd);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: _fventasBlack,
      ),
      child: Row(
        children: [
          const _SoftIcon(
            icon: Icons.receipt_long_outlined,
            color: Colors.white,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Historial de ordenes',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w900,
                      ),
                ),
                Text(
                  '${orders.length} ordenes - saldo ${_moneyFromUsd(openBalance)}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Color(0xFFD4D4D4),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _OrderHistoryMetric extends StatelessWidget {
  const _OrderHistoryMetric({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            color: _fventasMuted,
            fontSize: 12,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 3),
        Text(
          value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                color: color,
                fontWeight: FontWeight.w900,
              ),
        ),
      ],
    );
  }
}

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({
    super.key,
    required this.session,
    required this.onSessionChanged,
    required this.onSignOut,
  });

  final MobileUserSession session;
  final Future<void> Function() onSessionChanged;
  final Future<void> Function() onSignOut;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final _currentPasswordController = TextEditingController();
  final _newPasswordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  bool _isChangingPassword = false;
  bool _isPasswordSheetOpen = false;
  bool _isRequestingDeletion = false;

  @override
  void dispose() {
    _currentPasswordController.dispose();
    _newPasswordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  Future<void> _changePassword() async {
    if (_isChangingPassword) {
      return;
    }
    if (_newPasswordController.text != _confirmPasswordController.text) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('La confirmacion no coincide.')),
      );
      return;
    }

    setState(() => _isChangingPassword = true);

    try {
      await mobileAuthRepository.changePassword(
        currentPassword: _currentPasswordController.text,
        newPassword: _newPasswordController.text,
      );
      if (!mounted) {
        return;
      }
      _currentPasswordController.clear();
      _newPasswordController.clear();
      _confirmPasswordController.clear();
      setState(() => _isChangingPassword = false);
      await widget.onSessionChanged();
      if (!mounted) {
        return;
      }
      if (_isPasswordSheetOpen && Navigator.of(context).canPop()) {
        Navigator.of(context).pop();
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Contrasena actualizada.')),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _isChangingPassword = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString())),
      );
    }
  }

  Future<void> _openPasswordChangeSheet() async {
    if (_isPasswordSheetOpen) {
      return;
    }

    _isPasswordSheetOpen = true;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        final bottomInset = MediaQuery.viewInsetsOf(sheetContext).bottom;

        return Padding(
          padding: EdgeInsets.only(bottom: bottomInset),
          child: DecoratedBox(
            decoration: const BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
            ),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(height: 10),
                  Container(
                    width: 42,
                    height: 4,
                    decoration: BoxDecoration(
                      color: _fventasLine,
                      borderRadius: BorderRadius.circular(99),
                    ),
                  ),
                  _PasswordChangePanel(
                    currentPasswordController: _currentPasswordController,
                    newPasswordController: _newPasswordController,
                    confirmPasswordController: _confirmPasswordController,
                    isSaving: _isChangingPassword,
                    requiredChange: true,
                    asCard: false,
                    onSubmit: _changePassword,
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
    _isPasswordSheetOpen = false;
  }

  Future<void> _requestAccountDeletion() async {
    if (_isRequestingDeletion) {
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Eliminar cuenta movil'),
          content: const Text(
            'FVENTAS bloqueara tu acceso movil y revisara la solicitud. '
            'Las ordenes, pagos, auditoria y registros comerciales se '
            'conservaran cuando sean necesarios para trazabilidad legal u '
            'operativa.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('Solicitar'),
            ),
          ],
        );
      },
    );

    if (confirmed != true) {
      return;
    }

    setState(() => _isRequestingDeletion = true);

    try {
      await mobileAuthRepository.requestAccountDeletion(
        reason: 'Solicitud desde app movil',
      );
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Solicitud registrada. Acceso movil bloqueado.'),
        ),
      );
      await widget.onSessionChanged();
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _isRequestingDeletion = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString())),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
      children: [
        _AccountHeaderCard(
          session: session,
          onOpenPasswordChange:
              session.mustChangePassword ? _openPasswordChangeSheet : null,
        ),
        _CreditSnapshotPanel(customerId: session.id),
        _OrderSummaryPanel(customerId: session.id),
        _ClientCommercePreferencesCard(session: session),
        _AccountActionPanel(
          isRequestingDeletion: _isRequestingDeletion,
          onOpenHistory: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => OrderHistoryScreen(customerId: session.id),
            ),
          ),
          onRequestDeletion: _requestAccountDeletion,
          onSignOut: widget.onSignOut,
        ),
      ],
    );
  }
}

class _AccountHeaderCard extends StatelessWidget {
  const _AccountHeaderCard({
    required this.session,
    this.onOpenPasswordChange,
  });

  final MobileUserSession session;
  final VoidCallback? onOpenPasswordChange;

  @override
  Widget build(BuildContext context) {
    final terms = _positiveTerms(
      session.purchaseConditions.allowedPaymentTermsDays.isNotEmpty
          ? session.purchaseConditions.allowedPaymentTermsDays
          : session.allowedPaymentTermsDays,
    );

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: _fventasLine),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const FVENTASLogo(compact: true, size: 54),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Cuenta comercial',
                        style: TextStyle(
                          color: _fventasMuted,
                          fontWeight: FontWeight.w800,
                          fontSize: 12,
                        ),
                      ),
                      Text(
                        session.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context)
                            .textTheme
                            .titleMedium
                            ?.copyWith(fontWeight: FontWeight.w900),
                      ),
                      Text(
                        session.email,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: _fventasMuted,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
                _StatusPill(
                  label: session.mustChangePassword ? 'Clave' : 'Activa',
                  color: session.mustChangePassword
                      ? _fventasBlue
                      : const Color(0xFF198754),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _StatusPill(
                  label: session.roleLabel,
                  color: _fventasBlack,
                ),
                _StatusPill(
                  label: _displayCurrencyLabel(),
                  color: _fventasBlue,
                ),
                _StatusPill(
                  label: 'Pais ${_marketCountryCode()}',
                  color: const Color(0xFF6C757D),
                ),
              ],
            ),
            const SizedBox(height: 14),
            LayoutBuilder(
              builder: (context, constraints) {
                final itemWidth = (constraints.maxWidth - 10) / 2;
                return Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    SizedBox(
                      width: itemWidth,
                      child: _AccountSignalTile(
                        icon: Icons.support_agent_outlined,
                        label: 'Ejecutivo',
                        value: session.assignedSeller.name.isEmpty
                            ? 'Por asignar'
                            : session.assignedSeller.name,
                      ),
                    ),
                    SizedBox(
                      width: itemWidth,
                      child: _AccountSignalTile(
                        icon: Icons.event_available_outlined,
                        label: 'Plazos',
                        value: terms.isEmpty
                            ? 'Contado'
                            : '${terms.join(", ")} dias',
                      ),
                    ),
                    SizedBox(
                      width: itemWidth,
                      child: const _AccountSignalTile(
                        icon: Icons.verified_user_outlined,
                        label: 'Validacion',
                        value: 'FVENTAS',
                      ),
                    ),
                    SizedBox(
                      width: itemWidth,
                      child: const _AccountSignalTile(
                        icon: Icons.business_outlined,
                        label: 'Empresa',
                        value: 'Aislada',
                      ),
                    ),
                  ],
                );
              },
            ),
            if (onOpenPasswordChange != null) ...[
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: onOpenPasswordChange,
                icon: const Icon(Icons.lock_reset_outlined),
                label: const Text('Actualizar clave temporal'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _AccountSignalTile extends StatelessWidget {
  const _AccountSignalTile({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minHeight: 76),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: _fventasCanvas,
        border: Border.all(color: _fventasLine),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: _fventasBlue, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: _fventasMuted,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  value,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: _fventasBlack,
                    fontWeight: FontWeight.w900,
                    height: 1.05,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AccountMetaLine extends StatelessWidget {
  const _AccountMetaLine({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 18, color: _fventasMuted),
        const SizedBox(width: 8),
        Text(
          '$label: ',
          style: const TextStyle(
            color: _fventasMuted,
            fontWeight: FontWeight.w800,
          ),
        ),
        Expanded(
          child: Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: _fventasBlack,
              fontWeight: FontWeight.w900,
            ),
          ),
        ),
      ],
    );
  }
}

class _ClientCommercePreferencesCard extends StatelessWidget {
  const _ClientCommercePreferencesCard({required this.session});

  final MobileUserSession session;

  @override
  Widget build(BuildContext context) {
    final conditions = session.purchaseConditions;
    final terms = _positiveTerms(
      conditions.allowedPaymentTermsDays.isNotEmpty
          ? conditions.allowedPaymentTermsDays
          : session.allowedPaymentTermsDays,
    );
    final paymentLabel = conditions.paymentTermsLabel.isNotEmpty
        ? conditions.paymentTermsLabel
        : terms.isEmpty
            ? 'Contado'
            : 'Contado / ${terms.join(", ")} dias';
    final exchangeLabel = conditions.exchangeRateLabel.isNotEmpty
        ? conditions.exchangeRateLabel
        : !_displaysPrimaryCurrency()
            ? '${_exchangeRateValueLabel()} ${_exchangeRateLabel()}'
            : '';

    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: _fventasLine),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const _SoftIcon(icon: Icons.tune_outlined),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    conditions.title.isEmpty
                        ? 'Condiciones de compra'
                        : conditions.title,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w900,
                          color: _fventasBlack,
                        ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            _PreferenceLine(
              icon: Icons.payments_outlined,
              label: 'Moneda',
              value: conditions.currencyLabel.isEmpty
                  ? _displayCurrencyLabel()
                  : conditions.currencyLabel,
            ),
            if (exchangeLabel.isNotEmpty)
              _PreferenceLine(
                icon: Icons.currency_exchange_outlined,
                label: 'Tasa referencial',
                value: exchangeLabel,
              ),
            _PreferenceLine(
              icon: Icons.event_available_outlined,
              label: 'Pago',
              value: paymentLabel,
            ),
            _PreferenceLine(
              icon: Icons.verified_user_outlined,
              label: 'Tipo base',
              value: conditions.defaultSaleTypeLabel.isEmpty
                  ? _saleTypeLabel(
                      session.defaultSaleType,
                      terms.isNotEmpty ? terms.first : 0,
                    )
                  : conditions.defaultSaleTypeLabel,
            ),
            _PreferenceLine(
              icon: Icons.lock_outline,
              label: 'Alcance',
              value: conditions.scopeLabel.isEmpty
                  ? 'Solo datos de tu empresa'
                  : conditions.scopeLabel,
            ),
            if (conditions.note.trim().isNotEmpty) ...[
              const SizedBox(height: 4),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: _fventasCanvas,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: _fventasLine),
                ),
                child: Text(
                  conditions.note.trim(),
                  style: const TextStyle(
                    color: _fventasMuted,
                    fontWeight: FontWeight.w700,
                    height: 1.25,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _PreferenceLine extends StatelessWidget {
  const _PreferenceLine({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: _fventasMuted, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: _fventasMuted,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  value,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: _fventasBlack,
                    fontWeight: FontWeight.w900,
                    height: 1.15,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AccountActionPanel extends StatelessWidget {
  const _AccountActionPanel({
    required this.isRequestingDeletion,
    required this.onOpenHistory,
    required this.onRequestDeletion,
    required this.onSignOut,
  });

  final bool isRequestingDeletion;
  final VoidCallback onOpenHistory;
  final VoidCallback onRequestDeletion;
  final Future<void> Function() onSignOut;

  @override
  Widget build(BuildContext context) {
    final dangerColor = Theme.of(context).colorScheme.error;

    return Card(
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: _fventasLine),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Acceso y seguridad',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w900,
                    color: _fventasBlack,
                  ),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: onOpenHistory,
              icon: const Icon(Icons.receipt_long_outlined),
              label: const Text('Ver historial de ordenes'),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: onSignOut,
              icon: const Icon(Icons.logout_outlined),
              label: const Text('Cerrar sesion'),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: isRequestingDeletion ? null : onRequestDeletion,
              style: OutlinedButton.styleFrom(
                foregroundColor: dangerColor,
                side: BorderSide(color: dangerColor.withValues(alpha: 0.45)),
              ),
              icon: isRequestingDeletion
                  ? SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: dangerColor,
                      ),
                    )
                  : const Icon(Icons.delete_outline),
              label: Text(
                isRequestingDeletion
                    ? 'Solicitando...'
                    : 'Solicitar eliminacion de cuenta',
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PasswordChangePanel extends StatefulWidget {
  const _PasswordChangePanel({
    required this.currentPasswordController,
    required this.newPasswordController,
    required this.confirmPasswordController,
    required this.isSaving,
    required this.requiredChange,
    required this.onSubmit,
    this.asCard = true,
  });

  final TextEditingController currentPasswordController;
  final TextEditingController newPasswordController;
  final TextEditingController confirmPasswordController;
  final bool isSaving;
  final bool requiredChange;
  final VoidCallback onSubmit;
  final bool asCard;

  @override
  State<_PasswordChangePanel> createState() => _PasswordChangePanelState();
}

class _PasswordChangePanelState extends State<_PasswordChangePanel> {
  bool _showCurrentPassword = false;
  bool _showNewPassword = false;
  bool _showConfirmPassword = false;

  InputDecoration _passwordDecoration({
    required String labelText,
    required IconData prefixIcon,
    required bool isVisible,
    required VoidCallback onToggle,
  }) {
    return InputDecoration(
      labelText: labelText,
      prefixIcon: Icon(prefixIcon),
      suffixIcon: IconButton(
        tooltip: isVisible ? 'Ocultar clave' : 'Ver clave',
        onPressed: onToggle,
        icon: Icon(
          isVisible ? Icons.visibility_off_outlined : Icons.visibility_outlined,
        ),
      ),
      border: const OutlineInputBorder(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final content = Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.security_outlined, color: _fventasBlue),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  widget.requiredChange
                      ? 'Actualiza tu clave temporal'
                      : 'Cambiar contrasena',
                  style: Theme.of(context)
                      .textTheme
                      .titleMedium
                      ?.copyWith(fontWeight: FontWeight.w900),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          const Text(
            'Usa una contrasena privada de al menos 10 caracteres con letras y numeros.',
            style: TextStyle(color: _fventasMuted),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: widget.currentPasswordController,
            obscureText: !_showCurrentPassword,
            decoration: _passwordDecoration(
              labelText: 'Contrasena actual',
              prefixIcon: Icons.lock_outline,
              isVisible: _showCurrentPassword,
              onToggle: () => setState(
                () => _showCurrentPassword = !_showCurrentPassword,
              ),
            ),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: widget.newPasswordController,
            obscureText: !_showNewPassword,
            decoration: _passwordDecoration(
              labelText: 'Nueva contrasena',
              prefixIcon: Icons.key_outlined,
              isVisible: _showNewPassword,
              onToggle: () => setState(
                () => _showNewPassword = !_showNewPassword,
              ),
            ),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: widget.confirmPasswordController,
            obscureText: !_showConfirmPassword,
            decoration: _passwordDecoration(
              labelText: 'Confirmar nueva contrasena',
              prefixIcon: Icons.verified_user_outlined,
              isVisible: _showConfirmPassword,
              onToggle: () => setState(
                () => _showConfirmPassword = !_showConfirmPassword,
              ),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: widget.isSaving ? null : widget.onSubmit,
              icon: widget.isSaving
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.shield_outlined),
              label: Text(
                widget.isSaving ? 'Guardando' : 'Guardar contrasena',
              ),
            ),
          ),
        ],
      ),
    );

    if (!widget.asCard) {
      return content;
    }

    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 12),
      child: content,
    );
  }
}

class _CreditSnapshotPanel extends StatelessWidget {
  const _CreditSnapshotPanel({required this.customerId});

  final String customerId;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<MobileCreditSnapshot>(
      future: mobileRepository.getCredit(customerId),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const _InfoPanel(
            title: 'Linea de credito',
            lines: ['Cargando informacion comercial...'],
          );
        }

        final credit = snapshot.data;
        if (credit == null) {
          return const _InfoPanel(
            title: 'Linea de credito',
            lines: ['Credito no disponible.'],
          );
        }

        return _CreditDashboardCard(credit: credit);
      },
    );
  }
}

class _CreditDashboardCard extends StatelessWidget {
  const _CreditDashboardCard({required this.credit});

  final MobileCreditSnapshot credit;

  @override
  Widget build(BuildContext context) {
    final enabled = credit.creditEnabled;
    final usedRatio = credit.creditLimitUsd <= 0
        ? 0.0
        : (credit.creditExposureUsd / credit.creditLimitUsd).clamp(0.0, 1.0);
    final statusColor = enabled ? const Color(0xFF198754) : _fventasBlue;
    final terms = _positiveTerms(credit.allowedPaymentTermsDays);

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: _fventasLine),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                _SoftIcon(icon: Icons.credit_card_outlined, color: statusColor),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Cupo comercial',
                        style: Theme.of(context)
                            .textTheme
                            .titleMedium
                            ?.copyWith(fontWeight: FontWeight.w900),
                      ),
                      Text(
                        enabled
                            ? 'Linea aprobada para compras B2B'
                            : 'Compra bajo revision comercial',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: _fventasMuted,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
                _StatusPill(
                  label: enabled ? 'Aprobado' : 'Revision',
                  color: statusColor,
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: _CommerceMetric(
                    label: 'Disponible',
                    value: _moneyFromUsd(credit.creditAvailableUsd),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _CommerceMetric(
                    label: 'Limite',
                    value: _moneyFromUsd(credit.creditLimitUsd),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: _CommerceMetric(
                    label: 'Usado',
                    value: _moneyFromUsd(credit.creditUsedUsd),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _CommerceMetric(
                    label: 'En ordenes',
                    value: _moneyFromUsd(credit.creditOrdersUsd),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: LinearProgressIndicator(
                minHeight: 8,
                value: usedRatio,
                backgroundColor: const Color(0xFFE9ECEF),
                color: statusColor,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              terms.isEmpty
                  ? 'Total comprometido ${_moneyFromUsd(credit.creditExposureUsd)}'
                  : 'Total comprometido ${_moneyFromUsd(credit.creditExposureUsd)} - plazos ${terms.join(", ")} dias',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: _fventasMuted,
                fontWeight: FontWeight.w700,
              ),
            ),
            if (credit.assignedSeller.name.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                'Ejecutivo asignado: ${credit.assignedSeller.name}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: _fventasMuted,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _OrderSummaryPanel extends StatelessWidget {
  const _OrderSummaryPanel({required this.customerId});

  final String customerId;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<MobileOrderSummary>>(
      future: mobileRepository.listOrders(customerId),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const _InfoPanel(
            title: 'Ordenes recientes',
            lines: ['Cargando historial...'],
          );
        }

        final orders = snapshot.data ?? [];
        if (orders.isEmpty) {
          return const _InfoPanel(
            title: 'Ordenes recientes',
            lines: ['Sin ordenes registradas.'],
          );
        }

        return Card(
          elevation: 0,
          margin: const EdgeInsets.only(bottom: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
            side: const BorderSide(color: _fventasLine),
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const _SoftIcon(icon: Icons.receipt_long_outlined),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Ordenes recientes',
                        style:
                            Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w900,
                                  color: _fventasBlack,
                                ),
                      ),
                    ),
                    _StatusPill(
                      label: '${orders.length}',
                      color: _fventasBlue,
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                for (final order in orders.take(3)) _CustomerOrderRow(order),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _CustomerOrderRow extends StatelessWidget {
  const _CustomerOrderRow(this.order);

  final MobileOrderSummary order;

  @override
  Widget build(BuildContext context) {
    final status = _customerOrderStatus(order.status, order.paymentStatus);
    final stock = _customerStockStatus(order.stockStatus);
    final isCancelled = order.status.toLowerCase().contains('cancel');
    final amountLabel =
        isCancelled || order.balanceUsd <= 0 ? 'Total' : 'Saldo';
    final amount = isCancelled || order.balanceUsd <= 0
        ? order.totalUsd
        : order.balanceUsd;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: _fventasCanvas,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: _fventasLine),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(status.icon, color: status.color, size: 24),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        order.id,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w900,
                              color: _fventasBlack,
                            ),
                      ),
                    ),
                    Text(
                      _formatCustomerDate(order.createdAt),
                      style: const TextStyle(
                        color: _fventasMuted,
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 3),
                Text(
                  '${status.label} - $stock',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: _fventasMuted,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  '$amountLabel ${_moneyFromUsd(amount)}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        color: status.color,
                        fontWeight: FontWeight.w900,
                      ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

({String label, IconData icon, Color color}) _customerOrderStatus(
  String status,
  String paymentStatus,
) {
  final normalized = status.toLowerCase();
  final payment = paymentStatus.toLowerCase();

  if (normalized.contains('cancel')) {
    return (
      label: 'Cancelada',
      icon: Icons.cancel_outlined,
      color: const Color(0xFFDC3545)
    );
  }
  if (normalized.contains('approved')) {
    return (
      label: 'Aprobada con credito',
      icon: Icons.check_circle_outline,
      color: const Color(0xFF198754)
    );
  }
  if (payment.contains('partial') || normalized.contains('partial')) {
    return (
      label: 'Pago parcial',
      icon: Icons.payments_outlined,
      color: _fventasBlue
    );
  }
  if (payment.contains('paid')) {
    return (
      label: 'Pagada',
      icon: Icons.verified_outlined,
      color: const Color(0xFF198754)
    );
  }
  return (
    label: 'En revision FVENTAS',
    icon: Icons.schedule_outlined,
    color: _fventasBlue
  );
}

String _compactCustomerStatusLabel(String label) {
  return switch (label) {
    'Aprobada con credito' => 'Aprobada',
    'En revision FVENTAS' => 'Revision',
    _ => label,
  };
}

String _customerStockStatus(String stockStatus) {
  final normalized = stockStatus.toLowerCase();
  if (normalized.contains('reserved')) {
    return 'stock reservado';
  }
  if (normalized.contains('released')) {
    return 'stock liberado';
  }
  if (normalized.contains('partial')) {
    return 'stock parcial';
  }
  return 'stock por confirmar';
}

String _formatCustomerDate(DateTime value) {
  const months = [
    'ene',
    'feb',
    'mar',
    'abr',
    'may',
    'jun',
    'jul',
    'ago',
    'sep',
    'oct',
    'nov',
    'dic',
  ];
  return '${value.day.toString().padLeft(2, '0')} ${months[value.month - 1]}';
}

class _InfoPanel extends StatelessWidget {
  const _InfoPanel({
    required this.title,
    required this.lines,
    this.compact = false,
  });

  final String title;
  final List<String> lines;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final content = Padding(
      padding: EdgeInsets.all(compact ? 12 : 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(fontWeight: FontWeight.w900, color: _fventasBlack),
          ),
          const SizedBox(height: 8),
          for (final line in lines)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(
                line,
                style: const TextStyle(color: _fventasMuted),
              ),
            ),
        ],
      ),
    );

    if (compact) {
      return Container(
        width: double.infinity,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          color: const Color(0xFFF8F9FA),
          border: Border.all(color: _fventasLine),
        ),
        child: content,
      );
    }

    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 12),
      child: content,
    );
  }
}

class _DocumentLinksPanel extends StatelessWidget {
  const _DocumentLinksPanel({
    required this.title,
    required this.urls,
  });

  final String title;
  final List<String> urls;

  Future<void> _open(BuildContext context, String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null || !uri.hasScheme) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('URL de documento no valida.')),
      );
      return;
    }

    final opened = await launchUrl(
      uri,
      mode: LaunchMode.externalApplication,
    );
    if (!opened && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No se pudo abrir el documento.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const _SoftIcon(
                  icon: Icons.description_outlined,
                  color: _fventasBlack,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    title,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w900,
                          color: _fventasBlack,
                        ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            for (var index = 0; index < urls.length; index++)
              Padding(
                padding:
                    EdgeInsets.only(bottom: index == urls.length - 1 ? 0 : 8),
                child: OutlinedButton.icon(
                  onPressed: () => _open(context, urls[index]),
                  icon: const Icon(Icons.picture_as_pdf_outlined),
                  label: Text('Abrir documento ${index + 1}'),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _SoftIcon extends StatelessWidget {
  const _SoftIcon({
    required this.icon,
    this.color = _fventasBlue,
  });

  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    const size = 42.0;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(size * 0.34),
        color: color.withValues(alpha: 0.1),
      ),
      child: Icon(icon, color: color, size: size * 0.48),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: color.withValues(alpha: 0.1),
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

class _InlineNotice extends StatelessWidget {
  const _InlineNotice({
    required this.icon,
    required this.title,
    required this.message,
    required this.color,
  });

  final IconData icon;
  final String title;
  final String message;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        color: color.withValues(alpha: 0.08),
        border: Border.all(color: color.withValues(alpha: 0.18)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  message,
                  style: const TextStyle(
                    color: _fventasMuted,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AnnouncementsStrip extends StatefulWidget {
  const _AnnouncementsStrip({required this.placement});

  final String placement;

  @override
  State<_AnnouncementsStrip> createState() => _AnnouncementsStripState();
}

class _AnnouncementsStripState extends State<_AnnouncementsStrip> {
  final _controller = PageController();
  int _index = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<MobileAnnouncement>>(
      future: mobileRepository.listAnnouncements(widget.placement),
      builder: (context, snapshot) {
        final announcements = snapshot.data ?? [];

        if (snapshot.connectionState != ConnectionState.done ||
            announcements.isEmpty) {
          return const SizedBox.shrink();
        }

        if (announcements.length == 1) {
          return _AnnouncementCard(announcement: announcements.first);
        }

        return Column(
          children: [
            SizedBox(
              height: 178,
              child: PageView.builder(
                controller: _controller,
                itemCount: announcements.length,
                onPageChanged: (value) => setState(() => _index = value),
                itemBuilder: (context, index) {
                  return _AnnouncementCard(announcement: announcements[index]);
                },
              ),
            ),
            const SizedBox(height: 4),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                for (var index = 0; index < announcements.length; index++)
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 180),
                    width: _index == index ? 18 : 7,
                    height: 7,
                    margin: const EdgeInsets.symmetric(horizontal: 3),
                    decoration: BoxDecoration(
                      color: _index == index
                          ? _fventasBlue
                          : _fventasMuted.withValues(alpha: 0.22),
                      borderRadius: BorderRadius.circular(99),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 8),
          ],
        );
      },
    );
  }
}

class _AnnouncementCard extends StatelessWidget {
  const _AnnouncementCard({required this.announcement});

  final MobileAnnouncement announcement;

  @override
  Widget build(BuildContext context) {
    final imageUrl = announcement.imageUrl;

    if (imageUrl?.isNotEmpty == true) {
      return Container(
        margin: const EdgeInsets.only(bottom: 12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          color: _fventasBlack,
          boxShadow: [
            BoxShadow(
              color: _fventasBlack.withValues(alpha: 0.12),
              blurRadius: 22,
              offset: const Offset(0, 12),
            ),
          ],
        ),
        clipBehavior: Clip.antiAlias,
        child: AspectRatio(
          aspectRatio: 16 / 7,
          child: Stack(
            fit: StackFit.expand,
            children: [
              Image.network(
                imageUrl!,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const _AnnouncementFallbackArt(),
              ),
              const DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      Color(0xCC101010),
                      Color(0x66101010),
                      Color(0x00101010),
                    ],
                    begin: Alignment.centerLeft,
                    end: Alignment.centerRight,
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    _StatusPill(
                      label: announcement.ctaLabel?.isNotEmpty == true
                          ? announcement.ctaLabel!
                          : 'FVENTAS',
                      color: Colors.white,
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: 230,
                      child: Text(
                        announcement.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style:
                            Theme.of(context).textTheme.titleMedium?.copyWith(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w900,
                                  height: 1.04,
                                ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    }

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const _SoftIcon(icon: Icons.campaign_outlined),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    announcement.title,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w900,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(announcement.body),
                  if (announcement.ctaLabel?.isNotEmpty == true) ...[
                    const SizedBox(height: 8),
                    Text(
                      announcement.ctaLabel!,
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(
                            color: Theme.of(context).colorScheme.primary,
                            fontWeight: FontWeight.w900,
                          ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AnnouncementFallbackArt extends StatelessWidget {
  const _AnnouncementFallbackArt();

  @override
  Widget build(BuildContext context) {
    return const ColoredBox(
      color: _fventasBlack,
      child: Align(
        alignment: Alignment.centerRight,
        child: Padding(
          padding: EdgeInsets.only(right: 24),
          child: Icon(
            Icons.campaign_outlined,
            size: 74,
            color: _fventasBlue,
          ),
        ),
      ),
    );
  }
}

class _CartItemTile extends StatelessWidget {
  const _CartItemTile({
    required this.item,
    required this.onIncrement,
    required this.onDecrement,
    required this.onRemove,
  });

  final MobileCartItem item;
  final VoidCallback onIncrement;
  final VoidCallback onDecrement;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final lineTotal = item.quantity * item.unitPriceUsd;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _ProductThumb(imageUrl: item.imageUrl),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context)
                            .textTheme
                            .titleSmall
                            ?.copyWith(fontWeight: FontWeight.w900),
                      ),
                      const SizedBox(height: 3),
                      Text(item.sku),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Quitar',
                  onPressed: onRemove,
                  icon: const Icon(Icons.close),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Text(
                  _moneyFromUsd(lineTotal),
                  style: Theme.of(context)
                      .textTheme
                      .titleSmall
                      ?.copyWith(fontWeight: FontWeight.w900),
                ),
                const Spacer(),
                IconButton.filledTonal(
                  tooltip: 'Restar',
                  onPressed: onDecrement,
                  icon: const Icon(Icons.remove),
                ),
                SizedBox(
                  width: 38,
                  child: Text(
                    item.quantity.toString(),
                    textAlign: TextAlign.center,
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.w900),
                  ),
                ),
                IconButton.filledTonal(
                  tooltip: 'Sumar',
                  onPressed: onIncrement,
                  icon: const Icon(Icons.add),
                ),
              ],
            ),
            if (item.requiresQuote || item.requiresTechnicalValidation) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  if (item.requiresQuote)
                    const _InfoChip(
                      icon: Icons.request_quote_outlined,
                      label: 'Cotizacion',
                    ),
                  if (item.requiresTechnicalValidation)
                    const _InfoChip(
                      icon: Icons.engineering_outlined,
                      label: 'Validacion tecnica',
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _HeroPanel extends StatelessWidget {
  const _HeroPanel({required this.onOpenCatalog});

  final VoidCallback onOpenCatalog;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 352,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        color: _fventasBlack,
        boxShadow: [
          BoxShadow(
            color: _fventasBlack.withValues(alpha: 0.18),
            blurRadius: 28,
            offset: const Offset(0, 14),
          ),
        ],
      ),
      child: Stack(
        children: [
          Positioned(
            right: -26,
            bottom: -38,
            child: Icon(
              Icons.agriculture_outlined,
              size: 168,
              color: Colors.white.withValues(alpha: 0.08),
            ),
          ),
          Positioned(
            right: 18,
            top: 18,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(999),
                color: _fventasBlue,
              ),
              child: Text(
                _displayCurrencySymbol(),
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w900,
                  fontSize: 12,
                ),
              ),
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _HeroChip(
                icon: Icons.local_fire_department,
                label: 'FVENTAS ecommerce',
              ),
              const SizedBox(height: 24),
              Text(
                'Maquinaria lista para trabajar',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w900,
                      height: 0.98,
                    ),
              ),
              const SizedBox(height: 10),
              const SizedBox(
                width: 260,
                child: Text(
                  'Compra equipos, repuestos y accesorios con precio B2B y stock vigente.',
                  style: TextStyle(color: Color(0xFFD9D9D9), height: 1.35),
                ),
              ),
              const SizedBox(height: 18),
              FilledButton.icon(
                onPressed: onOpenCatalog,
                icon: const Icon(Icons.arrow_forward),
                label: const Text('Explorar catalogo'),
                style: FilledButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: _fventasBlack,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _HeroChip extends StatelessWidget {
  const _HeroChip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: Colors.white.withValues(alpha: 0.14),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: _fventasBlue, size: 16),
          const SizedBox(width: 6),
          Text(label, style: const TextStyle(color: Colors.white)),
        ],
      ),
    );
  }
}

class _AsyncList<T> extends StatelessWidget {
  const _AsyncList({
    required this.future,
    required this.itemBuilder,
  });

  final Future<List<T>> future;
  final Widget Function(T item) itemBuilder;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<T>>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const _LoadingState();
        }

        if (snapshot.hasError) {
          return _ErrorState(
            title: 'No pudimos cargar la informacion',
            message: _friendlyMobileError(snapshot.error),
          );
        }

        final items = snapshot.data ?? [];

        if (items.isEmpty) {
          return const _EmptyState(message: 'Sin datos disponibles');
        }

        return Column(
          children: [
            for (final item in items) itemBuilder(item),
          ],
        );
      },
    );
  }
}

class _LocationsList extends StatelessWidget {
  const _LocationsList();

  @override
  Widget build(BuildContext context) {
    return _AsyncList<MobileLocation>(
      future: mobileRepository.listLocations(),
      itemBuilder: (location) => _ServiceLocationCard(location: location),
    );
  }
}

class _ServiceLocationCard extends StatelessWidget {
  const _ServiceLocationCard({required this.location});

  final MobileLocation location;

  Future<void> _openPhone(BuildContext context) async {
    final phone = location.phone.trim();
    if (phone.isEmpty) {
      return;
    }
    final uri = Uri(scheme: 'tel', path: phone.replaceAll(' ', ''));
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri);
      return;
    }
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No se pudo abrir el telefono.')),
      );
    }
  }

  Future<void> _openWhatsApp(BuildContext context) async {
    final digits = location.whatsapp.replaceAll(RegExp(r'[^0-9]'), '');
    if (digits.isEmpty) {
      return;
    }
    final uri = Uri.parse('https://wa.me/$digits');
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
      return;
    }
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No se pudo abrir WhatsApp.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final hasPhone = location.phone.trim().isNotEmpty;
    final hasWhatsApp = location.whatsapp.trim().isNotEmpty;
    final hasAddress = location.address.trim().isNotEmpty;

    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SoftIcon(icon: Icons.build_circle_outlined),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        location.name,
                        style:
                            Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w900,
                                ),
                      ),
                      if (location.subtitle.isNotEmpty) ...[
                        const SizedBox(height: 3),
                        Text(
                          location.subtitle,
                          style: const TextStyle(
                            color: _fventasMuted,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
            if (hasAddress) ...[
              const SizedBox(height: 12),
              _AccountMetaLine(
                icon: Icons.location_on_outlined,
                label: 'Direccion',
                value: location.address,
              ),
            ],
            if (location.specialties.isNotEmpty) ...[
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final specialty in location.specialties)
                    _StatusPill(
                      label: specialty,
                      color: _fventasBlue,
                    ),
                ],
              ),
            ],
            if (hasPhone || hasWhatsApp) ...[
              const SizedBox(height: 14),
              Row(
                children: [
                  if (hasPhone)
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () => _openPhone(context),
                        icon: const Icon(Icons.call_outlined),
                        label: const Text('Llamar'),
                      ),
                    ),
                  if (hasPhone && hasWhatsApp) const SizedBox(width: 10),
                  if (hasWhatsApp)
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: () => _openWhatsApp(context),
                        icon: const Icon(Icons.chat_outlined),
                        label: const Text('WhatsApp'),
                      ),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _LoadingState extends StatelessWidget {
  const _LoadingState({
    this.message = 'Sincronizando con FVENTAS',
    this.compact = false,
  });

  final String message;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    if (compact) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            const SizedBox(width: 8),
            Text(
              message,
              style: const TextStyle(
                color: _fventasMuted,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      );
    }

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 12),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 24),
        child: Row(
          children: [
            const _SoftIcon(icon: Icons.sync_outlined),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    message,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w900,
                        ),
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Sincronizando catalogo comercial.',
                    style: TextStyle(
                      color: _fventasMuted,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(strokeWidth: 2.4),
            ),
          ],
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({
    required this.message,
    this.title = 'Sin informacion',
    this.icon = Icons.inbox_outlined,
    this.actionLabel,
    this.onAction,
  });

  final String message;
  final String title;
  final IconData icon;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 12),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _SoftIcon(icon: icon),
            const SizedBox(height: 12),
            Text(
              title,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w900,
                  ),
            ),
            const SizedBox(height: 6),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: _fventasMuted,
                fontWeight: FontWeight.w700,
              ),
            ),
            if (actionLabel != null && onAction != null) ...[
              const SizedBox(height: 14),
              OutlinedButton.icon(
                onPressed: onAction,
                icon: const Icon(Icons.refresh_outlined),
                label: Text(actionLabel!),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({
    required this.title,
    required this.message,
    this.onRetry,
  });

  final String title;
  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 12),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SoftIcon(
                  icon: Icons.cloud_off_outlined,
                  color: Color(0xFFC83232),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: Theme.of(context)
                            .textTheme
                            .titleMedium
                            ?.copyWith(fontWeight: FontWeight.w900),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        message,
                        style: const TextStyle(
                          color: _fventasMuted,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            if (onRetry != null) ...[
              const SizedBox(height: 14),
              OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh_outlined),
                label: const Text('Reintentar'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

String _friendlyMobileError(Object? error) {
  final raw = (error ?? 'Error desconocido').toString().trim();
  if (raw.isEmpty) {
    return 'No se pudo completar la operacion.';
  }
  return raw
      .replaceFirst('Bad state: ', '')
      .replaceFirst('Exception: ', '')
      .replaceFirst('ClientException: ', '');
}

class _MapPreview extends StatelessWidget {
  const _MapPreview();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 180,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        color: _fventasBlack,
        border: Border.all(color: _fventasBlack),
      ),
      child: Stack(
        children: [
          Positioned(
            right: -24,
            bottom: -30,
            child: Icon(
              Icons.location_on_outlined,
              size: 150,
              color: Colors.white.withValues(alpha: 0.08),
            ),
          ),
          const Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.map_outlined, size: 42, color: _fventasBlue),
                SizedBox(height: 10),
                Text(
                  'Red autorizada FVENTAS',
                  style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                Text(
                  'Retiro, entregas y soporte tecnico',
                  style: TextStyle(color: Color(0xFFD9D9D9)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SearchBox extends StatelessWidget {
  const _SearchBox({
    this.controller,
    this.onChanged,
    this.onTap,
    this.readOnly = false,
    required this.labelText,
  });

  final TextEditingController? controller;
  final ValueChanged<String>? onChanged;
  final VoidCallback? onTap;
  final bool readOnly;
  final String labelText;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      onChanged: onChanged,
      onTap: onTap,
      readOnly: readOnly,
      textInputAction: TextInputAction.search,
      decoration: InputDecoration(
        prefixIcon: const Icon(Icons.search, color: _fventasMuted),
        hintText: labelText,
        filled: true,
        fillColor: Colors.white,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: _fventasLine),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: _fventasLine),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: _fventasBlue, width: 1.5),
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({
    required this.title,
    this.actionLabel,
    this.onAction,
  });

  final String title;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: 12),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w900,
                    color: _fventasBlack,
                  ),
            ),
          ),
          if (actionLabel != null)
            TextButton(
              onPressed: onAction,
              child: Text(
                actionLabel!,
                style: const TextStyle(
                  color: _fventasBlue,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _ProductImageCarousel extends StatelessWidget {
  const _ProductImageCarousel({
    required this.images,
    required this.title,
    required this.accentColor,
    required this.controller,
    required this.selectedIndex,
    required this.onChanged,
  });

  final List<String> images;
  final String title;
  final Color accentColor;
  final PageController controller;
  final int selectedIndex;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final safeImages = images.isEmpty ? <String?>[null] : images;
    final hasGallery = safeImages.length > 1;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Stack(
          children: [
            AspectRatio(
              aspectRatio: 16 / 10,
              child: PageView.builder(
                controller: controller,
                itemCount: safeImages.length,
                onPageChanged: onChanged,
                itemBuilder: (context, index) => _ProductDetailMedia(
                  imageUrl: safeImages[index],
                  title: title,
                  accentColor: accentColor,
                ),
              ),
            ),
            if (hasGallery)
              Positioned(
                right: 12,
                top: 12,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.7),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    '${selectedIndex + 1}/${safeImages.length}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w900,
                      fontSize: 12,
                    ),
                  ),
                ),
              ),
            if (hasGallery)
              Positioned(
                left: 0,
                right: 0,
                bottom: 12,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    for (var index = 0; index < safeImages.length; index++)
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 180),
                        width: index == selectedIndex ? 18 : 7,
                        height: 7,
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(999),
                          color: index == selectedIndex
                              ? accentColor
                              : Colors.white.withValues(alpha: 0.85),
                        ),
                      ),
                  ],
                ),
              ),
          ],
        ),
        if (hasGallery) ...[
          const SizedBox(height: 10),
          SizedBox(
            height: 68,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: safeImages.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (context, index) => GestureDetector(
                onTap: () => controller.animateToPage(
                  index,
                  duration: const Duration(milliseconds: 220),
                  curve: Curves.easeOutCubic,
                ),
                child: _ProductThumb(
                  imageUrl: safeImages[index],
                  selected: index == selectedIndex,
                  accentColor: accentColor,
                ),
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _ProductDetailMedia extends StatelessWidget {
  const _ProductDetailMedia({
    required this.title,
    required this.accentColor,
    this.imageUrl,
  });

  final String title;
  final Color accentColor;
  final String? imageUrl;

  @override
  Widget build(BuildContext context) {
    final hasImage = imageUrl != null && imageUrl!.isNotEmpty;

    return AspectRatio(
      aspectRatio: 16 / 10,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                accentColor.withValues(alpha: 0.22),
                _fventasBlue.withValues(alpha: 0.12),
                Colors.white,
              ],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
          child: Stack(
            children: [
              Positioned(
                right: -26,
                bottom: -34,
                child: Icon(
                  Icons.agriculture_outlined,
                  size: 150,
                  color: accentColor.withValues(alpha: 0.12),
                ),
              ),
              Positioned.fill(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: hasImage
                      ? _catalogImage(
                          imageUrl: imageUrl!,
                          fit: BoxFit.contain,
                          semanticLabel: title,
                          fallbackBuilder: () =>
                              _ProductFallbackMark(accentColor: accentColor),
                        )
                      : _ProductFallbackMark(accentColor: accentColor),
                ),
              ),
              Positioned(
                left: 14,
                bottom: 14,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(999),
                    color: Colors.white.withValues(alpha: 0.92),
                    border: Border.all(
                      color: accentColor.withValues(alpha: 0.2),
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.verified_outlined,
                          size: 15, color: accentColor),
                      const SizedBox(width: 6),
                      Text(
                        'FVENTAS stock',
                        style: TextStyle(
                          color: accentColor,
                          fontSize: 12,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ProductFallbackMark extends StatelessWidget {
  const _ProductFallbackMark({required this.accentColor});

  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        width: 96,
        height: 96,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Colors.white,
          border: Border.all(color: accentColor.withValues(alpha: 0.22)),
          boxShadow: [
            BoxShadow(
              color: accentColor.withValues(alpha: 0.18),
              blurRadius: 24,
              offset: const Offset(0, 12),
            ),
          ],
        ),
        child: const Icon(
          Icons.inventory_2_outlined,
          color: _fventasBlack,
          size: 48,
        ),
      ),
    );
  }
}

class _ProductTile extends StatelessWidget {
  const _ProductTile({
    required this.sku,
    required this.title,
    required this.subtitle,
    required this.badge,
    this.imageUrl,
    this.priceUsd,
    this.originalPriceUsd,
    this.discountPercent = 0,
    this.category = "",
    this.variants = const [],
    this.stock,
    this.requiresQuote = false,
    this.onTap,
    this.onAddQuantity,
  });

  final String sku;
  final String title;
  final String subtitle;
  final String badge;
  final String? imageUrl;
  final double? priceUsd;
  final double? originalPriceUsd;
  final double discountPercent;
  final String category;
  final List<String> variants;
  final int? stock;
  final bool requiresQuote;
  final VoidCallback? onTap;
  final ValueChanged<int>? onAddQuantity;

  @override
  Widget build(BuildContext context) {
    final hasDiscount =
        discountPercent > 0 || ((originalPriceUsd ?? 0) > (priceUsd ?? 0));
    final accentColor = _productAccentColor(category);
    final effectiveImageUrl = _effectiveProductImage(
      imageUrl: imageUrl,
      title: title,
      category: category,
    );

    return InkWell(
      borderRadius: BorderRadius.circular(18),
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          color: Colors.white,
          border: Border.all(color: _fventasLine),
          boxShadow: [
            BoxShadow(
              color: _fventasBlack.withValues(alpha: 0.05),
              blurRadius: 14,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Stack(
              children: [
                _ProductImageFrame(
                  imageUrl: effectiveImageUrl,
                  accentColor: accentColor,
                ),
                if (hasDiscount)
                  Positioned(
                    top: 8,
                    left: 8,
                    child: _SaleBadge(discountPercent: discountPercent),
                  ),
                Positioned(
                  top: 8,
                  right: 8,
                  child: _StockBadge(stock: stock ?? 0),
                ),
              ],
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (category.isNotEmpty) ...[
                      Text(
                        category,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              color: accentColor,
                              fontWeight: FontWeight.w900,
                            ),
                      ),
                      const SizedBox(height: 3),
                    ],
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: _fventasBlack,
                            fontWeight: FontWeight.w900,
                            height: 1.04,
                          ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      subtitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: _fventasMuted,
                          ),
                    ),
                    const Spacer(),
                    if (hasDiscount && originalPriceUsd != null)
                      Text(
                        _moneyFromUsd(originalPriceUsd!),
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              decoration: TextDecoration.lineThrough,
                              color: _fventasMuted,
                            ),
                      ),
                    Text(
                      priceUsd == null ? 'Cotizar' : _moneyFromUsd(priceUsd!),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: _fventasBlack,
                            fontWeight: FontWeight.w900,
                          ),
                    ),
                    const SizedBox(height: 7),
                    _ProductCardActions(
                      stock: stock ?? 0,
                      requiresQuote: requiresQuote,
                      accentColor: accentColor,
                      onAddQuantity: onAddQuantity,
                    ),
                  ],
                ),
              ),
            )
          ],
        ),
      ),
    );
  }
}

class _ProductCardActions extends StatefulWidget {
  const _ProductCardActions({
    required this.stock,
    required this.requiresQuote,
    required this.accentColor,
    this.onAddQuantity,
  });

  final int stock;
  final bool requiresQuote;
  final Color accentColor;
  final ValueChanged<int>? onAddQuantity;

  @override
  State<_ProductCardActions> createState() => _ProductCardActionsState();
}

class _ProductCardActionsState extends State<_ProductCardActions> {
  int _quantity = 1;

  Future<void> _editQuantity() async {
    final selected = await _showQuantityPicker(
      context,
      initialQuantity: _quantity,
      stock: widget.stock,
      allowBeyondStock: widget.requiresQuote,
    );

    if (!mounted || selected == null) {
      return;
    }

    setState(() => _quantity = selected);
  }

  @override
  Widget build(BuildContext context) {
    final canAdd = widget.requiresQuote || widget.stock > 0;

    return Row(
      children: [
        SizedBox(
          width: 54,
          child: OutlinedButton.icon(
            onPressed: canAdd ? _editQuantity : null,
            icon: const Icon(Icons.format_list_numbered, size: 15),
            label: Text('$_quantity'),
            style: OutlinedButton.styleFrom(
              minimumSize: const Size(0, 32),
              padding: const EdgeInsets.symmetric(horizontal: 6),
              foregroundColor: widget.accentColor,
              side:
                  BorderSide(color: widget.accentColor.withValues(alpha: 0.4)),
              textStyle: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
        ),
        const SizedBox(width: 6),
        Expanded(
          child: FilledButton(
            onPressed: canAdd && widget.onAddQuantity != null
                ? () => widget.onAddQuantity!(_quantity)
                : null,
            style: FilledButton.styleFrom(
              minimumSize: const Size(0, 32),
              padding: const EdgeInsets.symmetric(horizontal: 8),
              backgroundColor: widget.accentColor,
              foregroundColor: Colors.white,
              disabledBackgroundColor: _fventasLine,
              disabledForegroundColor: _fventasMuted,
              textStyle: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w900,
              ),
            ),
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.add_shopping_cart, size: 16),
                  const SizedBox(width: 4),
                  Text(
                    canAdd ? 'Agregar' : 'Sin stock',
                    maxLines: 1,
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _QuantitySelectorButton extends StatelessWidget {
  const _QuantitySelectorButton({
    required this.quantity,
    required this.stock,
    required this.requiresQuote,
    required this.onPressed,
  });

  final int quantity;
  final int stock;
  final bool requiresQuote;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final helper = requiresQuote
        ? 'Cantidad para cotizar'
        : stock <= 0
            ? 'Sin stock disponible'
            : 'Disponible: $stock uds';

    return OutlinedButton.icon(
      onPressed: onPressed,
      icon: const Icon(Icons.format_list_numbered),
      label: Text('Cantidad $quantity - $helper'),
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(46),
        alignment: Alignment.centerLeft,
        foregroundColor: _fventasBlack,
        side: const BorderSide(color: _fventasLine),
      ),
    );
  }
}

Future<int?> _showQuantityPicker(
  BuildContext context, {
  required int initialQuantity,
  required int stock,
  required bool allowBeyondStock,
}) async {
  final limit = allowBeyondStock
      ? 999
      : stock <= 0
          ? 1
          : stock;
  int normalize(int value) {
    if (value < 1) {
      return 1;
    }
    if (value > limit) {
      return limit;
    }
    return value;
  }

  var quantity = normalize(initialQuantity);
  final controller = TextEditingController(text: quantity.toString());

  final result = await showDialog<int>(
    context: context,
    builder: (dialogContext) {
      return StatefulBuilder(
        builder: (context, setDialogState) {
          void setQuantity(int value) {
            final normalized = normalize(value);
            setDialogState(() => quantity = normalized);
            controller.text = normalized.toString();
            controller.selection = TextSelection.fromPosition(
              TextPosition(offset: controller.text.length),
            );
          }

          return AlertDialog(
            title: const Text('Cantidad a comprar'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  allowBeyondStock
                      ? 'Ingresa la cantidad para cotizar.'
                      : 'Maximo disponible: $limit uds.',
                  style: const TextStyle(color: _fventasMuted),
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    IconButton.filledTonal(
                      onPressed: () => setQuantity(quantity - 1),
                      icon: const Icon(Icons.remove),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: TextField(
                        controller: controller,
                        keyboardType: TextInputType.number,
                        textAlign: TextAlign.center,
                        onChanged: (value) {
                          final parsed = int.tryParse(value);
                          if (parsed != null) {
                            quantity = normalize(parsed);
                          }
                        },
                        decoration: const InputDecoration(
                          labelText: 'Unidades',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    IconButton.filledTonal(
                      onPressed: () => setQuantity(quantity + 1),
                      icon: const Icon(Icons.add),
                    ),
                  ],
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: const Text('Cancelar'),
              ),
              FilledButton(
                onPressed: () {
                  final parsed = int.tryParse(controller.text);
                  Navigator.of(dialogContext)
                      .pop(normalize(parsed ?? quantity));
                },
                child: const Text('Aplicar'),
              ),
            ],
          );
        },
      );
    },
  );

  controller.dispose();
  return result;
}

Color _productAccentColor(String value) {
  final normalized = value.toLowerCase();
  if (normalized.contains('repuesto')) {
    return const Color(0xFFFF6A1A);
  }
  if (normalized.contains('industrial')) {
    return _fventasBlack;
  }
  if (normalized.contains('maquinaria') ||
      normalized.contains('jardin') ||
      normalized.contains('bosque')) {
    return const Color(0xFFD83B00);
  }
  return _fventasBlue;
}

bool _isAssetImage(String imageUrl) => imageUrl.startsWith('asset:');

String _assetImagePath(String imageUrl) => imageUrl.replaceFirst('asset:', '');

String? _effectiveProductImage({
  required String? imageUrl,
  required String title,
  required String category,
}) {
  final explicit = imageUrl?.trim() ?? '';
  if (explicit.isNotEmpty) {
    return explicit;
  }

  final normalized = '$title $category'.toLowerCase();
  if (normalized.contains('motosierra')) {
    return 'asset:assets/products/motosierra-45cc.png';
  }
  if (normalized.contains('cadena')) {
    return 'asset:assets/products/cadena-18.png';
  }
  if (normalized.contains('motobomba') || normalized.contains('bomba')) {
    return 'asset:assets/products/motobomba-3x3.png';
  }
  return null;
}

Widget _catalogImage({
  required String imageUrl,
  required BoxFit fit,
  String? semanticLabel,
  required Widget Function() fallbackBuilder,
}) {
  if (_isAssetImage(imageUrl)) {
    return Image.asset(
      _assetImagePath(imageUrl),
      fit: fit,
      semanticLabel: semanticLabel,
      errorBuilder: (_, __, ___) => fallbackBuilder(),
    );
  }

  return Image.network(
    imageUrl,
    fit: fit,
    semanticLabel: semanticLabel,
    errorBuilder: (_, __, ___) => fallbackBuilder(),
  );
}

class _ProductImageFrame extends StatelessWidget {
  const _ProductImageFrame({
    this.imageUrl,
    this.accentColor = _fventasBlue,
  });

  final String? imageUrl;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 1.45,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(0),
        child: imageUrl == null || imageUrl!.isEmpty
            ? _FVENTASProductPlaceholder(accentColor: accentColor)
            : ColoredBox(
                color: accentColor.withValues(alpha: 0.08),
                child: Padding(
                  padding: const EdgeInsets.all(8),
                  child: _catalogImage(
                    imageUrl: imageUrl!,
                    fit: BoxFit.contain,
                    fallbackBuilder: () => const Center(
                      child: Icon(Icons.image_not_supported_outlined),
                    ),
                  ),
                ),
              ),
      ),
    );
  }
}

class _FVENTASProductPlaceholder extends StatelessWidget {
  const _FVENTASProductPlaceholder({
    this.accentColor = _fventasBlue,
  });

  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            accentColor.withValues(alpha: 0.16),
            _fventasBlue.withValues(alpha: 0.08),
            const Color(0xFFF8FAFD),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Stack(
        children: [
          Positioned(
            right: -18,
            bottom: -20,
            child: Icon(
              Icons.agriculture_outlined,
              size: 104,
              color: accentColor.withValues(alpha: 0.12),
            ),
          ),
          Center(
            child: Container(
              width: 74,
              height: 74,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white,
                border: Border.all(color: accentColor.withValues(alpha: 0.16)),
                boxShadow: [
                  BoxShadow(
                    color: accentColor.withValues(alpha: 0.16),
                    blurRadius: 20,
                    offset: const Offset(0, 10),
                  ),
                ],
              ),
              child: const Icon(
                Icons.inventory_2_outlined,
                size: 40,
                color: _fventasBlack,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SaleBadge extends StatelessWidget {
  const _SaleBadge({required this.discountPercent});

  final double discountPercent;

  @override
  Widget build(BuildContext context) {
    final label = discountPercent > 0
        ? '-${discountPercent.toStringAsFixed(0)}%'
        : 'Oferta';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: _fventasBlue,
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w900,
          fontSize: 11,
        ),
      ),
    );
  }
}

class _ProductThumb extends StatelessWidget {
  const _ProductThumb({
    this.imageUrl,
    this.selected = false,
    this.accentColor = _fventasBlue,
  });

  final String? imageUrl;
  final bool selected;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: selected ? accentColor : const Color(0xFFE3E8F0),
          width: selected ? 2 : 1,
        ),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: SizedBox(
          width: 78,
          height: 78,
          child: imageUrl == null || imageUrl!.isEmpty
              ? const ColoredBox(
                  color: Color(0xFFEFF4FB),
                  child: Icon(Icons.inventory_2_outlined),
                )
              : ColoredBox(
                  color: const Color(0xFFF8FAFD),
                  child: Padding(
                    padding: const EdgeInsets.all(6),
                    child: _catalogImage(
                      imageUrl: imageUrl!,
                      fit: BoxFit.contain,
                      fallbackBuilder: () => const Center(
                        child: Icon(Icons.image_not_supported_outlined),
                      ),
                    ),
                  ),
                ),
        ),
      ),
    );
  }
}
