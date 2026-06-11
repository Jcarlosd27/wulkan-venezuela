enum MobileDataSource {
  mock,
  api;

  static MobileDataSource fromValue(String value) {
    return switch (value) {
      "api" => MobileDataSource.api,
      _ => MobileDataSource.mock,
    };
  }
}

enum MobileAuthMode {
  mock,
  api;

  static MobileAuthMode fromValue(String value) {
    return switch (value) {
      "api" => MobileAuthMode.api,
      _ => MobileAuthMode.mock,
    };
  }
}

class MobileEnvironment {
  const MobileEnvironment({
    required this.appEnvironment,
    required this.dataSource,
    required this.authMode,
    required this.allowMock,
    required this.defaultCountry,
    required this.primaryCurrency,
    required this.secondaryCurrency,
    required this.exchangeRateUsdVes,
    required this.adminApiUrl,
    required this.orderApiUrl,
  });

  factory MobileEnvironment.fromDartDefines() {
    const exchangeRate = String.fromEnvironment(
      "WULKAN_EXCHANGE_RATE_USD_VES",
      defaultValue: "38.5",
    );
    const appEnvironment = String.fromEnvironment(
      "WULKAN_APP_ENV",
      defaultValue: "production",
    );
    const allowMock =
        bool.fromEnvironment("WULKAN_ALLOW_MOCK", defaultValue: false);

    return MobileEnvironment(
      appEnvironment: appEnvironment,
      dataSource: MobileDataSource.fromValue(
        const String.fromEnvironment(
          "WULKAN_MOBILE_DATA_SOURCE",
          defaultValue: "api",
        ),
      ),
      authMode: MobileAuthMode.fromValue(
        const String.fromEnvironment(
          "WULKAN_MOBILE_AUTH_MODE",
          defaultValue: "api",
        ),
      ),
      allowMock: allowMock,
      defaultCountry: const String.fromEnvironment(
        "WULKAN_DEFAULT_COUNTRY",
        defaultValue: "VE",
      ),
      primaryCurrency: const String.fromEnvironment(
        "WULKAN_PRIMARY_CURRENCY",
        defaultValue: "USD",
      ),
      secondaryCurrency: const String.fromEnvironment(
        "WULKAN_SECONDARY_CURRENCY",
        defaultValue: "VES",
      ),
      exchangeRateUsdVes: double.tryParse(exchangeRate) ?? 38.5,
      adminApiUrl: const String.fromEnvironment(
        "WULKAN_ADMIN_API_URL",
        defaultValue: "https://crmwulky.com.ve/api/v1/mobile",
      ),
      orderApiUrl: const String.fromEnvironment(
        "WULKAN_MOBILE_ORDER_API_URL",
        defaultValue: "https://crmwulky.com.ve/api/v1/mobile/orders",
      ),
    );
  }

  final String appEnvironment;
  final MobileDataSource dataSource;
  final MobileAuthMode authMode;
  final bool allowMock;
  final String defaultCountry;
  final String primaryCurrency;
  final String secondaryCurrency;
  final double exchangeRateUsdVes;
  final String adminApiUrl;
  final String orderApiUrl;

  bool get usesApi => dataSource == MobileDataSource.api;
  bool get usesApiAuth => authMode == MobileAuthMode.api;
  bool get usesMock => dataSource == MobileDataSource.mock;
  bool get usesMockAuth => authMode == MobileAuthMode.mock;
  bool get isProduction => appEnvironment == "production";

  String get dataSourceLabel => switch (dataSource) {
        MobileDataSource.api => "Flask API",
        MobileDataSource.mock => "Mock local",
      };
  String get authModeLabel => switch (authMode) {
        MobileAuthMode.api => "Flask API",
        MobileAuthMode.mock => "Mock local",
      };
  bool get usesOrderApi => orderApiUrl.isNotEmpty;

  void validateRuntime() {
    final usesAnyMock = usesMock || usesMockAuth;
    if (usesAnyMock && !allowMock) {
      throw StateError(
        "Modo mock bloqueado. Usa WULKAN_ALLOW_MOCK=true solo en desarrollo.",
      );
    }
  }
}

final mobileEnvironment = MobileEnvironment.fromDartDefines();
