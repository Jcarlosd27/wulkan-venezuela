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

const _zeroDecimalCurrencies = {"CLP"};

String _currencyCode(String value, String fallback) {
  final normalized = value.trim().toUpperCase().replaceAll(
        RegExp(r"[^A-Z]"),
        "",
      );
  if (normalized.isEmpty) {
    return fallback.trim().toUpperCase();
  }
  return normalized.length > 3 ? normalized.substring(0, 3) : normalized;
}

String _countryCode(String value, String fallback) {
  final normalized = value.trim().toUpperCase().replaceAll(
        RegExp(r"[^A-Z]"),
        "",
      );
  if (normalized.isEmpty) {
    return fallback.trim().toUpperCase();
  }
  return normalized;
}

class MobileEnvironment {
  const MobileEnvironment({
    required this.appEnvironment,
    required this.dataSource,
    required this.authMode,
    required this.allowMock,
    required this.mockSessionRole,
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
      mockSessionRole: const String.fromEnvironment(
        "FVENTAS_MOCK_SESSION_ROLE",
        defaultValue: "",
      ),
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
  final String mockSessionRole;
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
  String get countryCode => defaultCountry.trim().toUpperCase();
  bool get usesChileFormat => countryCode == "CL";
  String get displayCurrency => displayCurrencyForMarket();
  bool get displaysPrimaryCurrency => displayCurrency == primaryCurrency;
  String get localCurrency => displayCurrency;
  String get currencyPairLabel => displaysPrimaryCurrency
      ? displayCurrency
      : "$displayCurrency / $primaryCurrency";
  String get exchangeRateLabel => exchangeRateLabelForMarket();
  String get taxLabel => taxLabelForMarket();
  String get taxPlaceholder => taxPlaceholderForMarket();
  String get phonePlaceholder => phonePlaceholderForMarket();

  String taxLabelForMarket({String countryCode = ""}) {
    return switch (_countryCode(countryCode, defaultCountry)) {
      "CL" => "RUT",
      "VE" => "RIF",
      _ => "Documento fiscal",
    };
  }

  String taxPlaceholderForMarket({String countryCode = ""}) {
    return switch (_countryCode(countryCode, defaultCountry)) {
      "CL" => "76.123.456-7",
      "VE" => "J-12345678-9",
      _ => "Documento fiscal",
    };
  }

  String phonePlaceholderForMarket({String countryCode = ""}) {
    return switch (_countryCode(countryCode, defaultCountry)) {
      "CL" => "+56 9 1234 5678",
      "VE" => "+58 412 123 4567",
      _ => "+00 000 000 000",
    };
  }

  String primaryCurrencyForMarket({String primaryCurrency = ""}) {
    return _currencyCode(primaryCurrency, this.primaryCurrency);
  }

  String displayCurrencyForMarket({
    String countryCode = "",
    String localCurrency = "",
    String primaryCurrency = "",
  }) {
    final explicitLocalCurrency = _currencyCode(localCurrency, "");
    if (explicitLocalCurrency.isNotEmpty) {
      return explicitLocalCurrency;
    }

    final effectiveCountry = _countryCode(countryCode, defaultCountry);
    final effectivePrimaryCurrency =
        primaryCurrencyForMarket(primaryCurrency: primaryCurrency);
    return switch (effectiveCountry) {
      "CL" => "CLP",
      "VE" => "USD",
      _ => effectivePrimaryCurrency,
    };
  }

  bool displaysPrimaryCurrencyForMarket({
    String countryCode = "",
    String localCurrency = "",
    String primaryCurrency = "",
  }) {
    return displayCurrencyForMarket(
          countryCode: countryCode,
          localCurrency: localCurrency,
          primaryCurrency: primaryCurrency,
        ) ==
        primaryCurrencyForMarket(primaryCurrency: primaryCurrency);
  }

  double exchangeRateForMarket(double? exchangeRateUsdLocal) {
    final rate = exchangeRateUsdLocal ?? this.exchangeRateUsdLocal;
    return rate.isFinite && rate > 0 ? rate : 1;
  }

  String exchangeRateLabelForMarket({
    String countryCode = "",
    String localCurrency = "",
    String primaryCurrency = "",
  }) {
    final displayCurrency = displayCurrencyForMarket(
      countryCode: countryCode,
      localCurrency: localCurrency,
      primaryCurrency: primaryCurrency,
    );
    final effectivePrimaryCurrency =
        primaryCurrencyForMarket(primaryCurrency: primaryCurrency);
    return displayCurrency == effectivePrimaryCurrency
        ? displayCurrency
        : "$displayCurrency/$effectivePrimaryCurrency";
  }

  String currencySymbolForMarket({
    String countryCode = "",
    String localCurrency = "",
    String primaryCurrency = "",
  }) {
    return currencySymbolForCurrency(
      displayCurrencyForMarket(
        countryCode: countryCode,
        localCurrency: localCurrency,
        primaryCurrency: primaryCurrency,
      ),
    );
  }

  String currencySymbolForCurrency(String currency) {
    return switch (_currencyCode(currency, primaryCurrency)) {
      "USD" || "CLP" => r"$",
      _ => "${_currencyCode(currency, primaryCurrency)} ",
    };
  }

  double visibleAmountFromUsd(double usdAmount) {
    return visibleAmountFromUsdForMarket(usdAmount);
  }

  double visibleAmountFromUsdForMarket(
    double usdAmount, {
    String countryCode = "",
    String localCurrency = "",
    String primaryCurrency = "",
    double? exchangeRateUsdLocal,
  }) {
    final displayCurrency = displayCurrencyForMarket(
      countryCode: countryCode,
      localCurrency: localCurrency,
      primaryCurrency: primaryCurrency,
    );
    final effectivePrimaryCurrency =
        primaryCurrencyForMarket(primaryCurrency: primaryCurrency);
    if (displayCurrency == effectivePrimaryCurrency) {
      return usdAmount;
    }
    return usdAmount * exchangeRateForMarket(exchangeRateUsdLocal);
  }

  double visibleAmountToUsd(double visibleAmount) {
    return visibleAmountToUsdForMarket(visibleAmount);
  }

  double visibleAmountToUsdForMarket(
    double visibleAmount, {
    String countryCode = "",
    String localCurrency = "",
    String primaryCurrency = "",
    double? exchangeRateUsdLocal,
  }) {
    final displayCurrency = displayCurrencyForMarket(
      countryCode: countryCode,
      localCurrency: localCurrency,
      primaryCurrency: primaryCurrency,
    );
    final effectivePrimaryCurrency =
        primaryCurrencyForMarket(primaryCurrency: primaryCurrency);
    if (displayCurrency == effectivePrimaryCurrency) {
      return visibleAmount;
    }
    return visibleAmount / exchangeRateForMarket(exchangeRateUsdLocal);
  }

  String moneyFromUsd(double usdAmount, {int? fractionDigits}) {
    return moneyFromUsdForMarket(usdAmount, fractionDigits: fractionDigits);
  }

  String moneyFromUsdForMarket(
    double usdAmount, {
    String countryCode = "",
    String localCurrency = "",
    String primaryCurrency = "",
    double? exchangeRateUsdLocal,
    int? fractionDigits,
  }) {
    final displayCurrency = displayCurrencyForMarket(
      countryCode: countryCode,
      localCurrency: localCurrency,
      primaryCurrency: primaryCurrency,
    );
    final digits = fractionDigits ??
        (_zeroDecimalCurrencies.contains(displayCurrency) ? 0 : 2);
    final amount = visibleAmountFromUsdForMarket(
      usdAmount,
      countryCode: countryCode,
      localCurrency: localCurrency,
      primaryCurrency: primaryCurrency,
      exchangeRateUsdLocal: exchangeRateUsdLocal,
    );
    return "${currencySymbolForCurrency(displayCurrency)}${_formatMoneyAmount(amount, digits, displayCurrency)}";
  }

  String localMoney(double baseAmount) {
    return moneyFromUsd(baseAmount);
  }

  String _formatMoneyAmount(
    double amount,
    int fractionDigits,
    String currency,
  ) {
    final normalized = amount.isFinite ? amount : 0;
    final fixed = normalized.abs().toStringAsFixed(fractionDigits);
    final parts = fixed.split(".");
    final integer = parts.first;
    final buffer = StringBuffer();
    final usesLatinSeparators = currency != "USD";

    for (var index = 0; index < integer.length; index += 1) {
      final remaining = integer.length - index;
      buffer.write(integer[index]);
      if (remaining > 1 && remaining % 3 == 1) {
        buffer.write(usesLatinSeparators ? "." : ",");
      }
    }

    final sign = normalized < 0 ? "-" : "";
    if (fractionDigits == 0) {
      return "$sign$buffer";
    }
    final decimals = parts.length > 1 ? parts.last : "";
    final decimalSeparator = usesLatinSeparators ? "," : ".";
    return "$sign$buffer$decimalSeparator$decimals";
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
