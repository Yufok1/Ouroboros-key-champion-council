from __future__ import annotations

import json
from pathlib import Path

from middle_passage.ethics import protection_notice
from middle_passage.physics.scatter import generate_deposit_polygon
from middle_passage.voyages.models import SurveyPriorityZone


def zone_to_feature(zone: SurveyPriorityZone) -> dict:
    ring = generate_deposit_polygon(zone.center.lat, zone.center.lon, zone.radius_m)
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [ring],
        },
        "properties": {
            **zone.public_properties(),
            "protection_notice": protection_notice(),
        },
    }


def feature_collection(features: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "metadata": {
            "project": "Middle Passage Forensic Recovery Project",
            "artifact": "survey_priority_zones",
            "notice": protection_notice(),
            "license": "CC-BY-4.0",
        },
        "features": features,
    }


def probability_zones_to_geojson(zones: list[SurveyPriorityZone]) -> dict:
    return feature_collection([zone_to_feature(zone) for zone in zones])


def write_geojson(payload: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

