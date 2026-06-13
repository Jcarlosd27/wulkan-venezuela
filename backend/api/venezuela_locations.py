from __future__ import annotations

import re
import unicodedata


VENEZUELA_STATE_CITIES: dict[str, list[str]] = {
    "Amazonas": ["Puerto Ayacucho", "San Fernando de Atabapo", "Maroa"],
    "Anzoategui": ["Barcelona", "Puerto La Cruz", "Lecheria", "El Tigre", "Anaco", "Puerto Piritu", "Pariaguan"],
    "Apure": ["San Fernando de Apure", "Guasdualito", "Achaguas", "Biruaca"],
    "Aragua": ["Maracay", "Turmero", "La Victoria", "Cagua", "Palo Negro", "Villa de Cura"],
    "Barinas": ["Barinas", "Socopo", "Barinitas", "Sabaneta", "Santa Barbara"],
    "Bolivar": ["Ciudad Bolivar", "Puerto Ordaz", "San Felix", "Upata", "Ciudad Piar", "Tumeremo"],
    "Carabobo": ["Valencia", "Naguanagua", "San Diego", "Guacara", "Puerto Cabello", "Mariara", "Bejuma"],
    "Cojedes": ["San Carlos", "Tinaquillo", "Tinaco", "El Baul"],
    "Delta Amacuro": ["Tucupita", "Pedernales", "Curiapo"],
    "Distrito Capital": ["Caracas"],
    "Falcon": ["Coro", "Punto Fijo", "Tucacas", "Chichiriviche", "La Vela de Coro"],
    "Guarico": ["San Juan de los Morros", "Calabozo", "Valle de la Pascua", "Zaraza", "Altagracia de Orituco"],
    "Lara": ["Barquisimeto", "Cabudare", "Carora", "El Tocuyo", "Quibor"],
    "Merida": ["Merida", "El Vigia", "Ejido", "Tovar", "Mucuchies"],
    "Miranda": ["Los Teques", "Guarenas", "Guatire", "Charallave", "Santa Teresa del Tuy", "Petare", "Chacao", "Baruta"],
    "Monagas": ["Maturin", "Punta de Mata", "Temblador", "Caripe"],
    "Nueva Esparta": ["Porlamar", "La Asuncion", "Juan Griego", "Pampatar"],
    "Portuguesa": ["Guanare", "Acarigua", "Araure", "Turen", "Biscucuy"],
    "Sucre": ["Cumana", "Carupano", "Guiria", "Cariaco"],
    "Tachira": ["San Cristobal", "Rubio", "Tariba", "La Grita", "San Antonio del Tachira"],
    "Trujillo": ["Valera", "Trujillo", "Bocono", "Pampanito"],
    "La Guaira": ["La Guaira", "Catia La Mar", "Maiquetia", "Macuto", "Caraballeda"],
    "Yaracuy": ["San Felipe", "Yaritagua", "Chivacoa", "Nirgua"],
    "Zulia": ["Maracaibo", "Cabimas", "Ciudad Ojeda", "Machiques", "La Villa del Rosario", "Santa Barbara del Zulia"],
}

VENEZUELA_PHONE_PREFIXES = {
    "212", "234", "235", "238", "239", "240", "241", "242", "243", "244", "245", "246",
    "247", "248", "249", "251", "252", "253", "254", "255", "256", "257", "258", "259",
    "261", "262", "263", "264", "265", "266", "267", "268", "269", "271", "272", "273",
    "274", "275", "276", "277", "278", "279", "281", "282", "283", "285", "286", "287",
    "288", "291", "292", "293", "294", "295",
    "412", "414", "416", "424", "426",
}
VENEZUELA_RIF_PREFIXES = {"V", "E", "J", "G", "P"}


def _key(value: str | None) -> str:
    raw = str(value or "").strip()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def normalize_venezuelan_state(value: str | None) -> str:
    value_key = _key(value)
    if not value_key:
        return ""
    for state in VENEZUELA_STATE_CITIES:
        if _key(state) == value_key:
            return state
    return ""


def normalize_venezuelan_city(state: str | None, value: str | None) -> str:
    normalized_state = normalize_venezuelan_state(state)
    value_key = _key(value)
    if not normalized_state or not value_key:
        return ""
    for city in VENEZUELA_STATE_CITIES.get(normalized_state, []):
        if _key(city) == value_key:
            return city
    return ""


def normalize_venezuelan_location(state: str | None, city: str | None) -> tuple[str, str, str]:
    normalized_state = normalize_venezuelan_state(state)
    if not normalized_state:
        return "", "", "Selecciona un estado venezolano valido."
    normalized_city = normalize_venezuelan_city(normalized_state, city)
    if not normalized_city:
        return normalized_state, "", f"Selecciona una ciudad valida para {normalized_state}."
    return normalized_state, normalized_city, ""


def normalize_venezuelan_phone(value: str | None) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if digits.startswith("0058"):
        digits = digits[4:]
    elif digits.startswith("58") and len(digits) > 10:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10 or digits[:3] not in VENEZUELA_PHONE_PREFIXES:
        return ""
    return f"+58 {digits[:3]}-{digits[3:]}"


def normalize_venezuelan_rif(value: str | None) -> str:
    compact = re.sub(r"[^A-Za-z0-9]+", "", str(value or "").upper())
    if len(compact) < 8:
        return ""
    prefix = compact[0]
    digits = re.sub(r"\D+", "", compact[1:])
    if prefix not in VENEZUELA_RIF_PREFIXES or len(digits) not in {8, 9, 10}:
        return ""
    if len(digits) == 8:
        return f"{prefix}-{digits}"
    return f"{prefix}-{digits[:-1]}-{digits[-1]}"
