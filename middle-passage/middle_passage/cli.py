from __future__ import annotations

import argparse
import json
from pathlib import Path

from middle_passage.events.jettison import synthetic_development_event
from middle_passage.mapping.geojson import probability_zones_to_geojson, write_geojson
from middle_passage.pipeline import build_survey_zones
from middle_passage.voyages.loader import load_voyages
from middle_passage.voyages.models import Voyage


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="middle-passage",
        description="Protection-first Middle Passage forensic GIS scaffold.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("sample", help="Write a synthetic-safe sample GeoJSON.")
    sample.add_argument("--output", required=True, help="Output GeoJSON path.")

    model = sub.add_parser("model-deposits", help="Model generalized survey-priority zones.")
    model.add_argument("--voyages", help="Input voyage CSV. Uses synthetic sample if omitted.")
    model.add_argument("--corridor", default="west_africa_caribbean")
    model.add_argument("--output", required=True, help="Output GeoJSON path.")

    inspect = sub.add_parser("inspect-sources", help="Print package source and ethics notes.")
    inspect.add_argument("--json", action="store_true", help="Return JSON instead of text.")

    args = parser.parse_args(argv)
    if args.command == "sample":
        zones = build_survey_zones([_synthetic_voyage()], corridor="doldrums_zone")
        write_geojson(probability_zones_to_geojson(zones), args.output)
        print(f"wrote synthetic-safe sample: {args.output}")
        return

    if args.command == "model-deposits":
        voyages = load_voyages(args.voyages) if args.voyages else [_synthetic_voyage()]
        zones = build_survey_zones(voyages, corridor=args.corridor)
        write_geojson(probability_zones_to_geojson(zones), args.output)
        print(f"wrote {len(zones)} survey-priority zone(s): {args.output}")
        return

    if args.command == "inspect-sources":
        payload = {
            "status": "phase0_scaffold",
            "data_policy": "synthetic-safe by default; real sources require citation and release review",
            "sensitivity_labels": ["public", "generalized", "restricted", "do_not_publish"],
            "output_language": "survey-priority zones, not proof of remains",
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for key, value in payload.items():
                print(f"{key}: {value}")
        return


def _synthetic_voyage() -> Voyage:
    event = synthetic_development_event()
    return Voyage(
        voyage_id=event.event_id,
        ship_name="Synthetic Development Record",
        embark=event.coordinate,
        disembark=None,
        people_embarked=100,
        deaths_middle_passage=0,
        route="doldrums_zone",
        jettison_flag=False,
        source_refs=event.source_refs,
        notes="Synthetic only; not a historical coordinate.",
    )


if __name__ == "__main__":
    main()

