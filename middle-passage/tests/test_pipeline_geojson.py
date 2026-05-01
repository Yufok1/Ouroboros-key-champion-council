from middle_passage.mapping.geojson import probability_zones_to_geojson
from middle_passage.pipeline import build_survey_zones
from middle_passage.voyages.models import Coordinate, Voyage


def test_pipeline_builds_protection_first_geojson():
    voyage = Voyage(
        voyage_id="synthetic",
        embark=Coordinate(lat=0.0, lon=-30.0),
        people_embarked=100,
        deaths_middle_passage=10,
        route="doldrums_zone",
        source_refs=["synthetic:test"],
    )

    zones = build_survey_zones([voyage])
    payload = probability_zones_to_geojson(zones)

    assert payload["type"] == "FeatureCollection"
    assert payload["metadata"]["artifact"] == "survey_priority_zones"
    assert payload["features"][0]["properties"]["do_not_disturb"] is True
    assert "not proof of remains" in payload["features"][0]["properties"]["protection_notice"]

