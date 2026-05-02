from __future__ import annotations

import argparse
import json
from pathlib import Path

from middle_passage.events.jettison import synthetic_development_event
from middle_passage.mapping.geojson import probability_zones_to_geojson, write_geojson
from middle_passage.pipeline import build_survey_zones
from middle_passage.replay import build_replay_packet, load_replay_voyages, write_replay_packet
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
    sample.add_argument("--replay-output", help="Optional output path for replay input data.")

    model = sub.add_parser("model-deposits", help="Model generalized survey-priority zones.")
    model.add_argument("--voyages", help="Input voyage CSV. Uses synthetic sample if omitted.")
    model.add_argument("--corridor", default="west_africa_caribbean")
    model.add_argument("--output", required=True, help="Output GeoJSON path.")
    model.add_argument("--replay-output", help="Optional output path for replay input data.")

    replay = sub.add_parser("replay", help="Replay a saved input packet into GeoJSON.")
    replay.add_argument("--input", required=True, help="Input replay JSON packet.")
    replay.add_argument("--output", required=True, help="Output GeoJSON path.")
    replay.add_argument("--corridor", help="Optional corridor override.")
    replay.add_argument("--replay-output", help="Optional output path for refreshed replay data.")

    inspect = sub.add_parser("inspect-sources", help="Print package source and ethics notes.")
    inspect.add_argument("--json", action="store_true", help="Return JSON instead of text.")

    args = parser.parse_args(argv)
    if args.command == "sample":
        voyages = [_synthetic_voyage()]
        corridor = "doldrums_zone"
        zones = build_survey_zones(voyages, corridor=corridor)
        write_geojson(probability_zones_to_geojson(zones), args.output)
        if args.replay_output:
            packet = build_replay_packet(
                voyages,
                corridor=corridor,
                zones=zones,
                output_artifact=args.output,
            )
            write_replay_packet(packet, args.replay_output)
        print(f"wrote synthetic-safe sample: {args.output}")
        return

    if args.command == "model-deposits":
        voyages = load_voyages(args.voyages) if args.voyages else [_synthetic_voyage()]
        zones = build_survey_zones(voyages, corridor=args.corridor)
        write_geojson(probability_zones_to_geojson(zones), args.output)
        if args.replay_output:
            packet = build_replay_packet(
                voyages,
                corridor=args.corridor,
                zones=zones,
                output_artifact=args.output,
            )
            write_replay_packet(packet, args.replay_output)
        print(f"wrote {len(zones)} survey-priority zone(s): {args.output}")
        return

    if args.command == "replay":
        voyages, stored_corridor = load_replay_voyages(args.input)
        corridor = args.corridor or stored_corridor
        zones = build_survey_zones(voyages, corridor=corridor)
        write_geojson(probability_zones_to_geojson(zones), args.output)
        if args.replay_output:
            packet = build_replay_packet(
                voyages,
                corridor=corridor,
                zones=zones,
                output_artifact=args.output,
            )
            write_replay_packet(packet, args.replay_output)
        print(f"replayed {len(zones)} survey-priority zone(s): {args.output}")
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
