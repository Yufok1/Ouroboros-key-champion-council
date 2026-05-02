from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from middle_passage.voyages.models import Coordinate, SurveyPriorityZone, Voyage

REPLAY_SCHEMA = "middle_passage_replay_packet.v1"


def voyage_to_replay_dict(voyage: Voyage) -> dict[str, Any]:
    return {
        "voyage_id": voyage.voyage_id,
        "ship_name": voyage.ship_name,
        "year": voyage.year,
        "embark": _coordinate_to_dict(voyage.embark),
        "disembark": _coordinate_to_dict(voyage.disembark),
        "people_embarked": voyage.people_embarked,
        "deaths_middle_passage": voyage.deaths_middle_passage,
        "route": voyage.route,
        "jettison_flag": voyage.jettison_flag,
        "source_refs": list(voyage.source_refs),
        "notes": voyage.notes,
    }


def voyage_from_replay_dict(payload: dict[str, Any]) -> Voyage:
    return Voyage(
        voyage_id=str(payload["voyage_id"]),
        ship_name=payload.get("ship_name"),
        year=_optional_int(payload.get("year")),
        embark=_coordinate_from_dict(payload.get("embark")),
        disembark=_coordinate_from_dict(payload.get("disembark")),
        people_embarked=_optional_int(payload.get("people_embarked")),
        deaths_middle_passage=_optional_int(payload.get("deaths_middle_passage")),
        route=payload.get("route"),
        jettison_flag=bool(payload.get("jettison_flag", False)),
        source_refs=[str(ref) for ref in payload.get("source_refs", [])],
        notes=str(payload.get("notes") or ""),
    )


def zone_to_replay_dict(zone: SurveyPriorityZone) -> dict[str, Any]:
    return {
        "zone_id": zone.zone_id,
        "center": _coordinate_to_dict(zone.center),
        "radius_m": zone.radius_m,
        "confidence": zone.confidence,
        "sensitivity": zone.sensitivity.value,
        "do_not_disturb": zone.do_not_disturb,
        "source_refs": list(zone.source_refs),
        "assumptions": list(zone.assumptions),
        "label": zone.label,
    }


def build_replay_packet(
    voyages: list[Voyage],
    *,
    corridor: str | None,
    zones: list[SurveyPriorityZone],
    output_artifact: str | None = None,
) -> dict[str, Any]:
    inputs = {
        "corridor": corridor,
        "voyages": [voyage_to_replay_dict(voyage) for voyage in voyages],
    }
    outputs = {
        "artifact_path": output_artifact,
        "zones": [zone_to_replay_dict(zone) for zone in zones],
    }
    packet = {
        "schema": REPLAY_SCHEMA,
        "status": "replayable_input",
        "claim_language": "survey-priority zones, not proof of remains",
        "sensitivity": {
            "default_label": "generalized",
            "precision_policy": "generalized_public_output",
        },
        "inputs": inputs,
        "outputs": outputs,
        "receipts": {
            "input_hash": stable_hash(inputs),
            "output_hash": stable_hash(outputs),
        },
    }
    packet["receipts"]["packet_hash"] = stable_hash(packet)
    return packet


def load_replay_voyages(input_path: str | Path) -> tuple[list[Voyage], str | None]:
    packet = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if packet.get("schema") != REPLAY_SCHEMA:
        raise ValueError(f"unsupported replay schema: {packet.get('schema')!r}")
    inputs = packet.get("inputs") or {}
    voyages = [voyage_from_replay_dict(row) for row in inputs.get("voyages", [])]
    corridor = inputs.get("corridor")
    return voyages, corridor


def write_replay_packet(packet: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json(packet) + "\n", encoding="utf-8")


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def stable_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, separators=(",", ": "))


def _coordinate_to_dict(coordinate: Coordinate | None) -> dict[str, float] | None:
    if coordinate is None:
        return None
    return {"lat": coordinate.lat, "lon": coordinate.lon}


def _coordinate_from_dict(payload: Any) -> Coordinate | None:
    if not payload:
        return None
    return Coordinate(lat=float(payload["lat"]), lon=float(payload["lon"]))


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
