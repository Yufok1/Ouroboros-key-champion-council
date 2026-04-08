#!/usr/bin/env python
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import text_theater as tt


DEFAULT_BASE_URL = "http://127.0.0.1:7866"
DEFAULT_SCOPES = ("body", "part_only", "part_adjacent", "part_chain")
DEFAULT_BONES = (
    "head",
    "chest",
    "hand_l",
    "hand_r",
    "foot_l",
    "foot_r",
)


def _post_json(url, payload, timeout=20.0):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8")
    return json.loads(text)


def _env_control(base_url, command, target_id="", actor="codex", timeout=20.0):
    return _post_json(
        f"{base_url}/api/tool/env_control",
        {"command": command, "target_id": target_id, "actor": actor},
        timeout=timeout,
    )


def _env_read(base_url, query, timeout=20.0):
    resp = _post_json(
        f"{base_url}/api/tool/env_read",
        {"query": query},
        timeout=timeout,
    )
    try:
        text = resp["result"]["content"][0]["text"]
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"bad env_read response for {query}: {exc}") from exc
    return json.loads(text)


def _extract_scenario_summary(shared_state):
    snapshot = (((shared_state or {}).get("text_theater") or {}).get("snapshot") or {})
    workbench = snapshot.get("workbench") or {}
    embodiment = snapshot.get("embodiment") or {}
    render = snapshot.get("render") or {}
    motion = workbench.get("motion_diagnostics") or {}
    load_field = workbench.get("load_field") or {}
    selected = workbench.get("selected_part_surface") or {}
    scaffold_rows = embodiment.get("scaffold_pieces") or []
    render_model = tt._collect_render_model(snapshot)
    selected_bone = str((selected.get("bone_id") or workbench.get("selected_bone_id") or "")).strip()
    selected_scaffold = next(
        (row for row in scaffold_rows if str((row or {}).get("slot") or "").strip() == selected_bone),
        None,
    )
    foot_rows = {
        str((row or {}).get("slot") or "").strip(): row
        for row in scaffold_rows
        if str((row or {}).get("slot") or "").strip() in {"foot_l", "foot_r"}
    }
    browser_visible_scaffold_slots = sorted(
        {
            str((row or {}).get("slot") or (row or {}).get("joint") or "").strip()
            for row in scaffold_rows
            if isinstance(row, dict) and row.get("visible") is not False
        }
    )
    text_render_scaffold_slots = sorted(
        {
            str((row or {}).get("slot") or "").strip()
            for row in (render_model.get("scaffold_segments") or [])
            if isinstance(row, dict) and str((row or {}).get("slot") or "").strip()
        }
    )
    browser_limb_slots = sorted(slot for slot in browser_visible_scaffold_slots if any(
        token in slot for token in ("upper_arm", "lower_arm", "upper_leg", "lower_leg")
    ))
    text_limb_slots = sorted(slot for slot in text_render_scaffold_slots if any(
        token in slot for token in ("upper_arm", "lower_arm", "upper_leg", "lower_leg")
    ))
    return {
        "selected_bone": selected_bone,
        "display_scope": (
            workbench.get("configured_display_scope")
            or workbench.get("part_display_scope")
        ),
        "part_view": workbench.get("part_view"),
        "camera": (((shared_state.get("scene") or {}).get("camera3d")) or {}),
        "theater_camera": (((snapshot.get("theater") or {}).get("camera")) or {}),
        "workbench_stage_guide": render.get("workbench_stage_guide"),
        "selected_part_surface": {
            "world_anchor": selected.get("world_anchor"),
            "world_center": selected.get("world_center"),
            "world_bounds": selected.get("world_bounds"),
            "scope_bone_ids": selected.get("scope_bone_ids"),
            "chain_ids": selected.get("chain_ids"),
        },
        "selected_part_camera_recipes": workbench.get("part_camera_recipes") or [],
        "selected_scaffold": selected_scaffold,
        "foot_scaffold": foot_rows,
        "browser_visible_scaffold_slots": browser_visible_scaffold_slots,
        "browser_visible_limb_slots": browser_limb_slots,
        "text_render_scaffold_slots": text_render_scaffold_slots,
        "text_render_limb_slots": text_limb_slots,
        "text_render_missing_scaffold_slots": [
            slot for slot in browser_visible_scaffold_slots if slot not in text_render_scaffold_slots
        ],
        "text_render_missing_limb_slots": [
            slot for slot in browser_limb_slots if slot not in text_limb_slots
        ],
        "text_render": {
            "scoped_part_mode": bool(render_model.get("scoped_part_mode")),
            "segment_count": len(render_model.get("segments") or []),
            "scaffold_segment_count": len(render_model.get("scaffold_segments") or []),
            "marker_count": len(render_model.get("markers") or []),
            "floor_point_count": len(render_model.get("floor_points") or []),
            "guide_segment_count": len(render_model.get("guide_segments") or []),
            "guide_ring_count": len(render_model.get("guide_rings") or []),
            "objects_count": len(render_model.get("objects") or []),
        },
        "motion_diagnostics": {
            "support_phase": motion.get("support_phase"),
            "support_contact_count": motion.get("support_contact_count"),
            "supporting_ids": motion.get("supporting_ids"),
            "alerts": motion.get("alerts"),
            "contacts": motion.get("contacts"),
        },
        "load_field": {
            "support_count": load_field.get("support_count"),
            "support_polygon": load_field.get("support_polygon"),
            "stability_risk": load_field.get("stability_risk"),
            "support_loads": load_field.get("support_loads"),
        },
        "runtime_world_y": ((((shared_state.get("focus") or {}).get("payload") or {}).get("data") or {}).get("runtime_state") or {}).get("position", {}).get("world", {}).get("y"),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate workbench isolation scopes and capture evidence.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--bones", nargs="*", default=list(DEFAULT_BONES))
    parser.add_argument("--scopes", nargs="*", default=list(DEFAULT_SCOPES))
    parser.add_argument("--actor", default="codex")
    parser.add_argument("--capture", action="store_true", help="Capture frame/probe images for each scenario.")
    parser.add_argument("--pause", type=float, default=0.35, help="Pause after each control step.")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else (
        Path("data") / f"isolation_eval_{int(time.time())}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "base_url": args.base_url,
        "generated_ts": int(time.time()),
        "bones": list(args.bones),
        "scopes": list(args.scopes),
        "capture": bool(args.capture),
        "scenarios": [],
    }

    for bone_id in args.bones:
        _env_control(args.base_url, "workbench_select_bone", bone_id, actor=args.actor)
        time.sleep(args.pause)
        for scope in args.scopes:
            _env_control(args.base_url, "workbench_set_display_scope", scope, actor=args.actor)
            time.sleep(args.pause)
            if scope != "body":
                _env_control(
                    args.base_url,
                    "workbench_frame_part",
                    json.dumps({"bone_id": bone_id, "view": "iso_front"}),
                    actor=args.actor,
                )
                time.sleep(args.pause)

            frame_info = None
            probe_info = None
            if args.capture:
                _env_control(args.base_url, "capture_frame", "", actor=args.actor)
                time.sleep(args.pause)
                frame_info = _env_read(args.base_url, "frame")
                _env_control(args.base_url, "capture_probe", "character_runtime::mounted_primary", actor=args.actor)
                time.sleep(args.pause)
                probe_info = _env_read(args.base_url, "probe")

            shared_state = _env_read(args.base_url, "shared_state").get("shared_state") or {}
            report["scenarios"].append(
                {
                    "bone_id": bone_id,
                    "scope": scope,
                    "summary": _extract_scenario_summary(shared_state),
                    "frame_capture": frame_info,
                    "probe_capture": probe_info,
                }
            )

    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(str(output_path))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        raise SystemExit(f"network error: {exc}") from exc
