from __future__ import annotations

import math
from dataclasses import dataclass

from middle_passage.currents.drift import offset_coordinate
from middle_passage.voyages.models import Coordinate


@dataclass(frozen=True)
class DescentParams:
    entry_point: Coordinate
    water_depth_m: float
    current_velocity_m_s: float = 0.04
    current_bearing_degrees: float = 270.0
    cannonball_mass_kg: float = 12.0
    chain_length_m: float = 2.5
    number_of_people: int = 1


@dataclass(frozen=True)
class DescentPath:
    time_to_bottom_s: float
    lateral_offset_m: float
    final_center: Coordinate
    scatter_radius_m: float
    assumptions: list[str]


def model_descent(params: DescentParams) -> DescentPath:
    """Conservative, inspectable Phase 0 descent model.

    This is not a validated forensic model. It exists to make assumptions
    explicit and test the data pipeline.
    """

    depth = abs(params.water_depth_m)
    effective_mass = max(params.cannonball_mass_kg, 1.0)
    people_factor = max(params.number_of_people, 1)
    sink_rate_m_s = _estimate_sink_rate(effective_mass, people_factor)
    time_s = depth / sink_rate_m_s
    lateral_offset_m = params.current_velocity_m_s * time_s
    final_center = offset_coordinate(params.entry_point, lateral_offset_m, params.current_bearing_degrees)
    scatter_radius_m = max(5.0, params.chain_length_m * people_factor * math.log1p(depth / 100.0))

    return DescentPath(
        time_to_bottom_s=time_s,
        lateral_offset_m=lateral_offset_m,
        final_center=final_center,
        scatter_radius_m=scatter_radius_m,
        assumptions=[
            "phase0_descent_model_not_for_site_identification",
            f"sink_rate_m_s={sink_rate_m_s:.4f}",
            "constant_current_velocity",
            "scatter_radius_is_conservative_placeholder",
        ],
    )


def _estimate_sink_rate(cannonball_mass_kg: float, number_of_people: int) -> float:
    base = 0.35 + min(cannonball_mass_kg, 24.0) / 80.0
    drag_penalty = 1.0 / math.sqrt(max(number_of_people, 1))
    return max(0.12, base * drag_penalty)

