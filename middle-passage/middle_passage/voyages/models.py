from __future__ import annotations

from dataclasses import dataclass, field

from middle_passage.ethics import Sensitivity


@dataclass(frozen=True)
class Coordinate:
    lat: float
    lon: float

    def as_position(self) -> list[float]:
        return [self.lon, self.lat]


@dataclass(frozen=True)
class Voyage:
    voyage_id: str
    ship_name: str | None = None
    year: int | None = None
    embark: Coordinate | None = None
    disembark: Coordinate | None = None
    people_embarked: int | None = None
    deaths_middle_passage: int | None = None
    route: str | None = None
    jettison_flag: bool = False
    source_refs: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def mortality_rate(self) -> float | None:
        if not self.people_embarked or self.deaths_middle_passage is None:
            return None
        if self.people_embarked <= 0:
            return None
        return self.deaths_middle_passage / self.people_embarked


@dataclass(frozen=True)
class SurveyPriorityZone:
    zone_id: str
    center: Coordinate
    radius_m: float
    confidence: float
    sensitivity: Sensitivity = Sensitivity.GENERALIZED
    do_not_disturb: bool = True
    source_refs: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    label: str = "survey_priority_zone"

    def public_properties(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "label": self.label,
            "radius_m": round(self.radius_m, 3),
            "confidence": round(max(0.0, min(1.0, self.confidence)), 4),
            "sensitivity": self.sensitivity.value,
            "do_not_disturb": self.do_not_disturb,
            "source_refs": list(self.source_refs),
            "assumptions": list(self.assumptions),
        }

