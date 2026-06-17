const Map<String, List<String>> chileRegionCommunes = {
  'Arica y Parinacota': ['Arica', 'Putre'],
  'Tarapaca': ['Iquique', 'Alto Hospicio', 'Pozo Almonte'],
  'Antofagasta': ['Antofagasta', 'Calama', 'Tocopilla', 'Mejillones'],
  'Atacama': ['Copiapo', 'Caldera', 'Vallenar'],
  'Coquimbo': ['La Serena', 'Coquimbo', 'Ovalle', 'Illapel'],
  'Valparaiso': [
    'Valparaiso',
    'Vina del Mar',
    'Quilpue',
    'Villa Alemana',
    'San Antonio',
    'Los Andes'
  ],
  'Metropolitana': [
    'Santiago',
    'Puente Alto',
    'Maipu',
    'Las Condes',
    'Providencia',
    'La Florida',
    'Quilicura',
    'Pudahuel'
  ],
  "O'Higgins": ['Rancagua', 'San Fernando', 'Rengo', 'Machali'],
  'Maule': ['Talca', 'Curico', 'Linares', 'Cauquenes'],
  'Nuble': ['Chillan', 'San Carlos', 'Bulnes'],
  'Biobio': ['Concepcion', 'Talcahuano', 'Los Angeles', 'Coronel'],
  'La Araucania': ['Temuco', 'Padre Las Casas', 'Villarrica', 'Angol'],
  'Los Rios': ['Valdivia', 'La Union', 'Panguipulli'],
  'Los Lagos': ['Puerto Montt', 'Osorno', 'Castro', 'Ancud'],
  'Aysen': ['Coyhaique', 'Puerto Aysen', 'Chile Chico'],
  'Magallanes': ['Punta Arenas', 'Puerto Natales', 'Porvenir'],
};

List<String> get chileRegions => chileRegionCommunes.keys.toList(growable: false);

List<String> communesForRegion(String? region) {
  if (region == null || region.trim().isEmpty) {
    return const [];
  }
  return chileRegionCommunes[region] ?? const [];
}

String normalizeChileanPhone(String value) {
  var digits = value.replaceAll(RegExp(r'\D+'), '');
  if (digits.startsWith('0056')) {
    digits = digits.substring(4);
  } else if (digits.startsWith('56')) {
    digits = digits.substring(2);
  }
  if (digits.length == 8) {
    digits = '9$digits';
  }
  if (digits.length != 9 || !digits.startsWith('9')) {
    return '';
  }
  return '+56 9 ${digits.substring(1, 5)} ${digits.substring(5)}';
}

bool isValidChileanPhone(String value) => normalizeChileanPhone(value).isNotEmpty;

String _rutVerifier(String number) {
  const sequence = [2, 3, 4, 5, 6, 7];
  var total = 0;
  final reversed = number.split('').reversed.toList();
  for (var index = 0; index < reversed.length; index++) {
    total += int.parse(reversed[index]) * sequence[index % sequence.length];
  }
  final result = 11 - (total % 11);
  if (result == 11) return '0';
  if (result == 10) return 'K';
  return result.toString();
}

String normalizeChileanRut(String value) {
  final compact = value.toUpperCase().replaceAll(RegExp(r'[^0-9K]+'), '');
  if (compact.length < 8 || compact.length > 10) {
    return '';
  }
  final number = compact.substring(0, compact.length - 1);
  final verifier = compact.substring(compact.length - 1);
  if (!RegExp(r'^\d+$').hasMatch(number) ||
      !RegExp(r'^[0-9K]$').hasMatch(verifier) ||
      _rutVerifier(number) != verifier) {
    return '';
  }
  final parts = <String>[];
  var remaining = number;
  while (remaining.isNotEmpty) {
    final start = remaining.length > 3 ? remaining.length - 3 : 0;
    parts.insert(0, remaining.substring(start));
    remaining = remaining.substring(0, start);
  }
  return '${parts.join('.')}-$verifier';
}

bool isValidChileanRut(String value) => normalizeChileanRut(value).isNotEmpty;
