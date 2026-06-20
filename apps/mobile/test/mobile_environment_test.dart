import 'package:flutter_test/flutter_test.dart';
import 'package:fventas_mobile/src/config/mobile_environment.dart';
import 'package:fventas_mobile/src/domain/chile_locations.dart';
import 'package:fventas_mobile/src/domain/country_locations.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  MobileEnvironment environmentFor(String country) {
    return MobileEnvironment(
      appEnvironment: 'development',
      dataSource: MobileDataSource.mock,
      authMode: MobileAuthMode.mock,
      allowMock: true,
      mockSessionRole: '',
      defaultCountry: country,
      primaryCurrency: country == 'VE' ? 'USD' : 'CLP',
      secondaryCurrency: 'CLP',
      exchangeRateUsdLocal: 1,
      adminApiUrl: 'http://localhost:5000/api/v1/mobile',
      orderApiUrl: '',
    );
  }

  test('formats Chile prices in Chilean pesos', () {
    final environment = environmentFor('CL');

    expect(environment.displayCurrency, 'CLP');
    expect(environment.moneyFromUsd(153900), r'$153.900');
    expect(environment.visibleAmountToUsd(153900), 153900);
  });

  test('formats Venezuela prices in dollars', () {
    final environment = environmentFor('VE');

    expect(environment.displayCurrency, 'USD');
    expect(environment.moneyFromUsd(162), r'$162.00');
    expect(environment.visibleAmountToUsd(162), 162);
  });

  test('uses subscription market over build default country', () {
    final environment = environmentFor('CL');

    expect(
      environment.moneyFromUsdForMarket(
        162,
        countryCode: 'VE',
        localCurrency: 'USD',
        primaryCurrency: 'USD',
        exchangeRateUsdLocal: 1,
      ),
      r'$162.00',
    );
    expect(
      environment.visibleAmountToUsdForMarket(
        162,
        countryCode: 'VE',
        localCurrency: 'USD',
        primaryCurrency: 'USD',
        exchangeRateUsdLocal: 1,
      ),
      162,
    );
  });

  test('converts with the subscription market exchange rate', () {
    final environment = environmentFor('VE');

    expect(
      environment.moneyFromUsdForMarket(
        100,
        countryCode: 'CL',
        localCurrency: 'CLP',
        primaryCurrency: 'USD',
        exchangeRateUsdLocal: 900,
      ),
      r'$90.000',
    );
    expect(
      environment.visibleAmountToUsdForMarket(
        90000,
        countryCode: 'CL',
        localCurrency: 'CLP',
        primaryCurrency: 'USD',
        exchangeRateUsdLocal: 900,
      ),
      100,
    );
  });

  test('ships the complete Chile region and commune catalog', () {
    final totalCommunes = chileRegionCommunes.values.fold<int>(
      0,
      (total, communes) => total + communes.length,
    );

    expect(chileRegionCommunes.length, 16);
    expect(totalCommunes, 346);
    expect(chileRegionCommunes['Metropolitana'], contains('San Jose de Maipo'));
    expect(chileRegionCommunes['Aysen'], contains("O'Higgins"));
  });

  test('ships Chile and Venezuela country location catalogs', () async {
    await countryLocations.load();

    expect(countryLocations.profileFor('CL').states.length, 16);
    expect(countryLocations.profileFor('CL').citiesFor('Metropolitana'),
        contains('Santiago'));
    expect(countryLocations.profileFor('VE').states.length, 25);
    expect(countryLocations.profileFor('VE').citiesFor('Miranda'),
        contains('Baruta'));
    expect(countryLocations.profileFor('PE').hasLocations, isFalse);
    expect(countryLocations.profileFor('AR').hasLocations, isFalse);
    expect(countryLocations.profileFor('CO').hasLocations, isFalse);
    expect(countryLocations.profileFor('EC').hasLocations, isFalse);
  });
}
