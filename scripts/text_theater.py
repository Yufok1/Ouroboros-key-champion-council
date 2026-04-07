import argparse
import colorsys
import json
import math
import os
import re
import shutil
import sys
import textwrap
import time
import urllib.error
import urllib.request

try:
    from PyDrawille import CanvasSurface as _PyDrawilleCanvasSurface
except Exception:
    _PyDrawilleCanvasSurface = None


ALT_SCREEN_ON = "\x1b[?1049h"
ALT_SCREEN_OFF = "\x1b[?1049l"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLEAR_SCREEN = "\x1b[2J\x1b[H"
FRAME_HOME = "\x1b[H\x1b[J"
RESET = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
CYAN = "\x1b[36m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
RED = "\x1b[31m"
MAGENTA = "\x1b[35m"
BLUE = "\x1b[34m"
GRAY = "\x1b[38;5;240m"
LIGHT_GRAY = "\x1b[38;5;250m"
ORANGE = "\x1b[38;5;214m"

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
HEX_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
RGB_COLOR_RE = re.compile(
    r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*([0-9.]+))?\s*\)",
    re.IGNORECASE,
)

PANE_SECTIONS = [
    ("theater", "Theater"),
    ("scene", "Scene"),
    ("render", "Render"),
    ("layout", "Layout"),
    ("docs", "Docs"),
    ("navigation", "Navigation"),
    ("panel", "Panel"),
    ("inspector", "Inspector"),
    ("operations", "Operations"),
    ("runtime", "Runtime"),
    ("workbench", "Workbench"),
    ("embodiment", "Embodiment"),
    ("balance", "Balance"),
    ("contacts", "Contacts"),
    ("settle", "Settle"),
    ("timeline", "Timeline"),
    ("corroboration", "Corroboration"),
    ("semantic", "Semantic"),
]

CONTACT_MARKERS = {
    "grounded": "●",
    "planted": "●",
    "sliding": "◐",
    "lifting": "◌",
    "airborne": "◌",
}

BRAILLE_DOT_BITS = {
    (0, 0): 0x01,
    (0, 1): 0x02,
    (0, 2): 0x04,
    (1, 0): 0x08,
    (1, 1): 0x10,
    (1, 2): 0x20,
    (0, 3): 0x40,
    (1, 3): 0x80,
}

try:
    TEXT_THEATER_PERSPECTIVE_SCALE = max(
        0.35,
        min(1.0, float(os.environ.get("TEXT_THEATER_PERSPECTIVE_SCALE", "1.0"))),
    )
except Exception:
    TEXT_THEATER_PERSPECTIVE_SCALE = 1.0


def _enable_vt_mode():
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def _configure_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _read_key_nonblocking():
    if os.name == "nt":
        try:
            import msvcrt

            if not msvcrt.kbhit():
                return None
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                extra = msvcrt.getwch()
                return f"special:{ord(extra)}"
            return key
        except Exception:
            return None
    return None


def _post_json(url, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _tool_response_text(response):
    content = (((response or {}).get("result") or {}).get("content") or [])
    if not content:
        return ""
    return str((content[0] or {}).get("text") or "")


def _load_tool_payload(base_url, tool_name, payload, timeout):
    response = _post_json(f"{base_url}/api/tool/{tool_name}", payload, timeout)
    text = _tool_response_text(response)
    if not text:
        raise RuntimeError(f"{tool_name} returned empty text")
    data = json.loads(text)
    cache_id = ""
    if isinstance(data, dict):
        cache_id = str(data.get("_cached") or data.get("cache_id") or "").strip()
    if cache_id:
        cached = _post_json(f"{base_url}/api/tool/get_cached", {"cache_id": cache_id}, timeout)
        cached_text = _tool_response_text(cached)
        if cached_text:
            data = json.loads(cached_text)
    return data


def _env_read(base_url, query, timeout):
    payload = _load_tool_payload(base_url, "env_read", {"query": query}, timeout)
    value = payload.get(query)
    if value is None:
        alias_map = {
            "live": "live_state",
        }
        alias_key = alias_map.get(str(query or "").strip().lower(), "")
        if alias_key:
            value = payload.get(alias_key)
    if value is None:
        raise RuntimeError(f"env_read({query!r}) did not include {query!r}")
    return value


def _env_read_optional(base_url, query, timeout):
    try:
        return _env_read(base_url, query, timeout)
    except Exception:
        return None


def _merge_live_camera_into_snapshot(snapshot, live_state):
    if not isinstance(snapshot, dict) or not isinstance(live_state, dict):
        return snapshot
    shared_state = live_state.get("shared_state") if isinstance(live_state.get("shared_state"), dict) else {}
    scene = shared_state.get("scene") if isinstance(shared_state.get("scene"), dict) else {}
    camera3d = scene.get("camera3d") if isinstance(scene.get("camera3d"), dict) else {}
    viewport = scene.get("viewport") if isinstance(scene.get("viewport"), dict) else {}
    if not camera3d:
        return snapshot
    next_snapshot = dict(snapshot)
    theater = snapshot.get("theater") if isinstance(snapshot.get("theater"), dict) else {}
    next_theater = dict(theater)
    camera = theater.get("camera") if isinstance(theater.get("camera"), dict) else {}
    next_camera = dict(camera)
    for key in ("mode", "distance", "azimuth", "polar", "position", "target"):
        value = camera3d.get(key)
        if value not in (None, "", {}):
            next_camera[key] = value
    if viewport:
        merged_viewport = dict(next_camera.get("viewport") or {})
        for key in ("width", "height"):
            value = viewport.get(key)
            if value not in (None, 0, 0.0, ""):
                merged_viewport[key] = value
        if merged_viewport:
            next_camera["viewport"] = merged_viewport
            width = float(merged_viewport.get("width") or 0.0)
            height = float(merged_viewport.get("height") or 0.0)
            if width > 0.0 and height > 0.0:
                next_camera["aspect"] = width / height
    next_theater["camera"] = next_camera
    next_snapshot["theater"] = next_theater
    stale_flags = snapshot.get("stale_flags") if isinstance(snapshot.get("stale_flags"), dict) else {}
    next_stale = dict(stale_flags)
    next_stale["mirror_lag"] = False
    next_snapshot["stale_flags"] = next_stale
    synced_at = live_state.get("synced_at")
    try:
        synced_ms = float(synced_at) * 1000.0
    except Exception:
        synced_ms = 0.0
    if synced_ms > 0.0:
        next_snapshot["snapshot_timestamp"] = max(float(snapshot.get("snapshot_timestamp") or 0.0), synced_ms)
    return next_snapshot


def _safe_json_lines(value, width):
    try:
        rendered = json.dumps(value, indent=2, sort_keys=True)
    except Exception:
        rendered = str(value)
    return _wrap_block(rendered, width)


def _wrap_block(text, width):
    width = max(20, int(width or 20))
    lines = []
    for raw_line in str(text or "").splitlines() or [""]:
        expanded = raw_line.expandtabs(2)
        if not expanded:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(expanded, width=width, replace_whitespace=False, drop_whitespace=False) or [""])
    return lines


def _pad_line(text, width):
    raw = str(text or "")
    visible = len(ANSI_RE.sub("", raw))
    if visible > width:
        out = []
        index = 0
        taken = 0
        saw_ansi = False
        while index < len(raw) and taken < width:
            if raw[index] == "\x1b":
                match = ANSI_RE.match(raw, index)
                if match:
                    out.append(match.group(0))
                    index = match.end()
                    saw_ansi = True
                    continue
            out.append(raw[index])
            index += 1
            taken += 1
        clipped = "".join(out)
        if saw_ansi and not clipped.endswith(RESET):
            clipped += RESET
        return clipped
    return raw + (" " * max(0, width - visible))


def _box(title, lines, width, height, color=CYAN):
    inner_width = max(1, width - 2)
    body_height = max(0, height - 2)
    header = f"{color}{BOLD}{title}{RESET}"
    top = "┌" + _pad_line(header, inner_width) + "┐"
    out = [top]
    normalized = list(lines or [])
    for idx in range(body_height):
        line = normalized[idx] if idx < len(normalized) else ""
        out.append("│" + _pad_line(line, inner_width) + "│")
    out.append("└" + ("─" * inner_width) + "┘")
    return out[:height] if height > 0 else []


def _vec3(value):
    if isinstance(value, dict):
        return (
            float(value.get("x", 0) or 0),
            float(value.get("y", 0) or 0),
            float(value.get("z", 0) or 0),
        )
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (float(value[0] or 0), float(value[1] or 0), float(value[2] or 0))
    return (0.0, 0.0, 0.0)


def _v_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _v_dot(a, b):
    return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])


def _v_cross(a, b):
    return (
        (a[1] * b[2]) - (a[2] * b[1]),
        (a[2] * b[0]) - (a[0] * b[2]),
        (a[0] * b[1]) - (a[1] * b[0]),
    )


def _v_len(a):
    return math.sqrt(max(0.0, _v_dot(a, a)))


def _v_norm(a, fallback=(0.0, 0.0, 1.0)):
    length = _v_len(a)
    if length <= 1e-6:
        return fallback
    return (a[0] / length, a[1] / length, a[2] / length)


def _clamp(value, low, high):
    return max(low, min(high, value))


def _parse_css_color(value, fallback=(200, 210, 220)):
    if isinstance(fallback, str):
        fallback = _parse_css_color(fallback, (200, 210, 220))
    text = str(value or "").strip()
    if not text:
        return fallback
    match = HEX_COLOR_RE.match(text)
    if match:
        digits = match.group(1)
        return (
            int(digits[0:2], 16),
            int(digits[2:4], 16),
            int(digits[4:6], 16),
        )
    match = RGB_COLOR_RE.match(text)
    if match:
        rgb = [int(match.group(index) or 0) for index in (1, 2, 3)]
        alpha = match.group(4)
        if alpha is not None:
            try:
                factor = _clamp(float(alpha), 0.0, 1.0)
                rgb = [int(round(channel * factor)) for channel in rgb]
            except Exception:
                pass
        return tuple(_clamp(channel, 0, 255) for channel in rgb)
    return fallback


def _style_from_color(value, fallback=(200, 210, 220), brightness=1.0, solid=False, min_saturation=0.88, target_lightness=0.52):
    r, g, b = _parse_css_color(value, fallback)
    if solid:
        rf, gf, bf = (channel / 255.0 for channel in (r, g, b))
        hue, lightness, saturation = colorsys.rgb_to_hls(rf, gf, bf)
        saturation = max(float(min_saturation or 0.0), saturation)
        if lightness > float(target_lightness or 0.52):
            lightness = float(target_lightness or 0.52)
        rf, gf, bf = colorsys.hls_to_rgb(hue, lightness, saturation)
        r, g, b = (
            _clamp(int(round(rf * 255)), 0, 255),
            _clamp(int(round(gf * 255)), 0, 255),
            _clamp(int(round(bf * 255)), 0, 255),
        )
    factor = max(0.0, float(brightness or 0.0))
    r = _clamp(int(round(r * factor)), 0, 255)
    g = _clamp(int(round(g * factor)), 0, 255)
    b = _clamp(int(round(b * factor)), 0, 255)
    return f"\x1b[38;2;{r};{g};{b}m"


def _v_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _v_scale(a, scalar):
    value = float(scalar or 0.0)
    return (a[0] * value, a[1] * value, a[2] * value)


def _ground_vec(a):
    return (a[0], 0.0, a[2])


def _angle_delta_degrees(a, b):
    delta = (float(a or 0.0) - float(b or 0.0) + 180.0) % 360.0 - 180.0
    return abs(delta)


def _yaw_vector(yaw_degrees):
    radians = math.radians(float(yaw_degrees or 0.0))
    return (math.sin(radians), 0.0, math.cos(radians))


def _yaw_from_vector(direction):
    planar = _v_norm(_ground_vec(direction), (0.0, 0.0, 1.0))
    return math.degrees(math.atan2(planar[0], planar[2]))


def _snapshot_focus_point(snapshot):
    render = snapshot.get("render") or {}
    guide = (render.get("workbench_stage_guide") or {}) if isinstance(render, dict) else {}
    runtime_world = ((((snapshot.get("runtime") or {}).get("runtime_state") or {}).get("position") or {}).get("world")) or {}
    guide_center = _vec3(guide.get("center")) if isinstance(guide, dict) else (0.0, 0.0, 0.0)
    if _v_len(guide_center) > 0.001:
        return guide_center
    if runtime_world:
        return _vec3(runtime_world)
    return _vec3((((snapshot.get("theater") or {}).get("camera")) or {}).get("target"))


def _bone_point_from_map(bone_map, *names):
    for name in names:
        key = str(name or "")
        if not key:
            continue
        bone = bone_map.get(key)
        if bone:
            return _vec3(bone.get("world_pos"))
    return None


def _estimate_body_heading(bone_map, origin, yaw_hint_degrees):
    runtime_forward = _v_norm(_yaw_vector(yaw_hint_degrees), (0.0, 0.0, 1.0))
    left_point = (
        _bone_point_from_map(bone_map, "shoulder_l", "upper_arm_l", "arm_l", "mixamorig:LeftShoulder", "mixamorig:LeftArm")
        or _bone_point_from_map(bone_map, "upper_leg_l", "thigh_l", "mixamorig:LeftUpLeg")
    )
    right_point = (
        _bone_point_from_map(bone_map, "shoulder_r", "upper_arm_r", "arm_r", "mixamorig:RightShoulder", "mixamorig:RightArm")
        or _bone_point_from_map(bone_map, "upper_leg_r", "thigh_r", "mixamorig:RightUpLeg")
    )
    up_anchor = (
        _bone_point_from_map(bone_map, "head", "neck", "chest", "spine", "mixamorig:Head", "mixamorig:Neck", "mixamorig:Spine2", "mixamorig:Spine")
        or _v_add(origin, (0.0, 1.0, 0.0))
    )
    up_axis = _v_norm(_v_sub(up_anchor, origin), (0.0, 1.0, 0.0))
    if left_point and right_point:
        right_axis = _v_norm(_v_sub(right_point, left_point), (1.0, 0.0, 0.0))
        candidate_a = _v_norm(_ground_vec(_v_cross(up_axis, right_axis)), runtime_forward)
        candidate_b = (-candidate_a[0], -candidate_a[1], -candidate_a[2])
        if _v_dot(candidate_b, runtime_forward) > _v_dot(candidate_a, runtime_forward):
            return candidate_b
        return candidate_a
    return runtime_forward


def _extract_motion_sample(snapshot):
    embodiment = snapshot.get("embodiment") or {}
    workbench = snapshot.get("workbench") or {}
    runtime = snapshot.get("runtime") or {}
    balance = snapshot.get("balance") or {}
    animation = (((runtime.get("surfaces") or {}).get("animation")) or {})
    bones = embodiment.get("bones") or []
    bone_map = {str(bone.get("id") or bone.get("name") or ""): bone for bone in bones}
    focus_point = _snapshot_focus_point(snapshot)
    origin = (
        _bone_point_from_map(bone_map, "hips", "pelvis", "root", "mixamorig:Hips")
        or focus_point
    )
    runtime_yaw = float((((runtime.get("runtime_state") or {}).get("facing") or {}).get("yaw_degrees")) or 0.0)
    forward = _estimate_body_heading(bone_map, origin, runtime_yaw)
    clip_name = str(
        animation.get("active_clip")
        or workbench.get("preview_clip")
        or workbench.get("last_motion_preset")
        or ""
    ).strip()
    return {
        "timestamp": float(snapshot.get("snapshot_timestamp") or 0.0),
        "origin": origin,
        "focus": focus_point,
        "com": _vec3(balance.get("com")),
        "forward": forward,
        "body_yaw_degrees": round(_yaw_from_vector(forward), 2),
        "runtime_yaw_degrees": round(runtime_yaw, 2),
        "turntable": bool(workbench.get("turntable")),
        "clip": clip_name,
        "locomotion_mode": str(animation.get("locomotion_mode") or "").strip(),
        "locomotion_speed": float(animation.get("locomotion_speed") or 0.0),
        "loop_mode": str(animation.get("loop_mode") or "").strip(),
        "speed": float(animation.get("speed") or 0.0),
    }


def _append_motion_history(history, snapshot, limit=18):
    sample = _extract_motion_sample(snapshot)
    items = list(history or [])
    if not items:
        return [sample]
    previous = items[-1]
    same_clip = str(previous.get("clip") or "") == str(sample.get("clip") or "")
    root_delta = _v_len(_v_sub(sample["origin"], previous["origin"]))
    com_delta = _v_len(_v_sub(sample["com"], previous["com"]))
    yaw_delta = _angle_delta_degrees(sample.get("body_yaw_degrees"), previous.get("body_yaw_degrees"))
    if same_clip and root_delta < 0.003 and com_delta < 0.003 and yaw_delta < 0.5:
        items[-1] = sample
        return items[-limit:]
    items.append(sample)
    return items[-limit:]


def _camera_basis(snapshot):
    camera = (((snapshot.get("theater") or {}).get("camera")) or {})
    position = _vec3(camera.get("position"))
    target = _vec3(camera.get("target"))
    up = _v_norm(_vec3(camera.get("up")), (0.0, 1.0, 0.0))
    forward = _v_norm(_v_sub(target, position), (0.0, 0.0, -1.0))
    right = _v_norm(_v_cross(forward, up), (1.0, 0.0, 0.0))
    true_up = _v_norm(_v_cross(right, forward), (0.0, 1.0, 0.0))
    return position, right, true_up, forward


def _camera_basis_from_pose(position, target, up=(0.0, 1.0, 0.0)):
    position = _vec3(position)
    target = _vec3(target)
    up = _v_norm(_vec3(up), (0.0, 1.0, 0.0))
    forward = _v_norm(_v_sub(target, position), (0.0, 0.0, -1.0))
    right = _v_norm(_v_cross(forward, up), (1.0, 0.0, 0.0))
    true_up = _v_norm(_v_cross(right, forward), (0.0, 1.0, 0.0))
    return position, right, true_up, forward


def _make_canvas(width, height, fill=" "):
    return [[{"char": fill, "priority": 0, "style": ""} for _ in range(max(1, width))] for _ in range(max(1, height))]


def _canvas_put(canvas, x, y, char, priority=1, style=""):
    if not canvas:
        return
    h = len(canvas)
    w = len(canvas[0])
    if 0 <= x < w and 0 <= y < h:
        current = canvas[y][x]
        if int(priority) >= int(current.get("priority", 0)):
            canvas[y][x] = {"char": char, "priority": int(priority), "style": style or ""}


def _bresenham(x0, y0, x1, y1):
    points = []
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = err * 2
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return points


def _draw_line(canvas, start, end, char, priority=1, style=""):
    for x, y in _bresenham(int(start[0]), int(start[1]), int(end[0]), int(end[1])):
        _canvas_put(canvas, x, y, char, priority=priority, style=style)


def _sample_segment_points(start, end, count):
    steps = max(2, int(count or 2))
    points = []
    for idx in range(steps + 1):
        t = idx / float(steps)
        points.append((
            start[0] + ((end[0] - start[0]) * t),
            start[1] + ((end[1] - start[1]) * t),
            start[2] + ((end[2] - start[2]) * t),
        ))
    return points


def _line_char(start, end):
    dx = int(end[0]) - int(start[0])
    dy = int(end[1]) - int(start[1])
    abs_dx = abs(dx)
    abs_dy = abs(dy)
    if abs_dx == 0 and abs_dy == 0:
        return "•"
    if abs_dx >= max(1, int(abs_dy * 1.6)):
        return "─"
    if abs_dy >= max(1, int(abs_dx * 1.6)):
        return "│"
    return "╲" if (dx * dy) > 0 else "╱"


def _depth_char(depth, near_depth, far_depth, dense=False):
    if depth is None:
        return "•" if dense else "·"
    span = max(1e-6, float(far_depth or 0.0) - float(near_depth or 0.0))
    t = _clamp((float(depth) - float(near_depth or 0.0)) / span, 0.0, 1.0)
    if dense:
        if t <= 0.22:
            return "●"
        if t <= 0.55:
            return "•"
        return "·"
    if t <= 0.22:
        return "•"
    if t <= 0.62:
        return "·"
    return "."


def _segment_thickness_band(radius_start, radius_end):
    avg_radius = max(0.0, (float(radius_start or 0.0) + float(radius_end or 0.0)) * 0.5)
    if avg_radius >= 0.09:
        return 2
    if avg_radius >= 0.045:
        return 1
    return 0


def _sample_circle_points(center, radius, count):
    cx, cy, cz = center
    total = max(16, int(count or 16))
    points = []
    for idx in range(total):
        theta = (float(idx) / float(total)) * math.tau
        points.append((
            cx + (math.cos(theta) * radius),
            cy,
            cz + (math.sin(theta) * radius),
        ))
    return points


def _canvas_lines(canvas):
    lines = []
    for row in canvas:
        parts = []
        for cell in row:
            style = str((cell or {}).get("style") or "")
            char = str((cell or {}).get("char") or " ")
            if style:
                parts.append(style + char + RESET)
            else:
                parts.append(char)
        lines.append("".join(parts).rstrip())
    return lines


def _make_braille_canvas(width, height):
    canvas = {
        "width": max(1, int(width or 1)),
        "height": max(1, int(height or 1)),
        "backend": "native",
        "surface": None,
        "cells": [
            [
                {"mask": 0, "style": "", "priority": 0, "weight": 0}
                for _ in range(max(1, int(width or 1)))
            ]
            for _ in range(max(1, int(height or 1)))
        ],
    }
    if _PyDrawilleCanvasSurface is not None:
        try:
            canvas["surface"] = _PyDrawilleCanvasSurface(
                width=canvas["width"] * 2,
                height=canvas["height"] * 4,
            )
            canvas["backend"] = "pydrawille"
        except Exception:
            canvas["surface"] = None
            canvas["backend"] = "native"
    return canvas


def _braille_put(canvas, x, y, priority=1, style=""):
    if not canvas:
        return
    width = int(canvas.get("width") or 0)
    height = int(canvas.get("height") or 0)
    sub_w = width * 2
    sub_h = height * 4
    ix = int(round(x))
    iy = int(round(y))
    if ix < 0 or iy < 0 or ix >= sub_w or iy >= sub_h:
        return
    cell_x = ix // 2
    cell_y = iy // 4
    bit = BRAILLE_DOT_BITS.get((ix % 2, iy % 4))
    if bit is None:
        return
    cell = canvas["cells"][cell_y][cell_x]
    cell["mask"] |= bit
    cell["weight"] = int(cell.get("weight", 0)) + 1
    surface = canvas.get("surface")
    if surface is not None:
        try:
            surface.set_pixel(ix, iy, True)
        except Exception:
            canvas["surface"] = None
            canvas["backend"] = "native"
    if int(priority) >= int(cell.get("priority", 0)):
        cell["priority"] = int(priority)
        if style:
            cell["style"] = style


def _braille_cluster(canvas, x, y, priority=1, style="", radius=0):
    radius = max(0, int(radius or 0))
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if (dx * dx) + (dy * dy) > max(1, radius * radius + radius):
                continue
            _braille_put(canvas, x + dx, y + dy, priority=priority, style=style)


def _braille_lines(canvas):
    raw_rows = None
    surface = canvas.get("surface")
    if surface is not None:
        try:
            raw_rows = list(surface.dump_lines())
        except Exception:
            canvas["surface"] = None
            canvas["backend"] = "native"
            raw_rows = None
    rows = []
    for row_index, row in enumerate(canvas.get("cells") or []):
        raw = raw_rows[row_index] if raw_rows and row_index < len(raw_rows) else ""
        parts = []
        for col_index, cell in enumerate(row):
            mask = int((cell or {}).get("mask") or 0)
            style = str((cell or {}).get("style") or "")
            char = raw[col_index] if col_index < len(raw) else (" " if mask <= 0 else chr(0x2800 + mask))
            if style and char != " ":
                parts.append(style + char + RESET)
            else:
                parts.append(char)
        rows.append("".join(parts).rstrip())
    return rows


def _braille_backend_name(canvas):
    return str((canvas or {}).get("backend") or "native")


def _fit_projected_points(points, width, height, padding=2):
    valid = [point for point in points if point is not None]
    if not valid:
        return {}
    xs = [point[0] for point in valid]
    ys = [point[1] for point in valid]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    if abs(max_x - min_x) < 1e-6:
        min_x -= 1
        max_x += 1
    if abs(max_y - min_y) < 1e-6:
        min_y -= 1
        max_y += 1
    usable_w = max(1, width - (padding * 2))
    usable_h = max(1, height - (padding * 2))
    scale_x = usable_w / (max_x - min_x)
    scale_y = usable_h / (max_y - min_y)
    scale = min(scale_x, scale_y)
    center_x = (min_x + max_x) * 0.5
    center_y = (min_y + max_y) * 0.5

    def mapper(point):
        px = int(round(((point[0] - center_x) * scale) + (width * 0.5)))
        py = int(round((height * 0.5) - ((point[1] - center_y) * scale)))
        return (px, py)

    return {"map": mapper, "bounds": (min_x, max_x, min_y, max_y)}


def _bounds3(points):
    valid = [point for point in (points or []) if point is not None]
    if not valid:
        return {
            "center": (0.0, 0.0, 0.0),
            "size": (1.0, 1.0, 1.0),
            "radius": 1.0,
            "min": (-0.5, -0.5, -0.5),
            "max": (0.5, 0.5, 0.5),
        }
    xs = [point[0] for point in valid]
    ys = [point[1] for point in valid]
    zs = [point[2] for point in valid]
    min_point = (min(xs), min(ys), min(zs))
    max_point = (max(xs), max(ys), max(zs))
    center = (
        (min_point[0] + max_point[0]) * 0.5,
        (min_point[1] + max_point[1]) * 0.5,
        (min_point[2] + max_point[2]) * 0.5,
    )
    size = (
        max(1.0, max_point[0] - min_point[0]),
        max(1.0, max_point[1] - min_point[1]),
        max(1.0, max_point[2] - min_point[2]),
    )
    radius = max(
        _v_len(_v_sub(point, center))
        for point in valid
    )
    return {
        "center": center,
        "size": size,
        "radius": max(1.0, radius),
        "min": min_point,
        "max": max_point,
    }


def _percentile(values, fraction):
    rows = sorted(float(value or 0.0) for value in (values or []))
    if not rows:
        return 0.0
    if len(rows) == 1:
        return rows[0]
    position = _clamp(float(fraction or 0.0), 0.0, 1.0) * float(len(rows) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return rows[lower]
    mix = position - float(lower)
    return rows[lower] + ((rows[upper] - rows[lower]) * mix)


def _make_ndc_mapper(width, height, padding=4, points=None):
    usable_w = max(1, int(width or 1) - (padding * 2))
    usable_h = max(1, int(height or 1) - (padding * 2))
    if points:
        valid = [point for point in points if point is not None]
        abs_x = [abs(float(point[0] or 0.0)) for point in valid]
        abs_y = [abs(float(point[1] or 0.0)) for point in valid]
        bound_x = max(0.7, _percentile(abs_x, 0.9))
        bound_y = max(0.6, _percentile(abs_y, 0.88))
        scale = max(1.0, min(usable_w / (bound_x * 2.0), usable_h / (bound_y * 2.0)))
        center_y = float(height or 1) * 0.56
    else:
        scale = max(1.0, min(usable_w, usable_h) * 0.5)
        center_y = float(height or 1) * 0.5
    center_x = float(width or 1) * 0.5

    def mapper(point):
        px = int(round(center_x + (float(point[0] or 0.0) * scale)))
        py = int(round(center_y - (float(point[1] or 0.0) * scale)))
        return (px, py)

    return {"map": mapper, "bounds": (-1.0, 1.0, -1.0, 1.0)}


def _make_fixed_ndc_mapper(width, height, padding=4, target_aspect=None):
    usable_w = max(1, int(width or 1) - (padding * 2))
    usable_h = max(1, int(height or 1) - (padding * 2))
    viewport_w = float(usable_w)
    viewport_h = float(usable_h)
    aspect = float(target_aspect or 0.0)
    if aspect > 0.01:
        current_aspect = viewport_w / max(1.0, viewport_h)
        if current_aspect > aspect:
            viewport_w = viewport_h * aspect
        else:
            viewport_h = viewport_w / aspect
    viewport_w *= float(TEXT_THEATER_PERSPECTIVE_SCALE or 1.0)
    viewport_h *= float(TEXT_THEATER_PERSPECTIVE_SCALE or 1.0)
    offset_x = float(padding) + ((usable_w - viewport_w) * 0.5)
    offset_y = float(padding) + ((usable_h - viewport_h) * 0.5)

    def mapper(point):
        px = offset_x + ((_clamp(float(point[0] or 0.0), -1.0, 1.0) + 1.0) * 0.5 * viewport_w)
        py = offset_y + ((1.0 - ((_clamp(float(point[1] or 0.0), -1.0, 1.0) + 1.0) * 0.5)) * viewport_h)
        return (px, py)

    return {"map": mapper, "bounds": (-1.0, 1.0, -1.0, 1.0)}


def _project_perspective(point, basis, camera_meta=None):
    position, right, up, forward = basis
    relative = _v_sub(point, position)
    depth = _v_dot(relative, forward)
    if depth <= 0.05:
        return None
    camera = camera_meta if isinstance(camera_meta, dict) else {}
    fov_degrees = float(camera.get("fov_degrees") or 50.0)
    aspect = float(camera.get("aspect") or 1.0)
    if aspect <= 0.01:
        viewport = camera.get("viewport") or {}
        width = float((viewport.get("width") or 0) or 0)
        height = float((viewport.get("height") or 0) or 0)
        aspect = (width / height) if width > 0 and height > 0 else 1.0
    tan_half = math.tan(math.radians(max(1.0, min(179.0, fov_degrees))) * 0.5)
    tan_half = tan_half if tan_half > 1e-6 else math.tan(math.radians(50.0) * 0.5)
    x = (_v_dot(relative, right) / depth) / (tan_half * max(0.2, aspect))
    y = (_v_dot(relative, up) / depth) / tan_half
    if x < -1.02 or x > 1.02 or y < -1.02 or y > 1.02:
        return None
    return (x, y)


def _project_radius_to_subcells(radius_world, depth, render_height, camera_meta=None):
    if depth is None or depth <= 0.05:
        return 0
    camera = camera_meta if isinstance(camera_meta, dict) else {}
    fov_degrees = float(camera.get("fov_degrees") or 50.0)
    tan_half = math.tan(math.radians(max(1.0, min(179.0, fov_degrees))) * 0.5)
    tan_half = tan_half if tan_half > 1e-6 else math.tan(math.radians(50.0) * 0.5)
    screen_radius = (max(0.0, float(radius_world or 0.0)) / depth) / tan_half
    screen_radius *= max(1.0, float(render_height or 1.0) * 0.40)
    return int(_clamp(round(screen_radius), 0, 3))


def _perspective_segment_sample_count(mapped_start, mapped_end, projected_radius=0):
    dx = float((mapped_end or (0.0, 0.0))[0] - (mapped_start or (0.0, 0.0))[0])
    dy = float((mapped_end or (0.0, 0.0))[1] - (mapped_start or (0.0, 0.0))[1])
    length = math.sqrt((dx * dx) + (dy * dy))
    radius = max(0.0, float(projected_radius or 0.0))
    target = 32.0 + (length * 2.8) + (radius * 10.0)
    return int(_clamp(round(target), 44, 168))


def _body_stamp_offsets(radius, phase=0):
    radius = max(0, int(radius or 0))
    if radius <= 0:
        return [(0, 0, "body_core", 4)]
    if radius == 1:
        patterns = [
            [(0, 0, "body_core", 5), (-1, -1, "body_highlight", 2), (1, 1, "body_shadow", 2)],
            [(0, 0, "body_core", 5), (0, -1, "body_highlight", 2), (0, 1, "body_shadow", 2)],
            [(0, 0, "body_core", 5), (-1, 0, "body_highlight", 2), (1, 0, "body_shadow", 2)],
            [(0, 0, "body_core", 5), (1, -1, "body_highlight", 1), (-1, 1, "body_shadow", 1)],
        ]
        return patterns[int(phase or 0) % len(patterns)]
    offsets = [(0, 0, "body_core", 6)]
    offsets.extend([
        (-1, -1, "body_highlight", 2),
        (-1, 0, "body_highlight", 2),
        (0, -1, "body_highlight", 2),
        (1, 1, "body_shadow", 2),
        (1, 0, "body_shadow", 2),
        (0, 1, "body_shadow", 2),
    ])
    if (int(phase or 0) % 2) == 0:
        offsets.extend([(1, -1, "body_core", 1), (-1, 1, "body_core", 1)])
    else:
        offsets.extend([(1, -1, "body_shadow", 1), (-1, 1, "body_highlight", 1)])
    return offsets


def _body_style_key_for_depth(depth, near_depth, far_depth, slot):
    span = max(1e-6, float(far_depth or 0.0) - float(near_depth or 0.0))
    t = _clamp((float(depth or 0.0) - float(near_depth or 0.0)) / span, 0.0, 1.0)
    base = "body_core"
    if t <= 0.28:
        base = "body_front"
    elif t >= 0.72:
        base = "body_back"
    if slot == "body_highlight":
        return "body_front"
    if slot == "body_shadow":
        return "body_back" if base != "body_front" else "body_core"
    return base


def _orthographic_stamp_radius(radius_world):
    radius = float(radius_world or 0.0)
    if radius >= 0.075:
        return 2
    if radius >= 0.032:
        return 1
    return 0


def _landmark_kind(bone_id):
    text = str(bone_id or "").strip().lower()
    if not text:
        return ""
    if text == "head" or text.endswith(":head") or text.endswith("_head"):
        return "head"
    if "hand" in text or text.startswith("wrist") or text.endswith("_wrist"):
        return "hand"
    if "foot" in text:
        return "foot"
    return ""


def _depth_buffer_put(buffer, x, y, depth, style, priority=1):
    ix = int(round(x))
    iy = int(round(y))
    key = (ix, iy)
    current = buffer.get(key)
    sample = {
        "depth": float(depth if depth is not None else 1e9),
        "style": style or "",
        "priority": int(priority or 0),
    }
    if current is None:
        buffer[key] = sample
        return
    if sample["depth"] < current["depth"] - 1e-6:
        buffer[key] = sample
        return
    if abs(sample["depth"] - current["depth"]) <= 1e-6 and sample["priority"] >= current["priority"]:
        buffer[key] = sample


def _project_top(point):
    return (point[0], point[2])


def _project_front(point):
    return (point[0], point[1])


def _companion_camera(snapshot, model, mode):
    points = []
    for segment in model.get("segments") or []:
        points.extend([segment.get("start"), segment.get("end")])
    for patch in model.get("contact_patches") or []:
        points.extend(patch.get("points") or [])
    points.extend(model.get("support_polygon") or [])
    for marker in model.get("markers") or []:
        points.append(marker.get("point"))
    points.append(model.get("focus_point"))
    bounds = _bounds3(points)
    center = bounds["center"]
    motion = model.get("motion") or _extract_motion_sample(snapshot)
    forward = _v_norm(_ground_vec(motion.get("forward") or (0.0, 0.0, 1.0)), (0.0, 0.0, 1.0))
    right = _v_norm(_v_cross(forward, (0.0, 1.0, 0.0)), (1.0, 0.0, 0.0))
    radius = max(
        10.0,
        float(bounds["radius"]) * 1.7,
        _v_len(bounds["size"]) * 0.9,
    )
    lift = max(5.0, radius * 0.52)
    if mode == "profile":
        offset = _v_add(_v_scale(right, radius * 1.08), (0.0, lift, 0.0))
    else:
        oblique = _v_norm(_v_add(_v_scale(right, 0.86), _v_scale(forward, 0.62)), right)
        offset = _v_add(_v_scale(oblique, radius * 1.04), (0.0, lift, 0.0))
    position = _v_add(center, offset)
    return {
        "basis": _camera_basis_from_pose(position, center),
        "target": center,
        "position": position,
        "radius": radius,
        "bounds": bounds,
    }


def _collect_render_model(snapshot):
    embodiment = snapshot.get("embodiment") or {}
    balance = snapshot.get("balance") or {}
    contacts = snapshot.get("contacts") or []
    scene = snapshot.get("scene") or {}
    render = snapshot.get("render") or {}
    workbench = snapshot.get("workbench") or {}
    bones = embodiment.get("bones") or []
    connections = embodiment.get("connections") or []
    bone_map = {str(bone.get("id") or bone.get("name") or ""): bone for bone in bones}
    blueprint_bones = ((((workbench.get("builder_blueprint") or {}).get("bones")) or []))
    blueprint_map = {}
    for entry in blueprint_bones:
        if not isinstance(entry, dict):
            continue
        bone_id = str(entry.get("id") or "").strip()
        if not bone_id:
            continue
        profile = entry.get("radius_profile") or [0.05, 0.04]
        if not isinstance(profile, list):
            profile = [0.05, 0.04]
        while len(profile) < 2:
            profile.append(profile[-1] if profile else 0.04)
        blueprint_map[bone_id] = {
            "radius_start": max(0.004, float(profile[0] or 0.04)),
            "radius_end": max(0.004, float(profile[1] or profile[0] or 0.04)),
        }
    guide = (render.get("workbench_stage_guide") or {}) if isinstance(render, dict) else {}
    guide_palette = (guide.get("palette") or {}) if isinstance(guide, dict) else {}
    selection_palette = (
        (render.get("selection_palette") or {})
        if isinstance(render, dict)
        else {}
    ) or (workbench.get("selection_visual_state") or {})
    focus_visual = (
        (scene.get("focus_object_visual") or {})
        if isinstance(scene, dict)
        else {}
    ) or ((render.get("focus_object_visual") or {}) if isinstance(render, dict) else {})

    body_base_color = "#d2a074"
    body_style = _style_from_color(
        body_base_color,
        "#d2a074",
        1.0,
        solid=True,
        min_saturation=0.92,
        target_lightness=0.54,
    )
    body_front_style = _style_from_color(
        body_base_color,
        "#d2a074",
        1.1,
        solid=True,
        min_saturation=0.92,
        target_lightness=0.62,
    )
    body_back_style = _style_from_color(
        body_base_color,
        "#d2a074",
        0.82,
        solid=True,
        min_saturation=0.84,
        target_lightness=0.34,
    )
    body_edge_style = _style_from_color(
        body_base_color,
        "#d2a074",
        0.9,
        solid=True,
        min_saturation=0.86,
        target_lightness=0.44,
    )
    bone_line_style = _style_from_color(
        body_base_color,
        "#7b6043",
        0.52,
        solid=True,
        min_saturation=0.62,
        target_lightness=0.26,
    )
    support_trace_style = _style_from_color(
        body_base_color,
        "#d2a074",
        0.86,
        solid=True,
        min_saturation=0.84,
        target_lightness=0.42,
    )
    posed_style = _style_from_color(
        selection_palette.get("hover_color") or selection_palette.get("selected_color") or "#ffb44d",
        "#ffb44d",
        1.0,
        solid=True,
        min_saturation=0.92,
        target_lightness=0.5,
    )
    selected_style = _style_from_color(
        selection_palette.get("selected_color") or selection_palette.get("hover_color") or "#ffa726",
        "#ffa726",
        1.0,
        solid=True,
        min_saturation=0.95,
        target_lightness=0.48,
    )
    support_style = _style_from_color(
        body_base_color,
        "#d2a074",
        0.94,
        solid=True,
        min_saturation=0.88,
        target_lightness=0.48,
    )
    airborne_style = support_style
    sliding_style = support_style
    minor_grid_style = _style_from_color(
        guide_palette.get("grid_minor") or "#203544",
        "#203544",
        1.55,
        solid=True,
        min_saturation=0.72,
        target_lightness=0.28,
    )
    major_grid_style = _style_from_color(
        guide_palette.get("grid_major") or "#4fe9d0",
        "#4fe9d0",
        1.0,
        solid=True,
        min_saturation=0.92,
        target_lightness=0.42,
    )
    crosshair_style = _style_from_color(
        guide_palette.get("crosshair") or guide_palette.get("halo") or "#8bf3de",
        "#8bf3de",
        1.0,
        solid=True,
        min_saturation=0.9,
        target_lightness=0.52,
    )
    frame_style = _style_from_color(
        guide_palette.get("frame") or guide_palette.get("inner_ring") or "#75c6ff",
        "#75c6ff",
        1.0,
        solid=True,
        min_saturation=0.9,
        target_lightness=0.46,
    )
    floor_minor_style = _style_from_color(
        "#6f756f",
        "#6f756f",
        0.7,
        solid=True,
        min_saturation=0.1,
        target_lightness=0.34,
    )
    floor_major_style = _style_from_color(
        "#988a74",
        "#988a74",
        0.82,
        solid=True,
        min_saturation=0.18,
        target_lightness=0.44,
    )
    halo_style = _style_from_color(
        guide_palette.get("halo") or "#6fe9d9",
        "#6fe9d9",
        1.0,
        solid=True,
        min_saturation=0.82,
        target_lightness=0.38,
    )
    pad_fill_style = _style_from_color(
        guide_palette.get("pad_fill") or "#0d141d",
        "#0d141d",
        1.4,
        solid=True,
        min_saturation=0.45,
        target_lightness=0.13,
    )
    inner_ring_style = _style_from_color(
        guide_palette.get("inner_ring") or "#5ac8ff",
        "#5ac8ff",
        1.0,
        solid=True,
        min_saturation=0.88,
        target_lightness=0.44,
    )
    focus_style = _style_from_color(
        focus_visual.get("edge") or guide_palette.get("crosshair") or "#7dd3fc",
        "#7dd3fc",
        1.0,
        solid=True,
        min_saturation=0.92,
        target_lightness=0.5,
    )
    com_style = _style_from_color("#ff00b7", "#ff00b7", 1.0, solid=True, min_saturation=0.98, target_lightness=0.5)
    heading_style = _style_from_color(
        selection_palette.get("selected_color") or "#ffd000",
        "#ffd000",
        1.0,
        solid=True,
        min_saturation=0.96,
        target_lightness=0.48,
    )
    motion_style = _style_from_color(
        guide_palette.get("halo") or "#00d7ff",
        "#00d7ff",
        1.0,
        solid=True,
        min_saturation=0.92,
        target_lightness=0.46,
    )

    support_y = 0.0
    try:
        support_y = float((((workbench.get("motion_diagnostics") or {}).get("support_surface") or {}).get("support_y")) or 0.0)
    except Exception:
        support_y = 0.0
    try:
        guide_floor = float(guide.get("floor_y") or support_y)
        support_y = guide_floor
    except Exception:
        pass
    focus_point = _snapshot_focus_point(snapshot)

    scene_bounds = scene.get("bounds") or {}
    min_bound = scene_bounds.get("min") or {}
    max_bound = scene_bounds.get("max") or {}
    guide_grid_span = float(guide.get("grid_span") or 0.0) if isinstance(guide, dict) else 0.0
    if guide_grid_span > 0.1:
        half_span = guide_grid_span * 0.5
        min_x = focus_point[0] - half_span
        max_x = focus_point[0] + half_span
        min_z = focus_point[2] - half_span
        max_z = focus_point[2] + half_span
    else:
        min_x = float(min_bound.get("x", focus_point[0] - 8) or (focus_point[0] - 8))
        max_x = float(max_bound.get("x", focus_point[0] + 8) or (focus_point[0] + 8))
        min_z = float(min_bound.get("z", focus_point[2] - 8) or (focus_point[2] - 8))
        max_z = float(max_bound.get("z", focus_point[2] + 8) or (focus_point[2] + 8))
        span_x = max(4.0, abs(max_x - min_x))
        span_z = max(4.0, abs(max_z - min_z))
        expand_x = max(2.0, span_x * 0.15)
        expand_z = max(2.0, span_z * 0.15)
        min_x -= expand_x
        max_x += expand_x
        min_z -= expand_z
        max_z += expand_z

    span_x = max(4.0, abs(max_x - min_x))
    span_z = max(4.0, abs(max_z - min_z))
    motion = _extract_motion_sample(snapshot)
    heading_length = max(1.6, min(6.8, (guide_grid_span * 0.24) if guide_grid_span > 0.1 else (max(span_x, span_z) * 0.18)))
    heading_origin = (motion["origin"][0], support_y, motion["origin"][2])
    heading_forward = _v_norm(_ground_vec(motion["forward"]), (0.0, 0.0, 1.0))
    heading_tip = _v_add(heading_origin, _v_scale(heading_forward, heading_length))
    floor_points = []
    pad_fill_points = []
    guide_segments = []
    guide_rings = []
    guide_triangles = []
    guide_grid_lines = []

    if guide_grid_span > 0.1:
        half_span = guide_grid_span * 0.5
        center_x = focus_point[0]
        center_z = focus_point[2]
        grid_divisions = max(10, int(guide.get("grid_divisions") or 20))
        grid_step = guide_grid_span / float(grid_divisions)
        for xi in range(grid_divisions + 1):
            x_cursor = (center_x - half_span) + (grid_step * xi)
            is_edge_x = xi == 0 or xi == grid_divisions
            is_major_x = (xi % 5) == 0
            for zi in range(grid_divisions + 1):
                z_cursor = (center_z - half_span) + (grid_step * zi)
                is_edge_z = zi == 0 or zi == grid_divisions
                is_corner = is_edge_x and is_edge_z
                is_major = is_major_x or ((zi % 5) == 0)
                floor_points.append({
                    "point": (x_cursor, support_y, z_cursor),
                    "style": frame_style if is_corner else (major_grid_style if is_major else minor_grid_style),
                    "priority": 2 if is_corner else (1 if is_major else 0),
                    "radius": 0,
                })
        crosshair_extent = float(guide.get("crosshair_extent") or half_span)
        crosshair_extent = max(0.0, min(crosshair_extent, half_span))
        if crosshair_extent > 0.1:
            guide_segments.extend([
                {
                    "start": (center_x - crosshair_extent, support_y, center_z),
                    "end": (center_x + crosshair_extent, support_y, center_z),
                    "style": crosshair_style,
                    "priority": 1,
                    "samples": 44,
                },
                {
                    "start": (center_x, support_y, center_z - crosshair_extent),
                    "end": (center_x, support_y, center_z + crosshair_extent),
                    "style": crosshair_style,
                    "priority": 1,
                    "samples": 44,
                },
            ])
        seen_ring_radii = set()
        for radius_key, style in (
            ("pad_radius", frame_style),
            ("inner_ring_outer_radius", major_grid_style),
            ("inner_ring_inner_radius", minor_grid_style),
            ("halo_inner_radius", minor_grid_style),
        ):
            radius = float(guide.get(radius_key) or 0.0)
            if radius <= 0.1:
                continue
            radius_token = round(radius, 3)
            if radius_token in seen_ring_radii:
                continue
            guide_rings.append({
                "center": (center_x, support_y, center_z),
                "radius": radius,
                "style": style,
                "priority": 1,
                "samples": 88 if not guide_rings else 72,
            })
            seen_ring_radii.add(radius_token)
            if len(guide_rings) >= 2:
                break
    else:
        grid_step = max(1.75, round(max(span_x, span_z) / 12.0, 2))
        x_cursor = math.floor(min_x / grid_step) * grid_step
        last_x = math.ceil(max_x / grid_step) * grid_step
        last_z = math.ceil(max_z / grid_step) * grid_step
        while x_cursor <= last_x + 1e-6:
            is_edge_x = abs(x_cursor - (math.floor(min_x / grid_step) * grid_step)) < 1e-6 or abs(x_cursor - last_x) < 1e-6
            x_index = int(round((x_cursor - (math.floor(min_x / grid_step) * grid_step)) / grid_step))
            is_major_x = (x_index % 4) == 0
            z_cursor = math.floor(min_z / grid_step) * grid_step
            while z_cursor <= last_z + 1e-6:
                z_index = int(round((z_cursor - (math.floor(min_z / grid_step) * grid_step)) / grid_step))
                is_edge_z = abs(z_cursor - (math.floor(min_z / grid_step) * grid_step)) < 1e-6 or abs(z_cursor - last_z) < 1e-6
                is_corner = is_edge_x and is_edge_z
                is_major = is_major_x or ((z_index % 4) == 0)
                floor_points.append({
                    "point": (x_cursor, support_y, z_cursor),
                    "style": frame_style if is_corner else (major_grid_style if is_major else minor_grid_style),
                    "priority": 2 if is_corner else (1 if is_major else 0),
                    "radius": 0,
                })
                z_cursor += grid_step
            x_cursor += grid_step

    segments = []
    projected_points = []
    for start_id, end_id in connections:
        a = bone_map.get(str(start_id))
        b = bone_map.get(str(end_id))
        if not a or not b:
            continue
        pa = _vec3(a.get("world_pos"))
        pb = _vec3(b.get("world_pos"))
        dims = blueprint_map.get(str(start_id)) or {"radius_start": 0.03, "radius_end": 0.025}
        segments.append({
            "start": pa,
            "end": pb,
            "radius_start": float(dims.get("radius_start") or 0.03),
            "radius_end": float(dims.get("radius_end") or 0.025),
            "bone_id": str(start_id),
            "child_id": str(end_id),
        })
        projected_points.extend([pa, pb])

    contact_states = {str(row.get("joint") or ""): row for row in contacts}
    markers = []
    for bone in bones:
        point = _vec3(bone.get("world_pos"))
        bone_id = str(bone.get("id") or bone.get("name") or "")
        state = contact_states.get(bone_id)
        landmark = _landmark_kind(bone_id)
        label = "•"
        if state:
            label = CONTACT_MARKERS.get(str(state.get("state") or "").lower(), "o")
        elif landmark == "head":
            label = "●"
        elif landmark == "hand":
            label = "◦"
        marker_style = selected_style if bool(bone.get("selected")) else (posed_style if bool(bone.get("posed")) else body_style)
        marker_radius = 0
        marker_priority = 5 if landmark else 4
        if landmark == "head":
            marker_style = body_front_style
            marker_radius = 2
            marker_priority = 7
        elif landmark == "hand":
            marker_style = posed_style if bool(bone.get("posed") or bone.get("selected")) else body_front_style
            marker_radius = 1
            marker_priority = 6
        markers.append({
            "id": bone_id,
            "point": point,
            "char": label,
            "kind": landmark,
            "posed": bool(bone.get("posed")),
            "selected": bool(bone.get("selected")),
            "style": marker_style,
            "radius": marker_radius,
            "priority": marker_priority,
        })

    support_polygon = []
    for row in balance.get("support_polygon") or []:
        support_polygon.append((float(row.get("x") or 0), support_y, float(row.get("z") or 0)))
    projected_points.extend(support_polygon)

    contact_patches = []
    diagnostic_contacts = (((workbench.get("motion_diagnostics") or {}).get("contacts")) or [])
    for row in diagnostic_contacts:
        patch = ((row or {}).get("contact_patch")) or {}
        footprint_world = patch.get("footprint_world") or []
        points = [_vec3(point) for point in footprint_world if isinstance(point, dict)]
        if len(points) >= 3:
            contact_patches.append({
                "points": points,
                "style": support_style if row.get("supporting") else posed_style,
                "priority": 4 if row.get("supporting") else 3,
            })
            projected_points.extend(points)

    com = _vec3(balance.get("com"))
    projected_points.append(com)
    projected_points.append(heading_origin)
    projected_points.append(heading_tip)
    projected_points.append(focus_point)
    for row in floor_points + pad_fill_points:
        projected_points.append(row["point"])
    for row in guide_segments + guide_triangles + guide_grid_lines:
        projected_points.extend([row["start"], row["end"]])
    for row in guide_rings:
        projected_points.extend(_sample_circle_points(row["center"], row["radius"], row["samples"]))

    objects = []
    for index, obj in enumerate(scene.get("focus_neighborhood") or []):
        point = _vec3(obj.get("position"))
        objects.append({
            "char": "·",
            "label": str(obj.get("label") or obj.get("id") or obj.get("kind") or f"object_{index + 1}"),
            "point": point,
            "distance": obj.get("distance"),
            "style": _style_from_color(
                obj.get("color") or ((obj.get("colors") or {}).get("edge")) or "#66b8ff",
                "#66b8ff",
                1.0,
            ),
        })
        projected_points.append(point)

    perspective_points = [com, heading_origin, heading_tip, focus_point]
    perspective_points.extend(support_polygon)
    for segment in segments:
        perspective_points.extend([segment["start"], segment["end"]])
    for patch in contact_patches:
        perspective_points.extend(patch.get("points") or [])
    for marker in markers:
        perspective_points.append(marker["point"])
    for obj in objects:
        perspective_points.append(obj["point"])

    return {
        "segments": segments,
        "markers": markers,
        "support_polygon": support_polygon,
        "contact_patches": contact_patches,
        "com": com,
        "focus_point": focus_point,
        "motion": motion,
        "heading_origin": heading_origin,
        "heading_length": heading_length,
        "heading_tip": heading_tip,
        "objects": objects,
        "floor_points": floor_points,
        "pad_fill_points": pad_fill_points,
        "guide_segments": guide_segments,
        "guide_triangles": guide_triangles,
        "guide_grid_lines": guide_grid_lines,
        "guide_rings": guide_rings,
        "points": projected_points,
        "perspective_points": perspective_points,
        "support_y": support_y,
        "styles": {
            "body": body_style,
            "body_core": body_style,
            "body_front": body_front_style,
            "body_back": body_back_style,
            "body_highlight": body_front_style,
            "body_shadow": body_back_style,
            "body_edge": body_edge_style,
            "bone_line": bone_line_style,
            "posed": posed_style,
            "selected": selected_style,
            "support": support_style,
            "support_trace": support_trace_style,
            "sliding": sliding_style,
            "airborne": airborne_style,
            "floor_minor": floor_minor_style,
            "floor_major": floor_major_style,
            "com": com_style,
            "focus": focus_style,
            "heading": heading_style,
            "motion": motion_style,
        },
    }


def _render_projection(snapshot, width, height, mode, history=None):
    width = max(20, width)
    height = max(8, height)
    model = _collect_render_model(snapshot)
    motion = model.get("motion") or {}
    legend = []
    if mode == "perspective":
        legend.append("Perspective · fixed camera/stage/body projection")
        object_bits = [f"· {obj['label']}" for obj in model["objects"][:4]]
        if object_bits:
            legend.append("Objects: " + " | ".join(object_bits))
    elif mode == "quarter":
        legend.append("Quarter view · companion orbit")
    elif mode == "profile":
        legend.append("Profile view · companion orbit")
    elif mode == "top":
        legend.append("Top view · paired body/floor projection")
    else:
        legend.append("Front view · paired body/floor projection")
    scene_height = max(4, height - len(legend))
    use_cell_canvas = False
    if use_cell_canvas:
        canvas = _make_canvas(width, scene_height)
        render_width = width
        render_height = scene_height
        backend_name = "cell"
    else:
        canvas = _make_braille_canvas(width, scene_height)
        render_width = width * 2
        render_height = scene_height * 4
        backend_name = _braille_backend_name(canvas)

    camera_meta = {}
    if mode in {"perspective", "quarter", "profile"}:
        camera_meta = dict((((snapshot.get("theater") or {}).get("camera")) or {}))
        if mode == "perspective":
            basis = _camera_basis(snapshot)
            target_aspect = float(camera_meta.get("aspect") or 1.0)
        else:
            companion = _companion_camera(snapshot, model, mode)
            basis = companion["basis"]
            target_aspect = float(render_width) / max(1.0, float(render_height))
            camera_meta["aspect"] = target_aspect
        project = lambda point: _project_perspective(point, basis, camera_meta)
        mapper_meta = _make_fixed_ndc_mapper(
            render_width,
            render_height,
            padding=1,
            target_aspect=target_aspect,
        )
        depth_basis = basis
        depth_values = []
        for point in model.get("perspective_points") or []:
            try:
                depth = _v_dot(_v_sub(point, depth_basis[0]), depth_basis[3])
            except Exception:
                depth = None
            if depth is not None and depth > 0.05:
                depth_values.append(depth)
        near_depth = _percentile(depth_values, 0.16) if depth_values else 1.0
        far_depth = _percentile(depth_values, 0.92) if depth_values else max(near_depth + 1.0, 4.0)
    elif mode == "top":
        project = _project_top
        projected = []
        for point in model["points"]:
            coords = project(point)
            if coords is not None:
                projected.append(coords)
        mapper_meta = _fit_projected_points(projected, render_width, render_height, padding=4)
        depth_basis = None
        near_depth = 0.0
        far_depth = 1.0
    else:
        project = _project_front
        projected = []
        for point in model["points"]:
            coords = project(point)
            if coords is not None:
                projected.append(coords)
        mapper_meta = _fit_projected_points(projected, render_width, render_height, padding=4)
        depth_basis = None
        near_depth = 0.0
        far_depth = 1.0
    mapper = mapper_meta.get("map") if mapper_meta else None
    if not mapper:
        return ["No renderable scene data"]

    def point_depth(point):
        if depth_basis is None or point is None:
            return None
        try:
            return _v_dot(_v_sub(point, depth_basis[0]), depth_basis[3])
        except Exception:
            return None

    def put_mark(x, y, char, priority=1, style="", radius=0):
        if use_cell_canvas:
            radius = max(0, int(radius or 0))
            if radius <= 0:
                _canvas_put(canvas, int(x), int(y), char, priority=priority, style=style)
                return
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if (dx * dx) + (dy * dy) > max(1, radius * radius + radius):
                        continue
                    _canvas_put(canvas, int(x + dx), int(y + dy), char, priority=priority, style=style)
        elif radius > 0:
            _braille_cluster(canvas, x, y, priority=priority, style=style, radius=radius)
        else:
            _braille_put(canvas, x, y, priority=priority, style=style)

    perspective_body_layer = {}

    if mode != "perspective" and not use_cell_canvas:
        for row in model["pad_fill_points"]:
            coords = project(row["point"])
            if coords is None:
                continue
            x, y = mapper(coords)
            _braille_cluster(
                canvas,
                x,
                y,
                priority=int(row.get("priority", 0)),
                style=row.get("style") or GRAY,
                radius=1,
            )

    for index, row in enumerate(model["floor_points"]):
        coords = project(row["point"])
        if coords is None:
            continue
        x, y = mapper(coords)
        row_style = row.get("style") or GRAY
        if mode not in {"perspective", "quarter", "profile"}:
            row_style = (
                model["styles"]["floor_major"]
                if int(row.get("priority", 0)) >= 1
                else model["styles"]["floor_minor"]
            )
        if mode in {"quarter", "profile"} and int(row.get("priority", 0)) <= 0:
            continue
        put_mark(
            x,
            y,
            ".",
            priority=int(row.get("priority", 1)),
            style=row_style,
            radius=int(row.get("radius", 0)) if not use_cell_canvas else 0,
        )

    if mode in {"perspective", "quarter", "profile"} and not use_cell_canvas:
        for ring in model["guide_rings"]:
            for point in _sample_circle_points(ring["center"], ring["radius"], ring["samples"]):
                coords = project(point)
                if coords is None:
                    continue
                x, y = mapper(coords)
                _braille_put(
                    canvas,
                    x,
                    y,
                    priority=int(ring.get("priority", 1)),
                    style=ring.get("style") or model["styles"]["floor_major"],
                )
        for guide_row in model["guide_segments"]:
            for point in _sample_segment_points(guide_row["start"], guide_row["end"], guide_row["samples"]):
                coords = project(point)
                if coords is None:
                    continue
                x, y = mapper(coords)
                _braille_put(
                    canvas,
                    x,
                    y,
                    priority=int(guide_row.get("priority", 1)),
                    style=guide_row.get("style") or model["styles"]["floor_major"],
                )

    if mode not in {"perspective", "quarter", "profile"} and not use_cell_canvas:
        for guide_row in model["guide_grid_lines"]:
            for point in _sample_segment_points(guide_row["start"], guide_row["end"], guide_row["samples"]):
                coords = project(point)
                if coords is None:
                    continue
                x, y = mapper(coords)
                _braille_put(
                    canvas,
                    x,
                    y,
                    priority=int(guide_row.get("priority", 1)),
                    style=guide_row.get("style") or CYAN,
                )

        for ring in model["guide_rings"]:
            for point in _sample_circle_points(ring["center"], ring["radius"], ring["samples"]):
                coords = project(point)
                if coords is None:
                    continue
                x, y = mapper(coords)
                _braille_put(
                    canvas,
                    x,
                    y,
                    priority=int(ring.get("priority", 2)),
                    style=ring.get("style") or CYAN,
                )

        for guide_row in model["guide_segments"] + model["guide_triangles"]:
            for point in _sample_segment_points(guide_row["start"], guide_row["end"], guide_row["samples"]):
                coords = project(point)
                if coords is None:
                    continue
                x, y = mapper(coords)
                _braille_put(
                    canvas,
                    x,
                    y,
                    priority=int(guide_row.get("priority", 2)),
                    style=guide_row.get("style") or CYAN,
                )

    recent_history = list(history or [])
    if mode not in {"perspective", "quarter", "profile"} and recent_history:
        recent_history = recent_history[-8:]
        for idx, sample in enumerate(recent_history[:-1]):
            factor = float(idx + 1) / float(max(1, len(recent_history)))
            heading_style = _style_from_color(
                "#00d7ff",
                "#00d7ff",
                0.24 + (0.46 * factor),
                solid=True,
                min_saturation=0.9,
                target_lightness=0.42,
            )
            root_style = _style_from_color(
                "#ffd000",
                "#ffd000",
                0.2 + (0.42 * factor),
                solid=True,
                min_saturation=0.92,
                target_lightness=0.44,
            )
            com_style = _style_from_color(
                "#ff00b7",
                "#ff00b7",
                0.22 + (0.4 * factor),
                solid=True,
                min_saturation=0.96,
                target_lightness=0.46,
            )
            origin = sample.get("origin")
            com_point = sample.get("com")
            forward = sample.get("forward")
            if origin and forward:
                floor_origin = (origin[0], float(model.get("support_y") or 0.0), origin[2])
                floor_forward = _v_norm(_ground_vec(forward), (0.0, 0.0, 1.0))
                ray_end = _v_add(
                    floor_origin,
                    _v_scale(floor_forward, float(model.get("heading_length") or 2.4) * (0.8 + (0.12 * factor))),
                )
                start_coords = project(floor_origin)
                end_coords = project(ray_end)
                if start_coords is not None and end_coords is not None and use_cell_canvas:
                    for point in _sample_segment_points(floor_origin, ray_end, 18):
                        coords = project(point)
                        if coords is None:
                            continue
                        x, y = mapper(coords)
                        put_mark(x, y, "·", priority=2, style=heading_style)
                else:
                    for point in _sample_segment_points(floor_origin, ray_end, 18):
                        coords = project(point)
                        if coords is None:
                            continue
                        x, y = mapper(coords)
                        put_mark(x, y, "·", priority=2, style=heading_style)
            if origin:
                floor_origin = (origin[0], float(model.get("support_y") or 0.0), origin[2])
                coords = project(floor_origin)
                if coords is not None:
                    x, y = mapper(coords)
                    put_mark(x, y, "·", priority=2, style=root_style, radius=0)
            if com_point:
                coords = project(com_point)
                if coords is not None:
                    x, y = mapper(coords)
                    put_mark(x, y, "·", priority=2, style=com_style, radius=0)

    if len(model["support_polygon"]) >= 2:
        for idx in range(len(model["support_polygon"])):
            start = model["support_polygon"][idx]
            end = model["support_polygon"][(idx + 1) % len(model["support_polygon"])]
            start_coords = project(start)
            end_coords = project(end)
            if start_coords is None or end_coords is None:
                continue
            support_trace_style = (
                model["styles"]["body_edge"]
                if mode in {"perspective", "quarter", "profile"}
                else model["styles"]["support_trace"]
            )
            if use_cell_canvas:
                for point in _sample_segment_points(start, end, 18):
                    coords = project(point)
                    if coords is None:
                        continue
                    x, y = mapper(coords)
                    put_mark(x, y, "·", priority=3, style=support_trace_style)
            else:
                for point in _sample_segment_points(start, end, 20):
                    coords = project(point)
                    if coords is None:
                        continue
                    x, y = mapper(coords)
                    _braille_put(canvas, x, y, priority=2, style=support_trace_style)

    if mode not in {"perspective", "quarter", "profile"}:
        for patch in model["contact_patches"]:
            points = patch.get("points") or []
            for idx in range(len(points)):
                start = points[idx]
                end = points[(idx + 1) % len(points)]
                start_coords = project(start)
                end_coords = project(end)
                if start_coords is None or end_coords is None:
                    continue
                if use_cell_canvas:
                    for point in _sample_segment_points(start, end, 16):
                        coords = project(point)
                        if coords is None:
                            continue
                        x, y = mapper(coords)
                        put_mark(
                            x,
                            y,
                            "·",
                            priority=max(2, int(patch.get("priority", 4)) - 1),
                            style=model["styles"]["support_trace"],
                        )
                else:
                    for point in _sample_segment_points(start, end, 18):
                        coords = project(point)
                        if coords is None:
                            continue
                        x, y = mapper(coords)
                        _braille_put(
                            canvas,
                            x,
                            y,
                            priority=max(2, int(patch.get("priority", 4)) - 1),
                            style=model["styles"]["support_trace"],
                        )

    perspective_bone_layer = {}
    for segment in model["segments"]:
        start = segment["start"]
        end = segment["end"]
        if use_cell_canvas:
            segment_style = model["styles"]["body"]
            start_coords = project(start)
            end_coords = project(end)
            if start_coords is None or end_coords is None:
                continue
            mapped_start = mapper(start_coords)
            mapped_end = mapper(end_coords)
            normal_x = 0.0
            normal_y = 0.0
            dir_x = float(mapped_end[0] - mapped_start[0])
            dir_y = float(mapped_end[1] - mapped_start[1])
            dir_len = math.sqrt((dir_x * dir_x) + (dir_y * dir_y))
            if dir_len > 1e-6:
                normal_x = (-dir_y / dir_len)
                normal_y = (dir_x / dir_len)
            thickness = _segment_thickness_band(segment.get("radius_start"), segment.get("radius_end"))
            sample_count = 18 if thickness <= 0 else (22 if thickness == 1 else 28)
            for point in _sample_segment_points(start, end, sample_count):
                coords = project(point)
                if coords is None:
                    continue
                x, y = mapper(coords)
                depth_char = _depth_char(point_depth(point), near_depth, far_depth, dense=thickness > 0)
                put_mark(x, y, depth_char, priority=3, style=segment_style)
                if thickness >= 1 and dir_len > 1e-6:
                    put_mark(x + normal_x, y + normal_y, depth_char, priority=3, style=segment_style)
                    put_mark(x - normal_x, y - normal_y, depth_char, priority=3, style=segment_style)
                if thickness >= 2 and dir_len > 1e-6:
                    put_mark(x + (normal_x * 2), y + (normal_y * 2), depth_char, priority=2, style=segment_style)
                    put_mark(x - (normal_x * 2), y - (normal_y * 2), depth_char, priority=2, style=segment_style)
        else:
            if mode in {"perspective", "quarter", "profile"}:
                start_coords = project(start)
                end_coords = project(end)
                if start_coords is None or end_coords is None:
                    continue
                mapped_start = mapper(start_coords)
                mapped_end = mapper(end_coords)
                start_depth = point_depth(start)
                end_depth = point_depth(end)
                projected_radius = max(
                    _project_radius_to_subcells(float(segment.get("radius_start") or 0.02), start_depth, render_height, camera_meta),
                    _project_radius_to_subcells(float(segment.get("radius_end") or 0.02), end_depth, render_height, camera_meta),
                )
                sample_count = _perspective_segment_sample_count(mapped_start, mapped_end, projected_radius)
                for idx, point in enumerate(_sample_segment_points(start, end, sample_count)):
                    coords = project(point)
                    if coords is None:
                        continue
                    x, y = mapper(coords)
                    depth = point_depth(point)
                    if depth is None or depth <= 0.05:
                        continue
                    _depth_buffer_put(
                        perspective_bone_layer,
                        x,
                        y,
                        depth + 0.001,
                        model["styles"]["bone_line"],
                        priority=1,
                    )
                    t = float(idx) / float(max(1, sample_count))
                    radius_world = float(segment.get("radius_start") or 0.02) + (
                        (float(segment.get("radius_end") or 0.02) - float(segment.get("radius_start") or 0.02)) * t
                    )
                    radius = _project_radius_to_subcells(radius_world, depth, render_height, camera_meta)
                    if projected_radius >= 2 or radius_world >= 0.055:
                        radius = max(1, radius)
                    radius = int(_clamp(radius, 0, 2))
                    for dx, dy, style_slot, priority in _body_stamp_offsets(radius, idx):
                        style_key = _body_style_key_for_depth(depth, near_depth, far_depth, style_slot)
                        _depth_buffer_put(
                            perspective_body_layer,
                            x + dx,
                            y + dy,
                            depth + ((abs(dx) + abs(dy)) * 0.0005),
                            model["styles"][style_key],
                            priority=priority,
                        )
                continue
            sample_count = 28
            for idx, point in enumerate(_sample_segment_points(start, end, sample_count)):
                coords = project(point)
                if coords is None:
                    continue
                x, y = mapper(coords)
                _braille_put(canvas, x, y, priority=1, style=model["styles"]["bone_line"])
                t = float(idx) / float(max(1, sample_count))
                radius_world = float(segment.get("radius_start") or 0.02) + (
                    (float(segment.get("radius_end") or 0.02) - float(segment.get("radius_start") or 0.02)) * t
                )
                radius = _orthographic_stamp_radius(radius_world)
                for dx, dy, style_slot, priority in _body_stamp_offsets(radius, idx):
                    style_key = "body_core" if style_slot == "body_core" else "body_edge"
                    _braille_put(canvas, x + dx, y + dy, priority=priority, style=model["styles"][style_key])

    if mode in {"perspective", "quarter", "profile"} and not use_cell_canvas:
        for (x, y), sample in sorted(
            perspective_bone_layer.items(),
            key=lambda item: (item[1].get("depth", 1e9), item[1].get("priority", 0)),
            reverse=True,
        ):
            _braille_put(
                canvas,
                x,
                y,
                priority=int(sample.get("priority", 1)),
                style=sample.get("style") or model["styles"]["bone_line"],
            )
        for (x, y), sample in sorted(
            perspective_body_layer.items(),
            key=lambda item: (item[1].get("depth", 1e9), item[1].get("priority", 0)),
            reverse=True,
        ):
            _braille_put(
                canvas,
                x,
                y,
                priority=int(sample.get("priority", 3)),
                style=sample.get("style") or model["styles"]["body"],
            )
        for patch in model["contact_patches"]:
            points = patch.get("points") or []
            for idx in range(len(points)):
                start = points[idx]
                end = points[(idx + 1) % len(points)]
                for point in _sample_segment_points(start, end, 20):
                    coords = project(point)
                    if coords is None:
                        continue
                    x, y = mapper(coords)
                    _braille_put(
                        canvas,
                        x,
                        y,
                        priority=max(4, int(patch.get("priority", 4))),
                        style=model["styles"]["body_edge"],
                    )

    heading_tip_coords = project(model["heading_tip"])
    current_origin_coords = project(model.get("heading_origin"))

    for obj in ([] if mode != "perspective" else model["objects"]):
        coords = project(obj["point"])
        if coords is None:
            continue
        x, y = mapper(coords)
        put_mark(x, y, "·", priority=4, style=obj.get("style") or BLUE, radius=0)

    for marker in model["markers"]:
        coords = project(marker.get("point"))
        if coords is None:
            continue
        x, y = mapper(coords)
        marker_priority = int(marker.get("priority", 5))
        marker_style = marker.get("style") or model["styles"]["body_front"]
        marker_radius = int(marker.get("radius", 0))
        put_mark(
            x,
            y,
            str(marker.get("char") or "•"),
            priority=marker_priority,
            style=marker_style,
            radius=marker_radius,
        )
        if str(marker.get("kind") or "") == "head" and marker_radius > 0:
            offset = 1 if use_cell_canvas else 2
            put_mark(
                x,
                y - offset,
                "·",
                priority=max(1, marker_priority - 1),
                style=model["styles"]["body_highlight"],
                radius=max(0, marker_radius - 1),
            )

    lines = _canvas_lines(canvas) if use_cell_canvas else _braille_lines(canvas)
    return lines[:scene_height] + legend


def _motion_status_line(snapshot):
    theater = snapshot.get("theater") or {}
    camera = theater.get("camera") or {}
    motion = _extract_motion_sample(snapshot)
    clip = motion.get("clip") or "none"
    locomotion_mode = motion.get("locomotion_mode") or "-"
    locomotion_speed = float(motion.get("locomotion_speed") or 0.0)
    return (
        f"motion turntable={str(bool(motion.get('turntable'))).lower()} "
        f"body_yaw={float(motion.get('body_yaw_degrees') or 0.0):.1f}° "
        f"runtime_yaw={float(motion.get('runtime_yaw_degrees') or 0.0):.1f}° "
        f"clip={clip} loop={motion.get('loop_mode') or '-'} speed={float(motion.get('speed') or 0.0):.2f} "
        f"locomotion={locomotion_mode}@{locomotion_speed:.2f} "
        f"cam dist={float(camera.get('distance') or 0.0):.2f} "
        f"az={float(camera.get('azimuth') or 0.0):.2f} pol={float(camera.get('polar') or 0.0):.2f} "
        f"fov={float(camera.get('fov_degrees') or 0.0):.1f} aspect={float(camera.get('aspect') or 0.0):.2f}"
    )


def _compact_status_lines(snapshot, width):
    balance = snapshot.get("balance") or {}
    runtime = snapshot.get("runtime") or {}
    theater = snapshot.get("theater") or {}
    lines = [
        f"focus={((theater.get('focus') or {}).get('id') or 'none')} phase={balance.get('support_phase', 'unknown')} risk={balance.get('stability_risk', '?')} grounded={runtime.get('grounded', '?')} bundle={snapshot.get('bundle_version', '?')}",
        _motion_status_line(snapshot),
        "keys: q quit | d diagnostics | tab cycle diag | 1 render | 2 theater | 3 embodiment | 4 snapshot | 5 split",
    ]
    return _wrap_block("\n".join(lines), width)


def _section_lines(snapshot, section_key, width):
    if section_key == "theater":
        theater = snapshot.get("theater") or {}
        camera = theater.get("camera") or {}
        focus = theater.get("focus") or {}
        rows = [
            f"mode={theater.get('mode', '')} visual_mode={theater.get('visual_mode', '')}",
            f"focus kind={focus.get('kind', '')} id={focus.get('id', '')} class={focus.get('target_class', '')}",
            f"camera mode={camera.get('mode', '')} dist={camera.get('distance', 0)} az={camera.get('azimuth', 0)} pol={camera.get('polar', 0)}",
            f"camera pos={camera.get('position', {})}",
            f"camera target={camera.get('target', {})}",
            f"camera forward={camera.get('forward', {})} up={camera.get('up', {})}",
        ]
        return _wrap_block("\n".join(rows), width)
    if section_key == "scene":
        scene = snapshot.get("scene") or {}
        rows = [
            f"object_count={scene.get('object_count', 0)} focus_object_key={scene.get('focus_object_key', '')}",
            f"bounds={scene.get('bounds', {})}",
            f"focus_object_visual={scene.get('focus_object_visual', {})}",
        ]
        nearby = scene.get("focus_neighborhood") or []
        if nearby:
            rows.append("nearby:")
            for row in nearby[:8]:
                rows.append(
                    f"  {row.get('label', row.get('object_key', '?'))} "
                    f"key={row.get('object_key', '')} dist={row.get('distance', 0)} "
                    f"pos={row.get('position', {})}"
                )
        return _wrap_block("\n".join(rows), width)
    if section_key == "operations":
        operations = snapshot.get("operations") or {}
        recent = operations.get("recent") or operations.get("recent_actions") or operations.get("actions") or []
        rows = []
        if recent:
            for row in recent[:10]:
                rows.append(
                    f"{row.get('tool', row.get('kind', 'op'))} actor={row.get('actor', '')} "
                    f"target={row.get('target', '')} preview={row.get('preview', row.get('summary', ''))}"
                )
        if not rows:
            return ["No recent operations"]
        return _wrap_block("\n".join(rows), width)
    if section_key == "runtime":
        runtime = snapshot.get("runtime") or {}
        surfaces = runtime.get("surfaces") or {}
        rows = [
            f"enabled={runtime.get('enabled', False)} mode={runtime.get('mode', '')} behavior={runtime.get('behavior', '')} activity={runtime.get('activity', '')}",
            f"grounded={runtime.get('grounded', False)} support_key={runtime.get('support_key', '')} support_kind={runtime.get('support_kind', '')}",
            f"camera_binding={runtime.get('camera_binding', '')} object_key={runtime.get('object_key', '')}",
            f"surface_keys={', '.join(sorted(surfaces.keys())) if surfaces else 'none'}",
        ]
        return _wrap_block("\n".join(rows), width)
    if section_key == "workbench":
        workbench = snapshot.get("workbench") or {}
        gizmo = workbench.get("gizmo") or {}
        rows = [
            f"subject_mode={workbench.get('subject_mode', '')} editing_mode={workbench.get('editing_mode', '')} turntable={workbench.get('turntable', False)}",
            f"primary={workbench.get('primary_bone_id', '')} hover={workbench.get('hover_bone_id', '')} isolate={workbench.get('isolated_chain', '')}",
            f"selected={workbench.get('selected_bone_ids', [])}",
            f"posed={workbench.get('posed_bone_ids', [])}",
            f"gizmo mode={gizmo.get('mode', '')} space={gizmo.get('space', '')} active={gizmo.get('active', False)} attached={gizmo.get('attached', False)}",
            f"preview clip={workbench.get('preview_clip', '')} loop={workbench.get('preview_loop', '')} speed={workbench.get('preview_speed', 0)} paused={workbench.get('preview_paused', False)}",
            f"motion_preset_count={len(workbench.get('motion_preset_catalog') or [])} load_field_enabled={workbench.get('load_field_enabled', False)}",
        ]
        return _wrap_block("\n".join(rows), width)
    if section_key == "embodiment":
        embodiment = snapshot.get("embodiment") or {}
        rows = [
            f"family={embodiment.get('family', '')} builder_active={embodiment.get('builder_active', False)} scaffold_visible={embodiment.get('scaffold_visible', False)}",
            f"selected={embodiment.get('selected_bone_ids', [])}",
            f"posed={embodiment.get('posed_bone_ids', [])}",
            f"isolated_chain={embodiment.get('isolated_chain', '')} selected_chain={embodiment.get('selected_chain_bone_ids', [])}",
            f"bone_count={len(embodiment.get('bones') or [])} connection_count={len(embodiment.get('connections') or [])}",
        ]
        return _wrap_block("\n".join(rows), width)
    if section_key == "balance":
        balance = snapshot.get("balance") or {}
        rows = [
            f"phase={balance.get('support_phase', 'unknown')} risk={balance.get('stability_risk', 0)} margin={balance.get('stability_margin', 0)} inside_polygon={balance.get('inside_polygon', False)}",
            f"dominant_side={balance.get('dominant_side', 'balanced')} supporting={balance.get('supporting_joint_ids', [])}",
            f"projected_com={balance.get('projected_com', {})} support_polygon={balance.get('support_polygon', [])}",
            f"alerts={balance.get('alert_ids', [])}",
        ]
        return _wrap_block("\n".join(rows), width)
    if section_key == "contacts":
        contacts = (snapshot.get("contacts") or [])
        rows = []
        for row in contacts:
            rows.append(
                f"{row.get('joint', '?')}: {row.get('state', '?')} gap {row.get('gap', 0)}"
                + (" support" if row.get("supporting") else "")
            )
        return rows or ["No contacts"]
    if section_key == "settle":
        settle = snapshot.get("settle") or {}
        rows = [
            f"active={settle.get('active', False)} strategy={settle.get('strategy', '')} severity={settle.get('severity', '')}",
            f"frame_count={settle.get('frame_count', 0)} duration={settle.get('duration', 0)}",
        ]
        return _wrap_block("\n".join(rows), width)
    if section_key == "timeline":
        timeline = snapshot.get("timeline") or {}
        rows = [
            f"cursor={timeline.get('cursor', 0)} duration={timeline.get('duration', 0)}",
            f"key_pose_count={timeline.get('key_pose_count', 0)} interpolation={timeline.get('interpolation', '')}",
            f"last_motion_preset={timeline.get('last_motion_preset', '')}",
        ]
        return _wrap_block("\n".join(rows), width)
    if section_key == "semantic":
        semantic = snapshot.get("semantic") or {}
        rows = [f"summary={semantic.get('summary', '')}"]
        for triplet in (semantic.get("triplets") or [])[:16]:
            rows.append(str(triplet))
        return _wrap_block("\n".join(rows), width)
    value = snapshot.get(section_key)
    if value is None:
        return ["Unavailable"]
    return _safe_json_lines(value, width)


def _build_status_lines(snapshot, section_key, width):
    balance = snapshot.get("balance") or {}
    settle = snapshot.get("settle") or {}
    stale = snapshot.get("stale_flags") or {}
    runtime = snapshot.get("runtime") or {}
    lines = [
        f"phase={balance.get('support_phase', 'unknown')} risk={balance.get('stability_risk', '?')} margin={balance.get('stability_margin', '?')}",
        f"settle={settle.get('strategy') or 'inactive'} severity={settle.get('severity') or '-'} active={bool(settle.get('active'))}",
        f"runtime={runtime.get('mode', '?')} grounded={runtime.get('grounded', '?')} sync_reason={snapshot.get('last_sync_reason', '')}",
        _motion_status_line(snapshot),
        f"section={section_key} mirror_lag={bool(stale.get('mirror_lag'))} bundle={snapshot.get('bundle_version', '?')}",
        "keys: q quit | d diagnostics | tab cycle diag | 1 render | 2 theater | 3 embodiment | 4 snapshot | 5 split",
    ]
    return _wrap_block("\n".join(lines), width)


def _render_local_theater_text(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    theater = snapshot.get("theater") if isinstance(snapshot.get("theater"), dict) else {}
    scene = snapshot.get("scene") if isinstance(snapshot.get("scene"), dict) else {}
    runtime = snapshot.get("runtime") if isinstance(snapshot.get("runtime"), dict) else {}
    stale_flags = snapshot.get("stale_flags") if isinstance(snapshot.get("stale_flags"), dict) else {}
    focus = theater.get("focus") if isinstance(theater.get("focus"), dict) else {}
    camera = theater.get("camera") if isinstance(theater.get("camera"), dict) else {}
    bounds = scene.get("bounds") if isinstance(scene.get("bounds"), dict) else {}
    bounds_min = bounds.get("min") if isinstance(bounds.get("min"), dict) else {}
    bounds_max = bounds.get("max") if isinstance(bounds.get("max"), dict) else {}
    position = camera.get("position") if isinstance(camera.get("position"), dict) else {}
    neighborhood = scene.get("focus_neighborhood") if isinstance(scene.get("focus_neighborhood"), list) else []
    snapshot_ts = float(snapshot.get("snapshot_timestamp") or 0.0)
    source_ts = float(snapshot.get("source_timestamp") or 0.0)
    sync_age = max(0.0, (snapshot_ts - source_ts) / 1000.0) if snapshot_ts > 0.0 and source_ts > 0.0 else 0.0
    nearby = ", ".join(
        f"{str(row.get('label') or row.get('object_key') or '?')} ({float(row.get('distance') or 0.0):.2f}m)"
        for row in neighborhood[:8]
        if isinstance(row, dict)
    ) or "none"
    return "\n".join([
        "THEATER: "
        + str(theater.get("mode") or "")
        + " / "
        + str(theater.get("visual_mode") or "")
        + " / focus: "
        + str(focus.get("id") or focus.get("kind") or "none"),
        "CAMERA: "
        + str(camera.get("mode") or "")
        + " / dist "
        + f"{float(camera.get('distance') or 0.0):.2f}"
        + " / pos ("
        + f"{float(position.get('x') or 0.0):.2f}, "
        + f"{float(position.get('y') or 0.0):.2f}, "
        + f"{float(position.get('z') or 0.0):.2f})",
        "BUNDLE: "
        + str(snapshot.get("bundle_version") or "")
        + " / "
        + ("lagged" if stale_flags.get("mirror_lag") else "fresh")
        + " / synced "
        + f"{sync_age:.2f}s ago",
        "SCENE: "
        + str(int(scene.get("object_count") or 0))
        + " objects / bounds x "
        + f"{float(bounds_min.get('x') or 0.0):.2f}"
        + ".."
        + f"{float(bounds_max.get('x') or 0.0):.2f}"
        + " / z "
        + f"{float(bounds_min.get('z') or 0.0):.2f}"
        + ".."
        + f"{float(bounds_max.get('z') or 0.0):.2f}",
        "RUNTIME: "
        + ("enabled" if runtime.get("enabled") else "disabled")
        + " / "
        + str(runtime.get("mode") or "")
        + " / behavior "
        + str(runtime.get("behavior") or "")
        + " / activity "
        + str(runtime.get("activity") or ""),
        "NEARBY: " + nearby,
    ])


def _render_consult_orientation_text(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    theater = snapshot.get("theater") if isinstance(snapshot.get("theater"), dict) else {}
    scene = snapshot.get("scene") if isinstance(snapshot.get("scene"), dict) else {}
    focus = theater.get("focus") if isinstance(theater.get("focus"), dict) else {}
    camera = theater.get("camera") if isinstance(theater.get("camera"), dict) else {}
    target = camera.get("target") if isinstance(camera.get("target"), dict) else {}
    position = camera.get("position") if isinstance(camera.get("position"), dict) else {}
    neighborhood = scene.get("focus_neighborhood") if isinstance(scene.get("focus_neighborhood"), list) else []
    nearby = ", ".join(
        f"{str(row.get('label') or row.get('object_key') or '?')} {float(row.get('distance') or 0.0):.2f}m"
        for row in neighborhood[:6]
        if isinstance(row, dict)
    ) or "none"
    return "\n".join([
        "FOCUS: "
        + str(focus.get("id") or focus.get("kind") or "none")
        + " / mode "
        + str(theater.get("mode") or "")
        + " / visual "
        + str(theater.get("visual_mode") or ""),
        "CAMERA: "
        + str(camera.get("mode") or "")
        + " / dist "
        + f"{float(camera.get('distance') or 0.0):.2f}"
        + " / az "
        + f"{float(camera.get('azimuth') or 0.0):.3f}"
        + " / pol "
        + f"{float(camera.get('polar') or 0.0):.3f}",
        "POS: ("
        + f"{float(position.get('x') or 0.0):.2f}, "
        + f"{float(position.get('y') or 0.0):.2f}, "
        + f"{float(position.get('z') or 0.0):.2f})"
        + " -> target ("
        + f"{float(target.get('x') or 0.0):.2f}, "
        + f"{float(target.get('y') or 0.0):.2f}, "
        + f"{float(target.get('z') or 0.0):.2f})",
        "NEARBY: " + nearby,
    ])


def _render_consult_pose_text(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    workbench = snapshot.get("workbench") if isinstance(snapshot.get("workbench"), dict) else {}
    embodiment = snapshot.get("embodiment") if isinstance(snapshot.get("embodiment"), dict) else {}
    gizmo = workbench.get("gizmo") if isinstance(workbench.get("gizmo"), dict) else {}
    return "\n".join([
        "POSE: primary "
        + str(workbench.get("primary_bone_id") or "none")
        + " / hover "
        + str(workbench.get("hover_bone_id") or "none")
        + " / isolate "
        + str(workbench.get("isolated_chain") or "none"),
        "SELECTION: "
        + str(len(workbench.get("selected_bone_ids") or []))
        + " selected"
        + (" [" + ", ".join(str(v) for v in (workbench.get("selected_bone_ids") or [])) + "]" if workbench.get("selected_bone_ids") else ""),
        "POSED: "
        + str(len(workbench.get("posed_bone_ids") or []))
        + " bones"
        + (" [" + ", ".join(str(v) for v in (workbench.get("posed_bone_ids") or [])) + "]" if workbench.get("posed_bone_ids") else ""),
        "GIZMO: "
        + str(gizmo.get("mode") or "none")
        + " "
        + str(gizmo.get("space") or "")
        + " / "
        + ("attached" if gizmo.get("attached") else "detached")
        + " / editing "
        + str(workbench.get("editing_mode") or ""),
        "EMBODIMENT: family "
        + str(embodiment.get("family") or "")
        + " / scaffold "
        + ("visible" if embodiment.get("scaffold_visible") else "hidden")
        + " / turntable "
        + str(bool(workbench.get("turntable"))),
        "PREVIEW: clip "
        + str(workbench.get("preview_clip") or "none")
        + " / loop "
        + str(workbench.get("preview_loop") or "repeat")
        + " / speed "
        + str(workbench.get("preview_speed") or 0),
    ])


def _render_consult_motion_text(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    balance = snapshot.get("balance") if isinstance(snapshot.get("balance"), dict) else {}
    timeline = snapshot.get("timeline") if isinstance(snapshot.get("timeline"), dict) else {}
    settle = snapshot.get("settle") if isinstance(snapshot.get("settle"), dict) else {}
    contacts = snapshot.get("contacts") if isinstance(snapshot.get("contacts"), list) else []
    projected_com = balance.get("projected_com") if isinstance(balance.get("projected_com"), dict) else {}
    supporting = ", ".join(str(v) for v in (balance.get("supporting_joint_ids") or [])) or "none"
    alerts = ", ".join(str(v) for v in (balance.get("alert_ids") or [])) or "none"
    contact_summary = ", ".join(
        f"{str(row.get('joint') or '?')}={str(row.get('state') or '?')}"
        for row in contacts[:6]
        if isinstance(row, dict)
    ) or "none"
    return "\n".join([
        "BALANCE: phase "
        + str(balance.get("support_phase") or "unknown")
        + " / risk "
        + f"{float(balance.get('stability_risk') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / margin "
        + f"{float(balance.get('stability_margin') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / "
        + ("inside polygon" if balance.get("inside_polygon") else "outside polygon"),
        "SUPPORT: "
        + supporting
        + " / dominant "
        + str(balance.get("dominant_side") or "balanced")
        + " / CoM ("
        + f"{float(projected_com.get('x') or 0.0):.2f}, "
        + f"{float(projected_com.get('z') or 0.0):.2f})",
        "CONTACTS: " + contact_summary,
        "ALERTS: " + alerts,
        "SETTLE: "
        + ("active" if settle.get("active") else "inactive")
        + " / strategy "
        + str(settle.get("strategy") or "none")
        + " / severity "
        + str(settle.get("severity") or "-"),
        "TIMELINE: cursor "
        + f"{float(timeline.get('cursor') or 0.0):.3f}".rstrip("0").rstrip(".")
        + " / duration "
        + f"{float(timeline.get('duration') or 0.0):.3f}".rstrip("0").rstrip(".")
        + " / key poses "
        + str(int(timeline.get("key_pose_count") or 0))
        + " / preset "
        + str(timeline.get("last_motion_preset") or "none"),
    ])


def _render_consult_view(snapshot, width, height, diagnostics_visible, section_key):
    width = max(80, width)
    height = max(24, height)
    main_height = max(12, height - (15 if diagnostics_visible else 5))
    top_height = max(6, min(9, main_height // 3))
    middle_height = max(8, min(11, (main_height - top_height) // 2))
    bottom_height = max(8, main_height - top_height - middle_height)
    lines = []
    lines.extend(_box("Orientation", _wrap_block(_render_consult_orientation_text(snapshot), width - 2), width, top_height, color=CYAN))
    lines.extend(_box("Pose Control", _wrap_block(_render_consult_pose_text(snapshot), width - 2), width, middle_height, color=GREEN))
    lines.extend(_box("Footing And Motion", _wrap_block(_render_consult_motion_text(snapshot), width - 2), width, bottom_height, color=ORANGE))
    if diagnostics_visible:
        lines.extend(_box(
            f"Diagnostics · {dict(PANE_SECTIONS).get(section_key, section_key)}",
            _section_lines(snapshot, section_key, width - 2),
            width,
            max(7, min(12, height - len(lines) - 3)),
            color=GREEN,
        ))
        lines.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2), width, max(3, height - len(lines)), color=YELLOW))
    else:
        lines.extend(_box("Status", _compact_status_lines(snapshot, width - 2), width, max(3, height - len(lines)), color=YELLOW))
    return lines


def _build_local_bone_tree_lines(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    embodiment = snapshot.get("embodiment") if isinstance(snapshot.get("embodiment"), dict) else {}
    bones = embodiment.get("bones") if isinstance(embodiment.get("bones"), list) else []
    contacts = snapshot.get("contacts") if isinstance(snapshot.get("contacts"), list) else []
    contact_map = {}
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        key = str(contact.get("joint") or contact.get("bone_id") or "").strip()
        if key:
            contact_map[key] = contact
    by_id = {}
    child_map = {}
    for index, bone in enumerate(bones):
        if not isinstance(bone, dict):
            continue
        key = str(bone.get("id") or "").strip()
        if not key:
            continue
        row = dict(bone)
        row["_index"] = index
        by_id[key] = row
        child_map.setdefault(key, [])
    roots = []
    for bone in bones:
        if not isinstance(bone, dict):
            continue
        key = str(bone.get("id") or "").strip()
        if not key or key not in by_id:
            continue
        parent_id = str(bone.get("parent") or "").strip()
        if parent_id and parent_id in child_map:
            child_map[parent_id].append(by_id[key])
        else:
            roots.append(by_id[key])
    for key in child_map:
        child_map[key].sort(key=lambda row: int(row.get("_index") or 0))
    roots.sort(key=lambda row: int(row.get("_index") or 0))

    def render_label(node):
        label = str(node.get("name") or node.get("id") or "bone")
        if node.get("selected"):
            label += "*"
        if node.get("posed"):
            label += "+"
        contact = contact_map.get(str(node.get("id") or ""))
        if isinstance(contact, dict) and contact.get("state"):
            label += " [" + str(contact.get("state") or "").upper() + "]"
        return label

    lines = []

    def walk(node, prefix, is_last, depth):
        level = int(depth or 0)
        connector = ("\\- " if is_last else "|- ") if level > 0 else ""
        lines.append(prefix + connector + render_label(node))
        children = child_map.get(str(node.get("id") or ""), [])
        child_prefix = prefix + (("   " if is_last else "|  ") if level > 0 else "")
        for index, child in enumerate(children):
            walk(child, child_prefix, index == (len(children) - 1), level + 1)

    for index, root in enumerate(roots):
        walk(root, "", index == (len(roots) - 1), 0)
    return lines or ["(no bones)"]


def _render_local_embodiment_text(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    embodiment = snapshot.get("embodiment") if isinstance(snapshot.get("embodiment"), dict) else {}
    workbench = snapshot.get("workbench") if isinstance(snapshot.get("workbench"), dict) else {}
    balance = snapshot.get("balance") if isinstance(snapshot.get("balance"), dict) else {}
    settle = snapshot.get("settle") if isinstance(snapshot.get("settle"), dict) else {}
    timeline = snapshot.get("timeline") if isinstance(snapshot.get("timeline"), dict) else {}
    semantic = snapshot.get("semantic") if isinstance(snapshot.get("semantic"), dict) else {}
    gizmo = workbench.get("gizmo") if isinstance(workbench.get("gizmo"), dict) else {}
    projected_com = balance.get("projected_com") if isinstance(balance.get("projected_com"), dict) else {}
    contacts = snapshot.get("contacts") if isinstance(snapshot.get("contacts"), list) else []
    lines = [
        "EMBODIMENT: "
        + str(embodiment.get("family") or "")
        + " / "
        + ("builder" if embodiment.get("builder_active") else "runtime")
        + " / "
        + str(workbench.get("editing_mode") or "")
        + " mode / scaffold "
        + ("visible" if embodiment.get("scaffold_visible") else "hidden"),
        "WORKBENCH: primary "
        + str(workbench.get("primary_bone_id") or "none")
        + " / hover "
        + str(workbench.get("hover_bone_id") or "none")
        + " / gizmo "
        + str(gizmo.get("mode") or "none")
        + " "
        + str(gizmo.get("space") or "")
        + " "
        + ("attached" if gizmo.get("attached") else "detached"),
        "BONES ("
        + str(len(embodiment.get("bones") or []))
        + "): "
        + str(len(workbench.get("selected_bone_ids") or []))
        + " selected"
        + (" [" + ", ".join(str(v) for v in (workbench.get("selected_bone_ids") or [])) + "]" if workbench.get("selected_bone_ids") else "")
        + ", "
        + str(len(workbench.get("posed_bone_ids") or []))
        + " posed"
        + (" [" + ", ".join(str(v) for v in (workbench.get("posed_bone_ids") or [])) + "]" if workbench.get("posed_bone_ids") else ""),
    ]
    for line in _build_local_bone_tree_lines(snapshot):
        lines.append("  " + line)
    lines.append("  (* selected, + posed, [STATE] contact)")
    lines.append(
        "BALANCE: "
        + str(balance.get("support_phase") or "unknown")
        + " / risk "
        + f"{float(balance.get('stability_risk') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / margin "
        + f"{float(balance.get('stability_margin') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / "
        + ("inside polygon" if balance.get("inside_polygon") else "outside polygon")
    )
    lines.append(
        "  CoM: ("
        + f"{float(projected_com.get('x') or 0.0):.2f}, "
        + f"{float(projected_com.get('z') or 0.0):.2f})"
        + " / dominant: "
        + str(balance.get("dominant_side") or "balanced")
        + " / supporting: "
        + (", ".join(str(v) for v in (balance.get("supporting_joint_ids") or [])) if balance.get("supporting_joint_ids") else "none")
    )
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        lines.append(
            "  "
            + str(contact.get("joint") or "")
            + ": "
            + str(contact.get("state") or "")
            + " (gap "
            + f"{float(contact.get('gap') or 0.0):.3f}".rstrip("0").rstrip(".")
            + ")"
        )
    lines.append("  alerts: " + (", ".join(str(v) for v in (balance.get("alert_ids") or [])) if balance.get("alert_ids") else "none"))
    lines.append(
        "SETTLE: "
        + (
            str(settle.get("strategy") or "")
            + " / "
            + str(settle.get("severity") or "")
            + " / "
            + str(int(settle.get("frame_count") or 0))
            + " frames"
            if settle.get("active")
            else "inactive"
        )
    )
    lines.append(
        "TIMELINE: cursor "
        + f"{float(timeline.get('cursor') or 0.0):.3f}".rstrip("0").rstrip(".")
        + " / duration "
        + f"{float(timeline.get('duration') or 0.0):.3f}".rstrip("0").rstrip(".")
        + " / "
        + str(int(timeline.get("key_pose_count") or 0))
        + " key poses / preset: "
        + str(timeline.get("last_motion_preset") or "none")
    )
    if semantic.get("summary"):
        lines.append("SUMMARY: " + str(semantic.get("summary") or ""))
    return "\n".join(lines)


def _local_text_outputs(snapshot, view_mode):
    if not isinstance(snapshot, dict):
        return "", ""
    theater = _render_local_theater_text(snapshot) if view_mode in ("theater", "split") else ""
    embodiment = _render_local_embodiment_text(snapshot) if view_mode in ("embodiment", "split") else ""
    return theater, embodiment


def _render_render_view(snapshot, width, height, diagnostics_visible, section_key, history=None):
    width = max(80, width)
    height = max(24, height)
    content_height = max(10, height - 5)
    if diagnostics_visible:
        content_height = max(10, height - 17)

    lines = []
    if width >= 120 and content_height >= 18:
        left_width = max(48, int(width * 0.66))
        right_width = max(24, width - left_width - 1)
        main_box = _box("Scene", _render_projection(snapshot, left_width - 2, content_height - 2, "perspective", history=history), left_width, content_height)
        top_height = max(8, content_height // 2)
        front_height = content_height - top_height
        top_box = _box("Quarter", _render_projection(snapshot, right_width - 2, top_height - 2, "quarter", history=history), right_width, top_height)
        front_box = _box("Profile", _render_projection(snapshot, right_width - 2, front_height - 2, "profile", history=history), right_width, front_height)
        right_lines = top_box + front_box
        row_count = max(len(main_box), len(right_lines))
        for idx in range(row_count):
            left_line = main_box[idx] if idx < len(main_box) else (" " * left_width)
            right_line = right_lines[idx] if idx < len(right_lines) else (" " * right_width)
            lines.append(left_line + " " + right_line)
    else:
        lines.extend(_box("Scene", _render_projection(snapshot, width - 2, content_height - 2, "perspective", history=history), width, content_height))

    if diagnostics_visible:
        lines.extend(_box(
            f"Diagnostics · {dict(PANE_SECTIONS).get(section_key, section_key)}",
            _section_lines(snapshot, section_key, width - 2),
            width,
            max(7, min(12, height - len(lines) - 3)),
            color=GREEN,
        ))
        lines.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2), width, max(3, height - len(lines)), color=YELLOW))
    else:
        lines.extend(_box("Status", _compact_status_lines(snapshot, width - 2), width, max(3, height - len(lines)), color=YELLOW))
    return lines


def _render_removed_view(width, height, diagnostics_visible, section_key):
    width = max(80, width)
    height = max(24, height)
    main_height = max(10, height - (15 if diagnostics_visible else 5))
    lines = [
        "Scene render view removed pending rebuild.",
        "",
        "This terminal surface is text-only for now.",
        "",
        "Use:",
        "  1 theater",
        "  2 embodiment",
        "  3 snapshot",
        "  4 split",
    ]
    out = _box("Render Removed", lines, width, main_height, color=RED)
    if diagnostics_visible:
        out.extend(_box(
            f"Diagnostics · {dict(PANE_SECTIONS).get(section_key, section_key)}",
            _section_lines(snapshot, section_key, width - 2),
            width,
            max(7, min(12, height - len(out) - 3)),
            color=GREEN,
        ))
        out.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2), width, max(3, height - len(out)), color=YELLOW))
    else:
        out.extend(_box("Status", _compact_status_lines(snapshot, width - 2), width, max(3, height - len(out)), color=YELLOW))
    return out


def _render_frame(snapshot, theater_text, embodiment_text, view_mode, section_key, width, height, diagnostics_visible, history=None):
    width = max(80, width)
    height = max(24, height)
    header_title = "Text Theater"
    header_note = f"view={view_mode}  focus={(((snapshot.get('theater') or {}).get('focus') or {}).get('id') or 'none')}"
    header = f"{MAGENTA}{BOLD}{header_title}{RESET}  {DIM}{header_note}{RESET}"

    lines = [header]

    if view_mode == "render":
        lines.extend(_render_render_view(snapshot, width, height - 1, diagnostics_visible, section_key, history=history))
    elif view_mode == "consult":
        lines.extend(_render_consult_view(snapshot, width, height - 1, diagnostics_visible, section_key))
    elif view_mode == "theater":
        main_height = max(10, height - (15 if diagnostics_visible else 5))
        lines.extend(_box("Theater", _wrap_block(theater_text, width - 2), width, main_height))
        if diagnostics_visible:
            lines.extend(_box(
                f"Diagnostics · {dict(PANE_SECTIONS).get(section_key, section_key)}",
                _section_lines(snapshot, section_key, width - 2),
                width,
                max(7, min(12, height - len(lines) - 3)),
                color=GREEN,
            ))
            lines.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2), width, max(3, height - len(lines)), color=YELLOW))
        else:
            lines.extend(_box("Status", _compact_status_lines(snapshot, width - 2), width, max(3, height - len(lines)), color=YELLOW))
    elif view_mode == "embodiment":
        main_height = max(10, height - (15 if diagnostics_visible else 5))
        lines.extend(_box("Embodiment", _wrap_block(embodiment_text, width - 2), width, main_height))
        if diagnostics_visible:
            lines.extend(_box(
                f"Diagnostics · {dict(PANE_SECTIONS).get(section_key, section_key)}",
                _section_lines(snapshot, section_key, width - 2),
                width,
                max(7, min(12, height - len(lines) - 3)),
                color=GREEN,
            ))
            lines.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2), width, max(3, height - len(lines)), color=YELLOW))
        else:
            lines.extend(_box("Status", _compact_status_lines(snapshot, width - 2), width, max(3, height - len(lines)), color=YELLOW))
    elif view_mode == "snapshot":
        main_height = max(10, height - (15 if diagnostics_visible else 5))
        snapshot_lines = _safe_json_lines(snapshot, width - 2)
        lines.extend(_box("Snapshot", snapshot_lines, width, main_height))
        if diagnostics_visible:
            lines.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2), width, max(3, height - len(lines)), color=YELLOW))
        else:
            lines.extend(_box("Status", _compact_status_lines(snapshot, width - 2), width, max(3, height - len(lines)), color=YELLOW))
    else:
        main_height = max(10, height - (15 if diagnostics_visible else 5))
        left_width = max(36, (width - 1) // 2)
        right_width = max(36, width - left_width - 1)
        left_box = _box("Theater", _wrap_block(theater_text, left_width - 2), left_width, main_height)
        right_box = _box("Embodiment", _wrap_block(embodiment_text, right_width - 2), right_width, main_height)
        row_count = max(len(left_box), len(right_box))
        for idx in range(row_count):
            left_line = left_box[idx] if idx < len(left_box) else (" " * left_width)
            right_line = right_box[idx] if idx < len(right_box) else (" " * right_width)
            lines.append(left_line + " " + right_line)
        if diagnostics_visible:
            lines.extend(_box(
                f"Diagnostics · {dict(PANE_SECTIONS).get(section_key, section_key)}",
                _section_lines(snapshot, section_key, width - 2),
                width,
                max(7, min(12, height - len(lines) - 3)),
                color=GREEN,
            ))
            lines.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2), width, max(3, height - len(lines)), color=YELLOW))
        else:
            lines.extend(_box("Status", _compact_status_lines(snapshot, width - 2), width, max(3, height - len(lines)), color=YELLOW))
    return "\n".join(lines[:height])


def _fetch_all(base_url, timeout, view_mode):
    shared_state = _env_read_optional(base_url, "shared_state", timeout)
    if isinstance(shared_state, dict):
        text_theater = shared_state.get("text_theater") if isinstance(shared_state.get("text_theater"), dict) else {}
        snapshot = text_theater.get("snapshot") if isinstance(text_theater.get("snapshot"), dict) else None
        if isinstance(snapshot, dict):
            snapshot = _merge_live_camera_into_snapshot(snapshot, {"shared_state": shared_state})
            theater, embodiment = _local_text_outputs(snapshot, view_mode)
            return snapshot, theater, embodiment

    live_state = _env_read_optional(base_url, "live", timeout)
    if isinstance(live_state, dict):
        shared_state = live_state.get("shared_state") if isinstance(live_state.get("shared_state"), dict) else {}
        text_theater = shared_state.get("text_theater") if isinstance(text_theater := shared_state.get("text_theater"), dict) else {}
        snapshot = text_theater.get("snapshot") if isinstance(text_theater.get("snapshot"), dict) else None
        if isinstance(snapshot, dict):
            snapshot = _merge_live_camera_into_snapshot(snapshot, live_state)
            theater, embodiment = _local_text_outputs(snapshot, view_mode)
            return snapshot, theater, embodiment

    snapshot = _env_read(base_url, "text_theater_snapshot", timeout)
    theater, embodiment = _local_text_outputs(snapshot, view_mode)
    if not isinstance(snapshot, dict):
        theater = ""
        embodiment = ""
        if view_mode in ("theater", "split"):
            theater = _env_read(base_url, "text_theater", timeout)
        if view_mode in ("embodiment", "split"):
            embodiment = _env_read(base_url, "text_theater_embodiment", timeout)
    return snapshot, theater, embodiment


def render_text_theater_view(
    base_url,
    timeout=5.0,
    view_mode="split",
    width=140,
    height=44,
    diagnostics_visible=False,
    section_key="theater",
):
    width = max(80, int(width or 80))
    height = max(24, int(height or 24))
    section_lookup = {key: label for key, label in PANE_SECTIONS}
    section_name = str(section_key or "theater").strip().lower()
    if section_name not in section_lookup:
        section_name = "theater"
    mode = str(view_mode or "split").strip().lower()
    if mode not in {"render", "split", "theater", "embodiment", "snapshot", "consult"}:
        mode = "split"
    snapshot, theater_text, embodiment_text = _fetch_all(base_url, timeout, mode)
    history = _append_motion_history([], snapshot)
    frame = _render_frame(
        snapshot=snapshot,
        theater_text=theater_text,
        embodiment_text=embodiment_text,
        view_mode=mode,
        section_key=section_name,
        width=width,
        height=height,
        diagnostics_visible=bool(diagnostics_visible),
        history=history,
    )
    return {
        "frame": ANSI_RE.sub("", frame),
        "snapshot": snapshot,
        "theater_text": theater_text,
        "embodiment_text": embodiment_text,
        "view_mode": mode,
        "section_key": section_name,
        "width": width,
        "height": height,
        "diagnostics": bool(diagnostics_visible),
    }


def render_text_theater_shared_state(
    shared_state,
    synced_at=None,
    view_mode="split",
    width=140,
    height=44,
    diagnostics_visible=False,
    section_key="theater",
):
    width = max(80, int(width or 80))
    height = max(24, int(height or 24))
    section_lookup = {key: label for key, label in PANE_SECTIONS}
    section_name = str(section_key or "theater").strip().lower()
    if section_name not in section_lookup:
        section_name = "theater"
    mode = str(view_mode or "split").strip().lower()
    if mode not in {"render", "split", "theater", "embodiment", "snapshot", "consult"}:
        mode = "split"
    shared = shared_state if isinstance(shared_state, dict) else {}
    text_theater = shared.get("text_theater") if isinstance(shared.get("text_theater"), dict) else {}
    snapshot = text_theater.get("snapshot") if isinstance(text_theater.get("snapshot"), dict) else {}
    if isinstance(snapshot, dict) and snapshot:
        live_state = {"shared_state": shared}
        if synced_at is not None:
            live_state["synced_at"] = synced_at
        snapshot = _merge_live_camera_into_snapshot(snapshot, live_state)
        theater_text, embodiment_text = _local_text_outputs(snapshot, mode)
    else:
        snapshot = {}
        theater_text = str(text_theater.get("theater") or "") if mode in {"theater", "split"} else ""
        embodiment_text = str(text_theater.get("embodiment") or "") if mode in {"embodiment", "split"} else ""
    history = _append_motion_history([], snapshot)
    frame = _render_frame(
        snapshot=snapshot,
        theater_text=theater_text,
        embodiment_text=embodiment_text,
        view_mode=mode,
        section_key=section_name,
        width=width,
        height=height,
        diagnostics_visible=bool(diagnostics_visible),
        history=history,
    )
    return {
        "frame": ANSI_RE.sub("", frame),
        "snapshot": snapshot,
        "theater_text": theater_text,
        "embodiment_text": embodiment_text,
        "view_mode": mode,
        "section_key": section_name,
        "width": width,
        "height": height,
        "diagnostics": bool(diagnostics_visible),
    }


def _run(args):
    _configure_stdout()
    _enable_vt_mode()
    base_url = f"http://{args.host}:{args.port}"
    view_mode = args.view
    section_index = 0
    diagnostics_visible = args.diagnostics
    last_error = ""
    motion_history = []
    last_frame = None
    last_snapshot = None
    last_theater_text = ""
    last_embodiment_text = ""

    sys.stdout.write(ALT_SCREEN_ON + HIDE_CURSOR + CLEAR_SCREEN)
    sys.stdout.flush()
    try:
        while True:
            cycle_started = time.time()
            width, height = shutil.get_terminal_size((140, 44))
            try:
                snapshot, theater_text, embodiment_text = _fetch_all(base_url, args.timeout, view_mode)
                last_snapshot = snapshot
                last_theater_text = theater_text
                last_embodiment_text = embodiment_text
                motion_history = _append_motion_history(motion_history, snapshot)
                frame = _render_frame(
                    snapshot=snapshot,
                    theater_text=theater_text,
                    embodiment_text=embodiment_text,
                    view_mode=view_mode,
                    section_key=PANE_SECTIONS[section_index][0],
                    width=width,
                    height=height,
                    diagnostics_visible=diagnostics_visible,
                    history=motion_history,
                )
                last_error = ""
            except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                if isinstance(last_snapshot, dict):
                    stale_flags = last_snapshot.get("stale_flags") if isinstance(last_snapshot.get("stale_flags"), dict) else {}
                    next_stale = dict(stale_flags)
                    next_stale["fetch_error"] = last_error
                    last_snapshot["stale_flags"] = next_stale
                    frame = _render_frame(
                        snapshot=last_snapshot,
                        theater_text=last_theater_text,
                        embodiment_text=last_embodiment_text,
                        view_mode=view_mode,
                        section_key=PANE_SECTIONS[section_index][0],
                        width=width,
                        height=height,
                        diagnostics_visible=diagnostics_visible,
                        history=motion_history,
                    )
                else:
                    frame = "\n".join([
                        f"{RED}{BOLD}Text Theater{RESET}",
                        "",
                        "Live snapshot fetch failed.",
                        "",
                        last_error,
                        "",
                        f"Target: {base_url}",
                        "",
                        "Keys: q quit | r retry",
                    ])
            if frame != last_frame:
                sys.stdout.write(FRAME_HOME + frame)
                sys.stdout.flush()
                last_frame = frame

            remaining = max(0.0, float(args.interval) - (time.time() - cycle_started))
            started = time.time()
            while time.time() - started < remaining:
                key = _read_key_nonblocking()
                if key is None:
                    time.sleep(0.02)
                    continue
                if key.lower() == "q":
                    return 0
                if key.lower() == "r":
                    break
                if key == "\t":
                    section_index = (section_index + 1) % len(PANE_SECTIONS)
                    break
                if key == "1":
                    view_mode = "render"
                    break
                if key == "2":
                    view_mode = "consult"
                    break
                if key == "3":
                    view_mode = "theater"
                    break
                if key == "4":
                    view_mode = "embodiment"
                    break
                if key == "5":
                    view_mode = "snapshot"
                    break
                if key == "6":
                    view_mode = "split"
                    break
                if key.lower() == "d":
                    diagnostics_visible = not diagnostics_visible
                    break
                if key.lower() == "b":
                    section_index = 0
                    break
                if key.lower() == "c":
                    section_index = 1
                    break
                if key.lower() == "w":
                    section_index = 2
                    break
                if key.lower() == "e":
                    section_index = 3
                    break
                if key.lower() == "u":
                    section_index = 4
                    break
                if key.lower() == "o":
                    section_index = 5
                    break
            if args.once:
                return 0
    finally:
        sys.stdout.write(RESET + SHOW_CURSOR + ALT_SCREEN_OFF)
        sys.stdout.flush()
        if last_error:
            print(last_error, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Terminal-native Text Theater view for Champion Council.")
    parser.add_argument("--host", default=os.environ.get("WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("WEB_PORT", "7866")))
    parser.add_argument("--interval", type=float, default=0.04, help="Refresh interval in seconds.")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout in seconds.")
    parser.add_argument("--view", choices=["render", "consult", "split", "theater", "embodiment", "snapshot"], default="render")
    parser.add_argument("--diagnostics", action="store_true", help="Show diagnostics panes by default.")
    parser.add_argument("--once", action="store_true", help="Render once and exit.")
    raise SystemExit(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
