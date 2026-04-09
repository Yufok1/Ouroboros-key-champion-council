#!/usr/bin/env python
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_BASE_URL = "http://127.0.0.1:7866"

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


def _tool_text(resp):
    try:
        return resp["result"]["content"][0]["text"]
    except Exception:
        return ""


def _maybe_json(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


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
    parsed = _maybe_json(_tool_text(resp))
    if not isinstance(parsed, dict):
        raise RuntimeError(f"bad env_read response for {query}")
    return parsed


def _animation_state(base_url, actor="codex", timeout=20.0):
    shared = _shared_state(base_url)
    mounted = shared.get("mounted_character_runtime") if isinstance(shared.get("mounted_character_runtime"), dict) else {}
    surface = mounted.get("animation_surface") if isinstance(mounted.get("animation_surface"), dict) else {}
    return surface if isinstance(surface, dict) else {}


def _shared_state(base_url):
    return (_env_read(base_url, "shared_state").get("shared_state") or {})


def _snapshot(shared_state):
    text_theater = shared_state.get("text_theater") if isinstance(shared_state.get("text_theater"), dict) else {}
    snapshot = text_theater.get("snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _extract_state(base_url, include_animation=False):
    shared = _shared_state(base_url)
    snapshot = _snapshot(shared)
    mounted = shared.get("mounted_character_runtime") if isinstance(shared.get("mounted_character_runtime"), dict) else {}
    workbench_surface = mounted.get("workbench_surface") if isinstance(mounted.get("workbench_surface"), dict) else {}
    animation_surface = mounted.get("animation_surface") if isinstance(mounted.get("animation_surface"), dict) else {}
    workbench = snapshot.get("workbench") if isinstance(snapshot.get("workbench"), dict) else {}
    embodiment = snapshot.get("embodiment") if isinstance(snapshot.get("embodiment"), dict) else {}
    timeline = snapshot.get("timeline") if isinstance(snapshot.get("timeline"), dict) else {}
    settle_snapshot = snapshot.get("settle") if isinstance(snapshot.get("settle"), dict) else {}
    balance = snapshot.get("balance") if isinstance(snapshot.get("balance"), dict) else {}
    theater = snapshot.get("theater") if isinstance(snapshot.get("theater"), dict) else {}
    contacts = snapshot.get("contacts") if isinstance(snapshot.get("contacts"), list) else []
    motion = workbench.get("motion_diagnostics") if isinstance(workbench.get("motion_diagnostics"), dict) else (
        workbench_surface.get("motion_diagnostics") if isinstance(workbench_surface.get("motion_diagnostics"), dict) else {}
    )
    load_field = workbench.get("load_field") if isinstance(workbench.get("load_field"), dict) else (
        workbench_surface.get("load_field") if isinstance(workbench_surface.get("load_field"), dict) else {}
    )
    settle = settle_snapshot if settle_snapshot else (
        workbench_surface.get("settle_preview") if isinstance(workbench_surface.get("settle_preview"), dict) else {}
    )
    assertion = balance.get("assertion") if isinstance(balance.get("assertion"), dict) else (
        workbench.get("balance_assertion") if isinstance(workbench.get("balance_assertion"), dict) else (
            workbench_surface.get("balance_assertion") if isinstance(workbench_surface.get("balance_assertion"), dict) else {}
        )
    )
    capture = shared.get("capture") if isinstance(shared.get("capture"), dict) else {}
    strip_summary = workbench.get("latest_time_strip_motion_summary")
    if not isinstance(strip_summary, dict):
        strip_summary = workbench_surface.get("latest_time_strip_motion_summary")
    if not isinstance(strip_summary, dict):
        strip_summary = capture.get("motion_diagnostics_summary")
    if not isinstance(strip_summary, dict):
        strip_summary = {}
    state = {
        "theater_mode": str((theater.get("mode") or "")),
        "editing_mode": str(workbench.get("editing_mode") or embodiment.get("editing_mode") or workbench_surface.get("editing_mode") or ""),
        "builder_active": bool(embodiment.get("builder_active") or workbench_surface.get("builder_active")),
        "display_scope": str(workbench.get("part_display_scope") or workbench_surface.get("part_display_scope") or ""),
        "isolated_chain": str(workbench.get("isolated_chain") or embodiment.get("isolated_chain") or workbench_surface.get("isolated_chain") or ""),
        "posed_bone_ids": list(embodiment.get("posed_bone_ids") or workbench.get("posed_bone_ids") or workbench_surface.get("posed_bone_ids") or []),
        "timeline": {
            "cursor": timeline.get("cursor", workbench_surface.get("timeline_cursor")),
            "duration": timeline.get("duration", workbench_surface.get("timeline_duration")),
            "key_pose_count": timeline.get("key_pose_count", workbench_surface.get("timeline_key_pose_count")),
        },
        "authored_clips": {
            "count": workbench_surface.get("authored_clip_count"),
            "names": list(workbench_surface.get("authored_clip_names") or []),
            "last_compiled_clip": workbench_surface.get("last_compiled_clip"),
            "clips": list(workbench_surface.get("authored_clips") or []),
        },
        "settle_preview": {
            "active": bool(settle.get("active")),
            "strategy": settle.get("strategy"),
            "frame_count": settle.get("frame_count"),
            "duration": settle.get("duration"),
        },
        "assertion": {
            "active": bool(assertion.get("active")),
            "status": str(assertion.get("status") or "unchecked"),
            "summary": str(assertion.get("summary") or ""),
        },
        "balance": {
            "mode": str(balance.get("balance_mode") or ""),
            "support_phase": str(balance.get("support_phase") or ""),
            "support_count": int(
                balance.get("support_count")
                or load_field.get("support_count")
                or motion.get("support_contact_count")
                or 0
            ),
            "supporting_ids": list(
                balance.get("supporting_ids")
                or balance.get("supporting_joint_ids")
                or motion.get("supporting_ids")
                or []
            ),
            "stability_risk": float(balance.get("stability_risk") or 0.0),
            "inside_polygon": bool(balance.get("inside_polygon")),
        },
        "motion": {
            "support_contact_count": int(motion.get("support_contact_count") or 0),
            "supporting_ids": list(motion.get("supporting_ids") or []),
            "alert_count": len(motion.get("alerts") or []),
            "contact_count": len(contacts),
        },
        "load_field": {
            "balance_mode": str(load_field.get("balance_mode") or ""),
            "support_count": int(load_field.get("support_count") or 0),
            "support_loads_count": len(load_field.get("support_loads") or []),
            "segment_load_count": len((load_field.get("segment_loads") or {})),
        },
        "time_strip": {
            "frame_count": int(
                workbench_surface.get("last_time_strip_frame_count")
                or capture.get("frame_count")
                or 0
            ),
            "dominant_support_phase": str(strip_summary.get("dominant_support_phase") or ""),
            "max_support_contact_count": int(strip_summary.get("max_support_contact_count") or 0),
            "has_summary": bool(strip_summary),
        },
    }
    if include_animation:
        animation = animation_surface if animation_surface else _animation_state(base_url)
        state["animation"] = {
            "active_clip": str(animation.get("active_clip") or ""),
            "active_clip_raw": str(animation.get("active_clip_raw") or ""),
            "active_clip_source": str(animation.get("active_clip_source") or ""),
            "queue_length": int(len(animation.get("queue") or [])),
            "paused": bool(animation.get("paused")),
        }
    return state


def _sleep(seconds):
    time.sleep(max(0.0, float(seconds)))


def _check(name, passed, details):
    return {
        "name": str(name),
        "passed": bool(passed),
        "details": details,
    }


def _run_command(base_url, command, target="", actor="codex", pause=0.35):
    resp = _env_control(base_url, command, target, actor=actor)
    _sleep(pause)
    return resp


def _wait_for_state(base_url, predicate, timeout=3.0, interval=0.2, include_animation=False):
    deadline = time.time() + max(0.1, float(timeout))
    last_state = {}
    while time.time() <= deadline:
        last_state = _extract_state(base_url, include_animation=include_animation)
        try:
            if predicate(last_state):
                return last_state
        except Exception:
            pass
        _sleep(interval)
    return last_state


def _bool_clip_match(animation_state, clip_name):
    if not isinstance(animation_state, dict):
        return False
    target = str(clip_name or "").strip()
    if not target:
        return False
    return target in {
        str(animation_state.get("active_clip") or "").strip(),
        str(animation_state.get("active_clip_raw") or "").strip(),
    }


def _authored_clip_entry(state, clip_name):
    authored = state.get("authored_clips") if isinstance(state.get("authored_clips"), dict) else {}
    for entry in (authored.get("clips") or []):
        if str(entry.get("name") or "").strip() == str(clip_name or "").strip():
            return entry
    return {}


def _contact_phases(metadata):
    phases = metadata.get("contact_phases") if isinstance(metadata, dict) else []
    return phases if isinstance(phases, list) else []


def _contact_phase_support_rows(contact_phases):
    rows = []
    for entry in (contact_phases or []):
        support_phase = str(((entry or {}).get("support_phase")) or "").strip()
        if support_phase:
            rows.append(support_phase)
    return rows


def _contact_phase_states(contact_phases, contact_id):
    rows = []
    for entry in (contact_phases or []):
        contacts = entry.get("contacts") if isinstance(entry, dict) else {}
        payload = contacts.get(contact_id) if isinstance(contacts, dict) else {}
        state = str(((payload or {}).get("state")) or "").strip()
        if state:
            rows.append(state)
    return rows


def _preset_contact_phase_expectation(preset_id, contact_phases):
    support_rows = _contact_phase_support_rows(contact_phases)
    foot_l_states = _contact_phase_states(contact_phases, "foot_l")
    foot_r_states = _contact_phase_states(contact_phases, "foot_r")
    details = {
        "contact_phase_count": len(contact_phases or []),
        "support_phases": support_rows,
        "foot_l_states": foot_l_states,
        "foot_r_states": foot_r_states,
    }
    if preset_id == "idle_shift":
        passed = (
            len(contact_phases or []) >= 5
            and support_rows
            and set(support_rows) == {"double_support"}
            and "loading" in foot_l_states
            and "loading" in foot_r_states
        )
        return passed, details
    if preset_id == "step_left":
        passed = (
            len(contact_phases or []) >= 5
            and "single_support_right" in support_rows
            and "swing" in foot_l_states
            and "loading" in foot_r_states
        )
        return passed, details
    if preset_id == "brace_crouch":
        passed = (
            len(contact_phases or []) >= 5
            and "braced_support" in support_rows
            and "brace" in foot_l_states
            and "brace" in foot_r_states
        )
        return passed, details
    if preset_id == "torso_twist":
        passed = (
            len(contact_phases or []) >= 4
            and support_rows
            and set(support_rows) == {"double_support"}
            and foot_l_states
            and foot_r_states
            and set(foot_l_states) == {"planted"}
            and set(foot_r_states) == {"planted"}
        )
        return passed, details
    return bool(contact_phases), details


def main():
    parser = argparse.ArgumentParser(description="Evaluate workbench motion/mechanics systems together.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--actor", default="codex")
    parser.add_argument("--pause", type=float, default=0.4)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else (
        Path("data") / f"workbench_mechanics_eval_{int(time.time())}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "base_url": args.base_url,
        "generated_ts": int(time.time()),
        "checks": [],
        "baseline": {},
        "batch_pose": {},
        "settle": {},
        "summary": {},
    }

    _run_command(args.base_url, "set_theater_mode", "character", actor=args.actor, pause=args.pause)
    _run_command(args.base_url, "workbench_set_editing_mode", "pose", actor=args.actor, pause=args.pause)
    _run_command(args.base_url, "workbench_set_display_scope", json.dumps({"part_display_scope": "body"}), actor=args.actor, pause=args.pause)
    _run_command(args.base_url, "workbench_isolate_chain", "", actor=args.actor, pause=args.pause)
    _run_command(args.base_url, "workbench_clear_pose", json.dumps({"all": True}), actor=args.actor, pause=args.pause)
    _run_command(args.base_url, "workbench_reset_angles", "", actor=args.actor, pause=args.pause)

    baseline = _wait_for_state(
        args.base_url,
        lambda state: (
            state.get("builder_active")
            and state.get("theater_mode") == "character"
            and state.get("display_scope") == "body"
            and not state.get("isolated_chain")
        ),
        timeout=max(4.0, args.pause * 10),
        interval=max(0.15, args.pause * 0.5),
    )
    report["baseline"] = baseline
    report["checks"].append(_check(
        "baseline_builder_active",
        baseline["builder_active"] and baseline["theater_mode"] == "character",
        baseline,
    ))
    report["checks"].append(_check(
        "baseline_full_body_scope",
        baseline["display_scope"] == "body" and not baseline["isolated_chain"],
        {
            "display_scope": baseline["display_scope"],
            "isolated_chain": baseline["isolated_chain"],
        },
    ))
    report["checks"].append(_check(
        "baseline_balance_payload_live",
        baseline["balance"]["support_count"] >= 1
        and baseline["load_field"]["segment_load_count"] >= 1
        and bool(baseline["balance"]["mode"]),
        baseline["balance"],
    ))

    _run_command(args.base_url, "workbench_assert_balance", "", actor=args.actor, pause=args.pause)
    post_assert = _wait_for_state(
        args.base_url,
        lambda state: str(((state.get("assertion") or {}).get("status")) or "unchecked") != "unchecked",
        timeout=max(3.0, args.pause * 8),
        interval=max(0.15, args.pause * 0.5),
    )
    report["checks"].append(_check(
        "assert_balance_updates_state",
        post_assert["assertion"]["status"] != "unchecked",
        post_assert["assertion"],
    ))

    batch_payload = {
        "poses": [
            {"canonical_joint": "spine", "rotation_deg": [10, -8, 0]},
            {"canonical_joint": "chest", "rotation_deg": [-8, -14, 0]},
            {"canonical_joint": "upper_leg_r", "rotation_deg": [16, 0, -6]},
            {"canonical_joint": "lower_leg_r", "rotation_deg": [24, 0, 0]},
            {"canonical_joint": "upper_arm_l", "rotation_deg": [32, 0, -18]},
            {"canonical_joint": "upper_arm_r", "rotation_deg": [-22, 0, 16]},
        ]
    }
    _run_command(args.base_url, "workbench_set_pose_batch", json.dumps(batch_payload), actor=args.actor, pause=args.pause)
    batch_state = _extract_state(args.base_url)
    report["batch_pose"] = batch_state
    report["checks"].append(_check(
        "batch_pose_applies_transforms",
        len(batch_state["posed_bone_ids"]) >= 4,
        batch_state,
    ))
    report["checks"].append(_check(
        "batch_pose_keeps_mechanics_live",
        batch_state["motion"]["contact_count"] >= 1 and batch_state["load_field"]["segment_load_count"] >= 1,
        batch_state["motion"],
    ))

    _run_command(
        args.base_url,
        "workbench_preview_settle",
        json.dumps({"frame_count": 4, "duration": 0.8}),
        actor=args.actor,
        pause=args.pause,
    )
    settle_preview_state = _wait_for_state(
        args.base_url,
        lambda state: bool((state.get("settle_preview") or {}).get("active"))
        or int((((state.get("settle_preview") or {}).get("frame_count")) or 0)) >= 3,
        timeout=max(5.0, args.pause * 12),
        interval=max(0.15, args.pause * 0.5),
    )
    settle_clip_name = f"eval_settle_{int(time.time())}"
    _run_command(
        args.base_url,
        "workbench_commit_settle",
        json.dumps({"target": "clip", "clip_name": settle_clip_name, "preserve_preview": False}),
        actor=args.actor,
        pause=args.pause,
    )
    settle_commit_state = _wait_for_state(
        args.base_url,
        lambda state: settle_clip_name in ((state.get("authored_clips") or {}).get("names") or [])
        or str(((state.get("authored_clips") or {}).get("last_compiled_clip")) or "") == settle_clip_name,
        timeout=max(2.5, args.pause * 6),
        interval=max(0.15, args.pause * 0.5),
    )
    settle_clip_metadata = _authored_clip_entry(settle_commit_state, settle_clip_name)
    report["settle"] = {
        "preview": settle_preview_state,
        "commit": settle_commit_state,
        "clip_name": settle_clip_name,
        "clip_metadata": settle_clip_metadata,
    }
    report["checks"].append(_check(
        "settle_preview_generates_timeline",
        settle_preview_state["settle_preview"]["active"]
        and int(settle_preview_state["settle_preview"]["frame_count"] or 0) >= 3,
        settle_preview_state["settle_preview"],
    ))
    report["checks"].append(_check(
        "settle_commit_compiles_clip",
        settle_clip_name in (settle_commit_state["authored_clips"]["names"] or [])
        or str(settle_commit_state["authored_clips"]["last_compiled_clip"] or "") == settle_clip_name,
        settle_commit_state["authored_clips"],
    ))
    report["checks"].append(_check(
        "settle_commit_metadata_present",
        settle_clip_metadata.get("displacement_mode") == "in_place"
        and isinstance(settle_clip_metadata.get("contact_phases"), list)
        and settle_clip_metadata.get("root_trajectory") is None,
        settle_clip_metadata,
    ))

    all_checks = list(report["checks"])

    passed = sum(1 for check in all_checks if check["passed"])
    failed = len(all_checks) - passed
    report["summary"] = {
        "total_checks": len(all_checks),
        "passed": passed,
        "failed": failed,
        "failing_checks": [check["name"] for check in all_checks if not check["passed"]],
    }

    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(str(output_path))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        raise SystemExit(f"network error: {exc}") from exc
