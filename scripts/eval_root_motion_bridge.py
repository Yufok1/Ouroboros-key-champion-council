#!/usr/bin/env python
import argparse
import json
import math
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


def _shared_state(base_url):
    return (_env_read(base_url, "shared_state").get("shared_state") or {})


def _extract_state(base_url):
    shared = _shared_state(base_url)
    mounted = shared.get("mounted_character_runtime") if isinstance(shared.get("mounted_character_runtime"), dict) else {}
    runtime_state = mounted.get("runtime_state") if isinstance(mounted.get("runtime_state"), dict) else {}
    animation = mounted.get("animation_surface") if isinstance(mounted.get("animation_surface"), dict) else {}
    workbench = mounted.get("workbench_surface") if isinstance(mounted.get("workbench_surface"), dict) else {}
    position = (((runtime_state.get("position") or {}).get("world")) or {})
    root_motion = animation.get("root_motion") if isinstance(animation.get("root_motion"), dict) else {}
    return {
        "theater_mode": str(shared.get("theater_mode") or ""),
        "builder_active": bool(workbench.get("builder_active")),
        "display_scope": str(workbench.get("part_display_scope") or ""),
        "timeline_duration": float(workbench.get("timeline_duration") or 0.0),
        "timeline_displacement_mode": str(workbench.get("timeline_displacement_mode") or ""),
        "timeline_root_trajectory": workbench.get("timeline_root_trajectory"),
        "authored_clips": list(workbench.get("authored_clips") or []),
        "authored_clip_names": list(workbench.get("authored_clip_names") or []),
        "last_compiled_clip": str(workbench.get("last_compiled_clip") or ""),
        "position_world": {
            "x": float(position.get("x") or 0.0),
            "y": float(position.get("y") or 0.0),
            "z": float(position.get("z") or 0.0),
        },
        "grounded": bool(runtime_state.get("grounded")),
        "support_key": str(runtime_state.get("support_key") or ""),
        "animation": {
            "active_clip": str(animation.get("active_clip") or ""),
            "active_clip_raw": str(animation.get("active_clip_raw") or ""),
            "active_clip_source": str(animation.get("active_clip_source") or ""),
            "displacement_mode": str(animation.get("displacement_mode") or "in_place"),
            "source_motion_preset": str(animation.get("source_motion_preset") or ""),
            "paused": bool(animation.get("paused")),
            "loop_mode": str(animation.get("loop_mode") or ""),
            "speed": float(animation.get("speed") or 0.0),
            "override_active": bool(animation.get("override_active")),
            "root_motion": {
                "active": bool(root_motion.get("active")),
                "displacement_mode": str(root_motion.get("displacement_mode") or "in_place"),
                "trajectory_duration": float(root_motion.get("trajectory_duration") or 0.0),
                "trajectory_progress": float(root_motion.get("trajectory_progress") or 0.0),
                "loop_count": int(root_motion.get("loop_count") or 0),
                "sample_time": float(root_motion.get("sample_time") or 0.0),
                "sample_position": list(root_motion.get("sample_position") or []),
                "world_position": root_motion.get("world_position"),
                "yaw_deg": float(root_motion.get("yaw_deg") or 0.0),
                "space": str(root_motion.get("space") or ""),
                "reference": str(root_motion.get("reference") or ""),
            },
        },
    }


def _distance(a, b):
    return math.hypot(
        float((a or {}).get("x") or 0.0) - float((b or {}).get("x") or 0.0),
        float((a or {}).get("z") or 0.0) - float((b or {}).get("z") or 0.0),
    )


def _sleep(seconds):
    time.sleep(max(0.0, float(seconds)))


def _run_command(base_url, command, target="", actor="codex", pause=0.35):
    resp = _env_control(base_url, command, target, actor=actor)
    _sleep(pause)
    return resp


def _wait_for_state(base_url, predicate, timeout=3.0, interval=0.2):
    deadline = time.time() + max(0.1, float(timeout))
    last_state = {}
    while time.time() <= deadline:
        last_state = _extract_state(base_url)
        if predicate(last_state):
            return last_state
        _sleep(interval)
    return last_state


def _check(name, passed, details):
    return {"name": str(name), "passed": bool(passed), "details": details}


def _authored_clip_entry(state, clip_name):
    for clip in (state.get("authored_clips") or []):
        if str((clip or {}).get("name") or "") == str(clip_name or ""):
            return clip
    return {}


def _main():
    parser = argparse.ArgumentParser(description="Validate explicit root-motion bridge support for authored clips.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--actor", default="codex")
    parser.add_argument("--pause", type=float, default=0.4)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else Path("data") / f"root_motion_bridge_eval_{int(time.time())}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "generated_ts": int(time.time()),
        "checks": [],
        "baseline": {},
        "in_place_case": {},
        "root_motion_case": {},
        "summary": {},
    }

    _run_command(args.base_url, "set_theater_mode", "character", actor=args.actor, pause=args.pause)
    _run_command(args.base_url, "workbench_new_builder", json.dumps({"family": "humanoid_biped"}), actor=args.actor, pause=max(args.pause, 0.8))
    _run_command(args.base_url, "workbench_set_editing_mode", "pose", actor=args.actor, pause=args.pause)
    _run_command(args.base_url, "workbench_set_display_scope", json.dumps({"part_display_scope": "body"}), actor=args.actor, pause=args.pause)
    _run_command(args.base_url, "workbench_isolate_chain", "", actor=args.actor, pause=args.pause)
    _run_command(args.base_url, "workbench_clear_pose", json.dumps({"all": True}), actor=args.actor, pause=args.pause)
    _run_command(args.base_url, "workbench_reset_angles", "", actor=args.actor, pause=args.pause)

    baseline = _wait_for_state(
        args.base_url,
        lambda state: state.get("builder_active") and state.get("display_scope") == "body",
        timeout=max(6.0, args.pause * 14),
        interval=max(0.15, args.pause * 0.5),
    )
    report["baseline"] = baseline
    report["checks"].append(_check(
        "baseline_builder_active",
        baseline["builder_active"] and baseline["display_scope"] == "body",
        baseline,
    ))

    duration = max(0.6, float(baseline.get("timeline_duration") or 0.8))
    root_trajectory = {
        "space": "world",
        "reference": "support_frame",
        "samples": [
            {"time": round(duration * 0.5, 4), "position": [0.0, 0.0, 0.48], "yaw_deg": 4.0},
            {"time": round(duration, 4), "position": [0.08, 0.0, 0.96], "yaw_deg": 8.0},
        ],
    }

    try:
        _run_command(
            args.base_url,
            "workbench_set_motion_metadata",
            json.dumps({"displacement_mode": "in_place", "root_trajectory": None}),
            actor=args.actor,
            pause=args.pause,
        )
        in_place_metadata = _wait_for_state(
            args.base_url,
            lambda state: str(state.get("timeline_displacement_mode") or "") == "in_place" and state.get("timeline_root_trajectory") is None,
            timeout=max(3.0, args.pause * 8),
            interval=max(0.15, args.pause * 0.5),
        )
        in_place_clip_name = f"eval_in_place_{int(time.time() * 1000)}"
        _run_command(
            args.base_url,
            "workbench_compile_clip",
            json.dumps({"clip_name": in_place_clip_name, "duration": duration}),
            actor=args.actor,
            pause=args.pause,
        )
        in_place_compiled = _wait_for_state(
            args.base_url,
            lambda state: in_place_clip_name in (state.get("authored_clip_names") or []),
            timeout=max(3.0, args.pause * 8),
            interval=max(0.15, args.pause * 0.5),
        )
        in_place_start = _extract_state(args.base_url)
        _run_command(
            args.base_url,
            "workbench_play_authored_clip",
            json.dumps({"clip_name": in_place_clip_name, "loop": "once", "speed": 1.0, "fadeSeconds": 0.05}),
            actor=args.actor,
            pause=max(args.pause, 0.3),
        )
        in_place_play = _wait_for_state(
            args.base_url,
            lambda state: str((state.get("animation") or {}).get("active_clip") or "") == in_place_clip_name
            and bool((state.get("animation") or {}).get("override_active")),
            timeout=max(3.0, args.pause * 8),
            interval=max(0.15, args.pause * 0.5),
        )
        in_place_end = _wait_for_state(
            args.base_url,
            lambda state: not bool((state.get("animation") or {}).get("override_active")),
            timeout=max(4.0, duration + 2.0),
            interval=max(0.15, args.pause * 0.5),
        )
        in_place_distance = _distance(in_place_start["position_world"], in_place_end["position_world"])
        report["in_place_case"] = {
            "metadata": in_place_metadata,
            "compiled": in_place_compiled,
            "compiled_clip": _authored_clip_entry(in_place_compiled, in_place_clip_name),
            "start": in_place_start,
            "play": in_place_play,
            "end": in_place_end,
            "world_distance": in_place_distance,
        }
        report["checks"].append(_check(
            "in_place_clip_does_not_translate_runtime",
            in_place_distance < 0.08,
            {
                "world_distance": in_place_distance,
                "start": in_place_start["position_world"],
                "end": in_place_end["position_world"],
            },
        ))
        report["checks"].append(_check(
            "in_place_clip_reports_in_place_metadata",
            str(_authored_clip_entry(in_place_compiled, in_place_clip_name).get("displacement_mode") or "") == "in_place"
            and _authored_clip_entry(in_place_compiled, in_place_clip_name).get("root_trajectory") is None,
            _authored_clip_entry(in_place_compiled, in_place_clip_name),
        ))

        _run_command(
            args.base_url,
            "workbench_set_motion_metadata",
            json.dumps({"displacement_mode": "root_motion", "root_trajectory": root_trajectory}),
            actor=args.actor,
            pause=args.pause,
        )
        root_metadata = _wait_for_state(
            args.base_url,
            lambda state: str(state.get("timeline_displacement_mode") or "") == "root_motion"
            and isinstance(state.get("timeline_root_trajectory"), dict),
            timeout=max(3.0, args.pause * 8),
            interval=max(0.15, args.pause * 0.5),
        )
        root_clip_name = f"eval_root_motion_{int(time.time() * 1000)}"
        _run_command(
            args.base_url,
            "workbench_compile_clip",
            json.dumps({"clip_name": root_clip_name, "duration": duration}),
            actor=args.actor,
            pause=args.pause,
        )
        root_compiled = _wait_for_state(
            args.base_url,
            lambda state: root_clip_name in (state.get("authored_clip_names") or []),
            timeout=max(3.0, args.pause * 8),
            interval=max(0.15, args.pause * 0.5),
        )
        root_start = _extract_state(args.base_url)
        _run_command(
            args.base_url,
            "workbench_play_authored_clip",
            json.dumps({"clip_name": root_clip_name, "loop": "once", "speed": 1.0, "fadeSeconds": 0.05}),
            actor=args.actor,
            pause=max(args.pause, 0.3),
        )
        root_active = _wait_for_state(
            args.base_url,
            lambda state: str((state.get("animation") or {}).get("active_clip") or "") == root_clip_name
            and bool((((state.get("animation") or {}).get("root_motion")) or {}).get("active")),
            timeout=max(4.0, args.pause * 10),
            interval=max(0.15, args.pause * 0.5),
        )
        root_end = _wait_for_state(
            args.base_url,
            lambda state: not bool((state.get("animation") or {}).get("override_active")),
            timeout=max(5.0, duration + 2.5),
            interval=max(0.15, args.pause * 0.5),
        )
        root_distance = _distance(root_start["position_world"], root_end["position_world"])
        root_clip_metadata = _authored_clip_entry(root_compiled, root_clip_name)
        report["root_motion_case"] = {
            "metadata": root_metadata,
            "compiled": root_compiled,
            "compiled_clip": root_clip_metadata,
            "start": root_start,
            "active": root_active,
            "end": root_end,
            "world_distance": root_distance,
            "expected_distance": _distance({"x": 0.0, "z": 0.0}, {"x": 0.08, "z": 0.96}),
        }
        report["checks"].append(_check(
            "root_motion_clip_reports_root_motion_metadata",
            str(root_clip_metadata.get("displacement_mode") or "") == "root_motion"
            and isinstance(root_clip_metadata.get("root_trajectory"), dict),
            root_clip_metadata,
        ))
        report["checks"].append(_check(
            "root_motion_becomes_active_during_playback",
            bool((((root_active.get("animation") or {}).get("root_motion")) or {}).get("active"))
            and str((root_active.get("animation") or {}).get("displacement_mode") or "") == "root_motion",
            root_active.get("animation") or {},
        ))
        report["checks"].append(_check(
            "root_motion_translates_runtime",
            root_distance > 0.6,
            {
                "world_distance": root_distance,
                "start": root_start["position_world"],
                "end": root_end["position_world"],
            },
        ))
        report["checks"].append(_check(
            "root_motion_keeps_support_truth_alive",
            bool(root_end.get("grounded")) and bool(root_end.get("support_key")),
            {
                "grounded": root_end.get("grounded"),
                "support_key": root_end.get("support_key"),
                "position_world": root_end.get("position_world"),
            },
        ))
        report["checks"].append(_check(
            "root_motion_clears_after_once_clip_finishes",
            not bool((((root_end.get("animation") or {}).get("root_motion")) or {}).get("active")),
            root_end.get("animation") or {},
        ))
    finally:
        try:
            _run_command(
                args.base_url,
                "workbench_set_motion_metadata",
                json.dumps({"displacement_mode": "in_place", "root_trajectory": None}),
                actor=args.actor,
                pause=args.pause,
            )
        except Exception:
            pass
        try:
            _run_command(args.base_url, "character_stop_clip", "", actor=args.actor, pause=args.pause)
        except Exception:
            pass

    passed = sum(1 for check in report["checks"] if check["passed"])
    failed = len(report["checks"]) - passed
    report["summary"] = {
        "total_checks": len(report["checks"]),
        "passed": passed,
        "failed": failed,
        "failing_checks": [check["name"] for check in report["checks"] if not check["passed"]],
    }

    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(str(output_path))


if __name__ == "__main__":
    try:
        _main()
    except urllib.error.URLError as exc:
        raise SystemExit(f"network error: {exc}") from exc
