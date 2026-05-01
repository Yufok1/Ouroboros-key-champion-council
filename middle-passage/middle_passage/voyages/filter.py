from __future__ import annotations

from .models import Voyage


def filter_by_mortality(voyages: list[Voyage], min_death_rate: float = 0.1) -> list[Voyage]:
    return [
        voyage
        for voyage in voyages
        if voyage.mortality_rate is not None and voyage.mortality_rate >= min_death_rate
    ]


def filter_by_route(voyages: list[Voyage], corridor: str) -> list[Voyage]:
    wanted = corridor.strip().lower()
    return [voyage for voyage in voyages if (voyage.route or "").strip().lower() == wanted]


def filter_by_date_range(
    voyages: list[Voyage],
    start_year: int | None = None,
    end_year: int | None = None,
) -> list[Voyage]:
    out: list[Voyage] = []
    for voyage in voyages:
        if voyage.year is None:
            continue
        if start_year is not None and voyage.year < start_year:
            continue
        if end_year is not None and voyage.year > end_year:
            continue
        out.append(voyage)
    return out


def filter_jettison_events(voyages: list[Voyage]) -> list[Voyage]:
    return [voyage for voyage in voyages if voyage.jettison_flag]

