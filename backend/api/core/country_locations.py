from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path


DATA_PATH = Path(__file__).with_name("country_locations_data.json")


def _key(value: str | None) -> str:
    raw = str(value or "").strip()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


@lru_cache(maxsize=1)
def country_location_library() -> dict[str, dict]:
    if not DATA_PATH.exists():
        return {}
    with DATA_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def normalize_location_country(country_code: str | None) -> str:
    code = str(country_code or "").strip().upper()
    return code if code in country_location_library() else ""


def country_location_profile(country_code: str | None) -> dict:
    library = country_location_library()
    code = normalize_location_country(country_code)
    profile = library.get(code, {})
    return profile if isinstance(profile, dict) else {}


def country_location_options(country_code: str | None) -> dict[str, list[str]]:
    profile = country_location_profile(country_code)
    locations = profile.get("locations", {})
    if not isinstance(locations, dict):
        return {}
    return {
        str(state): [str(city) for city in cities if str(city).strip()]
        for state, cities in locations.items()
        if str(state).strip() and isinstance(cities, list)
    }


def country_location_labels(country_code: str | None) -> dict:
    profile = country_location_profile(country_code)
    return {
        "countryName": profile.get("countryName") or "Mercado configurado",
        "stateLabel": profile.get("stateLabel") or "Region / estado",
        "cityLabel": profile.get("cityLabel") or "Ciudad",
        "statePlaceholder": profile.get("statePlaceholder") or "Selecciona region / estado",
        "cityPlaceholder": profile.get("cityPlaceholder") or "Selecciona ciudad",
    }


def country_location_payload(country_code: str | None) -> dict:
    requested_code = str(country_code or "").strip().upper() or "CL"
    code = normalize_location_country(requested_code)
    labels = country_location_labels(code)
    locations = country_location_options(code)
    return {
        "country": code or requested_code,
        **labels,
        "locations": locations,
        "items": [
            {"state": state, "cities": cities}
            for state, cities in locations.items()
        ],
    }


def normalize_country_location(
    country_code: str | None,
    state: str | None,
    city: str | None,
) -> tuple[str, str, str]:
    code = normalize_location_country(country_code)
    labels = country_location_labels(code)
    locations = country_location_options(code)
    state_key = _key(state)
    city_key = _key(city)

    if not state_key:
        return "", "", f"{labels['statePlaceholder']}."

    normalized_state = ""
    for option in locations:
        if _key(option) == state_key:
            normalized_state = option
            break
    if not normalized_state:
        return "", "", f"{labels['statePlaceholder']} valida."

    if not city_key:
        return normalized_state, "", f"{labels['cityPlaceholder']}."

    for option in locations.get(normalized_state, []):
        if _key(option) == city_key:
            return normalized_state, option, ""
    return (
        normalized_state,
        "",
        f"{labels['cityPlaceholder']} valido para {normalized_state}.",
    )
