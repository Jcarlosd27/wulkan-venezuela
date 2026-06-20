from __future__ import annotations

import re
import unicodedata


CHILE_REGION_CITIES: dict[str, list[str]] = {
    "Arica y Parinacota": ["Arica", "Camarones", "General Lagos", "Putre"],
    "Tarapaca": [
        "Alto Hospicio",
        "Camina",
        "Colchane",
        "Huara",
        "Iquique",
        "Pica",
        "Pozo Almonte",
    ],
    "Antofagasta": [
        "Antofagasta",
        "Calama",
        "Maria Elena",
        "Mejillones",
        "Ollague",
        "San Pedro de Atacama",
        "Sierra Gorda",
        "Taltal",
        "Tocopilla",
    ],
    "Atacama": [
        "Alto del Carmen",
        "Caldera",
        "Chanaral",
        "Copiapo",
        "Diego de Almagro",
        "Freirina",
        "Huasco",
        "Tierra Amarilla",
        "Vallenar",
    ],
    "Coquimbo": [
        "Andacollo",
        "Canela",
        "Combarbala",
        "Coquimbo",
        "Illapel",
        "La Higuera",
        "La Serena",
        "Los Vilos",
        "Monte Patria",
        "Ovalle",
        "Paihuano",
        "Punitaqui",
        "Rio Hurtado",
        "Salamanca",
        "Vicuna",
    ],
    "Valparaiso": [
        "Algarrobo",
        "Cabildo",
        "Calera",
        "Calle Larga",
        "Cartagena",
        "Casablanca",
        "Catemu",
        "Concon",
        "El Quisco",
        "El Tabo",
        "Hijuelas",
        "Isla de Pascua",
        "Juan Fernandez",
        "La Cruz",
        "La Ligua",
        "Limache",
        "Llaillay",
        "Los Andes",
        "Nogales",
        "Olmue",
        "Panquehue",
        "Papudo",
        "Petorca",
        "Puchuncavi",
        "Putaendo",
        "Quillota",
        "Quilpue",
        "Quintero",
        "Rinconada",
        "San Antonio",
        "San Esteban",
        "San Felipe",
        "Santa Maria",
        "Santo Domingo",
        "Valparaiso",
        "Villa Alemana",
        "Vina del Mar",
        "Zapallar",
    ],
    "Metropolitana": [
        "Alhue",
        "Buin",
        "Calera de Tango",
        "Cerrillos",
        "Cerro Navia",
        "Colina",
        "Conchali",
        "Curacavi",
        "El Bosque",
        "El Monte",
        "Estacion Central",
        "Huechuraba",
        "Independencia",
        "Isla de Maipo",
        "La Cisterna",
        "La Florida",
        "La Granja",
        "La Pintana",
        "La Reina",
        "Lampa",
        "Las Condes",
        "Lo Barnechea",
        "Lo Espejo",
        "Lo Prado",
        "Macul",
        "Maipu",
        "Maria Pinto",
        "Melipilla",
        "Nunoa",
        "Padre Hurtado",
        "Paine",
        "Pedro Aguirre Cerda",
        "Penaflor",
        "Penalolen",
        "Pirque",
        "Providencia",
        "Pudahuel",
        "Puente Alto",
        "Quilicura",
        "Quinta Normal",
        "Recoleta",
        "Renca",
        "San Bernardo",
        "San Joaquin",
        "San Jose de Maipo",
        "San Miguel",
        "San Pedro",
        "San Ramon",
        "Santiago",
        "Talagante",
        "Tiltil",
        "Vitacura",
    ],
    "O'Higgins": [
        "Chepica",
        "Chimbarongo",
        "Codegua",
        "Coinco",
        "Coltauco",
        "Donihue",
        "Graneros",
        "La Estrella",
        "Las Cabras",
        "Litueche",
        "Lolol",
        "Machali",
        "Malloa",
        "Marchigue",
        "Mostazal",
        "Nancagua",
        "Navidad",
        "Olivar",
        "Palmilla",
        "Paredones",
        "Peralillo",
        "Peumo",
        "Pichidegua",
        "Pichilemu",
        "Placilla",
        "Pumanque",
        "Quinta de Tilcoco",
        "Rancagua",
        "Rengo",
        "Requinoa",
        "San Fernando",
        "San Vicente",
        "Santa Cruz",
    ],
    "Maule": [
        "Cauquenes",
        "Chanco",
        "Colbun",
        "Constitucion",
        "Curepto",
        "Curico",
        "Empedrado",
        "Hualane",
        "Licanten",
        "Linares",
        "Longavi",
        "Maule",
        "Molina",
        "Parral",
        "Pelarco",
        "Pelluhue",
        "Pencahue",
        "Rauco",
        "Retiro",
        "Rio Claro",
        "Romeral",
        "Sagrada Familia",
        "San Clemente",
        "San Javier",
        "San Rafael",
        "Talca",
        "Teno",
        "Vichuquen",
        "Villa Alegre",
        "Yerbas Buenas",
    ],
    "Nuble": [
        "Bulnes",
        "Chillan",
        "Chillan Viejo",
        "Cobquecura",
        "Coelemu",
        "Coihueco",
        "El Carmen",
        "Ninhue",
        "Niquen",
        "Pemuco",
        "Pinto",
        "Portezuelo",
        "Quillon",
        "Quirihue",
        "Ranquil",
        "San Carlos",
        "San Fabian",
        "San Ignacio",
        "San Nicolas",
        "Treguaco",
        "Yungay",
    ],
    "Biobio": [
        "Alto Biobio",
        "Antuco",
        "Arauco",
        "Cabrero",
        "Canete",
        "Chiguayante",
        "Concepcion",
        "Contulmo",
        "Coronel",
        "Curanilahue",
        "Florida",
        "Hualpen",
        "Hualqui",
        "Laja",
        "Lebu",
        "Los Alamos",
        "Los Angeles",
        "Lota",
        "Mulchen",
        "Nacimiento",
        "Negrete",
        "Penco",
        "Quilaco",
        "Quilleco",
        "San Pedro de la Paz",
        "San Rosendo",
        "Santa Barbara",
        "Santa Juana",
        "Talcahuano",
        "Tirua",
        "Tome",
        "Tucapel",
        "Yumbel",
    ],
    "La Araucania": [
        "Angol",
        "Carahue",
        "Cholchol",
        "Collipulli",
        "Cunco",
        "Curacautin",
        "Curarrehue",
        "Ercilla",
        "Freire",
        "Galvarino",
        "Gorbea",
        "Lautaro",
        "Loncoche",
        "Lonquimay",
        "Los Sauces",
        "Lumaco",
        "Melipeuco",
        "Nueva Imperial",
        "Padre Las Casas",
        "Perquenco",
        "Pitrufquen",
        "Pucon",
        "Puren",
        "Renaico",
        "Saavedra",
        "Temuco",
        "Teodoro Schmidt",
        "Tolten",
        "Traiguen",
        "Victoria",
        "Vilcun",
        "Villarrica",
    ],
    "Los Rios": [
        "Corral",
        "Futrono",
        "La Union",
        "Lago Ranco",
        "Lanco",
        "Los Lagos",
        "Mafil",
        "Mariquina",
        "Paillaco",
        "Panguipulli",
        "Rio Bueno",
        "Valdivia",
    ],
    "Los Lagos": [
        "Ancud",
        "Calbuco",
        "Castro",
        "Chaiten",
        "Chonchi",
        "Cochamo",
        "Curaco de Velez",
        "Dalcahue",
        "Fresia",
        "Frutillar",
        "Futaleufu",
        "Hualaihue",
        "Llanquihue",
        "Los Muermos",
        "Maullin",
        "Osorno",
        "Palena",
        "Puerto Montt",
        "Puerto Octay",
        "Puerto Varas",
        "Puqueldon",
        "Purranque",
        "Puyehue",
        "Queilen",
        "Quellon",
        "Quemchi",
        "Quinchao",
        "Rio Negro",
        "San Juan de la Costa",
        "San Pablo",
    ],
    "Aysen": [
        "Aysen",
        "Chile Chico",
        "Cisnes",
        "Cochrane",
        "Coyhaique",
        "Guaitecas",
        "Lago Verde",
        "O'Higgins",
        "Rio Ibanez",
        "Tortel",
    ],
    "Magallanes": [
        "Antartica",
        "Cabo de Hornos",
        "Laguna Blanca",
        "Natales",
        "Porvenir",
        "Primavera",
        "Punta Arenas",
        "Rio Verde",
        "San Gregorio",
        "Timaukel",
        "Torres del Paine",
    ],
}


def _key(value: str | None) -> str:
    raw = str(value or "").strip()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def normalize_chilean_region(value: str | None) -> str:
    value_key = _key(value)
    if not value_key:
        return ""
    for region in CHILE_REGION_CITIES:
        if _key(region) == value_key:
            return region
    return ""


def normalize_chilean_city(region: str | None, value: str | None) -> str:
    normalized_region = normalize_chilean_region(region)
    value_key = _key(value)
    if not normalized_region or not value_key:
        return ""
    for city in CHILE_REGION_CITIES.get(normalized_region, []):
        if _key(city) == value_key:
            return city
    return ""


def normalize_chilean_location(region: str | None, city: str | None) -> tuple[str, str, str]:
    normalized_region = normalize_chilean_region(region)
    if not normalized_region:
        return "", "", "Selecciona una region chilena valida."
    normalized_city = normalize_chilean_city(normalized_region, city)
    if not normalized_city:
        return normalized_region, "", f"Selecciona una comuna valida para {normalized_region}."
    return normalized_region, normalized_city, ""


def normalize_chilean_phone(value: str | None) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if digits.startswith("0056"):
        digits = digits[4:]
    elif digits.startswith("56"):
        digits = digits[2:]
    if len(digits) == 8:
        digits = "9" + digits
    if len(digits) != 9 or not digits.startswith("9"):
        return ""
    return f"+56 9 {digits[1:5]} {digits[5:]}"


def _rut_check_digit(number: str) -> str:
    sequence = [2, 3, 4, 5, 6, 7]
    total = 0
    for index, digit in enumerate(reversed(number)):
        total += int(digit) * sequence[index % len(sequence)]
    result = 11 - (total % 11)
    if result == 11:
        return "0"
    if result == 10:
        return "K"
    return str(result)


def normalize_chilean_rut(value: str | None) -> str:
    compact = re.sub(r"[^0-9Kk]+", "", str(value or "")).upper()
    if len(compact) < 8 or len(compact) > 10:
        return ""
    number, verifier = compact[:-1], compact[-1]
    if not number.isdigit() or verifier not in "0123456789K":
        return ""
    if _rut_check_digit(number) != verifier:
        return ""
    grouped = []
    remaining = number
    while remaining:
        grouped.insert(0, remaining[-3:])
        remaining = remaining[:-3]
    return f"{'.'.join(grouped)}-{verifier}"
