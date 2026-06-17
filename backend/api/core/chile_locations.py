from __future__ import annotations

import re
import unicodedata


CHILE_REGION_CITIES: dict[str, list[str]] = {
    "Arica y Parinacota": [
        "Arica", "Putre", "Camarones", "General Lagos"
    ],

    "Tarapaca": [
        "Iquique", "Alto Hospicio", "Pozo Almonte",
        "Pica", "Huara", "Colchane", "Camiña"
    ],

    "Antofagasta": [
        "Antofagasta", "Calama", "Tocopilla", "Mejillones",
        "San Pedro de Atacama", "Taltal", "Maria Elena", "Sierra Gorda", "Ollague"
    ],

    "Atacama": [
        "Copiapo", "Caldera", "Vallenar",
        "Chanaral", "Diego de Almagro", "Freirina",
        "Huasco", "Tierra Amarilla", "Alto del Carmen"
    ],

    "Coquimbo": [
        "La Serena", "Coquimbo", "Ovalle", "Illapel",
        "Salamanca", "Los Vilos", "Andacollo", "Vicuña",
        "Monte Patria", "Punitaqui", "Combarbala", "Paihuano"
    ],

    "Valparaiso": [
        "Valparaiso", "Vina del Mar", "Quilpue", "Villa Alemana",
        "San Antonio", "Los Andes", "Quillota", "La Calera",
        "Limache", "Concón", "Casablanca", "Cartagena",
        "El Quisco", "El Tabo", "Algarrobo", "La Ligua",
        "Cabildo", "San Felipe", "Putaendo", "Petorca"
    ],

    "Metropolitana": [
        "Santiago", "Puente Alto", "Maipu", "Las Condes",
        "Providencia", "La Florida", "Quilicura", "Pudahuel",
        "San Bernardo", "Estacion Central", "Lo Barnechea",
        "Penalolen", "Nunoa", "Recoleta", "Independencia",
        "Cerrillos", "Conchali", "Huechuraba", "Vitacura",
        "Colina", "Lampa", "Melipilla", "Talagante",
        "Buin", "Paine", "Curacavi", "Padre Hurtado"
    ],

    "O'Higgins": [
        "Rancagua", "San Fernando", "Rengo", "Machali",
        "Santa Cruz", "Graneros", "Codegua", "Mostazal",
        "Pichilemu", "Chimbarongo", "Las Cabras", "Requinoa"
    ],

    "Maule": [
        "Talca", "Curico", "Linares", "Cauquenes",
        "Constitucion", "Parral", "Molina", "San Javier",
        "Longavi", "Teno", "Romeral", "Retiro"
    ],

    "Nuble": [
        "Chillan", "San Carlos", "Bulnes",
        "Chillan Viejo", "Yungay", "Coihueco",
        "Quirihue", "Portezuelo", "Cobquecura"
    ],

    "Biobio": [
        "Concepcion", "Talcahuano", "Los Angeles",
        "Coronel", "Chiguayante", "San Pedro de la Paz",
        "Hualpen", "Lota", "Tome", "Penco",
        "Arauco", "Curanilahue", "Mulchen", "Nacimiento"
    ],

    "La Araucania": [
        "Temuco", "Padre Las Casas", "Villarrica",
        "Angol", "Pucon", "Victoria", "Lautaro",
        "Nueva Imperial", "Carahue", "Traiguen"
    ],

    "Los Rios": [
        "Valdivia", "La Union", "Panguipulli",
        "Rio Bueno", "Lanco", "Mariquina",
        "Paillaco", "Futrono", "Los Lagos"
    ],

    "Los Lagos": [
        "Puerto Montt", "Osorno", "Castro",
        "Ancud", "Puerto Varas", "Calbuco",
        "Quellon", "Frutillar", "Llanquihue",
        "Chonchi", "Dalcahue"
    ],

    "Aysen": [
        "Coyhaique", "Puerto Aysen", "Chile Chico",
        "Puerto Cisnes", "Cochrane", "Puerto Ibanez",
        "Villa O'Higgins"
    ],

    "Magallanes": [
        "Punta Arenas", "Puerto Natales",
        "Porvenir", "Puerto Williams",
        "Cabo de Hornos", "Primavera",
        "Timaukel", "Laguna Blanca"
    ]
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
