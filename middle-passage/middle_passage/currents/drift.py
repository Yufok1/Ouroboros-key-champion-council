from __future__ import annotations

import math
from dataclasses import dataclass

from middle_passage.voyages.models import Coordinate

EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class DriftVector:
    bearing_degrees: float
    distance_m: float
    velocity_m_s: float
    duration_s: float
    source: str = "assumption"


def calculate_drift(
    lat: float,
    lon: float,
    month: int | None = None,
    depth_m: float = 1000.0,
    current_velocity_m_s: float = 0.04,
    bearing_degrees: float = 270.0,
    duration_s: float = 3600.0,
) -> DriftVector:
    """Return a simple placeholder current vector.

    This is a transparent Phase 0 assumption, not a NOAA-backed hindcast.
    """

    _ = (lat, lon, month, depth_m)
    return DriftVector(
        bearing_degrees=bearing_degrees,
        distance_m=max(0.0, current_velocity_m_s * duration_s),
        velocity_m_s=current_velocity_m_s,
        duration_s=duration_s,
        source="phase0_constant_current_assumption",
    )


def apply_drift_to_entry(entry_point: Coordinate, drift_vector: DriftVector) -> Coordinate:
    return offset_coordinate(entry_point, drift_vector.distance_m, drift_vector.bearing_degrees)


def offset_coordinate(point: Coordinate, distance_m: float, bearing_degrees: float) -> Coordinate:
    bearing = math.radians(bearing_degrees)
    lat1 = math.radians(point.lat)
    lon1 = math.radians(point.lon)
    angular = distance_m / EARTH_RADIUS_M

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular)
        + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )

    return Coordinate(lat=math.degrees(lat2), lon=((math.degrees(lon2) + 540) % 360) - 180)

