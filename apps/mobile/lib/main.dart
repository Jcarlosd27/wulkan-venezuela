import 'dart:async';

import 'package:flutter/material.dart';

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
  await configureMobileRuntime();
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
              onSubmit: _signIn,
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
    required this.onSubmit,
  });

  final TextEditingController emailController;
  final TextEditingController passwordController;
  final String errorMessage;
  final bool isSigningIn;
  final VoidCallback onSubmit;

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
              obscureText: true,
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => onSubmit(),
              decoration: const InputDecoration(
                labelText: 'Clave',
                prefixIcon: Icon(Icons.key_outlined),
                border: OutlineInputBorder(),
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
                icon: switch (index % 4) {
                  0 => Icons.grass_outlined,
                  1 => Icons.construction_outlined,
                  2 => Icons.settings_suggest_outlined,
                  _ => Icons.agriculture_outlined,
                },
                onTap: onOpenCatalog,
              );
            },
          ),
        );
      },
    );
  }
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
    required this.icon,
    required this.onTap,
  });

  final String title;
  final String subtitle;
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
              CircleAvatar(
                radius: 17,
                backgroundColor: _wulkanOrange.withValues(alpha: 0.1),
                foregroundColor: _wulkanOrange,
                child: Icon(icon, size: 18),
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

  void _openProductPreview(BuildContext context, MobileProduct product) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (sheetContext) => _ProductDetailSheet(
        product: product,
        onAdd: () {
          mobileCartController.addProduct(product);
          Navigator.of(sheetContext).pop();
          onOpenCart();
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
            childAspectRatio: 0.56,
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

  void _addToCart(MobileProduct product) {
    if (product.availableStock <= 0 && !product.requiresQuote) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${product.name} no tiene stock disponible')),
      );
      return;
    }

    mobileCartController.addProduct(product);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('${product.name} agregado al carrito')),
    );
  }

  void _openProduct(MobileProduct product) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => _ProductDetailSheet(
        product: product,
        onAdd: () {
          _addToCart(product);
          Navigator.of(context).pop();
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
          ),
          const SizedBox(height: 12),
          _CatalogFilterBar(
            selected: _filter,
            onChanged: _onFilterChanged,
          ),
          const SizedBox(height: 14),
          const _AnnouncementsStrip(placement: 'catalog'),
          const SizedBox(height: 16),
          const _SectionTitle(title: 'Catalogo Wulkan'),
          if (_errorMessage != null)
            _InfoPanel(
              title: 'No pudimos cargar el catalogo',
              lines: [_errorMessage!],
            )
          else if (_isLoading)
            const _LoadingState()
          else if (_products.isEmpty)
            const _EmptyState(message: 'Sin productos para este filtro')
          else
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: _products.length,
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                mainAxisSpacing: 14,
                crossAxisSpacing: 14,
                childAspectRatio: 0.56,
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
                );
              },
            ),
          if (_isLoadingMore) const _LoadingState(),
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
  });

  final int loadedCount;
  final bool hasMore;
  final bool isLoading;

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
      (_CatalogFilter.machinery, 'Maquinaria'),
      (_CatalogFilter.spareParts, 'Repuestos'),
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

class _ProductDetailSheet extends StatelessWidget {
  const _ProductDetailSheet({
    required this.product,
    required this.onAdd,
  });

  final MobileProduct product;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    final ferreteroPrice = product.ferreteroPriceUsd;
    final referencePrice = product.ferreteroReferencePriceUsd;

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
          if (product.primaryImageUrl != null)
            _ProductImageHero(
              imageUrl: product.primaryImageUrl!,
              title: product.name,
            ),
          if (product.imageUrls.length > 1) ...[
            const SizedBox(height: 8),
            SizedBox(
              height: 62,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: product.imageUrls.length,
                separatorBuilder: (_, __) => const SizedBox(width: 8),
                itemBuilder: (context, index) =>
                    _ProductThumb(imageUrl: product.imageUrls[index]),
              ),
            ),
          ],
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
              onPressed: onAdd,
              icon: const Icon(Icons.add_shopping_cart),
              label: Text(
                product.requiresQuote
                    ? 'Agregar para cotizar'
                    : 'Agregar al carrito',
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

class ProductDetailScreen extends StatelessWidget {
  const ProductDetailScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<MobileProduct?>(
      future: mobileRepository.getProduct("avalon-wk-bl-43"),
      builder: (context, snapshot) {
        final product = snapshot.data;

        if (snapshot.connectionState != ConnectionState.done) {
          return const _LoadingState();
        }

        if (product == null) {
          return const _EmptyState(message: 'Producto no disponible');
        }

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (product.imageUrl != null)
              _ProductImageHero(
                  imageUrl: product.imageUrl!, title: product.name),
            const SizedBox(height: 12),
            _SectionTitle(title: product.name),
            Text('SKU ${product.sku}'),
            const SizedBox(height: 12),
            _InfoPanel(
              title: 'Ficha tecnica',
              lines: [
                'Categoria: ${product.categoryName}',
                'Precio publico: USD ${product.publicPriceUsd.toStringAsFixed(0)}',
                'Precio B2B: USD ${product.b2bPriceUsd.toStringAsFixed(0)}',
                'Stock disponible: ${product.availableStock}',
                if (product.originalPriceClp != null)
                  'Precio origen: CLP ${product.originalPriceClp!.toStringAsFixed(0)}',
                if (product.importExchangeRateClpUsd != null)
                  'Tasa importacion: ${product.importExchangeRateClpUsd} USD/CLP',
                'Garantia: 6 meses',
              ],
            ),
            _InfoPanel(
              title: 'Compatibilidad',
              lines: product.compatibilityNotes,
            ),
            const SizedBox(height: 8),
            FilledButton.icon(
              onPressed: () {
                mobileCartController.addProduct(product);
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('${product.name} agregado')),
                );
              },
              icon: const Icon(Icons.add_shopping_cart),
              label: const Text('Agregar al carrito'),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () {},
              icon: const Icon(Icons.support_agent),
              label: const Text('Solicitar validacion tecnica'),
            ),
          ],
        );
      },
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
        final draft = MobileSecureOrderDraft(items: items, preview: preview);

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
            _InfoPanel(
              title: 'Resumen de compra',
              lines: [
                'Subtotal: USD ${preview.subtotalUsd.toStringAsFixed(2)}',
                'Tasa referencial: ${preview.exchangeRateUsdVes} VES/USD',
                'Total referencial: ${preview.totalVes.toStringAsFixed(2)} VES',
                preview.requiresOperatorReview
                    ? 'Requiere revision operativa antes de confirmar.'
                    : 'Pago pendiente de validacion por operador.',
              ],
            ),
            const SizedBox(height: 8),
            _CreateOrderButton(draft: draft, session: session),
          ],
        );
      },
    );
  }
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
        SnackBar(content: Text(error.toString())),
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

class ProjectRequestScreen extends StatelessWidget {
  const ProjectRequestScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const _SectionTitle(title: 'Proyecto tecnico'),
        DropdownButtonFormField<String>(
          initialValue: 'lighting',
          decoration: const InputDecoration(
            labelText: 'Categoria tecnica',
            border: OutlineInputBorder(),
          ),
          items: const [
            DropdownMenuItem(value: 'lighting', child: Text('Iluminacion')),
            DropdownMenuItem(value: 'solar', child: Text('Energia solar')),
            DropdownMenuItem(
                value: 'electricity', child: Text('Electricidad limpia')),
          ],
          onChanged: (_) {},
        ),
        const SizedBox(height: 12),
        const TextField(
          decoration: InputDecoration(
            labelText: 'Direccion del proyecto',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        const TextField(
          decoration: InputDecoration(
            labelText: 'Medidas, fotos o requerimiento',
            border: OutlineInputBorder(),
          ),
          minLines: 4,
          maxLines: 6,
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: () {},
          icon: const Icon(Icons.calendar_month_outlined),
          label: const Text('Solicitar evaluacion'),
        ),
      ],
    );
  }
}

class QuotesScreen extends StatelessWidget {
  const QuotesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const _SectionTitle(title: 'Solicitud de cotizacion'),
        const TextField(
          decoration: InputDecoration(
            labelText: 'Producto, SKU o necesidad tecnica',
            border: OutlineInputBorder(),
          ),
          minLines: 1,
          maxLines: 2,
        ),
        const SizedBox(height: 12),
        const TextField(
          decoration: InputDecoration(
            labelText: 'Descripcion',
            border: OutlineInputBorder(),
          ),
          minLines: 4,
          maxLines: 6,
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: () {},
          icon: const Icon(Icons.send_outlined),
          label: const Text('Enviar solicitud'),
        ),
      ],
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
    return "Stock ${product.availableStock} - validar con Wulkan";
  }

  return "Stock ${product.availableStock} - precio ferretero USD ${product.ferreteroPriceUsd.toStringAsFixed(0)}";
}

class WorkModeScreen extends StatelessWidget {
  const WorkModeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: const [
        _SectionTitle(title: 'Acceso por rol'),
        _ModuleTile(
            title: 'Cliente final',
            subtitle: 'Compras, cotizaciones y seguimiento'),
        _ModuleTile(
            title: 'Ferretero', subtitle: 'Catalogo B2B y ordenes de compra'),
        _InfoPanel(
          title: 'Orden B2B demo',
          lines: [
            'Ferretero: Ferreteria Demo',
            'Producto: WUL-REP-CAD18',
            'Cantidad: 10',
            'Total: USD 150',
            'Estado: revision Wulkan',
          ],
        ),
        _InfoPanel(
          title: 'Condiciones B2B',
          lines: [
            'Descuento base: 8%',
            'Minimo de compra: USD 150',
            'Credito: no habilitado',
            'Reposicion: disponible por solicitud',
          ],
        ),
        _ModuleTile(
            title: 'Servicio tecnico',
            subtitle: 'Casos, diagnosticos y repuestos'),
        _InfoPanel(
          title: 'Caso tecnico demo',
          lines: [
            'Maquina: Motosierra 45cc',
            'Sintoma: No enciende',
            'Diagnostico: pendiente de repuesto',
            'Repuesto solicitado: WUL-REP-CAD18',
          ],
        ),
      ],
    );
  }
}

class OrderHistoryScreen extends StatelessWidget {
  const OrderHistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: const [
        _SectionTitle(title: 'Historial de ordenes'),
        _InfoPanel(
          title: 'ORD-1001',
          lines: [
            'Producto: Motosierra 45cc',
            'Total: USD 185',
            'Pago: en revision',
            'Entrega: pendiente de confirmacion',
          ],
        ),
        _InfoPanel(
          title: 'PO-2001',
          lines: [
            'Tipo: Orden B2B',
            'Producto: Cadena 18 pulgadas compatible',
            'Cantidad: 10',
            'Estado: revision Wulkan',
          ],
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

class _PasswordChangePanel extends StatelessWidget {
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
                  requiredChange
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
            controller: currentPasswordController,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'Contrasena actual',
              prefixIcon: Icon(Icons.lock_outline),
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: newPasswordController,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'Nueva contrasena',
              prefixIcon: Icon(Icons.key_outlined),
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: confirmPasswordController,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'Confirmar nueva contrasena',
              prefixIcon: Icon(Icons.verified_user_outlined),
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: isSaving ? null : onSubmit,
              icon: isSaving
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.shield_outlined),
              label: Text(isSaving ? 'Guardando' : 'Guardar contrasena'),
            ),
          ),
        ],
      ),
    );

    if (!asCard) {
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
              'Comprometido USD ${credit.creditExposureUsd.toStringAsFixed(2)} - ${credit.paymentTermsDays} dias',
              style: const TextStyle(
                color: _wulkanMuted,
                fontWeight: FontWeight.w700,
              ),
            ),
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
      color: const Color(0xFF0D6EFD)
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
  const _InfoPanel({required this.title, required this.lines});

  final String title;
  final List<String> lines;

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

class _AnnouncementsStrip extends StatelessWidget {
  const _AnnouncementsStrip({required this.placement});

  final String placement;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<MobileAnnouncement>>(
      future: mobileRepository.listAnnouncements(placement),
      builder: (context, snapshot) {
        final announcements = snapshot.data ?? [];

        if (snapshot.connectionState != ConnectionState.done ||
            announcements.isEmpty) {
          return const SizedBox.shrink();
        }

        return Column(
          children: [
            for (final announcement in announcements)
              _AnnouncementCard(announcement: announcement),
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
      itemBuilder: (location) =>
          _ModuleTile(title: location.name, subtitle: location.subtitle),
    );
  }
}

class _LoadingState extends StatelessWidget {
  const _LoadingState();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 24),
      child: Center(child: CircularProgressIndicator()),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 24),
      child: Center(child: Text(message)),
    );
  }
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

class _ModuleTile extends StatelessWidget {
  const _ModuleTile({
    required this.title,
    required this.subtitle,
  });

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
      ),
    );
  }
}

class _ProductImageHero extends StatelessWidget {
  const _ProductImageHero({required this.imageUrl, required this.title});

  final String imageUrl;
  final String title;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: AspectRatio(
        aspectRatio: 16 / 11,
        child: ColoredBox(
          color: const Color(0xFFF8FAFD),
          child: Padding(
            padding: const EdgeInsets.all(10),
            child: Image.network(
              imageUrl,
              fit: BoxFit.contain,
              semanticLabel: title,
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

  @override
  Widget build(BuildContext context) {
    final hasDiscount =
        discountPercent > 0 || ((originalPriceUsd ?? 0) > (priceUsd ?? 0));

    return InkWell(
      borderRadius: BorderRadius.circular(22),
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(22),
          color: Colors.white,
          border: Border.all(color: _wulkanLine),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Stack(
              children: [
                _ProductImageFrame(imageUrl: imageUrl),
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
                            color: _wulkanOrange,
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
                                    color: _wulkanOrange,
                                    fontWeight: FontWeight.w900,
                                  ),
                        ),
                      ],
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

class _ProductImageFrame extends StatelessWidget {
  const _ProductImageFrame({this.imageUrl});

  final String? imageUrl;

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 1.12,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(0),
        child: imageUrl == null || imageUrl!.isEmpty
            ? const _WulkanProductPlaceholder()
            : ColoredBox(
                color: const Color(0xFFF3F0ED),
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
  const _WulkanProductPlaceholder();

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: const Color(0xFFF3F0ED),
      child: Stack(
        children: [
          Positioned(
            right: -18,
            bottom: -20,
            child: Icon(
              Icons.agriculture_outlined,
              size: 104,
              color: _wulkanBlack.withValues(alpha: 0.06),
            ),
          ),
          Center(
            child: Container(
              width: 74,
              height: 74,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white,
                border: Border.all(color: _wulkanLine),
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
  const _ProductThumb({this.imageUrl});

  final String? imageUrl;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
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
    );
  }
}
