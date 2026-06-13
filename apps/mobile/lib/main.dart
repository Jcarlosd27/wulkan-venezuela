import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'src/auth/mobile_auth.dart';
import 'src/brand/wulkan_logo.dart';
import 'src/bootstrap/mobile_bootstrap.dart';
import 'src/cart/mobile_cart_service.dart';
import 'src/config/mobile_environment.dart';
import 'src/data/mobile_repository.dart';
import 'src/domain/mobile_models.dart';
import 'src/orders/mobile_order_service.dart';

const _wulkanOrange = Color(0xFFFF4B00);
const _wulkanBlack = Color(0xFF101010);
const _wulkanInk = Color(0xFF242424);
const _wulkanMuted = Color(0xFF767676);
const _wulkanCanvas = Color(0xFFFAF8F6);
const _wulkanSurface = Color(0xFFFFFFFF);
const _wulkanLine = Color(0xFFEDE8E4);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  mobileEnvironment.validateRuntime();
  await configureMobileRuntime();
  await mobileCartController.load();
  runApp(const WulkanApp());
}

class WulkanApp extends StatelessWidget {
  const WulkanApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Wulkan',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: _wulkanOrange,
          primary: _wulkanOrange,
          secondary: _wulkanBlack,
          error: const Color(0xFFC83232),
          surface: _wulkanSurface,
          onSurface: _wulkanInk,
        ),
        scaffoldBackgroundColor: _wulkanCanvas,
        appBarTheme: const AppBarTheme(
          backgroundColor: _wulkanCanvas,
          foregroundColor: _wulkanBlack,
          elevation: 0,
          scrolledUnderElevation: 0,
          centerTitle: false,
        ),
        cardTheme: CardThemeData(
          color: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(18),
            side: const BorderSide(color: _wulkanLine),
          ),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            backgroundColor: _wulkanOrange,
            foregroundColor: Colors.white,
            minimumSize: const Size(48, 48),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
            ),
          ),
        ),
        navigationBarTheme: NavigationBarThemeData(
          backgroundColor: Colors.white,
          indicatorColor: _wulkanOrange.withValues(alpha: 0.12),
          labelTextStyle: WidgetStateProperty.resolveWith(
            (states) => TextStyle(
              color: states.contains(WidgetState.selected)
                  ? _wulkanOrange
                  : _wulkanMuted,
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
        useMaterial3: true,
      ),
      home: const WulkanSessionGate(),
    );
  }
}

class WulkanSessionGate extends StatefulWidget {
  const WulkanSessionGate({super.key});

  @override
  State<WulkanSessionGate> createState() => _WulkanSessionGateState();
}

class _WulkanSessionGateState extends State<WulkanSessionGate> {
  late Future<MobileUserSession> _sessionFuture;

  @override
  void initState() {
    super.initState();
    _sessionFuture = mobileAuthRepository.getCurrentSession();
  }

  void _setSession(MobileUserSession session) {
    setState(() {
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
          return WulkanLoginScreen(onAuthenticated: _setSession);
        }

        return WulkanShell(
          session: session,
          onSessionChanged: _refreshSession,
          onSignOut: _signOut,
        );
      },
    );
  }
}

class WulkanLoginScreen extends StatefulWidget {
  const WulkanLoginScreen({super.key, required this.onAuthenticated});

  final ValueChanged<MobileUserSession> onAuthenticated;

  @override
  State<WulkanLoginScreen> createState() => _WulkanLoginScreenState();
}

class _WulkanLoginScreenState extends State<WulkanLoginScreen> {
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
          content: Text('Solicitud recibida. Wulkan validara tu acceso movil.'),
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
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: _wulkanBlack,
                  borderRadius: BorderRadius.circular(26),
                  boxShadow: [
                    BoxShadow(
                      color: _wulkanBlack.withValues(alpha: 0.18),
                      blurRadius: 26,
                      offset: const Offset(0, 14),
                    ),
                  ],
                ),
                child: const Center(
                  child: WulkanLogo(compact: true, onDark: true),
                ),
              ),
            ),
            const SizedBox(height: 22),
            Text(
              'Wulkan B2B',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w900,
                    color: _wulkanBlack,
                  ),
            ),
            const SizedBox(height: 6),
            const Text(
              'Acceso para ferreteros autorizados',
              textAlign: TextAlign.center,
              style:
                  TextStyle(color: _wulkanMuted, fontWeight: FontWeight.w700),
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
                  color: _wulkanOrange,
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
        border: Border.all(color: _wulkanLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _SoftIcon(icon: icon, color: _wulkanOrange),
          Text(
            label,
            style: const TextStyle(
              color: _wulkanBlack,
              fontWeight: FontWeight.w900,
            ),
          ),
        ],
      ),
    );
  }
}

class WulkanShell extends StatefulWidget {
  const WulkanShell({
    super.key,
    required this.session,
    required this.onSessionChanged,
    required this.onSignOut,
  });

  final MobileUserSession session;
  final Future<void> Function() onSessionChanged;
  final Future<void> Function() onSignOut;

  @override
  State<WulkanShell> createState() => _WulkanShellState();
}

class _WulkanShellState extends State<WulkanShell> {
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
            const WulkanLogo(compact: true),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Wulkan',
                  style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16),
                ),
                Text(
                  widget.session.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: _wulkanMuted,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
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
                  backgroundColor: _wulkanOrange,
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
            const WulkanLogo(compact: true),
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
            color: _wulkanOrange,
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
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final screens = [
      SellerHomeScreen(
        session: widget.session,
        onOpenCatalog: () => setState(() => _index = 1),
        onOpenOrder: () => setState(() => _index = 2),
        onOpenClients: () => setState(() => _index = 3),
      ),
      const CatalogScreen(),
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
            const WulkanLogo(compact: true),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Ventas Wulkan',
                    style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16),
                  ),
                  Text(
                    widget.session.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: _wulkanMuted,
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
                tooltip: 'Pedido asistido',
                onPressed: () => setState(() => _index = 2),
                icon: Badge(
                  isLabelVisible: count > 0,
                  backgroundColor: _wulkanOrange,
                  label: Text(count.toString()),
                  child: const Icon(Icons.assignment_add),
                ),
              );
            },
          ),
          IconButton(
            tooltip: 'Cerrar sesion',
            onPressed: widget.onSignOut,
            icon: const Icon(Icons.logout),
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
              icon: Icon(Icons.grid_view_outlined), label: 'Catalogo'),
          NavigationDestination(
              icon: Icon(Icons.assignment_add), label: 'Pedido'),
          NavigationDestination(
              icon: Icon(Icons.storefront_outlined), label: 'Clientes'),
          NavigationDestination(
              icon: Icon(Icons.payments_outlined), label: 'Comisiones'),
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
            backgroundColor: _wulkanOrange,
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
            color: _wulkanSurface,
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: _wulkanLine),
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
                  'Sincronizando alertas Wulkan',
                  style: TextStyle(
                    color: _wulkanBlack,
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
              color: _wulkanSurface,
              borderRadius: BorderRadius.circular(26),
              border: Border.all(color: _wulkanLine),
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
                        color: _wulkanBlack,
                        fontWeight: FontWeight.w900,
                      ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Las notificaciones de pedidos, credito, stock y comisiones apareceran aqui cuando exista una accion pendiente.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: _wulkanMuted,
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
        color: _wulkanSurface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: notification.isUnread
              ? color.withValues(alpha: .28)
              : _wulkanLine,
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
                          color: _wulkanBlack,
                        ),
                      ),
                    ),
                    if (notification.isUnread)
                      Container(
                        width: 8,
                        height: 8,
                        decoration: const BoxDecoration(
                          color: _wulkanOrange,
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
                    color: _wulkanMuted,
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
                      color: _wulkanInk,
                    ),
                    if (notification.entityId.isNotEmpty)
                      _MiniChip(
                        label: notification.entityId,
                        color: _wulkanMuted,
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
  return _wulkanOrange;
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
        _PromoCarousel(onOpenCatalog: onOpenCatalog),
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
      padding: const EdgeInsets.fromLTRB(18, 8, 18, 24),
      children: [
        _SearchBox(
          labelText: 'Buscar producto para pedido asistido',
          readOnly: true,
          onTap: onOpenCatalog,
        ),
        const SizedBox(height: 14),
        _SellerSummaryCard(
          session: session,
          onOpenOrder: onOpenOrder,
          onOpenClients: onOpenClients,
        ),
        const SizedBox(height: 18),
        _SectionTitle(
          title: 'Ordenes de cartera',
          actionLabel: 'Tomar pedido',
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
    required this.onOpenOrder,
    required this.onOpenClients,
  });

  final MobileUserSession session;
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

        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(24),
            color: _wulkanBlack,
            boxShadow: [
              BoxShadow(
                color: _wulkanBlack.withValues(alpha: 0.14),
                blurRadius: 28,
                offset: const Offset(0, 16),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const _SoftIcon(
                    icon: Icons.badge_outlined,
                    color: Colors.white,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          session.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style:
                              Theme.of(context).textTheme.titleLarge?.copyWith(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w900,
                                  ),
                        ),
                        Text(
                          sellerMeta.isEmpty
                              ? (summary?.roleLabel ?? session.roleLabel)
                              : sellerMeta,
                          style: const TextStyle(
                            color: Color(0xFFD4D4D4),
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
                  _StatusPill(
                    label: isLoading ? 'Sync' : 'Cartera',
                    color: Colors.white,
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(16),
                  color: Colors.white.withValues(alpha: 0.08),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.12),
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
                            color: Color(0xFFD4D4D4),
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        Text(
                          isLoading
                              ? 'Sync'
                              : '${(summary?.goalProgressPercent ?? 0).toStringAsFixed(0)}%',
                          style: const TextStyle(
                            color: Colors.white,
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
                        backgroundColor: Colors.white24,
                        valueColor: const AlwaysStoppedAnimation<Color>(
                          _wulkanOrange,
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      isLoading
                          ? 'Sincronizando cartera'
                          : 'USD ${(summary?.salesMonthUsd ?? 0).toStringAsFixed(0)} de USD ${(summary?.salesGoalUsd ?? 0).toStringAsFixed(0)}',
                      style: const TextStyle(
                        color: Color(0xFFD4D4D4),
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
                    child: _DarkMetric(
                      label: 'Clientes',
                      value: isLoading
                          ? '...'
                          : '${summary?.activeClientsCount ?? summary?.clientsCount ?? 0}/${summary?.clientsCount ?? 0}',
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _DarkMetric(
                      label: 'Ticket prom.',
                      value: isLoading
                          ? '...'
                          : 'USD ${(summary?.ticketAverageUsd ?? 0).toStringAsFixed(0)}',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: _DarkMetric(
                      label: 'Comision pend.',
                      value: isLoading
                          ? '...'
                          : 'USD ${(summary?.pendingCommissionUsd ?? 0).toStringAsFixed(2)}',
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _DarkMetric(
                      label: 'Credito por aprobar',
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
                      onPressed: onOpenOrder,
                      icon: const Icon(Icons.assignment_add),
                      label: const Text('Pedido'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: onOpenClients,
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.white,
                        side: const BorderSide(color: Colors.white54),
                      ),
                      icon: const Icon(Icons.storefront_outlined),
                      label: const Text('Clientes'),
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
  int _paymentTermDays = 10;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<List<MobileCartItem>>(
      valueListenable: mobileCartController,
      builder: (context, items, _) {
        if (items.isEmpty) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const _SectionTitle(title: 'Pedido asistido'),
              const _EmptyState(
                message: 'Agrega productos del catalogo para tomar un pedido',
              ),
              FilledButton.icon(
                onPressed: widget.onOpenCatalog,
                icon: const Icon(Icons.search),
                label: const Text('Explorar catalogo'),
              ),
            ],
          );
        }

        final preview = mobileCartService.calculatePreview(items);

        return FutureBuilder<List<MobileSellerClient>>(
          future: mobileRepository.listSellerClients(),
          builder: (context, snapshot) {
            final clients = snapshot.data ?? [];
            if (_selectedClientId.isEmpty && clients.isNotEmpty) {
              _selectedClientId = clients.first.id;
            }

            final selectedTerm =
                _saleType == "term_credit" ? _paymentTermDays : 0;
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
                    const Expanded(
                        child: _SectionTitle(title: 'Pedido asistido')),
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
                            'Cliente ferretero',
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
                            onChanged: (value) => setState(
                              () => _selectedClientId = value ?? "",
                            ),
                          ),
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
                              onSelected: () =>
                                  setState(() => _saleType = "term_credit"),
                            ),
                            _SaleTypeChip(
                              label: 'Linea de credito',
                              selected: _saleType == "credit_line",
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
                              for (final term in const [10, 15, 20, 30, 40])
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
                            'Total USD ${preview.totalUsd.toStringAsFixed(2)}',
                            'Referencia VES ${preview.totalVes.toStringAsFixed(2)}',
                            'Condicion: ${_saleTypeLabel(_saleType, selectedTerm)}',
                          ],
                        ),
                        const SizedBox(height: 10),
                        _CreateOrderButton(
                          draft: draft,
                          session: widget.session,
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
    final stateController = TextEditingController();
    final cityController = TextEditingController();
    final addressController = TextEditingController();
    final creditController = TextEditingController();
    final notesController = TextEditingController();

    Future<void> disposeControllers() async {
      businessNameController.dispose();
      emailController.dispose();
      phoneController.dispose();
      taxIdController.dispose();
      contactNameController.dispose();
      stateController.dispose();
      cityController.dispose();
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

        Future<void> submit(StateSetter setSheetState) async {
          if (isSaving || formKey.currentState?.validate() != true) {
            return;
          }
          setSheetState(() => isSaving = true);
          try {
            final requestedCredit = double.tryParse(
                  creditController.text.trim().replaceAll(',', '.'),
                ) ??
                0;
            final result = await mobileRepository.createSellerClient(
              MobileSellerClientDraft(
                businessName: businessNameController.text.trim(),
                email: emailController.text.trim().toLowerCase(),
                phone: phoneController.text.trim(),
                taxId: taxIdController.text.trim(),
                contactName: contactNameController.text.trim(),
                state: stateController.text.trim(),
                city: cityController.text.trim(),
                address: addressController.text.trim(),
                notes: notesController.text.trim(),
                creditRequestedUsd: requestedCredit,
                defaultSaleType: requestedCredit > 0 ? 'term_credit' : 'cash',
                allowedPaymentTermsDays: requestedCredit > 0
                    ? const [0, 10, 15, 20, 30, 40]
                    : const [0],
              ),
            );
            if (sheetContext.mounted) {
              Navigator.of(sheetContext).pop(result);
            }
          } catch (error) {
            if (!sheetContext.mounted) {
              return;
            }
            setSheetState(() => isSaving = false);
            ScaffoldMessenger.of(sheetContext).showSnackBar(
              SnackBar(
                content: Text(
                  error.toString().replaceFirst('Bad state: ', ''),
                ),
              ),
            );
          }
        }

        return StatefulBuilder(
          builder: (context, setSheetState) {
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
                            color: _wulkanLine,
                            borderRadius: BorderRadius.circular(99),
                          ),
                        ),
                      ),
                      const SizedBox(height: 18),
                      Text(
                        'Nuevo cliente ferretero',
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.w900,
                            ),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Quedara asignado a tu cartera y el credito pasara a aprobacion comercial.',
                        style: TextStyle(
                          color: _wulkanMuted,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 16),
                      TextFormField(
                        controller: businessNameController,
                        textInputAction: TextInputAction.next,
                        decoration: const InputDecoration(
                          labelText: 'Razon social / ferreteria',
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
                          final email = value?.trim() ?? '';
                          if (email.isEmpty) {
                            return 'Ingresa el correo';
                          }
                          if (!email.contains('@')) {
                            return 'Correo no valido';
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
                              decoration: const InputDecoration(
                                labelText: 'Telefono',
                                border: OutlineInputBorder(),
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: TextFormField(
                              controller: taxIdController,
                              textInputAction: TextInputAction.next,
                              decoration: const InputDecoration(
                                labelText: 'RIF',
                                border: OutlineInputBorder(),
                              ),
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
                      Row(
                        children: [
                          Expanded(
                            child: TextFormField(
                              controller: stateController,
                              textInputAction: TextInputAction.next,
                              decoration: const InputDecoration(
                                labelText: 'Estado',
                                border: OutlineInputBorder(),
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: TextFormField(
                              controller: cityController,
                              textInputAction: TextInputAction.next,
                              decoration: const InputDecoration(
                                labelText: 'Ciudad',
                                border: OutlineInputBorder(),
                              ),
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
                        decoration: const InputDecoration(
                          labelText: 'Cupo solicitado USD',
                          helperText:
                              'Opcional. El gerente lo aprueba en el panel.',
                          prefixIcon: Icon(Icons.credit_card_outlined),
                          border: OutlineInputBorder(),
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
                            isSaving ? 'Creando cliente' : 'Crear cliente',
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
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Cliente creado'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(created.client.businessName),
            const SizedBox(height: 10),
            const Text(
              'Clave temporal',
              style: TextStyle(fontWeight: FontWeight.w900),
            ),
            SelectableText(created.temporaryPassword),
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
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Row(
              children: [
                const Expanded(child: _SectionTitle(title: 'Clientes')),
                FilledButton.icon(
                  onPressed: _showCreateClientSheet,
                  icon: const Icon(Icons.person_add_alt_1),
                  label: const Text('Nuevo'),
                ),
              ],
            ),
            const SizedBox(height: 8),
            const _InlineNotice(
              icon: Icons.assignment_ind_outlined,
              title: 'Cartera comercial',
              message:
                  'Los clientes creados aqui quedan asignados a tu usuario vendedor.',
              color: _wulkanOrange,
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

class _SellerClientsSyncCard extends StatelessWidget {
  const _SellerClientsSyncCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _wulkanLine),
        boxShadow: [
          BoxShadow(
            color: _wulkanBlack.withValues(alpha: 0.04),
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
              color: _wulkanOrange.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Padding(
              padding: EdgeInsets.all(10),
              child: CircularProgressIndicator(
                strokeWidth: 2.5,
                color: _wulkanOrange,
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
                        color: _wulkanBlack,
                        fontWeight: FontWeight.w900,
                      ),
                ),
                const SizedBox(height: 2),
                const Text(
                  'Sincronizando clientes asignados, cupo y estado comercial.',
                  style: TextStyle(
                    color: _wulkanMuted,
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
                      color: _wulkanMuted,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Disponible USD ${client.creditAvailableUsd.toStringAsFixed(2)}',
                    style: const TextStyle(fontWeight: FontWeight.w900),
                  ),
                  Text(
                    client.email,
                    style: const TextStyle(color: _wulkanMuted),
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
    return (label: 'Contado', color: _wulkanMuted);
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
              const _CommissionPolicyNotice(),
              const SizedBox(height: 12),
              if (orders.isEmpty)
                const _EmptyState(
                  title: 'Sin comisiones',
                  message:
                      'Cuando tus pedidos sean registrados y evaluados por Wulkan, veras aqui el estado de liquidacion.',
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
          colors: [_wulkanBlack, Color(0xFF2C1A12)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        boxShadow: [
          BoxShadow(
            color: _wulkanBlack.withValues(alpha: 0.14),
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
                  color: _wulkanOrange.withValues(alpha: 0.18),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Padding(
                  padding: EdgeInsets.all(12),
                  child: CircularProgressIndicator(
                    strokeWidth: 2.6,
                    color: _wulkanOrange,
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
          colors: [_wulkanBlack, Color(0xFF2C1A12)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        boxShadow: [
          BoxShadow(
            color: _wulkanBlack.withValues(alpha: 0.18),
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
                  color: _wulkanOrange.withValues(alpha: 0.18),
                  borderRadius: BorderRadius.circular(16),
                ),
                child:
                    const Icon(Icons.payments_outlined, color: _wulkanOrange),
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
                color: _wulkanOrange,
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            'USD ${totalCommission.toStringAsFixed(2)}',
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
                  value:
                      'USD ${summary.pendingCommissionUsd.toStringAsFixed(2)}',
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _DarkMetric(
                  label: 'Aprobada',
                  value:
                      'USD ${summary.approvedCommissionUsd.toStringAsFixed(2)}',
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _DarkMetric(
                  label: 'Pagada',
                  value: 'USD ${summary.paidCommissionUsd.toStringAsFixed(2)}',
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
                selectedColor: _wulkanBlack,
                backgroundColor: Colors.white,
                side: BorderSide(
                  color: selected == filter ? _wulkanBlack : _wulkanLine,
                ),
                labelStyle: TextStyle(
                  color: selected == filter ? Colors.white : _wulkanInk,
                  fontWeight: FontWeight.w900,
                ),
                avatar: Icon(
                  _commissionFilterIcon(filter),
                  size: 16,
                  color: selected == filter ? Colors.white : _wulkanMuted,
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

class _CommissionPolicyNotice extends StatelessWidget {
  const _CommissionPolicyNotice();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF3CD),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFFFE69C)),
      ),
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.verified_user_outlined, color: Color(0xFF996404)),
          SizedBox(width: 10),
          Expanded(
            child: Text(
              'La comision queda trazada por orden y se libera segun validacion comercial, entrega o cobro definido por Wulkan.',
              style: TextStyle(
                color: Color(0xFF664D03),
                fontWeight: FontWeight.w800,
                height: 1.35,
              ),
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
                          color: _wulkanMuted,
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
                    value: 'USD ${order.commissionUsd.toStringAsFixed(2)}',
                    color: commission.color,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _CommissionAmountTile(
                    label: 'Venta',
                    value: 'USD ${order.totalUsd.toStringAsFixed(2)}',
                    color: _wulkanInk,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _MiniChip(label: order.saleTypeLabel, color: _wulkanOrange),
                _MiniChip(label: orderStatus.label, color: orderStatus.color),
                _MiniChip(
                  label: '${order.itemsCount} items',
                  color: _wulkanMuted,
                ),
                if (rate > 0)
                  _MiniChip(
                    label: '${(rate * 100).toStringAsFixed(1)}%',
                    color: commission.color,
                  ),
                if (order.dueDate != null)
                  _MiniChip(
                    label: 'Vence ${_formatCustomerDate(order.dueDate!)}',
                    color: _wulkanMuted,
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
        border: Border.all(color: _wulkanLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: _wulkanMuted,
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
      return 'Liquidada por Wulkan. Esta comision ya forma parte del historial pagado.';
    case _CommissionFilter.approved:
      return 'Aprobada comercialmente. Queda lista para liquidacion segun el cierre interno.';
    case _CommissionFilter.blocked:
      return 'Retenida o anulada. Revisa con gerencia comercial antes de considerarla cobrable.';
    case _CommissionFilter.pending:
    case _CommissionFilter.all:
      if (order.balanceUsd > 0) {
        return 'Pendiente por saldo de cliente: USD ${order.balanceUsd.toStringAsFixed(2)}.';
      }
      if (order.stockStatus.toLowerCase().contains('reserved')) {
        return 'Pedido con stock reservado. Falta validacion de entrega o cierre comercial.';
      }
      return 'Pendiente de validacion Wulkan para liberar la comision.';
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
                      color: _wulkanMuted,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Total USD ${order.totalUsd.toStringAsFixed(2)}',
                    style: const TextStyle(fontWeight: FontWeight.w900),
                  ),
                  if (showCommission)
                    Text(
                      'Comision USD ${order.commissionUsd.toStringAsFixed(2)} - ${order.commissionStatusLabel}',
                      style: const TextStyle(
                        color: _wulkanMuted,
                        fontWeight: FontWeight.w700,
                      ),
                    )
                  else
                    Text(
                      'Saldo USD ${order.balanceUsd.toStringAsFixed(2)}',
                      style: const TextStyle(color: _wulkanMuted),
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
            height: 104,
            child: Center(child: CircularProgressIndicator()),
          );
        }

        return SizedBox(
          height: 104,
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
            border: Border.all(color: _wulkanLine),
            boxShadow: [
              BoxShadow(
                color: _wulkanBlack.withValues(alpha: 0.05),
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
                            color: _wulkanMuted,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
                  _StatusPill(
                    label:
                        isLoading ? 'Sync' : (enabled ? 'Credito' : 'Revision'),
                    color: enabled ? const Color(0xFF198754) : _wulkanOrange,
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: _CommerceMetric(
                      label: 'Disponible',
                      value: isLoading
                          ? '...'
                          : 'USD ${available.toStringAsFixed(2)}',
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _CommerceMetric(
                      label: 'Comprometido',
                      value: isLoading
                          ? '...'
                          : 'USD ${exposure.toStringAsFixed(2)}',
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
                  color: enabled ? _wulkanOrange : const Color(0xFFADB5BD),
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      session.mustChangePassword
                          ? 'Clave temporal pendiente'
                          : 'Catalogo sincronizado desde Admin',
                      style: const TextStyle(
                        color: _wulkanMuted,
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
        border: Border.all(color: _wulkanLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: _wulkanMuted,
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
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            color: Colors.white,
            border: Border.all(color: _wulkanLine),
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
                      backgroundColor: _wulkanOrange.withValues(alpha: 0.1),
                      foregroundColor: _wulkanOrange,
                      child: Icon(icon, size: 20),
                    ),
                  ),
                )
              else
                CircleAvatar(
                  radius: 22,
                  backgroundColor: _wulkanOrange.withValues(alpha: 0.1),
                  foregroundColor: _wulkanOrange,
                  child: Icon(icon, size: 20),
                ),
              const Spacer(),
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
                style: const TextStyle(color: _wulkanMuted, fontSize: 12),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PromoCarousel extends StatefulWidget {
  const _PromoCarousel({required this.onOpenCatalog});

  final VoidCallback onOpenCatalog;

  @override
  State<_PromoCarousel> createState() => _PromoCarouselState();
}

class _PromoCarouselState extends State<_PromoCarousel> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<MobileAnnouncement>>(
      future: mobileRepository.listAnnouncements('home'),
      builder: (context, snapshot) {
        final announcements = snapshot.data ?? [];

        if (snapshot.connectionState != ConnectionState.done) {
          return const SizedBox(
            height: 180,
            child: Center(child: CircularProgressIndicator()),
          );
        }

        if (announcements.isEmpty) {
          return const SizedBox.shrink();
        }
        final activeIndex = _index.clamp(0, announcements.length - 1).toInt();

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              height: 184,
              child: PageView.builder(
                itemCount: announcements.length,
                onPageChanged: (value) => setState(() => _index = value),
                itemBuilder: (context, index) {
                  final announcement = announcements[index];
                  return Padding(
                    padding: const EdgeInsets.only(right: 10),
                    child: _PromoSlide(
                      announcement: announcement,
                      onTap: widget.onOpenCatalog,
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 10),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                for (var i = 0; i < announcements.length; i++)
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 220),
                    width: i == activeIndex ? 22 : 7,
                    height: 7,
                    margin: const EdgeInsets.symmetric(horizontal: 3),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(99),
                      color: i == activeIndex
                          ? _wulkanOrange
                          : _wulkanOrange.withValues(alpha: 0.18),
                    ),
                  ),
              ],
            ),
          ],
        );
      },
    );
  }
}

class _PromoSlide extends StatelessWidget {
  const _PromoSlide({required this.announcement, required this.onTap});

  final MobileAnnouncement announcement;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final imageUrl = announcement.imageUrl?.trim();
    final ctaLabel = announcement.ctaLabel?.trim().isNotEmpty == true
        ? announcement.ctaLabel!.trim()
        : 'Ver catalogo';

    return InkWell(
      borderRadius: BorderRadius.circular(26),
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(26),
          boxShadow: [
            BoxShadow(
              color: _wulkanOrange.withValues(alpha: 0.2),
              blurRadius: 22,
              offset: const Offset(0, 12),
            ),
          ],
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (imageUrl != null && imageUrl.isNotEmpty)
              Image.network(
                imageUrl,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const _PromoFallbackArt(),
              )
            else
              const _PromoFallbackArt(),
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    Color(0xEE101010),
                    Color(0xAA101010),
                    Color(0x33101010),
                  ],
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(18),
              child: SizedBox(
                width: MediaQuery.sizeOf(context).width * 0.62,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    _StatusPill(label: ctaLabel, color: Colors.white),
                    const SizedBox(height: 12),
                    Text(
                      announcement.title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w900,
                            height: 1.02,
                          ),
                    ),
                    if (announcement.body.trim().isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text(
                        announcement.body,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: Color(0xFFE7E7E7),
                          fontSize: 13,
                          height: 1.25,
                        ),
                      ),
                    ],
                    const SizedBox(height: 12),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          ctaLabel,
                          style: const TextStyle(
                            color: Colors.white,
                            decoration: TextDecoration.underline,
                            decorationColor: Colors.white,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(width: 6),
                        const Icon(
                          Icons.arrow_forward,
                          color: Colors.white,
                          size: 16,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PromoFallbackArt extends StatelessWidget {
  const _PromoFallbackArt();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: [_wulkanBlack, Color(0xFF272727)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Stack(
        children: [
          Positioned(
            right: -14,
            bottom: -18,
            child: Icon(
              Icons.local_offer_outlined,
              color: Colors.white.withValues(alpha: 0.08),
              size: 152,
            ),
          ),
          Positioned(
            right: 22,
            top: 22,
            child: Container(
              width: 62,
              height: 62,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(18),
                color: _wulkanOrange,
              ),
              child: const Icon(
                Icons.campaign_outlined,
                color: Colors.white,
                size: 34,
              ),
            ),
          ),
        ],
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
            mainAxisSpacing: 14,
            crossAxisSpacing: 14,
            childAspectRatio: 0.46,
          ),
          itemBuilder: (context, index) {
            final product = products[index];
            return _ProductTile(
              sku: product.sku,
              title: product.name,
              subtitle: _productSubtitle(product),
              badge: product.badge,
              imageUrl: product.primaryImageUrl,
              priceUsd: product.ferreteroPriceUsd,
              originalPriceUsd: product.ferreteroReferencePriceUsd,
              discountPercent: product.ferreteroDiscountPercent,
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
        padding: const EdgeInsets.fromLTRB(18, 8, 18, 24),
        children: [
          _SearchBox(
            controller: _searchController,
            onChanged: _onSearchChanged,
            labelText: 'Buscar producto, SKU o repuesto',
          ),
          const SizedBox(height: 14),
          _CatalogSummary(
            loadedCount: _products.length,
            hasMore: _hasMore,
            isLoading: _isLoading,
            categoryLabel: _selectedCategoryLabel,
          ),
          const SizedBox(height: 12),
          _CatalogFilterBar(
            selected: _filter,
            onChanged: _onFilterChanged,
          ),
          const SizedBox(height: 10),
          _CategoryFilterStrip(
            selectedCategoryId: _selectedCategoryId,
            onChanged: _onCategoryChanged,
          ),
          const SizedBox(height: 14),
          const _AnnouncementsStrip(placement: 'catalog'),
          const SizedBox(height: 16),
          const _SectionTitle(title: 'Catalogo Wulkan'),
          if (_errorMessage != null)
            _ErrorState(
              title: 'No pudimos cargar el catalogo',
              message: _friendlyMobileError(_errorMessage),
              onRetry: _loadFirstPage,
            )
          else if (_isLoading)
            const _LoadingState(message: 'Sincronizando catalogo Wulkan')
          else if (_products.isEmpty)
            _EmptyState(
              icon: Icons.inventory_2_outlined,
              title: 'Sin productos visibles',
              message:
                  'No hay productos para esta busqueda o categoria. Revisa stock, estado y publicacion desde el admin.',
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
                mainAxisSpacing: 14,
                crossAxisSpacing: 14,
                childAspectRatio: 0.46,
              ),
              itemBuilder: (context, index) {
                final product = _products[index];
                return _ProductTile(
                  sku: product.sku,
                  title: product.name,
                  subtitle: _productSubtitle(product),
                  badge: product.badge,
                  imageUrl: product.primaryImageUrl,
                  priceUsd: product.ferreteroPriceUsd,
                  originalPriceUsd: product.ferreteroReferencePriceUsd,
                  discountPercent: product.ferreteroDiscountPercent,
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

class _CatalogSummary extends StatelessWidget {
  const _CatalogSummary({
    required this.loadedCount,
    required this.hasMore,
    required this.isLoading,
    required this.categoryLabel,
  });

  final int loadedCount;
  final bool hasMore;
  final bool isLoading;
  final String categoryLabel;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        color: Colors.white,
        border: Border.all(color: _wulkanLine),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(8),
              color: _wulkanOrange.withValues(alpha: 0.1),
            ),
            child: const Icon(
              Icons.inventory_2_outlined,
              color: _wulkanOrange,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isLoading
                      ? 'Cargando catalogo'
                      : '$loadedCount productos disponibles',
                  style: Theme.of(context)
                      .textTheme
                      .titleSmall
                      ?.copyWith(fontWeight: FontWeight.w900),
                ),
                Text(
                  hasMore ? 'Stock sincronizado' : 'Catalogo al dia',
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(color: _wulkanMuted),
                ),
                if (categoryLabel != "Todas")
                  Text(
                    'Categoria: $categoryLabel',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: _wulkanOrange,
                          fontWeight: FontWeight.w800,
                        ),
                  ),
              ],
            ),
          ),
          const _InfoChip(icon: Icons.storefront_outlined, label: 'B2B'),
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
                selectedColor: _wulkanBlack,
                backgroundColor: Colors.white,
                labelStyle: TextStyle(
                  color: selected == filter ? Colors.white : _wulkanInk,
                  fontWeight: FontWeight.w800,
                ),
                side: BorderSide(
                  color: selected == filter ? _wulkanBlack : _wulkanLine,
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
                'El catalogo sigue operativo, pero no pudimos leer las familias desde el admin.',
            color: _wulkanOrange,
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
                    color: _wulkanMuted,
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
                      selectedColor: _wulkanBlack,
                      backgroundColor: Colors.white,
                      labelStyle: TextStyle(
                        color: selectedCategoryId == null
                            ? Colors.white
                            : _wulkanInk,
                        fontWeight: FontWeight.w800,
                      ),
                      side: BorderSide(
                        color: selectedCategoryId == null
                            ? _wulkanBlack
                            : _wulkanLine,
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
                        selectedColor: _wulkanBlack,
                        backgroundColor: Colors.white,
                        labelStyle: TextStyle(
                          color: selectedCategoryId == categories[index].id
                              ? Colors.white
                              : _wulkanInk,
                          fontWeight: FontWeight.w800,
                        ),
                        side: BorderSide(
                          color: selectedCategoryId == categories[index].id
                              ? _wulkanBlack
                              : _wulkanLine,
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
    final ferreteroPrice = product.ferreteroPriceUsd;
    final referencePrice = product.ferreteroReferencePriceUsd;
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
                label: 'Ferretero USD ${ferreteroPrice.toStringAsFixed(2)}',
              ),
              if (product.ferreteroDiscountPercent > 0)
                _InfoChip(
                  icon: Icons.local_offer_outlined,
                  label: product.ferreteroDiscountPercent > 0
                      ? '${product.ferreteroDiscountPercent.toStringAsFixed(0)}% ahorro'
                      : 'Oferta',
                ),
              _InfoChip(
                icon: Icons.currency_exchange,
                label:
                    'VES ${(ferreteroPrice * mobileEnvironment.exchangeRateUsdVes).toStringAsFixed(2)}',
              ),
              if (referencePrice != null)
                _InfoChip(
                  icon: Icons.storefront_outlined,
                  label: 'PVP USD ${referencePrice.toStringAsFixed(2)}',
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
        color: _wulkanOrange.withValues(alpha: 0.1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 15, color: _wulkanOrange),
          const SizedBox(width: 6),
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: _wulkanOrange,
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
    final color = isOut ? const Color(0xFFC83232) : _wulkanBlack;

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

        final preview = mobileCartService.calculatePreview(items);

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
                color: _wulkanOrange,
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
                                ? 'Orden revisada por Wulkan'
                                : 'Vendedor asignado: $sellerName',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: _wulkanMuted,
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
                        'Puedes enviar la solicitud como efectivo o revision. Wulkan validara credito, saldo y condiciones en el admin.',
                    color: _wulkanOrange,
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
                    'Subtotal: USD ${widget.preview.subtotalUsd.toStringAsFixed(2)}',
                    'Total referencial: ${widget.preview.totalVes.toStringAsFixed(2)} VES',
                    'Condicion: ${_saleTypeLabel(_saleType, selectedTerm)}',
                    if (credit != null && _saleType == "credit_line")
                      'Credito disponible: USD ${credit.creditAvailableUsd.toStringAsFixed(2)}',
                    widget.preview.requiresOperatorReview
                        ? 'Requiere revision operativa antes de confirmar.'
                        : 'Validacion operativa Wulkan antes del despacho.',
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
      selectedColor: _wulkanBlack,
      backgroundColor: enabled ? Colors.white : const Color(0xFFF1F3F5),
      labelStyle: TextStyle(
        color: selected
            ? Colors.white
            : (enabled ? _wulkanInk : const Color(0xFFADB5BD)),
        fontWeight: FontWeight.w900,
      ),
      side: BorderSide(
        color: selected ? _wulkanBlack : _wulkanLine,
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
  const _CreateOrderButton({required this.draft, required this.session});

  final MobileSecureOrderDraft draft;
  final MobileUserSession session;

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
        SnackBar(content: Text('Orden $orderId registrada en Wulkan Admin')),
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
    return FilledButton.icon(
      onPressed: _isSubmitting || widget.session.mustChangePassword
          ? null
          : _createOrder,
      icon: _isSubmitting
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.lock_outline),
      label: Text(
        widget.session.mustChangePassword
            ? 'Actualiza tu clave'
            : (_isSubmitting ? 'Registrando orden' : 'Crear orden segura'),
      ),
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
                label: Text('Ferreteros'), selected: false, onSelected: null),
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
    return "Cotizacion asistida por Wulkan";
  }

  if (product.requiresTechnicalValidation) {
    return "${product.availableStock} disp. - validar Wulkan";
  }

  return "${product.availableStock} disp. - ferretero USD ${product.ferreteroPriceUsd.toStringAsFixed(0)}";
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
            padding: const EdgeInsets.all(16),
            children: [
              const _SectionTitle(title: 'Historial de ordenes'),
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
    final dueLabel = order.dueDate == null
        ? 'Sin vencimiento'
        : 'Vence ${_formatCustomerDate(order.dueDate!)}';

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
                    order.id,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w900,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${order.saleTypeLabel} - ${status.label}',
                    style: const TextStyle(
                      color: _wulkanMuted,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Total USD ${order.totalUsd.toStringAsFixed(2)}',
                    style: const TextStyle(fontWeight: FontWeight.w900),
                  ),
                  Text(
                    'Saldo USD ${order.balanceUsd.toStringAsFixed(2)} - $dueLabel',
                    style: const TextStyle(color: _wulkanMuted),
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
                      color: _wulkanLine,
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

  @override
  Widget build(BuildContext context) {
    final session = widget.session;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const _SectionTitle(title: 'Cuenta'),
        _AccountHeaderCard(
          session: session,
          onOpenPasswordChange:
              session.mustChangePassword ? _openPasswordChangeSheet : null,
        ),
        _CreditSnapshotPanel(customerId: session.id),
        _OrderSummaryPanel(customerId: session.id),
        OutlinedButton.icon(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => OrderHistoryScreen(customerId: session.id),
            ),
          ),
          icon: const Icon(Icons.receipt_long_outlined),
          label: const Text('Ver historial completo'),
        ),
        const SizedBox(height: 12),
        _InfoPanel(
          title: 'Preferencias de ecommerce',
          lines: [
            'Moneda principal: ${mobileEnvironment.primaryCurrency}',
            'Referencia: ${mobileEnvironment.secondaryCurrency}',
            'Tasa referencial: ${mobileEnvironment.exchangeRateUsdVes} VES/USD',
            'Soporte: validacion operativa Wulkan',
          ],
        ),
        OutlinedButton.icon(
          onPressed: widget.onSignOut,
          icon: const Icon(Icons.logout_outlined),
          label: const Text('Cerrar sesion'),
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
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const _SoftIcon(icon: Icons.storefront_outlined),
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
                            .titleMedium
                            ?.copyWith(fontWeight: FontWeight.w900),
                      ),
                      Text(
                        session.email,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: _wulkanMuted,
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
                _StatusPill(
                  label: session.roleLabel,
                  color: _wulkanBlack,
                ),
                _StatusPill(
                  label: mobileEnvironment.defaultCountry,
                  color: const Color(0xFF6C757D),
                ),
                if (session.mustChangePassword)
                  const _StatusPill(
                    label: 'Clave temporal',
                    color: _wulkanOrange,
                  )
                else
                  const _StatusPill(
                    label: 'Acceso activo',
                    color: Color(0xFF198754),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            if (session.assignedSeller.name.isNotEmpty) ...[
              _AccountMetaLine(
                icon: Icons.support_agent_outlined,
                label: 'Vendedor',
                value: session.assignedSeller.name,
              ),
              const SizedBox(height: 8),
            ],
            if (_positiveTerms(session.allowedPaymentTermsDays).isNotEmpty) ...[
              _AccountMetaLine(
                icon: Icons.event_available_outlined,
                label: 'Plazos',
                value:
                    '${_positiveTerms(session.allowedPaymentTermsDays).join(", ")} dias',
              ),
              const SizedBox(height: 8),
            ],
            Row(
              children: [
                const Icon(Icons.sync_outlined, color: _wulkanMuted, size: 18),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    'Cuenta sincronizada con Wulkan Admin.',
                    style: TextStyle(
                      color: _wulkanMuted,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                if (onOpenPasswordChange != null)
                  TextButton.icon(
                    onPressed: onOpenPasswordChange,
                    icon: const Icon(Icons.lock_reset_outlined, size: 18),
                    label: const Text('Cambiar clave'),
                  ),
              ],
            ),
          ],
        ),
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
        Icon(icon, size: 18, color: _wulkanMuted),
        const SizedBox(width: 8),
        Text(
          '$label: ',
          style: const TextStyle(
            color: _wulkanMuted,
            fontWeight: FontWeight.w800,
          ),
        ),
        Expanded(
          child: Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: _wulkanBlack,
              fontWeight: FontWeight.w900,
            ),
          ),
        ),
      ],
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
              const Icon(Icons.security_outlined, color: _wulkanOrange),
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
            style: TextStyle(color: _wulkanMuted),
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
    final statusColor = enabled ? const Color(0xFF198754) : _wulkanOrange;
    final terms = _positiveTerms(credit.allowedPaymentTermsDays);

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
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
                        'Linea de credito',
                        style: Theme.of(context)
                            .textTheme
                            .titleMedium
                            ?.copyWith(fontWeight: FontWeight.w900),
                      ),
                      Text(
                        enabled
                            ? 'Aprobada por Wulkan'
                            : 'Compra bajo revision',
                        style: const TextStyle(
                          color: _wulkanMuted,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
                _StatusPill(
                  label: enabled ? 'Activa' : 'Revision',
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
                    value:
                        'USD ${credit.creditAvailableUsd.toStringAsFixed(2)}',
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _CommerceMetric(
                    label: 'Limite',
                    value: 'USD ${credit.creditLimitUsd.toStringAsFixed(2)}',
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
                color: _wulkanOrange,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              terms.isEmpty
                  ? 'Comprometido USD ${credit.creditExposureUsd.toStringAsFixed(2)}'
                  : 'Comprometido USD ${credit.creditExposureUsd.toStringAsFixed(2)} - plazos ${terms.join(", ")} dias',
              style: const TextStyle(
                color: _wulkanMuted,
                fontWeight: FontWeight.w700,
              ),
            ),
            if (credit.assignedSeller.name.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                'Vendedor: ${credit.assignedSeller.name}',
                style: const TextStyle(
                  color: _wulkanMuted,
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
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Ordenes recientes',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w900,
                        color: _wulkanBlack,
                      ),
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

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
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
                  'Orden del ${_formatCustomerDate(order.createdAt)}',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w900,
                      ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${status.label} - $stock',
                  style: const TextStyle(
                    color: _wulkanMuted,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '$amountLabel USD ${amount.toStringAsFixed(2)}',
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
      color: _wulkanOrange
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
    label: 'En revision Wulkan',
    icon: Icons.schedule_outlined,
    color: _wulkanOrange
  );
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
                ?.copyWith(fontWeight: FontWeight.w900, color: _wulkanBlack),
          ),
          const SizedBox(height: 8),
          for (final line in lines)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(
                line,
                style: const TextStyle(color: _wulkanMuted),
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
          border: Border.all(color: _wulkanLine),
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
                  color: _wulkanBlack,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    title,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w900,
                          color: _wulkanBlack,
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
    this.color = _wulkanOrange,
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
                    color: _wulkanMuted,
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
                          ? _wulkanOrange
                          : _wulkanMuted.withValues(alpha: 0.22),
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
          color: _wulkanBlack,
          boxShadow: [
            BoxShadow(
              color: _wulkanBlack.withValues(alpha: 0.12),
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
                          : 'Wulkan',
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
      color: _wulkanBlack,
      child: Align(
        alignment: Alignment.centerRight,
        child: Padding(
          padding: EdgeInsets.only(right: 24),
          child: Icon(
            Icons.campaign_outlined,
            size: 74,
            color: _wulkanOrange,
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
                  'USD ${lineTotal.toStringAsFixed(2)}',
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
      height: 320,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        color: _wulkanBlack,
        boxShadow: [
          BoxShadow(
            color: _wulkanBlack.withValues(alpha: 0.18),
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
                color: _wulkanOrange,
              ),
              child: const Text(
                'USD / VES',
                style: TextStyle(
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
                label: 'Wulkan ecommerce',
              ),
              const SizedBox(height: 34),
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
                  'Compra equipos, repuestos y accesorios con stock actualizado desde el admin.',
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
                  foregroundColor: _wulkanBlack,
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
          Icon(icon, color: _wulkanOrange, size: 16),
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
                            color: _wulkanMuted,
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
                      color: _wulkanOrange,
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
    this.message = 'Sincronizando con Wulkan',
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
                color: _wulkanMuted,
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
                    'Leyendo datos publicados desde el admin.',
                    style: TextStyle(
                      color: _wulkanMuted,
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
                color: _wulkanMuted,
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
                          color: _wulkanMuted,
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
        color: _wulkanBlack,
        border: Border.all(color: _wulkanBlack),
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
                Icon(Icons.map_outlined, size: 42, color: _wulkanOrange),
                SizedBox(height: 10),
                Text(
                  'Red autorizada Wulkan',
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
        prefixIcon: const Icon(Icons.search, color: _wulkanMuted),
        hintText: labelText,
        filled: true,
        fillColor: Colors.white,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: _wulkanLine),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: _wulkanLine),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: _wulkanOrange, width: 1.5),
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
                    color: _wulkanBlack,
                  ),
            ),
          ),
          if (actionLabel != null)
            TextButton(
              onPressed: onAction,
              child: Text(
                actionLabel!,
                style: const TextStyle(
                  color: _wulkanOrange,
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
                _wulkanOrange.withValues(alpha: 0.12),
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
                      ? Image.network(
                          imageUrl!,
                          fit: BoxFit.contain,
                          semanticLabel: title,
                          errorBuilder: (_, __, ___) =>
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
                        'Wulkan stock',
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
          color: _wulkanBlack,
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

    return InkWell(
      borderRadius: BorderRadius.circular(22),
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(22),
          color: Colors.white,
          border: Border.all(color: accentColor.withValues(alpha: 0.18)),
          boxShadow: [
            BoxShadow(
              color: accentColor.withValues(alpha: 0.14),
              blurRadius: 18,
              offset: const Offset(0, 10),
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
                  imageUrl: imageUrl,
                  accentColor: accentColor,
                ),
                Positioned(
                  top: 10,
                  right: 10,
                  child: CircleAvatar(
                    radius: 17,
                    backgroundColor: Colors.white,
                    foregroundColor: _wulkanBlack,
                    child: IconButton(
                      tooltip: 'Ver detalle',
                      padding: EdgeInsets.zero,
                      iconSize: 17,
                      onPressed: onTap,
                      icon: const Icon(Icons.visibility_outlined),
                    ),
                  ),
                ),
                if (hasDiscount)
                  Positioned(
                    top: 10,
                    left: 10,
                    child: _SaleBadge(discountPercent: discountPercent),
                  ),
                Positioned(
                  top: 10,
                  left: hasDiscount ? 78 : 10,
                  child: _StockBadge(stock: stock ?? 0),
                ),
              ],
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      category,
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: accentColor,
                            fontWeight: FontWeight.w900,
                          ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: _wulkanBlack,
                            fontWeight: FontWeight.w900,
                            height: 1.08,
                          ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: _wulkanMuted,
                          ),
                    ),
                    const SizedBox(height: 8),
                    if (hasDiscount && originalPriceUsd != null)
                      Text(
                        'USD ${originalPriceUsd!.toStringAsFixed(2)}',
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              decoration: TextDecoration.lineThrough,
                              color: _wulkanMuted,
                            ),
                      ),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            priceUsd == null
                                ? 'Cotizar'
                                : 'USD ${priceUsd!.toStringAsFixed(2)}',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context)
                                .textTheme
                                .titleMedium
                                ?.copyWith(
                                  color: _wulkanBlack,
                                  fontWeight: FontWeight.w900,
                                ),
                          ),
                        ),
                        Text(
                          'USD',
                          style:
                              Theme.of(context).textTheme.labelSmall?.copyWith(
                                    color: accentColor,
                                    fontWeight: FontWeight.w900,
                                  ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
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
    final quantityLabel = canAdd ? 'Cant. $_quantity' : 'Sin stock';

    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: canAdd ? _editQuantity : null,
            icon: const Icon(Icons.format_list_numbered, size: 16),
            label: Text(quantityLabel),
            style: OutlinedButton.styleFrom(
              minimumSize: const Size(0, 34),
              padding: const EdgeInsets.symmetric(horizontal: 8),
              foregroundColor: widget.accentColor,
              side:
                  BorderSide(color: widget.accentColor.withValues(alpha: 0.4)),
              textStyle: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
        ),
        const SizedBox(width: 7),
        SizedBox(
          width: 38,
          height: 34,
          child: IconButton.filled(
            tooltip: 'Agregar cantidad',
            onPressed: canAdd && widget.onAddQuantity != null
                ? () => widget.onAddQuantity!(_quantity)
                : null,
            icon: const Icon(Icons.add_shopping_cart, size: 17),
            style: IconButton.styleFrom(
              backgroundColor: widget.accentColor,
              foregroundColor: Colors.white,
              disabledBackgroundColor: _wulkanLine,
              disabledForegroundColor: _wulkanMuted,
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
        foregroundColor: _wulkanBlack,
        side: const BorderSide(color: _wulkanLine),
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
                  style: const TextStyle(color: _wulkanMuted),
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
    return _wulkanBlack;
  }
  if (normalized.contains('maquinaria') ||
      normalized.contains('jardin') ||
      normalized.contains('bosque')) {
    return const Color(0xFFD83B00);
  }
  return _wulkanOrange;
}

class _ProductImageFrame extends StatelessWidget {
  const _ProductImageFrame({
    this.imageUrl,
    this.accentColor = _wulkanOrange,
  });

  final String? imageUrl;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 1.12,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(0),
        child: imageUrl == null || imageUrl!.isEmpty
            ? _WulkanProductPlaceholder(accentColor: accentColor)
            : ColoredBox(
                color: accentColor.withValues(alpha: 0.08),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Image.network(
                    imageUrl!,
                    fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => const Center(
                      child: Icon(Icons.image_not_supported_outlined),
                    ),
                  ),
                ),
              ),
      ),
    );
  }
}

class _WulkanProductPlaceholder extends StatelessWidget {
  const _WulkanProductPlaceholder({
    this.accentColor = _wulkanOrange,
  });

  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            accentColor.withValues(alpha: 0.16),
            _wulkanOrange.withValues(alpha: 0.08),
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
                color: _wulkanBlack,
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
        color: _wulkanOrange,
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
    this.accentColor = _wulkanOrange,
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
                    child: Image.network(
                      imageUrl!,
                      fit: BoxFit.contain,
                      errorBuilder: (_, __, ___) => const Center(
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
