from __future__ import annotations

from middle_passage.bathymetry.gebco import estimate_depth
from middle_passage.currents.routes import corridor_bearing_degrees
from middle_passage.ethics import Sensitivity
from middle_passage.physics.descent import DescentParams, model_descent
from middle_passage.voyages.models import SurveyPriorityZone, Voyage


def voyage_to_survey_zone(voyage: Voyage, corridor: str | None = None) -> SurveyPriorityZone | None:
    entry = voyage.embark
    if entry is None:
        return None

    depth = estimate_depth(entry)
    bearing = corridor_bearing_degrees(corridor or voyage.route)
    path = model_descent(
        DescentParams(
            entry_point=entry,
            water_depth_m=depth.depth_m,
            current_bearing_degrees=bearing,
        )
    )
    confidence = _confidence_for_voyage(voyage)
    return SurveyPriorityZone(
        zone_id=f"zone-{voyage.voyage_id}",
        center=path.final_center,
        radius_m=path.scatter_radius_m + max(1000.0, path.lateral_offset_m * 0.25),
        confidence=confidence,
        sensitivity=Sensitivity.GENERALIZED,
        source_refs=voyage.source_refs + [depth.source],
        assumptions=path.assumptions + ["entry_point_uses_embark_coordinate_placeholder"],
    )


def build_survey_zones(voyages: list[Voyage], corridor: str | None = None) -> list[SurveyPriorityZone]:
    zones: list[SurveyPriorityZone] = []
    for voyage in voyages:
        zone = voyage_to_survey_zone(voyage, corridor=corridor)
        if zone is not None:
            zones.append(zone)
    return zones


def _confidence_for_voyage(voyage: Voyage) -> float:
    score = 0.1
    if voyage.embark and voyage.disembark:
        score += 0.15
    if voyage.mortality_rate is not None:
        score += min(0.25, voyage.mortality_rate)
    if voyage.jettison_flag:
        score += 0.25
    if voyage.source_refs:
        score += 0.1
    return min(score, 0.85)

