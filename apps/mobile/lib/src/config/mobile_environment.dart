enum MobileDataSource {
  mock,
  api,
  firestore;

  static MobileDataSource fromValue(String value) {
    return switch (value) {
      "api" => MobileDataSource.api,
      "firestore" => MobileDataSource.firestore,
      _ => MobileDataSource.mock,
    };
  }
}

enum MobileAuthMode {
  mock,
  api,
  firebase;

  static MobileAuthMode fromValue(String value) {
    return switch (value) {
      "api" => MobileAuthMode.api,
      "firebase" => MobileAuthMode.firebase,
      _ => MobileAuthMode.mock,
    };
  }
}

class MobileEnvironment {
  const MobileEnvironment({
    required this.projectId,
    required this.dataSource,
    required this.authMode,
    required this.defaultCountry,
    required this.primaryCurrency,
    required this.secondaryCurrency,
    required this.exchangeRateUsdVes,
    required this.firestoreEmulatorHost,
    required this.adminApiUrl,
    required this.orderApiUrl,
  });

  factory MobileEnvironment.fromDartDefines() {
    const exchangeRate = String.fromEnvironment("WULKAN_EXCHANGE_RATE_USD_VES",
        defaultValue: "38.5");

    return MobileEnvironment(
      projectId: const String.fromEnvironment("WULKAN_FIREBASE_PROJECT_ID",
          defaultValue: "wulkan-dev"),
      dataSource: MobileDataSource.fromValue(
        const String.fromEnvironment("WULKAN_MOBILE_DATA_SOURCE",
            defaultValue: "mock"),
      ),
      authMode: MobileAuthMode.fromValue(
        const String.fromEnvironment("WULKAN_MOBILE_AUTH_MODE",
            defaultValue: "mock"),
      ),
      defaultCountry: const String.fromEnvironment("WULKAN_DEFAULT_COUNTRY",
          defaultValue: "VE"),
      primaryCurrency: const String.fromEnvironment("WULKAN_PRIMARY_CURRENCY",
          defaultValue: "USD"),
      secondaryCurrency: const String.fromEnvironment(
          "WULKAN_SECONDARY_CURRENCY",
          defaultValue: "VES"),
      exchangeRateUsdVes: double.tryParse(exchangeRate) ?? 38.5,
      firestoreEmulatorHost:
          const String.fromEnvironment("WULKAN_FIRESTORE_EMULATOR_HOST"),
      adminApiUrl: const String.fromEnvironment(
        "WULKAN_ADMIN_API_URL",
        defaultValue: "http://10.0.2.2:5000/api/mobile",
      ),
      orderApiUrl: const String.fromEnvironment(
        "WULKAN_MOBILE_ORDER_API_URL",
      ),
    );
  }

  final String projectId;
  final MobileDataSource dataSource;
  final MobileAuthMode authMode;
  final String defaultCountry;
  final String primaryCurrency;
  final String secondaryCurrency;
  final double exchangeRateUsdVes;
  final String firestoreEmulatorHost;
  final String adminApiUrl;
  final String orderApiUrl;

  bool get usesFirestore => dataSource == MobileDataSource.firestore;
  bool get usesApi => dataSource == MobileDataSource.api;
  bool get usesApiAuth => authMode == MobileAuthMode.api;
  bool get usesFirebaseAuth => authMode == MobileAuthMode.firebase;

  String get dataSourceLabel => switch (dataSource) {
        MobileDataSource.api => "Flask API",
        MobileDataSource.firestore => "Firestore",
        MobileDataSource.mock => "Mock",
      };
  String get authModeLabel => switch (authMode) {
        MobileAuthMode.api => "Flask API",
        MobileAuthMode.firebase => "Firebase Auth",
        MobileAuthMode.mock => "Mock",
      };
  bool get usesOrderApi => orderApiUrl.isNotEmpty;
}

final mobileEnvironment = MobileEnvironment.fromDartDefines();
