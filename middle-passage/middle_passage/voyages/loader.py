from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .models import Coordinate, Voyage


FIELD_ALIASES = {
    "voyage_id": ("voyage_id", "id", "voyageid", "voyage"),
    "ship_name": ("ship_name", "shipname", "vessel", "ship"),
    "year": ("year_arrived", "year", "arrival_year", "date"),
    "embark_lat": ("port_embark_lat", "embark_lat", "embarkation_latitude"),
    "embark_lon": ("port_embark_lon", "embark_lon", "embarkation_longitude"),
    "disembark_lat": ("port_disembark_lat", "disembark_lat", "disembarkation_latitude"),
    "disembark_lon": ("port_disembark_lon", "disembark_lon", "disembarkation_longitude"),
    "people_embarked": ("slaves_embarked", "people_embarked", "embarked"),
    "deaths_middle_passage": (
        "slaves_died_middle_passage",
        "deaths_middle_passage",
        "middle_passage_deaths",
        "deaths",
    ),
    "route": ("route", "corridor"),
    "jettison_flag": ("jettison_flag", "jettison", "overboard_event"),
}


def load_voyages(filepath: str | Path) -> list[Voyage]:
    path = Path(filepath)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        return [row_to_voyage(row) for row in rows]


def row_to_voyage(row: dict[str, str]) -> Voyage:
    normalized = {_normalize_key(k): v for k, v in row.items()}
    voyage_id = _first(normalized, FIELD_ALIASES["voyage_id"]) or "unknown"

    embark = _coordinate(
        _first_float(normalized, FIELD_ALIASES["embark_lat"]),
        _first_float(normalized, FIELD_ALIASES["embark_lon"]),
    )
    disembark = _coordinate(
        _first_float(normalized, FIELD_ALIASES["disembark_lat"]),
        _first_float(normalized, FIELD_ALIASES["disembark_lon"]),
    )

    return Voyage(
        voyage_id=str(voyage_id),
        ship_name=_first(normalized, FIELD_ALIASES["ship_name"]),
        year=_first_int(normalized, FIELD_ALIASES["year"]),
        embark=embark,
        disembark=disembark,
        people_embarked=_first_int(normalized, FIELD_ALIASES["people_embarked"]),
        deaths_middle_passage=_first_int(normalized, FIELD_ALIASES["deaths_middle_passage"]),
        route=_first(normalized, FIELD_ALIASES["route"]),
        jettison_flag=_first_bool(normalized, FIELD_ALIASES["jettison_flag"]),
        source_refs=[f"csv:{voyage_id}"],
    )


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_").replace("-", "_")


def _first(row: dict[str, str], names: Iterable[str]) -> str | None:
    for name in names:
        value = row.get(_normalize_key(name))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _first_int(row: dict[str, str], names: Iterable[str]) -> int | None:
    value = _first(row, names)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _first_float(row: dict[str, str], names: Iterable[str]) -> float | None:
    value = _first(row, names)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _first_bool(row: dict[str, str], names: Iterable[str]) -> bool:
    value = _first(row, names)
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "y", "known", "probable"}


def _coordinate(lat: float | None, lon: float | None) -> Coordinate | None:
    if lat is None or lon is None:
        return None
    return Coordinate(lat=lat, lon=lon)

