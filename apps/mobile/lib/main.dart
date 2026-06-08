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
      home: const WulkanShell(),
    );
  }
}

class WulkanShell extends StatefulWidget {
  const WulkanShell({super.key});

  @override
  State<WulkanShell> createState() => _WulkanShellState();
}

class _WulkanShellState extends State<WulkanShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final screens = [
      HomeScreen(
        onOpenCatalog: () => setState(() => _index = 1),
        onOpenCart: () => setState(() => _index = 2),
      ),
      const CatalogScreen(),
      CartScreen(onOpenCatalog: () => setState(() => _index = 1)),
      const LocationsScreen(),
      const ProfileScreen(),
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Row(
          children: [
            WulkanLogo(compact: true),
            SizedBox(width: 8),
            Text(
              'Store',
              style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16),
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
    required this.onOpenCatalog,
    required this.onOpenCart,
  });

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
        const SizedBox(height: 18),
        _HeroPanel(onOpenCatalog: onOpenCatalog),
        const SizedBox(height: 18),
        _PromoCarousel(onOpenCatalog: onOpenCatalog),
        const SizedBox(height: 18),
        const _AnnouncementsStrip(placement: 'home'),
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
          onOpenCatalog: onOpenCatalog,
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
    return FutureBuilder<MobileProductPage>(
      future: mobileRepository.listProductPage(
        const MobileProductQuery(onlyAvailable: true, limit: 5),
      ),
      builder: (context, snapshot) {
        final products = snapshot.data?.products ?? [];

        if (snapshot.connectionState != ConnectionState.done) {
          return const SizedBox(
            height: 180,
            child: Center(child: CircularProgressIndicator()),
          );
        }

        if (products.isEmpty) {
          return const SizedBox.shrink();
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              height: 184,
              child: PageView.builder(
                itemCount: products.length,
                onPageChanged: (value) => setState(() => _index = value),
                itemBuilder: (context, index) {
                  final product = products[index];
                  return Padding(
                    padding: const EdgeInsets.only(right: 10),
                    child: _PromoSlide(
                      product: product,
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
                for (var i = 0; i < products.length; i++)
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 220),
                    width: i == _index ? 22 : 7,
                    height: 7,
                    margin: const EdgeInsets.symmetric(horizontal: 3),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(99),
                      color: i == _index
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
  const _PromoSlide({required this.product, required this.onTap});

  final MobileProduct product;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final discount = product.discountPercent > 0
        ? '${product.discountPercent.toStringAsFixed(0)}% OFF'
        : 'Oferta Wulkan';

    return InkWell(
      borderRadius: BorderRadius.circular(26),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(26),
          gradient: const LinearGradient(
            colors: [_wulkanBlack, Color(0xFF2A1710), _wulkanOrange],
            begin: Alignment.centerLeft,
            end: Alignment.centerRight,
          ),
          boxShadow: [
            BoxShadow(
              color: _wulkanOrange.withValues(alpha: 0.2),
              blurRadius: 22,
              offset: const Offset(0, 12),
            ),
          ],
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(999),
                      color: Colors.white.withValues(alpha: 0.14),
                    ),
                    child: Text(
                      discount,
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w900,
                        fontSize: 12,
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    product.name,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.w900,
                          height: 1.02,
                        ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'USD ${product.publicPriceUsd.toStringAsFixed(2)}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w900,
                      fontSize: 16,
                    ),
                  ),
                  const SizedBox(height: 10),
                  const Text(
                    'Ver promocion',
                    style: TextStyle(
                      color: Colors.white,
                      decoration: TextDecoration.underline,
                      decorationColor: Colors.white,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 14),
            _PromoProductArt(product: product),
          ],
        ),
      ),
    );
  }
}

class _PromoProductArt extends StatelessWidget {
  const _PromoProductArt({required this.product});

  final MobileProduct product;

  @override
  Widget build(BuildContext context) {
    final imageUrl = product.primaryImageUrl;

    return Container(
      width: 118,
      height: 128,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(22),
        color: Colors.white.withValues(alpha: 0.92),
      ),
      child: imageUrl == null || imageUrl.isEmpty
          ? Stack(
              alignment: Alignment.center,
              children: [
                Icon(
                  Icons.inventory_2_outlined,
                  size: 58,
                  color: _wulkanBlack.withValues(alpha: 0.88),
                ),
                Positioned(
                  right: 12,
                  top: 12,
                  child: Icon(
                    Icons.local_fire_department,
                    color: _wulkanOrange.withValues(alpha: 0.9),
                  ),
                ),
              ],
            )
          : Padding(
              padding: const EdgeInsets.all(10),
              child: Image.network(
                imageUrl,
                fit: BoxFit.contain,
                errorBuilder: (_, __, ___) => const Icon(
                  Icons.inventory_2_outlined,
                  size: 58,
                  color: _wulkanBlack,
                ),
              ),
            ),
    );
  }
}

class _FeaturedProductGrid extends StatelessWidget {
  const _FeaturedProductGrid({
    required this.onOpenCatalog,
    required this.onOpenCart,
  });

  final VoidCallback onOpenCatalog;
  final VoidCallback onOpenCart;

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
              priceUsd: product.publicPriceUsd,
              originalPriceUsd: product.originalPriceUsd,
              discountPercent: product.discountPercent,
              category: product.categoryName,
              variants: product.variants,
              stock: product.availableStock,
              requiresQuote: product.requiresQuote,
              onTap: onOpenCatalog,
              onAction: () {
                mobileCartController.addProduct(product);
                onOpenCart();
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
                  priceUsd: product.publicPriceUsd,
                  originalPriceUsd: product.originalPriceUsd,
                  discountPercent: product.discountPercent,
                  category: product.categoryName,
                  variants: product.variants,
                  stock: product.availableStock,
                  requiresQuote: product.requiresQuote,
                  onTap: () => _openProduct(product),
                  onAction: () => _addToCart(product),
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
                  isLoading ? 'Cargando catalogo' : '$loadedCount productos',
                  style: Theme.of(context)
                      .textTheme
                      .titleSmall
                      ?.copyWith(fontWeight: FontWeight.w900),
                ),
                Text(
                  hasMore ? 'Lectura paginada activa' : 'Catalogo al dia',
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(color: _wulkanMuted),
                ),
              ],
            ),
          ),
          const _InfoChip(icon: Icons.sync_outlined, label: 'Admin'),
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
      (_CatalogFilter.validation, 'Validar'),
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
    return FractionallySizedBox(
      heightFactor: 0.88,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: [
          Center(
            child: Container(
              width: 42,
              height: 4,
              decoration: BoxDecoration(
                color: const Color(0xFFD3DAE5),
                borderRadius: BorderRadius.circular(99),
              ),
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
                label: 'USD ${product.publicPriceUsd.toStringAsFixed(2)}',
              ),
              if (product.hasDiscount)
                _InfoChip(
                  icon: Icons.local_offer_outlined,
                  label: product.discountPercent > 0
                      ? '${product.discountPercent.toStringAsFixed(0)}% OFF'
                      : 'Oferta',
                ),
              _InfoChip(
                icon: Icons.currency_exchange,
                label:
                    'VES ${(product.publicPriceUsd * mobileEnvironment.exchangeRateUsdVes).toStringAsFixed(2)}',
              ),
              _InfoChip(
                icon: Icons.storefront_outlined,
                label: 'B2B ${product.b2bPriceUsd.toStringAsFixed(2)}',
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
          FilledButton.icon(
            onPressed: onAdd,
            icon: const Icon(Icons.add_shopping_cart),
            label: Text(
              product.requiresQuote ? 'Agregar para cotizar' : 'Agregar',
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
  const CartScreen({super.key, required this.onOpenCatalog});

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
            _CreateOrderButton(draft: draft),
          ],
        );
      },
    );
  }
}

class _CreateOrderButton extends StatefulWidget {
  const _CreateOrderButton({required this.draft});

  final MobileSecureOrderDraft draft;

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
      onPressed: _isSubmitting ? null : _createOrder,
      icon: _isSubmitting
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.lock_outline),
      label: Text(_isSubmitting ? 'Registrando orden' : 'Crear orden segura'),
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
    return "Requiere cotizacion e instalacion";
  }

  if (product.requiresTechnicalValidation) {
    return "Stock ${product.availableStock} - requiere validacion tecnica";
  }

  return "Stock ${product.availableStock} - precio publico USD ${product.publicPriceUsd.toStringAsFixed(0)}";
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
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final _emailController = TextEditingController(text: 'ferreteria@wulkan.local');
  final _passwordController = TextEditingController(text: 'ferretero2026');
  late Future<MobileUserSession> _sessionFuture;
  bool _isSigningIn = false;

  @override
  void initState() {
    super.initState();
    _sessionFuture = mobileAuthRepository.getCurrentSession();
  }

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

    setState(() => _isSigningIn = true);

    try {
      await mobileAuthRepository.signIn(
        email: _emailController.text.trim(),
        password: _passwordController.text,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _sessionFuture = mobileAuthRepository.getCurrentSession();
        _isSigningIn = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _isSigningIn = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString())),
      );
    }
  }

  Future<void> _signOut() async {
    await mobileAuthRepository.signOut();
    if (!mounted) {
      return;
    }
    setState(() => _sessionFuture = mobileAuthRepository.getCurrentSession());
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<MobileUserSession>(
      future: _sessionFuture,
      builder: (context, snapshot) {
        final session = snapshot.data;

        if (snapshot.connectionState != ConnectionState.done) {
          return const _LoadingState();
        }

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const _SectionTitle(title: 'Cuenta'),
            _InfoPanel(
              title: session?.isAuthenticated == true
                  ? 'Cliente activo'
                  : 'Cliente invitado',
              lines: [
                'Nombre: ${session?.name ?? "Invitado"}',
                'Email: ${session?.email ?? ""}',
                'Pais: ${mobileEnvironment.defaultCountry}',
                'Rol activo: ${session?.roleLabel ?? "Sin sesion"}',
              ],
            ),
            if (session?.isAuthenticated != true)
              _LoginPanel(
                emailController: _emailController,
                passwordController: _passwordController,
                isSigningIn: _isSigningIn,
                onSubmit: _signIn,
              ),
            const _InfoPanel(
              title: 'Datos de compra',
              lines: [
                'Catalogo: administrado desde Wulkan Admin',
                'Pagos: validacion por operador autorizado',
                'Ordenes: historial y seguimiento en preparacion',
              ],
            ),
            _InfoPanel(
              title: 'Preferencias de ecommerce',
              lines: [
                'Moneda principal: ${mobileEnvironment.primaryCurrency}',
                'Referencia: ${mobileEnvironment.secondaryCurrency}',
                'Tasa referencial: ${mobileEnvironment.exchangeRateUsdVes} VES/USD',
                'Notificaciones: preparadas para FCM',
                'Soporte: WhatsApp asistido',
              ],
            ),
            if (session?.isAuthenticated == true) ...[
              _CreditSnapshotPanel(customerId: session!.id),
              _OrderSummaryPanel(customerId: session.id),
            ],
            if (session?.isAuthenticated == true)
              OutlinedButton.icon(
                onPressed: _signOut,
                icon: const Icon(Icons.logout_outlined),
                label: const Text('Cerrar sesion'),
              ),
          ],
        );
      },
    );
  }
}

class _LoginPanel extends StatelessWidget {
  const _LoginPanel({
    required this.emailController,
    required this.passwordController,
    required this.isSigningIn,
    required this.onSubmit,
  });

  final TextEditingController emailController;
  final TextEditingController passwordController;
  final bool isSigningIn;
  final VoidCallback onSubmit;

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
              'Acceso ferretero',
              style: Theme.of(context)
                  .textTheme
                  .titleMedium
                  ?.copyWith(fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: emailController,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                labelText: 'Email',
                prefixIcon: Icon(Icons.mail_outline),
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: passwordController,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: 'Contrasena',
                prefixIcon: Icon(Icons.lock_outline),
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: isSigningIn ? null : onSubmit,
              icon: isSigningIn
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.login_outlined),
              label: Text(isSigningIn ? 'Ingresando' : 'Iniciar sesion'),
            ),
          ],
        ),
      ),
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

        return _InfoPanel(
          title: 'Linea de credito',
          lines: [
            credit.creditEnabled
                ? 'Estado: ${credit.status}'
                : 'Estado: no habilitado',
            'Limite: USD ${credit.creditLimitUsd.toStringAsFixed(2)}',
            'Comprometido: USD ${credit.creditExposureUsd.toStringAsFixed(2)}',
            'Disponible: USD ${credit.creditAvailableUsd.toStringAsFixed(2)}',
            'Dias de credito: ${credit.paymentTermsDays}',
          ],
        );
      },
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

        return _InfoPanel(
          title: 'Ordenes recientes',
          lines: [
            for (final order in orders.take(3))
              '${order.id}: ${order.status} - saldo USD ${order.balanceUsd.toStringAsFixed(2)} - stock ${order.stockStatus}',
          ],
        );
      },
    );
  }
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
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(14),
                color: _wulkanOrange.withValues(alpha: 0.12),
              ),
              child: const Icon(
                Icons.campaign_outlined,
                color: _wulkanOrange,
              ),
            ),
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
        borderRadius: BorderRadius.circular(8),
        color: const Color(0xFFEFF4FB),
        border: Border.all(color: const Color(0xFFD9DEE8)),
      ),
      child: const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.map_outlined, size: 40, color: Color(0xFF12315F)),
            SizedBox(height: 8),
            Text('Mapa mock de puntos autorizados'),
            Text('Google Maps/Mapbox pendiente'),
          ],
        ),
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
    this.onAction,
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
  final VoidCallback? onAction;

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
                      padding: EdgeInsets.zero,
                      iconSize: 17,
                      onPressed: onAction ?? onTap,
                      icon: Icon(
                        requiresQuote
                            ? Icons.request_quote_outlined
                            : Icons.shopping_bag_outlined,
                      ),
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
