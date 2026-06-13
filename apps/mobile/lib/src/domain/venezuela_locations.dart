const Map<String, List<String>> venezuelaStateCities = {
  'Amazonas': ['Puerto Ayacucho', 'San Fernando de Atabapo', 'Maroa'],
  'Anzoategui': [
    'Barcelona',
    'Puerto La Cruz',
    'Lecheria',
    'El Tigre',
    'Anaco',
    'Puerto Piritu',
    'Pariaguan'
  ],
  'Apure': ['San Fernando de Apure', 'Guasdualito', 'Achaguas', 'Biruaca'],
  'Aragua': [
    'Maracay',
    'Turmero',
    'La Victoria',
    'Cagua',
    'Palo Negro',
    'Villa de Cura'
  ],
  'Barinas': ['Barinas', 'Socopo', 'Barinitas', 'Sabaneta', 'Santa Barbara'],
  'Bolivar': [
    'Ciudad Bolivar',
    'Puerto Ordaz',
    'San Felix',
    'Upata',
    'Ciudad Piar',
    'Tumeremo'
  ],
  'Carabobo': [
    'Valencia',
    'Naguanagua',
    'San Diego',
    'Guacara',
    'Puerto Cabello',
    'Mariara',
    'Bejuma'
  ],
  'Cojedes': ['San Carlos', 'Tinaquillo', 'Tinaco', 'El Baul'],
  'Delta Amacuro': ['Tucupita', 'Pedernales', 'Curiapo'],
  'Distrito Capital': ['Caracas'],
  'Falcon': [
    'Coro',
    'Punto Fijo',
    'Tucacas',
    'Chichiriviche',
    'La Vela de Coro'
  ],
  'Guarico': [
    'San Juan de los Morros',
    'Calabozo',
    'Valle de la Pascua',
    'Zaraza',
    'Altagracia de Orituco'
  ],
  'Lara': ['Barquisimeto', 'Cabudare', 'Carora', 'El Tocuyo', 'Quibor'],
  'Merida': ['Merida', 'El Vigia', 'Ejido', 'Tovar', 'Mucuchies'],
  'Miranda': [
    'Los Teques',
    'Guarenas',
    'Guatire',
    'Charallave',
    'Santa Teresa del Tuy',
    'Petare',
    'Chacao',
    'Baruta'
  ],
  'Monagas': ['Maturin', 'Punta de Mata', 'Temblador', 'Caripe'],
  'Nueva Esparta': ['Porlamar', 'La Asuncion', 'Juan Griego', 'Pampatar'],
  'Portuguesa': ['Guanare', 'Acarigua', 'Araure', 'Turen', 'Biscucuy'],
  'Sucre': ['Cumana', 'Carupano', 'Guiria', 'Cariaco'],
  'Tachira': [
    'San Cristobal',
    'Rubio',
    'Tariba',
    'La Grita',
    'San Antonio del Tachira'
  ],
  'Trujillo': ['Valera', 'Trujillo', 'Bocono', 'Pampanito'],
  'La Guaira': [
    'La Guaira',
    'Catia La Mar',
    'Maiquetia',
    'Macuto',
    'Caraballeda'
  ],
  'Yaracuy': ['San Felipe', 'Yaritagua', 'Chivacoa', 'Nirgua'],
  'Zulia': [
    'Maracaibo',
    'Cabimas',
    'Ciudad Ojeda',
    'Machiques',
    'La Villa del Rosario',
    'Santa Barbara del Zulia'
  ],
};

const Set<String> _venezuelaPhonePrefixes = {
  '212',
  '234',
  '235',
  '238',
  '239',
  '240',
  '241',
  '242',
  '243',
  '244',
  '245',
  '246',
  '247',
  '248',
  '249',
  '251',
  '252',
  '253',
  '254',
  '255',
  '256',
  '257',
  '258',
  '259',
  '261',
  '262',
  '263',
  '264',
  '265',
  '266',
  '267',
  '268',
  '269',
  '271',
  '272',
  '273',
  '274',
  '275',
  '276',
  '277',
  '278',
  '279',
  '281',
  '282',
  '283',
  '285',
  '286',
  '287',
  '288',
  '291',
  '292',
  '293',
  '294',
  '295',
  '412',
  '414',
  '416',
  '424',
  '426',
};

const Set<String> _rifPrefixes = {'V', 'E', 'J', 'G', 'P'};

List<String> get venezuelaStates =>
    venezuelaStateCities.keys.toList(growable: false);

List<String> venezuelanCitiesFor(String? state) {
  if (state == null || state.trim().isEmpty) {
    return const [];
  }
  return venezuelaStateCities[state] ?? const [];
}

String normalizeVenezuelanPhone(String value) {
  var digits = value.replaceAll(RegExp(r'\D+'), '');
  if (digits.startsWith('0058')) {
    digits = digits.substring(4);
  } else if (digits.startsWith('58')) {
    digits = digits.substring(2);
  }
  if (digits.startsWith('0') && digits.length == 11) {
    digits = digits.substring(1);
  }
  if (digits.length != 10 ||
      !_venezuelaPhonePrefixes.contains(digits.substring(0, 3))) {
    return '';
  }
  return '+58 ${digits.substring(0, 3)}-${digits.substring(3)}';
}

bool isValidVenezuelanPhone(String value) =>
    normalizeVenezuelanPhone(value).isNotEmpty;

String normalizeVenezuelanRif(String value) {
  final compact = value.toUpperCase().replaceAll(RegExp(r'[^A-Z0-9]+'), '');
  if (compact.length < 8) {
    return '';
  }
  final prefix = compact.substring(0, 1);
  final digits = compact.substring(1).replaceAll(RegExp(r'\D+'), '');
  if (!_rifPrefixes.contains(prefix) || digits.length != 9) {
    return '';
  }
  return '$prefix-${digits.substring(0, 8)}-${digits.substring(8)}';
}

bool isValidVenezuelanRif(String value) =>
    normalizeVenezuelanRif(value).isNotEmpty;
