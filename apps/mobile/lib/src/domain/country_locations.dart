import 'dart:convert';

import 'package:flutter/services.dart';

class CountryLocationProfile {
  const CountryLocationProfile({
    required this.countryCode,
    required this.countryName,
    required this.stateLabel,
    required this.cityLabel,
    required this.statePlaceholder,
    required this.cityPlaceholder,
    required this.locations,
  });

  final String countryCode;
  final String countryName;
  final String stateLabel;
  final String cityLabel;
  final String statePlaceholder;
  final String cityPlaceholder;
  final Map<String, List<String>> locations;

  bool get hasLocations => locations.isNotEmpty;

  List<String> get states => locations.keys.toList(growable: false);

  List<String> citiesFor(String? state) {
    if (state == null || state.trim().isEmpty) {
      return const [];
    }
    return locations[state] ?? const [];
  }

  factory CountryLocationProfile.fromJson(
    String countryCode,
    Map<String, dynamic> json,
  ) {
    final rawLocations = json["locations"];
    final locations = <String, List<String>>{};
    if (rawLocations is Map<String, dynamic>) {
      for (final entry in rawLocations.entries) {
        final rawCities = entry.value;
        if (rawCities is List) {
          locations[entry.key] = rawCities
              .map((city) => city.toString())
              .where((city) => city.trim().isNotEmpty)
              .toList(growable: false);
        }
      }
    }
    return CountryLocationProfile(
      countryCode: countryCode,
      countryName: json["countryName"]?.toString() ?? countryCode,
      stateLabel: json["stateLabel"]?.toString() ?? "Region / estado",
      cityLabel: json["cityLabel"]?.toString() ?? "Ciudad",
      statePlaceholder:
          json["statePlaceholder"]?.toString() ?? "Selecciona region / estado",
      cityPlaceholder:
          json["cityPlaceholder"]?.toString() ?? "Selecciona ciudad",
      locations: locations,
    );
  }

  static CountryLocationProfile fallback(String countryCode) {
    return CountryLocationProfile(
      countryCode: countryCode,
      countryName: countryCode,
      stateLabel: "Region / estado",
      cityLabel: "Ciudad",
      statePlaceholder: "Ingresa region / estado",
      cityPlaceholder: "Ingresa ciudad",
      locations: const {},
    );
  }
}

class CountryLocationLibrary {
  final Map<String, CountryLocationProfile> _profiles = {};

  Future<void> load({
    String assetPath = "assets/country_locations.json",
  }) async {
    if (_profiles.isNotEmpty) {
      return;
    }
    final raw = await rootBundle.loadString(assetPath);
    final decoded = jsonDecode(raw);
    if (decoded is! Map<String, dynamic>) {
      return;
    }
    for (final entry in decoded.entries) {
      final value = entry.value;
      if (value is Map<String, dynamic>) {
        _profiles[_normalizeCountry(entry.key)] =
            CountryLocationProfile.fromJson(
                _normalizeCountry(entry.key), value);
      }
    }
  }

  CountryLocationProfile profileFor(String countryCode) {
    final code = _normalizeCountry(countryCode);
    return _profiles[code] ?? CountryLocationProfile.fallback(code);
  }

  static String _normalizeCountry(String value) =>
      value.trim().toUpperCase().isEmpty ? "CL" : value.trim().toUpperCase();
}

final countryLocations = CountryLocationLibrary();
