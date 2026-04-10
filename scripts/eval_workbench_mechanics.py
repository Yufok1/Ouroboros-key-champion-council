#!/usr/bin/env python
# Slice 2 eval harness — tracks current source truth at HEAD 33cae7f + post-baseline rebuild work.
# Rules:
#   1. Assertions track what source actually produces. Never speculative.
#   2. Update this eval AFTER source changes, never before.
#   3. No motion preset assertions beyond the retired metadata defaults carried in the live contract.
#   4. No root-motion behavior assertions (Slice 3 territory).
#   5. No observer/prospect/blackboard/Tinkerbell assertions (later slices).
#   6. Settle is removed; this harness only protects the clean post-settle baseline.
# When adding assertions:
#   - Verify against live shared_state first.
#   - Add a rationale comment.
#   - Run against current baseline — must pass before commit.

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:7866"
KNOWN_BALANCE_MODES = {"supported", "braced", "falling", "free_float"}
KNOWN_SUPPORT_PHASES = {
    "airborne",
    "double_support",
    "single_support_left",
    "single_support_right",
    "braced_support",
}
KNOWN_CONTACT_STATES = {"planted", "grounded", "sliding", "lifting", "airborne"}
VECTOR_TOLERANCE = 1e-4


def _post_json(url: str, payload: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
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


def _tool_payload(base_url: str, tool_name: str, payload: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
    raw = _post_json(f"{base_url}/api/tool/{tool_name}", payload, timeout=timeout)
    try:
        text = raw["result"]["content"][0]["text"]
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"bad {tool_name} response: {exc}") from exc
    return json.loads(text)


def _env_read_shared_state(base_url: str, timeout: float = 20.0) -> dict[str, Any]:
    payload = _tool_payload(base_url, "env_read", {"query": "shared_state"}, timeout=timeout)
    shared_state = payload.get("shared_state")
    if not isinstance(shared_state, dict):
        raise RuntimeError("env_read(shared_state) returned no shared_state payload")
    return shared_state


def _wait_for_convergence(loader, predicate, timeout_s: float = 5.0, interval_s: float = 0.1):
    """Poll shared_state until predicate is True or timeout."""
    deadline = time.time() + float(timeout_s)
    last_state = None
    last_reason = "no samples"
    while time.time() < deadline:
        try:
            state = loader()
            last_state = state
            ok, reason = predicate(state)
            if ok:
                return state
            last_reason = reason
        except Exception as exc:  # pragma: no cover - defensive
            last_reason = str(exc)
        time.sleep(interval_s)
    raise RuntimeError(f"Timed out waiting for shared_state convergence: {last_reason}")


def _snapshot(shared_state: dict[str, Any]) -> dict[str, Any]:
    return (((shared_state.get("text_theater") or {}).get("snapshot")) or {})


def _workbench_surface(shared_state: dict[str, Any]) -> dict[str, Any]:
    return (((shared_state.get("mounted_character_runtime") or {}).get("workbench_surface")) or {})


def _focus(shared_state: dict[str, Any]) -> dict[str, Any]:
    return (shared_state.get("focus") or {})


def _baseline_ready(shared_state: dict[str, Any]) -> tuple[bool, str]:
    snap = _snapshot(shared_state)
    wb = _workbench_surface(shared_state)
    if not snap:
        return False, "text_theater.snapshot missing"
    if not wb:
        return False, "mounted_character_runtime.workbench_surface missing"
    if not wb.get("builder_active"):
        return False, "builder_active false"
    timeline = snap.get("timeline") or {}
    required_timeline = {"source_motion_preset", "displacement_mode", "contact_phases", "root_trajectory"}
    if not required_timeline.issubset(set(timeline.keys())):
        return False, "timeline metadata incomplete"
    if "settle" in snap:
        return False, "stale settle snapshot still present"
    if "settle_preview" in wb:
        return False, "stale settle workbench field still present"
    return True, "ready"


def _json_compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _vector3(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    out: dict[str, float] = {}
    for key in ("x", "y", "z"):
        raw = value.get(key)
        if not _is_number(raw):
            return None
        out[key] = float(raw)
    return out


def _vector_equal(left: Any, right: Any, tolerance: float = VECTOR_TOLERANCE) -> bool:
    lv = _vector3(left)
    rv = _vector3(right)
    if not lv or not rv:
        return False
    return all(abs(lv[key] - rv[key]) <= tolerance for key in ("x", "y", "z"))


def _vector_list(value: Any) -> list[dict[str, float]] | None:
    if not isinstance(value, list):
        return None
    rows: list[dict[str, float]] = []
    for item in value:
        vec = _vector3(item)
        if not vec:
            return None
        rows.append(vec)
    return rows


def _vector_list_equal(left: Any, right: Any, tolerance: float = VECTOR_TOLERANCE) -> bool:
    lrows = _vector_list(left)
    rrows = _vector_list(right)
    if lrows is None or rrows is None or len(lrows) != len(rrows):
        return False
    for lvec, rvec in zip(lrows, rrows):
        if any(abs(lvec[key] - rvec[key]) > tolerance for key in ("x", "y", "z")):
            return False
    return True


def _approx_equal(left: Any, right: Any, tolerance: float = VECTOR_TOLERANCE) -> bool:
    if not _is_number(left) or not _is_number(right):
        return False
    return abs(float(left) - float(right)) <= tolerance


def _support_frame_ok(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return all(_vector3(value.get(key)) for key in ("origin", "normal", "up", "axis_x", "axis_z"))


def _support_frame_equal(left: Any, right: Any) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    for key in ("origin", "normal", "up", "axis_x", "axis_z"):
        if not _vector_equal(left.get(key), right.get(key)):
            return False
    return True


def _string_triplet(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _contact_map(rows: Any) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("canonical_joint") or row.get("bone_id") or row.get("joint") or "").strip()
        if key:
            mapping[key] = row
    return mapping


class EvalRecorder:
    def __init__(self) -> None:
        self.sections: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self.failures: list[dict[str, Any]] = []

    def section(self, name: str) -> None:
        entry = {"name": name, "checks": []}
        self.sections.append(entry)
        self._current = entry

    def check(self, name: str, passed: bool, reason: str, details: Any = None) -> None:
        if self._current is None:  # pragma: no cover - defensive
            raise RuntimeError("no active section")
        status = "PASS" if passed else "FAIL"
        row = {"name": name, "status": status, "reason": reason}
        if details is not None:
            row["details"] = details
        self._current["checks"].append(row)
        print(f"{status} {self._current['name']} :: {name} :: {reason}")
        if not passed:
            self.failures.append(row)

    def summary(self) -> dict[str, Any]:
        total = 0
        passed = 0
        failed = 0
        per_section = []
        for section in self.sections:
            checks = section["checks"]
            section_total = len(checks)
            section_passed = sum(1 for row in checks if row["status"] == "PASS")
            section_failed = section_total - section_passed
            total += section_total
            passed += section_passed
            failed += section_failed
            per_section.append(
                {
                    "name": section["name"],
                    "passed": section_passed,
                    "failed": section_failed,
                    "total": section_total,
                }
            )
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "sections": per_section,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate current workbench mechanics against live source truth.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout", type=float, default=5.0, help="shared_state convergence timeout in seconds")
    parser.add_argument("--output", default="", help="optional explicit output path")
    args = parser.parse_args()

    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    output_path = Path(args.output) if args.output else data_dir / f"workbench_mechanics_eval_{ts}.json"
    failure_state_path = data_dir / f"workbench_mechanics_eval_{ts}_shared_state.json"

    recorder = EvalRecorder()

    shared_state = _wait_for_convergence(
        lambda: _env_read_shared_state(args.base_url),
        _baseline_ready,
        timeout_s=args.timeout,
    )

    snap = _snapshot(shared_state)
    theater = snap.get("theater") or {}
    snap_workbench = snap.get("workbench") or {}
    snap_balance = snap.get("balance") or {}
    snap_timeline = snap.get("timeline") or {}
    snap_contacts = snap.get("contacts") or []
    snap_semantic = ((snap.get("semantic") or {}).get("triplets")) or []
    focus = _focus(shared_state)
    focus_payload = ((focus.get("payload") or {}).get("data")) or {}
    wb = _workbench_surface(shared_state)
    wb_load = wb.get("load_field") or {}
    wb_motion = wb.get("motion_diagnostics") or {}

    # These checks protect the active builder baseline, not speculative future state.
    recorder.section("Baseline")
    recorder.check(
        "theater mode",
        theater.get("mode") == "character",
        f"snapshot.theater.mode={theater.get('mode')!r}; character mode is the current mounted workbench baseline",
    )
    recorder.check(
        "visual mode",
        theater.get("visual_mode") == "builder_subject",
        f"snapshot.theater.visual_mode={theater.get('visual_mode')!r}; builder_subject is the current live bundle mode",
    )
    recorder.check(
        "focus target",
        focus.get("kind") == "character_runtime"
        and focus.get("id") == "mounted_primary"
        and (((focus_payload.get("mount_contract") or {}).get("target_class")) == "mounted_character_runtime"),
        "focus resolves to mounted_character_runtime so workbench assertions read the right subject",
        {
            "focus_kind": focus.get("kind"),
            "focus_id": focus.get("id"),
            "target_class": ((focus_payload.get("mount_contract") or {}).get("target_class")),
        },
    )
    recorder.check(
        "builder active",
        wb.get("builder_active") is True,
        "workbench_surface.builder_active must stay true for all downstream mechanics surfaces to be meaningful",
    )
    recorder.check(
        "display scope body",
        wb.get("configured_display_scope") == "body"
        and wb.get("part_display_scope") == "body"
        and snap_workbench.get("part_display_scope") == "body",
        "full-body scope is the current baseline; scoped-part mode would change the visible/measured contract",
        {
            "configured_display_scope": wb.get("configured_display_scope"),
            "part_display_scope": wb.get("part_display_scope"),
            "snapshot_part_display_scope": snap_workbench.get("part_display_scope"),
        },
    )
    recorder.check(
        "no isolated chain",
        str(wb.get("isolated_chain") or "").strip() == ""
        and not list(snap_workbench.get("selected_chain_bone_ids") or []),
        "no chain isolation should be active in the baseline because it would intentionally narrow the mechanics surface",
        {
            "workbench_isolated_chain": wb.get("isolated_chain"),
            "snapshot_selected_chain_bone_ids": snap_workbench.get("selected_chain_bone_ids"),
        },
    )
    recorder.check(
        "settle surfaces absent",
        "settle_preview" not in wb and "settle" not in snap,
        "the deleted settle workflow must stay absent from live shared state",
    )

    # These checks protect the Slice 1 motion metadata contract that now feeds the later locomotion/blackboard work.
    recorder.section("Timeline")
    recorder.check(
        "timeline fields present",
        all(key in snap_timeline for key in ("source_motion_preset", "displacement_mode", "contact_phases", "root_trajectory")),
        "snapshot.timeline must carry the retired-preset metadata defaults honestly instead of backfilling from dead commands",
        {"timeline_keys": list(snap_timeline.keys())},
    )
    recorder.check(
        "timeline displacement mode default",
        wb.get("timeline_displacement_mode") == "in_place" and snap_timeline.get("displacement_mode") == "in_place",
        "current source truth is in-place motion only; root-motion behavior is a later slice",
        {
            "workbench": wb.get("timeline_displacement_mode"),
            "snapshot": snap_timeline.get("displacement_mode"),
        },
    )
    recorder.check(
        "timeline contact phases default",
        wb.get("timeline_contact_phases") == [] and snap_timeline.get("contact_phases") == [],
        "contact phases are present in schema now, but current baseline publishes an empty list until authoring lands",
        {
            "workbench": wb.get("timeline_contact_phases"),
            "snapshot": snap_timeline.get("contact_phases"),
        },
    )
    recorder.check(
        "timeline root trajectory default",
        wb.get("timeline_root_trajectory") is None and snap_timeline.get("root_trajectory") is None,
        "root trajectory must stay null until root-motion slice actually ships",
    )
    recorder.check(
        "timeline source motion preset default",
        wb.get("timeline_source_motion_preset") == "" and snap_timeline.get("source_motion_preset") == "",
        "retired presets should only survive as an empty metadata field, not as a live command path",
    )
    recorder.check(
        "timeline parity",
        wb.get("timeline_displacement_mode") == snap_timeline.get("displacement_mode")
        and _json_compact(wb.get("timeline_contact_phases")) == _json_compact(snap_timeline.get("contact_phases"))
        and wb.get("timeline_root_trajectory") == snap_timeline.get("root_trajectory")
        and wb.get("timeline_source_motion_preset") == snap_timeline.get("source_motion_preset"),
        "workbench_surface and text_theater.snapshot must tell the same story about motion metadata",
        {
            "workbench": {
                "displacement_mode": wb.get("timeline_displacement_mode"),
                "contact_phases": wb.get("timeline_contact_phases"),
                "root_trajectory": wb.get("timeline_root_trajectory"),
                "source_motion_preset": wb.get("timeline_source_motion_preset"),
            },
            "snapshot": {
                "displacement_mode": snap_timeline.get("displacement_mode"),
                "contact_phases": snap_timeline.get("contact_phases"),
                "root_trajectory": snap_timeline.get("root_trajectory"),
                "source_motion_preset": snap_timeline.get("source_motion_preset"),
            },
        },
    )

    # These checks protect the restored balance/load contract and verify snapshot parity against the canonical workbench source.
    recorder.section("Balance")
    recorder.check(
        "support phase vocabulary",
        str(wb_motion.get("support_phase") or "").strip() in KNOWN_SUPPORT_PHASES
        and wb_motion.get("support_phase") == snap_balance.get("support_phase"),
        "support_phase must stay in the current source vocabulary and match the snapshot export",
        {"workbench": wb_motion.get("support_phase"), "snapshot": snap_balance.get("support_phase")},
    )
    recorder.check(
        "balance mode vocabulary",
        str(wb_load.get("balance_mode") or "").strip() in KNOWN_BALANCE_MODES
        and wb_load.get("balance_mode") == snap_balance.get("balance_mode"),
        "balance_mode is the regime vocabulary for later recovery logic and must stay honest across both surfaces",
        {"workbench": wb_load.get("balance_mode"), "snapshot": snap_balance.get("balance_mode")},
    )
    recorder.check(
        "gravity vector parity",
        _vector3(wb_load.get("gravity_vector")) is not None
        and _vector_equal(wb_load.get("gravity_vector"), snap_balance.get("gravity_vector")),
        "gravity_vector is part of the restored balance contract and must remain a 3-vector in both exports",
        {"workbench": wb_load.get("gravity_vector"), "snapshot": snap_balance.get("gravity_vector")},
    )
    recorder.check(
        "support frame parity",
        _support_frame_ok(wb_load.get("support_frame"))
        and _support_frame_equal(wb_load.get("support_frame"), snap_balance.get("support_frame")),
        "support_frame provides the support-plane basis used by later terrain/gravity work and must match in both surfaces",
        {"workbench": wb_load.get("support_frame"), "snapshot": snap_balance.get("support_frame")},
    )
    recorder.check(
        "projected CoM world parity",
        _vector3(wb_load.get("projected_com_world")) is not None
        and _vector_equal(wb_load.get("projected_com_world"), snap_balance.get("projected_com_world")),
        "projected_com_world is the world-space CoM anchor for overlay/blackboard work and must stay aligned",
        {"workbench": wb_load.get("projected_com_world"), "snapshot": snap_balance.get("projected_com_world")},
    )
    recorder.check(
        "projected CoM lies on support plane",
        _approx_equal(
            ((wb_load.get("projected_com_world") or {}).get("y")),
            (((wb_load.get("support_frame") or {}).get("origin") or {}).get("y")),
        ),
        "projected_com_world should sit on the support plane height defined by support_frame.origin",
        {
            "projected_com_world": wb_load.get("projected_com_world"),
            "support_frame_origin": ((wb_load.get("support_frame") or {}).get("origin")),
        },
    )
    recorder.check(
        "support polygon world parity",
        _vector_list(wb_load.get("support_polygon_world")) is not None
        and _vector_list_equal(wb_load.get("support_polygon_world"), snap_balance.get("support_polygon_world")),
        "support_polygon_world must stay a world-space polygon list shared by workbench and snapshot",
        {
            "workbench_count": len(wb_load.get("support_polygon_world") or []),
            "snapshot_count": len(snap_balance.get("support_polygon_world") or []),
        },
    )
    polygon_world = _vector_list(wb_load.get("support_polygon_world")) or []
    plane_height = (((wb_load.get("support_frame") or {}).get("origin") or {}).get("y"))
    recorder.check(
        "support polygon world lies on support plane",
        all(_approx_equal(point["y"], plane_height) for point in polygon_world),
        "each support polygon vertex should live on the same support plane as the support frame origin",
        {"plane_height": plane_height, "point_count": len(polygon_world)},
    )
    recorder.check(
        "stability risk parity",
        _is_number(wb_load.get("stability_risk"))
        and 0.0 <= float(wb_load.get("stability_risk")) <= 1.0
        and _approx_equal(wb_load.get("stability_risk"), snap_balance.get("stability_risk")),
        "stability_risk is a normalized substrate output and must stay bounded and parity-aligned",
        {"workbench": wb_load.get("stability_risk"), "snapshot": snap_balance.get("stability_risk")},
    )
    recorder.check(
        "inside polygon parity",
        isinstance(wb_load.get("inside_support_polygon"), bool)
        and isinstance(snap_balance.get("inside_polygon"), bool)
        and wb_load.get("inside_support_polygon") == snap_balance.get("inside_polygon"),
        "inside-polygon truth drives alerting and must not diverge between workbench and text snapshot",
        {"workbench": wb_load.get("inside_support_polygon"), "snapshot": snap_balance.get("inside_polygon")},
    )
    recorder.check(
        "dominant side parity",
        str(wb_load.get("dominant_support_side") or "").strip() == str(snap_balance.get("dominant_side") or "").strip(),
        "dominant support side is a compact directional cue and should read identically in both surfaces",
        {"workbench": wb_load.get("dominant_support_side"), "snapshot": snap_balance.get("dominant_side")},
    )
    recorder.check(
        "supporting ids parity",
        _json_compact(sorted(wb_motion.get("supporting_ids") or [])) == _json_compact(sorted(snap_balance.get("supporting_joint_ids") or [])),
        "supporting joint ids are derived from motion diagnostics and must match the snapshot balance export",
        {"workbench": wb_motion.get("supporting_ids"), "snapshot": snap_balance.get("supporting_joint_ids")},
    )
    recorder.check(
        "alert ids parity",
        _json_compact(sorted(wb_motion.get("alerts") or [])) == _json_compact(sorted(snap_balance.get("alert_ids") or [])),
        "alert ids should agree so the text consumer reflects the same balance warnings as the workbench source",
        {"workbench": wb_motion.get("alerts"), "snapshot": snap_balance.get("alert_ids")},
    )

    # These checks protect the live contact contract without asserting future patch families that source does not yet ship.
    recorder.section("Contacts")
    wb_contacts = wb_motion.get("contacts") or []
    snap_contact_map = _contact_map(snap_contacts)
    wb_contact_map = _contact_map(wb_contacts)
    recorder.check(
        "contacts list shape",
        isinstance(snap_contacts, list),
        "snapshot.contacts must stay a list because later locomotion/blackboard consumers iterate it directly",
        {"type": type(snap_contacts).__name__, "count": len(snap_contacts) if isinstance(snap_contacts, list) else None},
    )
    recorder.check(
        "contact parity count",
        isinstance(wb_contacts, list) and len(wb_contacts) == len(snap_contacts),
        "snapshot contacts should remain a lossless subset of the workbench motion diagnostics contacts",
        {"workbench_count": len(wb_contacts) if isinstance(wb_contacts, list) else None, "snapshot_count": len(snap_contacts) if isinstance(snap_contacts, list) else None},
    )
    required_contact_keys = {"joint", "state", "group", "gap"}
    contact_shape_ok = all(isinstance(row, dict) and required_contact_keys.issubset(set(row.keys())) for row in snap_contacts)
    recorder.check(
        "contact required fields",
        contact_shape_ok,
        "each snapshot contact row must carry the minimal joint/state/group/gap contract",
        {"required_keys": sorted(required_contact_keys)},
    )
    contact_state_ok = all(str((row or {}).get("state") or "").strip() in KNOWN_CONTACT_STATES for row in snap_contacts if isinstance(row, dict))
    recorder.check(
        "contact state vocabulary",
        contact_state_ok,
        "contact states must stay within the current source vocabulary so later substrate slices extend a stable base",
        {"states_seen": sorted({str((row or {}).get('state') or '').strip() for row in snap_contacts if isinstance(row, dict)})},
    )
    parity_failures = []
    for joint, snap_row in snap_contact_map.items():
        wb_row = wb_contact_map.get(joint)
        if not wb_row:
            parity_failures.append({"joint": joint, "reason": "missing_workbench_row"})
            continue
        if str(wb_row.get("state") or "") != str(snap_row.get("state") or ""):
            parity_failures.append({"joint": joint, "field": "state", "workbench": wb_row.get("state"), "snapshot": snap_row.get("state")})
        if str(wb_row.get("group") or "") != str(snap_row.get("group") or ""):
            parity_failures.append({"joint": joint, "field": "group", "workbench": wb_row.get("group"), "snapshot": snap_row.get("group")})
        if str(wb_row.get("side") or "") != str(snap_row.get("side") or ""):
            parity_failures.append({"joint": joint, "field": "side", "workbench": wb_row.get("side"), "snapshot": snap_row.get("side")})
        if bool(wb_row.get("supporting")) != bool(snap_row.get("supporting")):
            parity_failures.append({"joint": joint, "field": "supporting", "workbench": wb_row.get("supporting"), "snapshot": snap_row.get("supporting")})
        if not _approx_equal(wb_row.get("gap"), snap_row.get("gap"), tolerance=1e-3):
            parity_failures.append({"joint": joint, "field": "gap", "workbench": wb_row.get("gap"), "snapshot": snap_row.get("gap")})
    recorder.check(
        "contact subset parity",
        not parity_failures,
        "snapshot contacts should preserve the key joint/state/group/gap/supporting subset from workbench motion diagnostics",
        parity_failures[:8],
    )

    # These checks protect the semantic summary layer that later blackboard and agent consumers depend on.
    recorder.section("Semantic")
    recorder.check(
        "triplet list shape",
        isinstance(snap_semantic, list),
        "semantic.triplets must stay a list because it is the compact agent-readable semantics layer",
        {"type": type(snap_semantic).__name__, "count": len(snap_semantic) if isinstance(snap_semantic, list) else None},
    )
    recorder.check(
        "triplet entries are 3 non-empty strings",
        all(_string_triplet(row) for row in snap_semantic),
        "every semantic triplet must remain a compact [subject, relation, object] triple with no empty strings",
    )
    support_triplets = [row for row in snap_semantic if _string_triplet(row) and row[0] == "support_phase"]
    recorder.check(
        "support phase triplet present",
        len(support_triplets) >= 1,
        "semantic triplets must include support_phase so compact agent views can reason without the full balance payload",
        support_triplets,
    )
    balance_triplets = [row for row in snap_semantic if _string_triplet(row) and row[0] == "balance_mode"]
    recorder.check(
        "balance mode triplet present",
        len(balance_triplets) >= 1,
        "semantic triplets must include balance_mode because later recovery logic and blackboard summaries key off that regime label",
        balance_triplets,
    )
    settle_triplets = [row for row in snap_semantic if _string_triplet(row) and row[0] == "settle"]
    recorder.check(
        "settle triplets absent",
        len(settle_triplets) == 0,
        "deleted settle workflow must not leak back into semantic triplets",
    )

    summary = recorder.summary()
    for section in summary["sections"]:
        print(f"SECTION {section['name']}: {section['passed']}/{section['total']} PASS")
    overall_line = f"OVERALL {summary['passed']}/{summary['total']} PASS"
    print(overall_line if summary["failed"] == 0 else f"{overall_line} ({summary['failed']} failed)")

    report = {
        "generated_ts": ts,
        "base_url": args.base_url,
        "summary": summary,
        "sections": recorder.sections,
        "state_excerpt": {
            "theater_mode": theater.get("mode"),
            "visual_mode": theater.get("visual_mode"),
            "focus_kind": focus.get("kind"),
            "focus_id": focus.get("id"),
            "builder_active": wb.get("builder_active"),
            "configured_display_scope": wb.get("configured_display_scope"),
            "part_display_scope": wb.get("part_display_scope"),
            "isolated_chain": wb.get("isolated_chain"),
            "balance_mode": wb_load.get("balance_mode"),
            "support_phase": wb_motion.get("support_phase"),
            "contact_count": len(snap_contacts),
            "semantic_triplet_count": len(snap_semantic),
        },
    }

    if summary["failed"]:
        failure_state_path.write_text(json.dumps(shared_state, indent=2), encoding="utf-8")
        report["failure_shared_state_path"] = str(failure_state_path)
        report["shared_state_dumped"] = True
    else:
        report["shared_state_dumped"] = False

    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"REPORT {output_path}")
    if summary["failed"]:
        print(f"FAILURE_SHARED_STATE {failure_state_path}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
