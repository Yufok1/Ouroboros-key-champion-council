from __future__ import annotations

from dataclasses import dataclass, field

from middle_passage.ethics import Sensitivity
from middle_passage.voyages.models import Coordinate


@dataclass(frozen=True)
class KnownEvent:
    event_id: str
    label: str
    coordinate: Coordinate
    year: int | None = None
    confidence: float = 0.0
    sensitivity: Sensitivity = Sensitivity.RESTRICTED
    source_refs: list[str] = field(default_factory=list)
    notes: str = ""


def synthetic_development_event() -> KnownEvent:
    return KnownEvent(
        event_id="synthetic-phase0-001",
        label="Synthetic development event, not a historical coordinate",
        coordinate=Coordinate(lat=0.0, lon=-30.0),
        year=None,
        confidence=0.0,
        sensitivity=Sensitivity.PUBLIC,
        source_refs=["synthetic:test_only"],
        notes="Use only for software tests and demos.",
    )

