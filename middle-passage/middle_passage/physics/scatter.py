from __future__ import annotations

from middle_passage.currents.drift import offset_coordinate
from middle_passage.voyages.models import Coordinate


def calculate_scatter_radius(num_people: int, chain_length_m: float, depth_m: float) -> float:
    depth_factor = max(abs(depth_m), 1.0) ** 0.25
    return max(5.0, max(num_people, 1) * max(chain_length_m, 0.1) * depth_factor)


def generate_deposit_polygon(
    center_lat: float,
    center_lon: float,
    scatter_radius_m: float,
    segments: int = 36,
) -> list[list[float]]:
    center = Coordinate(lat=center_lat, lon=center_lon)
    ring: list[list[float]] = []
    for index in range(max(12, segments)):
        bearing = (360.0 * index) / max(12, segments)
        point = offset_coordinate(center, scatter_radius_m, bearing)
        ring.append(point.as_position())
    ring.append(ring[0])
    return ring

