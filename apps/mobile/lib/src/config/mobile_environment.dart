enum MobileDataSource {
  mock,
  api;

  static MobileDataSource fromValue(String value) {
    return switch (value.trim().toLowerCase()) {
      "mock" => MobileDataSource.mock,
      "api" => MobileDataSource.api,
      _ => MobileDataSource.api,
    };
  }
}

enum MobileAuthMode {
  mock,
  api;

  static MobileAuthMode fromValue(String value) {
    return switch (value.trim().toLowerCase()) {
      "mock" => MobileAuthMode.mock,
      "api" => MobileAuthMode.api,
      _ => MobileAuthMode.api,
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
    required this.exchangeRateUsdLocal,
    required this.adminApiUrl,
    required this.orderApiUrl,
  });

  factory MobileEnvironment.fromDartDefines() {
    const legacyExchangeRate = String.fromEnvironment(
      "FVENTAS_EXCHANGE_RATE_USD_CLP",
      defaultValue: "950",
    );
    const exchangeRate = String.fromEnvironment(
      "FVENTAS_EXCHANGE_RATE_USD_LOCAL",
      defaultValue: legacyExchangeRate,
    );
    const appEnvironment = String.fromEnvironment(
      "FVENTAS_APP_ENV",
      defaultValue: "production",
    );
    const allowMock =
        bool.fromEnvironment("FVENTAS_ALLOW_MOCK", defaultValue: false);

    return MobileEnvironment(
      appEnvironment: appEnvironment,
      dataSource: MobileDataSource.fromValue(
        const String.fromEnvironment(
          "FVENTAS_MOBILE_DATA_SOURCE",
          defaultValue: "api",
        ),
      ),
      authMode: MobileAuthMode.fromValue(
        const String.fromEnvironment(
          "FVENTAS_MOBILE_AUTH_MODE",
          defaultValue: "api",
        ),
      ),
      allowMock: allowMock,
      defaultCountry: const String.fromEnvironment(
        "FVENTAS_DEFAULT_COUNTRY",
        defaultValue: "CL",
      ),
      primaryCurrency: const String.fromEnvironment(
        "FVENTAS_PRIMARY_CURRENCY",
        defaultValue: "USD",
      ),
      secondaryCurrency: const String.fromEnvironment(
        "FVENTAS_SECONDARY_CURRENCY",
        defaultValue: "CLP",
      ),
      exchangeRateUsdLocal: double.tryParse(exchangeRate) ?? 950,
      adminApiUrl: const String.fromEnvironment(
        "FVENTAS_ADMIN_API_URL",
        defaultValue: "https://fventas.cl/api/v1/mobile",
      ),
      orderApiUrl: const String.fromEnvironment(
        "FVENTAS_MOBILE_ORDER_API_URL",
        defaultValue: "https://fventas.cl/api/v1/mobile/orders",
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
  final double exchangeRateUsdLocal;
  final String adminApiUrl;
  final String orderApiUrl;

  bool get usesApi => dataSource == MobileDataSource.api;
  bool get usesApiAuth => authMode == MobileAuthMode.api;
  bool get usesMock => dataSource == MobileDataSource.mock;
  bool get usesMockAuth => authMode == MobileAuthMode.mock;
  bool get isProduction => appEnvironment == "production";
  bool get usesChileFormat => defaultCountry.trim().toUpperCase() == "CL";
  String get localCurrency => secondaryCurrency;
  String get currencyPairLabel => "$primaryCurrency / $secondaryCurrency";
  String get exchangeRateLabel => "$secondaryCurrency/$primaryCurrency";
  String get taxLabel => usesChileFormat ? "RUT" : "Documento fiscal";
  String get taxPlaceholder =>
      usesChileFormat ? "76.123.456-7" : "Documento fiscal";
  String get phonePlaceholder =>
      usesChileFormat ? "+56 9 1234 5678" : "+00 000 000 000";

  String localMoney(double baseAmount) {
    return "$secondaryCurrency ${(baseAmount * exchangeRateUsdLocal).toStringAsFixed(2)}";
  }

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
        "Modo mock bloqueado. Usa FVENTAS_ALLOW_MOCK=true solo en desarrollo.",
      );
    }
    if (isProduction) {
      _requireHttpsEndpoint("FVENTAS_ADMIN_API_URL", adminApiUrl);
      if (usesOrderApi) {
        _requireHttpsEndpoint("FVENTAS_MOBILE_ORDER_API_URL", orderApiUrl);
      }
    }
  }

  void _requireHttpsEndpoint(String label, String value) {
    final uri = Uri.tryParse(value);
    if (uri == null || !uri.hasScheme || uri.scheme != "https") {
      throw StateError("$label debe usar HTTPS en produccion.");
    }
  }
}

final mobileEnvironment = MobileEnvironment.fromDartDefines();
