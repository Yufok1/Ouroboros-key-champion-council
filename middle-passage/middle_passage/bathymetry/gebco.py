from __future__ import annotations

from dataclasses import dataclass

from middle_passage.voyages.models import Coordinate


@dataclass(frozen=True)
class DepthSample:
    coordinate: Coordinate
    depth_m: float
    source: str
    confidence: float


def estimate_depth(point: Coordinate) -> DepthSample:
    """Placeholder depth estimator for Phase 0 tests.

    Real GEBCO integration should replace this with tile-backed lookup.
    """

    rough_atlantic_depth = -4200.0 if -80 <= point.lon <= 20 and -35 <= point.lat <= 35 else -2500.0
    return DepthSample(
        coordinate=point,
        depth_m=rough_atlantic_depth,
        source="phase0_rough_atlantic_depth_assumption",
        confidence=0.1,
    )

