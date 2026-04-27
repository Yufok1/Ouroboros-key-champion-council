import argparse
import copy
import colorsys
from functools import lru_cache
import json
import math
import os
import re
import shutil
import sys
import textwrap
import threading
import time
import unicodedata
import urllib.error
import urllib.request

try:
    from PyDrawille import CanvasSurface as _PyDrawilleCanvasSurface
except Exception:
    _PyDrawilleCanvasSurface = None

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None


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
BG_GRAPHITE = "\x1b[48;5;235m"
BG_STEEL = "\x1b[48;5;237m"
PLATE_GRAIN = "\x1b[38;5;239m"
PLATE_GRAIN_SOFT = "\x1b[38;5;238m"

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
    ("timeline", "Timeline"),
    ("corroboration", "Corroboration"),
    ("blackboard", "Blackboard"),
    ("profiles", "Profiles"),
    ("semantic", "Semantic"),
]

VIEW_MODES = {"render", "consult", "theater", "embodiment", "snapshot", "split"}
SECTION_INDEX_BY_KEY = {key: idx for idx, (key, _label) in enumerate(PANE_SECTIONS)}

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

TEXT_THEATER_SURFACE_MODES = ("legacy", "sharp", "granular")
TEXT_THEATER_SURFACE_MODE = str(os.environ.get("TEXT_THEATER_SURFACE_MODE", "sharp")).strip().lower() or "sharp"
if TEXT_THEATER_SURFACE_MODE not in TEXT_THEATER_SURFACE_MODES:
    TEXT_THEATER_SURFACE_MODE = "sharp"
try:
    TEXT_THEATER_SURFACE_DENSITY = max(
        0.0,
        min(1.0, float(os.environ.get("TEXT_THEATER_SURFACE_DENSITY", "0.42"))),
    )
except Exception:
    TEXT_THEATER_SURFACE_DENSITY = 0.42


def _control_help_text():
    return "keys: m/6 main split | 2 consult | 3 theater | 4 embodiment | 5 snapshot | s surface | -/= density | d diagnostics | tab next | g blackboard | p profiles | h help | q quit"


TEXT_UI_FONT_PATHS = (
    r"C:\Windows\Fonts\times.ttf",
    r"C:\Windows\Fonts\georgia.ttf",
    r"C:\Windows\Fonts\cambria.ttc",
    r"C:\Windows\Fonts\cour.ttf",
    r"C:\Windows\Fonts\consola.ttf",
)
TEXT_UI_FONT_BOLD_PATHS = (
    r"C:\Windows\Fonts\timesbd.ttf",
    r"C:\Windows\Fonts\georgiab.ttf",
    r"C:\Windows\Fonts\cambria.ttc",
    r"C:\Windows\Fonts\courbd.ttf",
    r"C:\Windows\Fonts\consolab.ttf",
)


def _control_menu_lines(width):
    return [
        "views  m/6 split | 2 consult | 3 theater | 4 embodiment | 5 snapshot",
        "board  d diagnostics | tab next section | g blackboard | p profiles",
        "surface s cycle spectrum | - density down | = density up",
        "help   h help | q quit | r retry | direct  b theater | c scene | w render | e layout | u docs | o nav",
    ]


@lru_cache(maxsize=4)
def _ui_font_path(bold=False):
    candidates = TEXT_UI_FONT_BOLD_PATHS if bold else TEXT_UI_FONT_PATHS
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


@lru_cache(maxsize=64)
def _load_ui_font(size_px, bold=False):
    size_px = max(6, int(size_px or 6))
    if ImageFont is None:
        return None
    path = _ui_font_path(bool(bold))
    if path:
        try:
            return ImageFont.truetype(path, size_px)
        except Exception:
            pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _font_text_width(font, text):
    if not text:
        return 0
    if font is None:
        return len(text)
    try:
        return int(math.ceil(float(font.getlength(text))))
    except Exception:
        try:
            bbox = font.getbbox(text)
            return max(0, int(bbox[2] - bbox[0]))
        except Exception:
            return len(text)


def _font_text_height(font):
    if font is None:
        return 8
    try:
        bbox = font.getbbox("Ag")
        return max(1, int(bbox[3] - bbox[1]))
    except Exception:
        try:
            ascent, descent = font.getmetrics()
            return max(1, int(ascent + descent))
        except Exception:
            return 8


def _token_tracking_px(size_px, text):
    return 0


def _token_draw_width(font, text, size_px=None):
    text = str(text or "")
    if not text:
        return 0
    return _font_text_width(font, text)


@lru_cache(maxsize=2048)
def _token_bitmap(text, size_px, bold=False):
    text = str(text or "")
    logical_size = max(6, int(size_px or 8))
    font = _load_ui_font(logical_size, bold=bool(bold))
    if font is None or Image is None or ImageDraw is None:
        return {"width": 1, "height": 1, "points": []}
    width = max(1, _token_draw_width(font, text, logical_size))
    height = max(1, _font_text_height(font))
    supersample = 3
    pad = supersample * 2
    hi_font = _load_ui_font(logical_size * supersample, bold=bool(bold))
    if hi_font is None:
        hi_font = font
        supersample = 1
        pad = 2
    mask = Image.new("L", ((width * supersample) + pad, (height * supersample) + (pad * 2)), 0)
    draw = ImageDraw.Draw(mask)
    draw.text((0, 0), text, font=hi_font, fill=255)
    pixels = mask.load()
    points = []
    # Keep enough stroke coverage that serif/typewriter forms survive the
    # braille-cell reduction instead of collapsing into symbol noise.
    coverage_threshold = 96 if logical_size >= 10 else 84
    for py in range(height + 3):
        for px in range(width + 1):
            total = 0
            samples = 0
            for sy in range(supersample):
                for sx in range(supersample):
                    hx = (px * supersample) + sx
                    hy = (py * supersample) + sy
                    if 0 <= hx < mask.width and 0 <= hy < mask.height:
                        total += int(pixels[hx, hy])
                        samples += 1
            if samples and (total / float(samples)) >= coverage_threshold:
                points.append((px, py))
    return {
        "width": width,
        "height": height + 3,
        "points": tuple(points),
    }


def _bridge_bitmap_points(points, max_gap=1):
    return tuple(points or ())


def _bitmap_emboss_layers(points):
    return {"highlight": (), "shadow": (), "body": ()}


def _ansi_segments(text, default_style=""):
    raw = str(text or "")
    if not raw:
        return []
    segments = []
    buffer = []
    current_style = str(default_style or "")
    index = 0
    while index < len(raw):
        if raw[index] == "\x1b":
            match = ANSI_RE.match(raw, index)
            if match:
                if buffer:
                    segments.append(("".join(buffer), current_style))
                    buffer = []
                code = match.group(0)
                if code == RESET or code.endswith("[0m"):
                    current_style = str(default_style or "")
                else:
                    current_style = (current_style + code) if current_style else code
                index = match.end()
                continue
        buffer.append(raw[index])
        index += 1
    if buffer:
        segments.append(("".join(buffer), current_style))
    return segments


def _char_display_width(char):
    ch = str(char or "")
    if not ch:
        return 0
    if ch == "\n":
        return 0
    if unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in {"F", "W"}:
        return 2
    return 1


def _display_width(text):
    raw = str(text or "")
    width = 0
    index = 0
    while index < len(raw):
        if raw[index] == "\x1b":
            match = ANSI_RE.match(raw, index)
            if match:
                index = match.end()
                continue
        width += _char_display_width(raw[index])
        index += 1
    return width


def _widen_char(char):
    ch = str(char or "")
    if not ch:
        return ""
    code = ord(ch)
    if ch == " ":
        return " "
    if 0x21 <= code <= 0x7E:
        return chr(code + 0xFEE0)
    return ch


def _widen_text(text):
    return "".join(_widen_char(ch) for ch in str(text or ""))


def _collapse_segment_runs(segments):
    out = []
    for text, style in segments:
        if not text:
            continue
        if out and out[-1][1] == style:
            out[-1] = (out[-1][0] + text, style)
        else:
            out.append((text, style))
    return out


def _tokenize_styled_segments(segments):
    tokens = []
    for text, style in segments:
        for token in re.findall(r"\S+|\s+", str(text or "")):
            tokens.append((token, style))
    return tokens


def _wrap_styled_display_line(text, width_cells, default_style="", widen=True):
    width_cells = max(6, int(width_cells or 6))
    tokens = _tokenize_styled_segments(_ansi_segments(text, default_style=default_style))
    if not tokens:
        return [[]]
    wrapped = []
    current = []
    current_width = 0

    def flush():
        nonlocal current, current_width
        trimmed = []
        for chunk, style in current:
            if chunk and not trimmed and chunk.isspace():
                continue
            trimmed.append((chunk, style))
        while trimmed and trimmed[-1][0].isspace():
            trimmed.pop()
        wrapped.append(_collapse_segment_runs(trimmed))
        current = []
        current_width = 0

    for token, style in tokens:
        if not token:
            continue
        rendered = token if token.isspace() or not widen else _widen_text(token)
        token_width = _display_width(rendered)
        if token.isspace():
            if current and (current_width + token_width) <= width_cells:
                current.append((rendered, style))
                current_width += token_width
            continue
        if current and (current_width + token_width) > width_cells:
            flush()
        if token_width <= width_cells:
            current.append((rendered, style))
            current_width += token_width
            continue
        for char in rendered:
            char_width = _char_display_width(char)
            if current and (current_width + char_width) > width_cells:
                flush()
            current.append((char, style))
            current_width += char_width
    if current or not wrapped:
        flush()
    return wrapped or [[]]


def _segments_to_text(segments):
    out = []
    for text, style in list(segments or []):
        if not text:
            continue
        if style:
            out.append(f"{style}{text}{RESET}")
        else:
            out.append(text)
    return "".join(out)


def _render_wide_text_lines(lines, width_cells, max_rows, default_style=LIGHT_GRAY, align="left", widen=True):
    width_cells = max(6, int(width_cells or 6))
    max_rows = max(1, int(max_rows or 1))
    if not lines:
        return []
    wrapped = []
    for raw_line in list(lines or []):
        plain = str(raw_line or "")
        if not ANSI_RE.sub("", plain).strip():
            wrapped.append([])
            continue
        wrapped.extend(_wrap_styled_display_line(plain.expandtabs(2), width_cells, default_style=default_style, widen=widen))
    out = []
    for segments in wrapped[:max_rows]:
        row = _segments_to_text(segments)
        visible = _display_width(row)
        if align == "center":
            row = (" " * max(0, (width_cells - visible) // 2)) + row
        elif align == "right":
            row = (" " * max(0, width_cells - visible)) + row
        out.append(row)
    return out


def _wrap_styled_line(text, width_px, font, default_style=""):
    width_px = max(8, int(width_px or 8))
    tokens = _tokenize_styled_segments(_ansi_segments(text, default_style=default_style))
    if not tokens:
        return [[]]
    wrapped = []
    current = []
    current_width = 0

    def flush():
        nonlocal current, current_width
        trimmed = []
        for chunk, style in current:
            if chunk and not trimmed and chunk.isspace():
                continue
            trimmed.append((chunk, style))
        while trimmed and trimmed[-1][0].isspace():
            trimmed.pop()
        wrapped.append(_collapse_segment_runs(trimmed))
        current = []
        current_width = 0

    for token, style in tokens:
        if not token:
            continue
        if token.isspace():
            if current:
                token_width = _token_draw_width(font, token, _font_text_height(font))
                if (current_width + token_width) <= width_px:
                    current.append((token, style))
                    current_width += token_width
            continue
        token_width = _token_draw_width(font, token, _font_text_height(font))
        if current and (current_width + token_width) > width_px:
            flush()
        if token_width <= width_px:
            current.append((token, style))
            current_width += token_width
            continue
        for char in token:
            char_width = _font_text_width(font, char)
            if current and (current_width + char_width) > width_px:
                flush()
            current.append((char, style))
            current_width += char_width
    if current or not wrapped:
        flush()
    return wrapped or [[]]


def _wrap_raster_text_lines(lines, width_px, font, default_style=""):
    wrapped = []
    for raw_line in list(lines or []):
        plain = str(raw_line or "")
        if not ANSI_RE.sub("", plain).strip():
            wrapped.append([])
            continue
        wrapped.extend(_wrap_styled_line(plain.expandtabs(2), width_px, font, default_style=default_style))
    return wrapped


def _estimate_raster_rows(wrapped_lines, font, gap_px=1):
    line_height_px = _font_text_height(font)
    y_px = 0
    for line in list(wrapped_lines or []):
        if line:
            y_px += line_height_px + gap_px
        else:
            y_px += max(2, line_height_px // 2)
    return max(0, int(math.ceil(max(0, y_px - gap_px) / 4.0)))


def _render_raster_text_lines(
    lines,
    width_cells,
    max_rows,
    default_style=LIGHT_GRAY,
    preferred_px=12,
    min_px=8,
    bold=False,
    align="left",
    plate_style=BG_GRAPHITE,
    plate_texture="typewriter",
    full_surface_style="",
    full_surface_texture="paper",
    full_surface_texture_style="",
    full_surface_density=0.0,
):
    width_cells = max(8, int(width_cells or 8))
    max_rows = max(1, int(max_rows or 1))
    if not lines:
        return []
    if Image is None or ImageDraw is None or ImageFont is None:
        fallback = _stack_wrapped_rows([ANSI_RE.sub("", str(line or "")) for line in lines], width_cells)
        return fallback[:max_rows]

    render_width_px = max(8, (width_cells * 2) - 2)
    chosen_font = None
    chosen_size_px = int(min_px or 7)
    chosen_lines = []
    chosen_gap = 1
    for size_px in range(max(int(preferred_px or 10), int(min_px or 7)), int(min_px or 7) - 1, -1):
        font = _load_ui_font(size_px, bold=bool(bold))
        if font is None:
            continue
        gap_px = 1 if size_px >= 9 else 0
        wrapped = _wrap_raster_text_lines(lines, render_width_px, font, default_style=default_style)
        if _estimate_raster_rows(wrapped, font, gap_px=gap_px) <= max_rows:
            chosen_font = font
            chosen_size_px = int(size_px)
            chosen_lines = wrapped
            chosen_gap = gap_px
            break
    if chosen_font is None:
        chosen_size_px = int(min_px or 7)
        chosen_font = _load_ui_font(chosen_size_px, bold=bool(bold))
        chosen_gap = 0
        chosen_lines = _wrap_raster_text_lines(lines, render_width_px, chosen_font, default_style=default_style)

    line_height_px = _font_text_height(chosen_font)
    canvas = _make_braille_canvas(width_cells, max_rows)
    if full_surface_style:
        _braille_fill_rect(
            canvas,
            0,
            0,
            max(0, (width_cells * 2) - 1),
            max(0, (max_rows * 4) - 1),
            style=full_surface_style,
            priority=0,
        )
        _braille_texture_rect(
            canvas,
            0,
            0,
            max(0, (width_cells * 2) - 1),
            max(0, (max_rows * 4) - 1),
            style=str(full_surface_texture_style or ""),
            priority=0,
            texture=full_surface_texture,
            density=full_surface_density,
        )
    y_px = 0
    for line_segments in chosen_lines:
        step_px = (line_height_px + chosen_gap) if line_segments else max(2, line_height_px // 2)
        if int(math.ceil((y_px + step_px) / 4.0)) > max_rows:
            break
        if line_segments:
            line_width_px = sum(
                _token_draw_width(chosen_font, text, chosen_size_px)
                for text, _style in line_segments
            )
            if align == "center":
                x_px = max(0, (render_width_px - line_width_px) // 2)
            elif align == "right":
                x_px = max(0, render_width_px - line_width_px)
            else:
                x_px = 0
            if plate_style:
                _braille_fill_rect(
                    canvas,
                    max(0, x_px - 2),
                    max(0, y_px - 1),
                    min((width_cells * 2) - 1, x_px + line_width_px + 2),
                    min((max_rows * 4) - 1, y_px + line_height_px + 1),
                    style=plate_style,
                    priority=1,
                )
                _braille_texture_rect(
                    canvas,
                    max(0, x_px - 2),
                    max(0, y_px - 1),
                    min((width_cells * 2) - 1, x_px + line_width_px + 2),
                    min((max_rows * 4) - 1, y_px + line_height_px + 1),
                    style=(DIM + PLATE_GRAIN) if chosen_size_px >= 9 else PLATE_GRAIN_SOFT,
                    priority=1,
                    texture=plate_texture,
                    density=1.0,
                )
            for segment_text, segment_style in line_segments:
                if not segment_text:
                    continue
                style = (BOLD if bold else "") + str(segment_style or default_style or "")
                edge_style = DIM + str(segment_style or default_style or LIGHT_GRAY)
                shadow_style = DIM + GRAY
                for token in re.findall(r"\S+|\s+", str(segment_text)):
                    if not token:
                        continue
                    if token.isspace():
                        x_px += max(1, _font_text_width(chosen_font, token))
                        continue
                    glyph = _token_bitmap(token, chosen_size_px, bool(bold))
                    token_points = tuple(glyph.get("points") or ())
                    for px, py in token_points:
                        _braille_put(canvas, x_px + px, y_px + py, priority=3, style=style, glyph_mode="raster")
                    x_px += max(1, int(glyph.get("width") or _token_draw_width(chosen_font, token, chosen_size_px) or 1))
        y_px += step_px
    return _braille_lines(canvas)[:max_rows]


@lru_cache(maxsize=128)
def _surface_cell_template(width_cells, max_rows, bg_style="", texture="paper", texture_style="", density_key=0):
    width_cells = max(1, int(width_cells or 1))
    max_rows = max(1, int(max_rows or 1))
    bg = str(bg_style or "")
    grain = str(texture_style or "")
    fill_density = _normalize_surface_density(float(density_key or 0) / 100.0)
    rows = []
    for row_index in range(max_rows):
        row = []
        for col_index in range(width_cells):
            char = _plate_texture_char(col_index, row_index, texture=texture, density=fill_density)
            row.append((
                char if char and char != " " else " ",
                bg,
                grain if char and char != " " else "",
            ))
        rows.append(tuple(row))
    return tuple(rows)


def _surface_cells(width_cells, max_rows, bg_style="", texture="paper", texture_style="", density=0.0):
    width_cells = max(1, int(width_cells or 1))
    max_rows = max(1, int(max_rows or 1))
    bg = str(bg_style or "")
    grain = str(texture_style or "")
    density_key = int(round(_normalize_surface_density(density) * 100.0))
    template = _surface_cell_template(
        width_cells,
        max_rows,
        bg_style=bg,
        texture=texture,
        texture_style=grain,
        density_key=density_key,
    )
    rows = []
    for template_row in template:
        row = []
        for char, cell_bg, fg_style in template_row:
            row.append({
                "char": char,
                "bg_style": cell_bg,
                "fg_style": fg_style,
            })
        rows.append(row)
    return rows


def _overlay_surface_text(surface_rows, text_lines, start_row=0):
    rows = list(surface_rows or [])
    base_row = max(0, int(start_row or 0))
    for row_offset, line in enumerate(list(text_lines or [])):
        row_index = base_row + row_offset
        if row_index >= len(rows):
            break
        cells = rows[row_index]
        column = 0
        for segment_text, segment_style in _ansi_segments(line):
            style = str(segment_style or "")
            for char in str(segment_text or ""):
                char_width = _char_display_width(char)
                if char_width <= 0:
                    continue
                if char.isspace():
                    column += char_width
                    continue
                if column >= len(cells):
                    break
                cells[column]["char"] = char
                cells[column]["fg_style"] = style
                column += char_width
            if column >= len(cells):
                break
    return rows


def _surface_rows_to_text(surface_rows):
    out = []
    for row in list(surface_rows or []):
        parts = []
        for cell in list(row or []):
            char = str((cell or {}).get("char") or " ")
            style = str((cell or {}).get("bg_style") or "") + str((cell or {}).get("fg_style") or "")
            if style:
                parts.append(style + char + RESET)
            else:
                parts.append(char)
        out.append("".join(parts))
    return out


def _render_surface_text_lines(
    lines,
    width_cells,
    max_rows,
    default_style=LIGHT_GRAY,
    align="left",
    widen=False,
    bg_style=BG_GRAPHITE,
    texture="paper",
    texture_style=PLATE_GRAIN_SOFT,
    density=0.35,
):
    text_rows = _render_wide_text_lines(
        lines,
        width_cells,
        max_rows,
        default_style=default_style,
        align=align,
        widen=widen,
    )
    surface = _surface_cells(
        width_cells,
        max_rows,
        bg_style=bg_style,
        texture=texture,
        texture_style=texture_style,
        density=density,
    )
    return _surface_rows_to_text(_overlay_surface_text(surface, text_rows))


def _stack_wrapped_rows(rows, width):
    width = max(20, int(width or 20))
    out = []
    for row in list(rows or []):
        text = str(row or "")
        if not text.strip():
            if out and out[-1] != "":
                out.append("")
            elif not out:
                out.append("")
            continue
        out.extend(_wrap_block(text, width))
    while out and not str(out[-1]).strip():
        out.pop()
    return out


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


def _clamp01(value):
    try:
        num = float(value)
    except Exception:
        num = 0.0
    if num < 0.0:
        return 0.0
    if num > 1.0:
        return 1.0
    return num


def _normalize_surface_mode(value, default=TEXT_THEATER_SURFACE_MODE):
    mode = str(value or default or "legacy").strip().lower() or "legacy"
    if mode not in TEXT_THEATER_SURFACE_MODES:
        return str(default or "legacy")
    return mode


def _normalize_surface_density(value, default=TEXT_THEATER_SURFACE_DENSITY):
    if value is None:
        return _clamp01(default)
    return _clamp01(value)


def _cycle_surface_mode(current, step=1):
    current_mode = _normalize_surface_mode(current)
    index = TEXT_THEATER_SURFACE_MODES.index(current_mode)
    return TEXT_THEATER_SURFACE_MODES[(index + int(step or 1)) % len(TEXT_THEATER_SURFACE_MODES)]


def _surface_status_line(surface_mode, surface_density):
    mode = _normalize_surface_mode(surface_mode)
    density = _normalize_surface_density(surface_density)
    return f"surface={mode} density={density:.2f}"


def _surface_profile(surface_mode, surface_density):
    mode = _normalize_surface_mode(surface_mode)
    density = _normalize_surface_density(surface_density)
    if mode == "granular":
        return {
            "mode": mode,
            "density": density,
            "title_mode": "raster",
            "body_mode": "raster",
            "title_widen": False,
            "body_widen": False,
            "surface_style": BG_GRAPHITE,
            "surface_texture": "typewriter",
            "surface_texture_style": DIM + PLATE_GRAIN,
            "surface_texture_density": min(1.0, 0.35 + (density * 0.65)),
            "raster_preferred_px": 11,
            "raster_min_px": 7,
        }
    if mode == "sharp":
        return {
            "mode": mode,
            "density": density,
            "title_mode": "wide",
            "body_mode": "wide",
            "title_widen": False,
            "body_widen": False,
            "surface_style": BG_GRAPHITE,
            "surface_texture": "paper",
            "surface_texture_style": "",
            "surface_texture_density": 0.0,
            "raster_preferred_px": 10,
            "raster_min_px": 7,
        }
    return {
        "mode": "legacy",
        "density": density,
        "title_mode": "wide",
        "body_mode": "wide",
        "title_widen": True,
        "body_widen": True,
        "surface_style": "",
        "surface_texture": "paper",
        "surface_texture_style": "",
        "surface_texture_density": 0.0,
        "raster_preferred_px": 10,
        "raster_min_px": 7,
    }


def _style_inline(text, style):
    if not style:
        return str(text or "")
    return f"{style}{text}{RESET}"


def _load_band(score):
    value = _clamp01(score)
    if value >= 0.84:
        return {"id": "critical", "label": "CRITICAL", "style": RED}
    if value >= 0.64:
        return {"id": "strain", "label": "STRAIN", "style": ORANGE}
    if value >= 0.4:
        return {"id": "watch", "label": "WATCH", "style": YELLOW}
    return {"id": "stable", "label": "STABLE", "style": GREEN}


def _contact_load_band(contact):
    if not isinstance(contact, dict):
        return _load_band(0.0)
    state = str(contact.get("state") or "").strip().lower()
    gap = abs(float(contact.get("gap") or 0.0))
    manifold = max(0.0, float(contact.get("manifold_points") or 0.0))
    role = str(contact.get("support_role") or "").strip().lower()
    score = 0.18
    if state in ("grounded", "planted"):
        score = 0.12 if role != "brace" else 0.32
    elif state == "sliding":
        score = 0.68
    elif state == "lifting":
        score = 0.72 if gap < 0.15 else 0.88
    elif state == "airborne":
        score = 0.92
    if manifold >= 3 and state in ("grounded", "planted"):
        score = min(score, 0.1)
    return _load_band(score)


def _balance_load_band(balance):
    if not isinstance(balance, dict):
        return _load_band(0.0)
    risk = float(balance.get("stability_risk") or 0.0)
    return _load_band(risk)


def _blackboard_row_style(row):
    if not isinstance(row, dict):
        return CYAN
    state = str(row.get("tolerance_state") or "INFO").strip().upper()
    if state == "CRITICAL":
        return RED
    if state == "DEGRADED":
        return ORANGE
    if state == "WATCH":
        return YELLOW
    if state == "WITHIN":
        return GREEN
    return CYAN


def _blackboard_anchor_text(anchor):
    if not isinstance(anchor, dict):
        return "global"
    kind = str(anchor.get("type") or "global").strip().lower() or "global"
    if kind == "bone":
        return f"bone:{str(anchor.get('id') or '')}"
    if kind == "contact":
        return f"contact:{str(anchor.get('id') or '')}"
    if kind == "object":
        return f"object:{str(anchor.get('key') or '')}"
    if kind == "world":
        pos = anchor.get("position") if isinstance(anchor.get("position"), dict) else {}
        return "world:(" + f"{float(pos.get('x') or 0.0):.2f}, {float(pos.get('y') or 0.0):.2f}, {float(pos.get('z') or 0.0):.2f})"
    if kind == "screen":
        pos = anchor.get("position") if isinstance(anchor.get("position"), dict) else {}
        return "screen:(" + f"{float(pos.get('x') or 0.0):.2f}, {float(pos.get('y') or 0.0):.2f})"
    return kind


def _format_blackboard_row(row):
    if not isinstance(row, dict):
        return ""
    style = _blackboard_row_style(row)
    source = str(row.get("source") or "MEAS").strip().upper()
    state = str(row.get("tolerance_state") or "INFO").strip().upper()
    family = str(row.get("family") or "misc").strip()
    label = str(row.get("label") or row.get("id") or "row")
    value_text = str(row.get("value_text") or row.get("value") or "").strip()
    anchor_text = _blackboard_anchor_text(row.get("anchor"))
    priority = float(row.get("priority") or 0.0)
    session_weight = float(row.get("session_weight") or 0.0)
    line = (
        f"[{source}/{state}] "
        + label
        + (f": {value_text}" if value_text else "")
        + f" / {family}"
        + f" / @ {anchor_text}"
        + f" / p {priority:.2f}"
        + f" / s {session_weight:.2f}"
    )
    detail = str(row.get("detail") or "").strip()
    if detail:
        line += " / " + detail
    return _style_inline(line, style)


def _blackboard_family_rows(rows, family, limit):
    target = str(family or "").strip()
    filtered = [
        row
        for row in list(rows or [])
        if isinstance(row, dict) and str(row.get("family") or "").strip() == target
    ]
    filtered.sort(
        key=lambda row: float(row.get("priority") or 0.0) + float(row.get("session_weight") or 0.0),
        reverse=True,
    )
    return filtered[: max(0, int(limit or 0))]


def _render_blackboard_section(snapshot, width):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    blackboard = snapshot.get("blackboard") if isinstance(snapshot.get("blackboard"), dict) else {}
    working = blackboard.get("working_set") if isinstance(blackboard.get("working_set"), dict) else {}
    query_thread = working.get("query_thread") if isinstance(working.get("query_thread"), dict) else {}
    output_state = _output_state(snapshot)
    pan_probe = output_state.get("pan_probe") if isinstance(output_state.get("pan_probe"), dict) else {}
    field_disposition = output_state.get("field_disposition") if isinstance(output_state.get("field_disposition"), dict) else {}
    watch_board = output_state.get("watch_board") if isinstance(output_state.get("watch_board"), dict) else {}
    equilibrium = output_state.get("equilibrium") if isinstance(output_state.get("equilibrium"), dict) else {}
    drift = output_state.get("drift") if isinstance(output_state.get("drift"), dict) else {}
    placement = _output_state_placement(output_state)
    correlator = _output_state_correlator(output_state)
    entry_gate = _output_state_entry_gate(output_state)
    continuity_cue = _output_state_continuity_cue(output_state)
    tinkerbell_attention = _output_state_tinkerbell_attention(output_state)
    render_spine_packet = _output_state_render_spine_packet(output_state)
    docs_packet = _output_state_docs_packet(output_state)
    workspace_packet = _output_state_workspace_packet(output_state)
    continuity_packet = _output_state_continuity_packet(output_state)
    misunderstanding_box = _output_state_misunderstanding_box(output_state)
    technolit_measure = _output_state_technolit_measure(output_state)
    technolit_distribution_packet = _output_state_technolit_distribution_packet(output_state)
    technolit_treasury_bridge_packet = _output_state_technolit_treasury_bridge_packet(output_state)
    holder_snapshot_packet = _output_state_holder_snapshot_packet(output_state)
    raid_contribution_packet = _output_state_raid_contribution_packet(output_state)
    settlement_epoch_packet = _output_state_settlement_epoch_packet(output_state)
    hold_door_raid_report_packet = _output_state_hold_door_raid_report_packet(output_state)
    hold_door_comedia_packet = _output_state_hold_door_comedia_packet(output_state)
    threat_bounty_packet = _output_state_threat_bounty_packet(output_state)
    active_pointer = (
        tinkerbell_attention.get("active_pointer")
        if isinstance(tinkerbell_attention.get("active_pointer"), dict)
        else {}
    )
    render_spine_front = (
        render_spine_packet.get("current_front")
        if isinstance(render_spine_packet.get("current_front"), dict)
        else {}
    )
    render_spine_pointer = (
        render_spine_packet.get("active_pointer")
        if isinstance(render_spine_packet.get("active_pointer"), dict)
        else {}
    )
    render_spine_captures = (
        render_spine_packet.get("capture_receipts")
        if isinstance(render_spine_packet.get("capture_receipts"), list)
        else []
    )
    confidence = output_state.get("confidence") if isinstance(output_state.get("confidence"), dict) else {}
    freshness = output_state.get("freshness") if isinstance(output_state.get("freshness"), dict) else {}
    focus = blackboard.get("focus") if isinstance(blackboard.get("focus"), dict) else {}
    rows = blackboard.get("rows") if isinstance(blackboard.get("rows"), list) else []
    families = blackboard.get("families") if isinstance(blackboard.get("families"), list) else []
    range_gate_rows = _blackboard_family_rows(rows, "range_gate", 6)
    reach_envelope_rows = _blackboard_family_rows(rows, "reach_envelope", 6)
    lines = [
        f"row_count={int(blackboard.get('row_count') or 0)} families={families}",
        f"focus kind={focus.get('kind', '')} id={focus.get('id', '')} class={focus.get('target_class', '')}",
        "output_summary=" + str(output_state.get("summary") or ""),
        "render_spine="
        + str(render_spine_packet.get("spine_id") or "")
        + " frame="
        + str(render_spine_packet.get("frame_id") or "")
        + " trace="
        + str(render_spine_packet.get("trace_id") or ""),
        "render_front="
        + str(render_spine_front.get("objective_label") or render_spine_front.get("objective_id") or "")
        + " / focus "
        + str(render_spine_front.get("focus_key") or render_spine_packet.get("focus_key") or ""),
        "render_pointer="
        + str(render_spine_pointer.get("target_kind") or "")
        + " / "
        + str(render_spine_pointer.get("target") or "")
        + " / next "
        + str(render_spine_pointer.get("expected_read") or ""),
        "render_captures="
        + str(
            [
                str((row or {}).get("key") or "")
                + ("*" if bool((row or {}).get("active")) else "")
                for row in render_spine_captures[:4]
                if isinstance(row, dict)
            ]
        ),
        "output_equilibrium="
        + str(equilibrium.get("band") or "")
        + " drift="
        + str(drift.get("band") or "")
        + " confidence="
        + str(confidence.get("band") or ""),
        "output_techlit="
        + str(technolit_measure.get("band") or "quiet")
        + " symbol="
        + str(technolit_measure.get("symbol") or "")
        + " intake="
        + str(technolit_measure.get("creator_rewards_unclaimed_sol") or 0)
        + " SOL flow="
        + str(technolit_measure.get("flow_posture") or "")
        + " burn="
        + str(technolit_measure.get("burn_gate") or ""),
        "output_distribution="
        + str(technolit_distribution_packet.get("stage") or "inactive")
        + " agent="
        + str(technolit_distribution_packet.get("tokenized_agent_mode") or "n/a")
        + " next="
        + str(technolit_distribution_packet.get("next_contract") or ""),
        "output_treasury_bridge="
        + str(technolit_treasury_bridge_packet.get("stage") or "inactive")
        + " asset="
        + str(technolit_treasury_bridge_packet.get("settlement_asset") or "n/a")
        + " mode="
        + str(technolit_treasury_bridge_packet.get("settlement_style") or "n/a")
        + " next="
        + str(technolit_treasury_bridge_packet.get("next_contract") or ""),
        "output_holder_snapshot="
        + str(holder_snapshot_packet.get("stage") or "inactive")
        + " camp="
        + str(holder_snapshot_packet.get("camp_label") or "n/a")
        + " retention="
        + str(holder_snapshot_packet.get("retention_band") or "n/a"),
        "output_raid_contribution="
        + str(raid_contribution_packet.get("stage") or "inactive")
        + " raid="
        + str(raid_contribution_packet.get("raid_label") or "n/a")
        + " evidence="
        + str(raid_contribution_packet.get("evidence_mode") or "n/a"),
        "output_settlement_epoch="
        + str(settlement_epoch_packet.get("stage") or "inactive")
        + " asset="
        + str(settlement_epoch_packet.get("settlement_asset") or "n/a")
        + " weekly="
        + str((((settlement_epoch_packet.get("game_clock") or {}).get("weekly")) or "n/a")),
        "output_hold_door_report="
        + str(hold_door_raid_report_packet.get("stage") or "inactive")
        + " name="
        + str(hold_door_raid_report_packet.get("display_name") or "n/a"),
        "output_hold_door_comedia="
        + str(hold_door_comedia_packet.get("stage") or "inactive")
        + " react="
        + str(hold_door_comedia_packet.get("reaction") or "n/a")
        + " bpm="
        + str(hold_door_comedia_packet.get("tempo_bpm") or 0),
        "output_threat_bounty="
        + str(threat_bounty_packet.get("stage") or "inactive")
        + " mode="
        + str(threat_bounty_packet.get("jackpot_mode") or "n/a"),
        "output_freshness=age_ms "
        + str(int(freshness.get("age_ms") or 0))
        + " mirror_lag="
        + str(bool(freshness.get("mirror_lag"))),
        "output_sources=" + str(_output_state_ready_sources(output_state)),
        "field_disposition="
        + str(field_disposition.get("medium_kind") or "")
        + " / "
        + str(field_disposition.get("propagation_mode") or "")
        + " / settle "
        + str(field_disposition.get("settling_band") or ""),
        "pan_probe="
        + str(pan_probe.get("band") or "")
        + " rotational="
        + str(bool(pan_probe.get("rotational_grounding")))
        + " writer="
        + str((((pan_probe.get("writer_identity") or {}).get("last_sync_reason")) or "")),
        "watch_board="
        + str(watch_board.get("band") or "")
        + " alerts="
        + str(watch_board.get("alerts") or []),
        *_sequence_field_blackboard_lines(snapshot),
        "trajectory_correlator="
        + str((((correlator.get("correlation") or {}).get("relation")) or ""))
        + " grade="
        + str(correlator.get("grade") or "")
        + " return="
        + str((((correlator.get("return_path") or {}).get("reads")) or [])),
        "entry_gate="
        + str(entry_gate.get("band") or "quiet")
        + " status="
        + str(entry_gate.get("status") or "")
        + " verified="
        + str(list(entry_gate.get("verified_surfaces") or [])[:4]),
        "entry_gate_reads=" + str(list(entry_gate.get("required_reads") or [])[:4]),
        "continuity_cue="
        + str(continuity_cue.get("severity") or "quiet")
        + " needed="
        + str(bool(continuity_cue.get("needed")))
        + " next="
        + str(continuity_cue.get("next_action") or ""),
        "misunderstanding_box="
        + str(misunderstanding_box.get("band") or "quiet")
        + " kind="
        + str(misunderstanding_box.get("unknown_kind") or "")
        + " teaching="
        + str(bool(misunderstanding_box.get("operator_teaching_needed"))),
        "misunderstanding_summary=" + str(misunderstanding_box.get("summary") or ""),
        "misunderstanding_reads=" + str(list(misunderstanding_box.get("required_reads") or [])[:4]),
        "tinkerbell_attention="
        + str(tinkerbell_attention.get("band") or "quiet")
        + " kind="
        + str(active_pointer.get("target_kind") or tinkerbell_attention.get("attention_kind") or "")
        + " target="
        + str(active_pointer.get("target") or tinkerbell_attention.get("attention_target") or "")
        + " hold="
        + str(bool(active_pointer.get("hold_candidate", tinkerbell_attention.get("hold_candidate")))),
        "tinkerbell_pointer="
        + str(active_pointer.get("why_now") or active_pointer.get("why_this_spot") or tinkerbell_attention.get("summary") or "")
        + " / next "
        + str(active_pointer.get("expected_read") or ""),
        "docs_packet="
        + str(docs_packet.get("band") or "empty")
        + " posture="
        + str(docs_packet.get("posture") or "")
        + " context="
        + str(docs_packet.get("context_kind") or "")
        + " results="
        + str(int(docs_packet.get("result_count") or 0)),
        "docs_summary=" + str(docs_packet.get("summary") or ""),
        "docs_active="
        + str(docs_packet.get("active_doc") or "")
        + " / index "
        + str(docs_packet.get("continuity_index") or ""),
        "docs_top_results="
        + str(
            [
                str((row or {}).get("key") or "")
                for row in list(docs_packet.get("top_results") or [])[:3]
                if isinstance(row, dict)
            ]
        ),
        "docs_update_lane=" + str(list(docs_packet.get("update_lane") or [])[:4]),
        "workspace_packet="
        + str(workspace_packet.get("band") or "idle")
        + " active="
        + str(bool(workspace_packet.get("active")))
        + " doc="
        + str(workspace_packet.get("active_doc") or workspace_packet.get("bag_doc_key") or ""),
        "workspace_paths=" + str(list(workspace_packet.get("last_modified_paths") or [])[:4]),
        "workspace_update_lane=" + str(list(workspace_packet.get("update_lane") or [])[:4]),
        "continuity_packet="
        + str(continuity_packet.get("band") or "empty")
        + " posture="
        + str(continuity_packet.get("posture") or "")
        + " session="
        + str(continuity_packet.get("best_session_id") or ""),
        "continuity_summary=" + str(continuity_packet.get("summary") or ""),
        "continuity_open_loops=" + str(list(continuity_packet.get("open_loops") or [])[:3]),
        "continuity_recent_pressures=" + str(list(continuity_packet.get("recent_pressures") or [])[:3]),
        "continuity_update_lane=" + str(list(continuity_packet.get("update_lane") or [])[:4]),
        "placement="
        + str(placement.get("subject") or "")
        + " / "
        + str(placement.get("objective") or "")
        + " / seam "
        + str(placement.get("seam") or "")
        + " / drift "
        + str((((placement.get("drift") or {}).get("band")) or "")),
        "placement_evidence="
        + str((((placement.get("evidence") or {}).get("anchor_row_ids")) or []))
        + " / sources "
        + str((((placement.get("evidence") or {}).get("ready_sources")) or [])),
        "placement_next="
        + str((((placement.get("next") or {}).get("reads")) or []))
        + " / help "
        + str((((placement.get("next") or {}).get("help")) or [])),
        "query_sequence=" + str(query_thread.get("sequence_id") or ""),
        "query_segment="
        + str(query_thread.get("segment_id") or "")
        + " status="
        + str(query_thread.get("status") or ""),
        "query_pivot=" + str(query_thread.get("current_pivot_id") or ""),
        "priority_pivots="
        + str(
            [
                str((row or {}).get("pivot_id") or "")
                for row in list(query_thread.get("priority_pivots") or [])[:4]
                if isinstance(row, dict)
            ]
        ),
        "query_subject=" + str(query_thread.get("subject_key") or ""),
        "query_objective="
        + str(query_thread.get("objective_label") or query_thread.get("objective_id") or "scene_orientation"),
        "visible_read=" + str(query_thread.get("visible_read") or ""),
        "query_anchor_rows=" + str(query_thread.get("anchor_row_ids") or working.get("lead_row_ids", [])),
        f"active_controller={working.get('active_controller_id', '')} active_route={working.get('active_route_id', '')}",
        f"selection={working.get('selected_bone_ids', [])}",
        f"intended_support={working.get('intended_support_set', [])} missing_support={working.get('missing_support_set', [])}",
        f"lead_rows={working.get('lead_row_ids', [])}",
        f"range_gate_targets={working.get('range_gate_targets', [])}",
        f"reach_envelope_targets={working.get('reach_envelope_targets', [])}",
        "query_next_reads="
        + str(
            [
                _format_query_lane_entry(row)
                for row in list(query_thread.get("next_reads") or [])[:4]
                if isinstance(row, dict)
            ]
        ),
        "query_help_lane="
        + str(
            [
                _format_query_lane_entry(row)
                for row in list(query_thread.get("help_lane") or [])[:3]
                if isinstance(row, dict)
            ]
        ),
        "query_guardrail=" + str(query_thread.get("raw_state_guardrail") or ""),
    ]
    if range_gate_rows:
        lines.append("RANGE_GATES:")
        for row in range_gate_rows:
            rendered = _format_blackboard_row(row)
            if rendered:
                lines.append(rendered)
    if reach_envelope_rows:
        lines.append("REACH_ENVELOPE:")
        for row in reach_envelope_rows:
            rendered = _format_blackboard_row(row)
            if rendered:
                lines.append(rendered)
    for row in rows[:12]:
        rendered = _format_blackboard_row(row)
        if rendered:
            lines.append(rendered)
    return _wrap_block("\n".join(lines), width)


def _format_query_lane_entry(row):
    row = row if isinstance(row, dict) else {}
    tool = str(row.get("tool") or "")
    args = row.get("args") if isinstance(row.get("args"), dict) else {}
    if tool == "env_read":
        return "env_read(query='" + str(args.get("query") or "") + "')"
    if tool == "env_report":
        return "env_report(report_id='" + str(args.get("report_id") or "") + "')"
    if tool == "env_help":
        topic = str(args.get("topic") or "")
        category = str(args.get("category") or "")
        search = str(args.get("search") or "")
        if topic:
            return "env_help(topic='" + topic + "')"
        if category:
            return "env_help(category='" + category + "')"
        if search:
            return "env_help(search='" + search + "')"
        return "env_help(topic='index')"
    return tool or "read"


def _output_state(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    return snapshot.get("output_state") if isinstance(snapshot.get("output_state"), dict) else {}


def _output_state_placement(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    return output_state.get("placement") if isinstance(output_state.get("placement"), dict) else {}


def _output_state_correlator(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    return output_state.get("trajectory_correlator") if isinstance(output_state.get("trajectory_correlator"), dict) else {}


def _output_state_continuity_cue(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    return output_state.get("continuity_cue") if isinstance(output_state.get("continuity_cue"), dict) else {}


def _output_state_entry_gate(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    return output_state.get("entry_gate") if isinstance(output_state.get("entry_gate"), dict) else {}


def _output_state_tinkerbell_attention(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    return output_state.get("tinkerbell_attention") if isinstance(output_state.get("tinkerbell_attention"), dict) else {}


def _output_state_render_spine_packet(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    return output_state.get("render_spine_packet") if isinstance(output_state.get("render_spine_packet"), dict) else {}


def _output_state_docs_packet(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    return output_state.get("docs_packet") if isinstance(output_state.get("docs_packet"), dict) else {}


def _output_state_workspace_packet(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    return output_state.get("workspace_packet") if isinstance(output_state.get("workspace_packet"), dict) else {}


def _output_state_continuity_packet(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    return output_state.get("continuity_packet") if isinstance(output_state.get("continuity_packet"), dict) else {}


def _output_state_misunderstanding_box(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    return output_state.get("misunderstanding_box") if isinstance(output_state.get("misunderstanding_box"), dict) else {}


def _output_state_technolit_measure(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    equilibrium = output_state.get("equilibrium") if isinstance(output_state.get("equilibrium"), dict) else {}
    return equilibrium.get("technolit_measure") if isinstance(equilibrium.get("technolit_measure"), dict) else {}


def _output_state_technolit_distribution_packet(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    packet = output_state.get("technolit_distribution_packet")
    return packet if isinstance(packet, dict) else {}


def _output_state_technolit_treasury_bridge_packet(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    packet = output_state.get("technolit_treasury_bridge_packet")
    return packet if isinstance(packet, dict) else {}


def _output_state_holder_snapshot_packet(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    packet = output_state.get("holder_snapshot_packet")
    return packet if isinstance(packet, dict) else {}


def _output_state_raid_contribution_packet(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    packet = output_state.get("raid_contribution_packet")
    return packet if isinstance(packet, dict) else {}


def _output_state_settlement_epoch_packet(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    packet = output_state.get("settlement_epoch_packet")
    return packet if isinstance(packet, dict) else {}


def _output_state_hold_door_raid_report_packet(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    packet = output_state.get("hold_door_raid_report_packet")
    return packet if isinstance(packet, dict) else {}


def _output_state_hold_door_comedia_packet(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    packet = output_state.get("hold_door_comedia_packet")
    return packet if isinstance(packet, dict) else {}


def _output_state_threat_bounty_packet(output_state):
    output_state = output_state if isinstance(output_state, dict) else {}
    packet = output_state.get("threat_bounty_packet")
    return packet if isinstance(packet, dict) else {}


def _output_state_ready_sources(output_state):
    sources = output_state.get("sources") if isinstance(output_state.get("sources"), dict) else {}
    return [
        str(key)
        for key, value in list(sources.items())
        if isinstance(value, dict) and value.get("ready")
    ]


def _consult_query_thread(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    blackboard = snapshot.get("blackboard") if isinstance(snapshot.get("blackboard"), dict) else {}
    working = blackboard.get("working_set") if isinstance(blackboard.get("working_set"), dict) else {}
    query_thread = working.get("query_thread") if isinstance(working.get("query_thread"), dict) else {}
    output_state = _output_state(snapshot)
    pan_probe = output_state.get("pan_probe") if isinstance(output_state.get("pan_probe"), dict) else {}
    field_disposition = output_state.get("field_disposition") if isinstance(output_state.get("field_disposition"), dict) else {}
    watch_board = output_state.get("watch_board") if isinstance(output_state.get("watch_board"), dict) else {}
    equilibrium = output_state.get("equilibrium") if isinstance(output_state.get("equilibrium"), dict) else {}
    drift = output_state.get("drift") if isinstance(output_state.get("drift"), dict) else {}
    placement = _output_state_placement(output_state)
    correlator = _output_state_correlator(output_state)
    entry_gate = _output_state_entry_gate(output_state)
    continuity_cue = _output_state_continuity_cue(output_state)
    workspace_packet = _output_state_workspace_packet(output_state)
    misunderstanding_box = _output_state_misunderstanding_box(output_state)
    tinkerbell_attention = _output_state_tinkerbell_attention(output_state)
    render_spine_packet = _output_state_render_spine_packet(output_state)
    technolit_measure = _output_state_technolit_measure(output_state)
    technolit_distribution_packet = _output_state_technolit_distribution_packet(output_state)
    technolit_treasury_bridge_packet = _output_state_technolit_treasury_bridge_packet(output_state)
    holder_snapshot_packet = _output_state_holder_snapshot_packet(output_state)
    raid_contribution_packet = _output_state_raid_contribution_packet(output_state)
    settlement_epoch_packet = _output_state_settlement_epoch_packet(output_state)
    hold_door_raid_report_packet = _output_state_hold_door_raid_report_packet(output_state)
    hold_door_comedia_packet = _output_state_hold_door_comedia_packet(output_state)
    threat_bounty_packet = _output_state_threat_bounty_packet(output_state)
    active_pointer = (
        tinkerbell_attention.get("active_pointer")
        if isinstance(tinkerbell_attention.get("active_pointer"), dict)
        else {}
    )
    render_spine_front = (
        render_spine_packet.get("current_front")
        if isinstance(render_spine_packet.get("current_front"), dict)
        else {}
    )
    render_spine_pointer = (
        render_spine_packet.get("active_pointer")
        if isinstance(render_spine_packet.get("active_pointer"), dict)
        else {}
    )
    render_spine_captures = (
        render_spine_packet.get("capture_receipts")
        if isinstance(render_spine_packet.get("capture_receipts"), list)
        else []
    )
    confidence = output_state.get("confidence") if isinstance(output_state.get("confidence"), dict) else {}
    objective = str(query_thread.get("objective_label") or query_thread.get("objective_id") or "Scene Orientation")
    visible_read = str(query_thread.get("visible_read") or "")
    anchor_rows = query_thread.get("anchor_row_ids") if isinstance(query_thread.get("anchor_row_ids"), list) else working.get("lead_row_ids", [])
    help_lane = query_thread.get("help_lane") if isinstance(query_thread.get("help_lane"), list) else []
    return [
        "SEQUENCE: " + str(query_thread.get("sequence_id") or "n/a"),
        "SEGMENT: "
        + str(query_thread.get("segment_id") or "n/a")
        + " / status "
        + str(query_thread.get("status") or "active"),
        "SPINE: " + str(render_spine_packet.get("spine_id") or "n/a"),
        "FRAME: "
        + str(render_spine_packet.get("frame_id") or "n/a")
        + " / trace "
        + str(render_spine_packet.get("trace_id") or "n/a")
        + " / seq "
        + str(render_spine_packet.get("trace_seq") or 0),
        "PIVOT: "
        + str(query_thread.get("current_pivot_id") or "n/a")
        + " / retract "
        + (
            str(
                ((query_thread.get("priority_pivots") or [{}])[0] or {}).get(
                    "retract_to_after_completion"
                )
                or ""
            )
            or "n/a"
        ),
        "SUBJECT: " + str(query_thread.get("subject_key") or "n/a"),
        "OBJECTIVE: " + objective,
        "FRONT: "
        + str(render_spine_front.get("objective_label") or render_spine_front.get("objective_id") or "n/a")
        + " / focus "
        + str(render_spine_front.get("focus_key") or render_spine_packet.get("focus_key") or "n/a"),
        "PLACEMENT: "
        + str(placement.get("subject") or "n/a")
        + " / "
        + str(placement.get("objective") or "n/a")
        + " / seam "
        + str(placement.get("seam") or "n/a"),
        "SPINE POINTER: "
        + str(render_spine_pointer.get("target_kind") or "n/a")
        + " / "
        + str(render_spine_pointer.get("target") or "n/a")
        + " / next "
        + str(render_spine_pointer.get("expected_read") or "n/a"),
        "SPINE CAPTURES: "
        + str(
            [
                str((row or {}).get("key") or "")
                + ("*" if bool((row or {}).get("active")) else "")
                for row in render_spine_captures[:4]
                if isinstance(row, dict)
            ]
        ),
        "VISIBLE READ: " + (visible_read or "n/a"),
        "SEED: selected "
        + str(working.get("selected_bone_ids", []))
        + " / supporting "
        + str(working.get("supporting_joint_ids", [])),
        "ROUTE: active "
        + str(working.get("active_route_id", ""))
        + " / intended "
        + str(working.get("intended_support_set", []))
        + " / missing "
        + str(working.get("missing_support_set", [])),
        "OUTPUT: "
        + str(equilibrium.get("band") or "n/a")
        + " / drift "
        + str(drift.get("band") or "n/a")
        + " / confidence "
        + str(confidence.get("band") or "n/a"),
        "TECHLIT: "
        + str(technolit_measure.get("band") or "quiet")
        + " / "
        + str(technolit_measure.get("symbol") or "n/a")
        + " / intake "
        + str(technolit_measure.get("creator_rewards_unclaimed_sol") or 0)
        + " SOL / flow "
        + str(technolit_measure.get("flow_posture") or "n/a")
        + " / burn "
        + str(technolit_measure.get("burn_gate") or "n/a"),
        "TECHLIT POLICY: "
        + str(technolit_distribution_packet.get("stage") or "inactive")
        + " / agent "
        + str(technolit_distribution_packet.get("tokenized_agent_mode") or "n/a")
        + " / next "
        + str(technolit_distribution_packet.get("next_contract") or "n/a"),
        "TREASURY BRIDGE: "
        + str(technolit_treasury_bridge_packet.get("stage") or "inactive")
        + " / asset "
        + str(technolit_treasury_bridge_packet.get("settlement_asset") or "n/a")
        + " / mode "
        + str(technolit_treasury_bridge_packet.get("settlement_style") or "n/a")
        + " / next "
        + str(technolit_treasury_bridge_packet.get("next_contract") or "n/a"),
        "HOLDER SNAPSHOT: "
        + str(holder_snapshot_packet.get("stage") or "inactive")
        + " / camp "
        + str(holder_snapshot_packet.get("camp_label") or "n/a")
        + " / retention "
        + str(holder_snapshot_packet.get("retention_band") or "n/a"),
        "RAID CONTRIBUTION: "
        + str(raid_contribution_packet.get("stage") or "inactive")
        + " / raid "
        + str(raid_contribution_packet.get("raid_label") or "n/a")
        + " / evidence "
        + str(raid_contribution_packet.get("evidence_mode") or "n/a"),
        "SETTLEMENT EPOCH: "
        + str(settlement_epoch_packet.get("stage") or "inactive")
        + " / asset "
        + str(settlement_epoch_packet.get("settlement_asset") or "n/a")
        + " / clocks "
        + str((((settlement_epoch_packet.get("game_clock") or {}).get("hourly")) or "n/a"))
        + " -> "
        + str((((settlement_epoch_packet.get("game_clock") or {}).get("weekly")) or "n/a"))
        + " / breaker "
        + str(settlement_epoch_packet.get("circuit_breaker_mode") or "n/a"),
        "HOLD DOOR RAID REPORT: "
        + str(hold_door_raid_report_packet.get("stage") or "inactive")
        + " / "
        + str(hold_door_raid_report_packet.get("display_name") or "n/a")
        + " / asset "
        + str(hold_door_raid_report_packet.get("custody_asset") or "n/a")
        + " / cadence "
        + str(hold_door_raid_report_packet.get("cadence_line") or "n/a")
        + " / safety "
        + str(hold_door_raid_report_packet.get("safety_line") or "n/a"),
        "HOLD DOOR COMEDIA: "
        + str(hold_door_comedia_packet.get("stage") or "inactive")
        + " / mood "
        + str(hold_door_comedia_packet.get("mood") or "n/a")
        + " / react "
        + str(hold_door_comedia_packet.get("reaction") or "n/a")
        + " / bpm "
        + str(hold_door_comedia_packet.get("tempo_bpm") or 0)
        + " / text "
        + str(hold_door_comedia_packet.get("caption_line") or "n/a"),
        "THREAT BOUNTY: "
        + str(threat_bounty_packet.get("stage") or "inactive")
        + " / threats "
        + str(threat_bounty_packet.get("active_threats") or [])
        + " / mode "
        + str(threat_bounty_packet.get("jackpot_mode") or "n/a"),
        "CORRELATOR: "
        + str((((correlator.get("correlation") or {}).get("relation")) or "n/a"))
        + " / grade "
        + str(correlator.get("grade") or "n/a")
        + " / return "
        + str((((correlator.get("return_path") or {}).get("reads")) or [])),
        "ENTRY GATE: "
        + str(entry_gate.get("band") or "quiet")
        + " / status "
        + str(entry_gate.get("status") or "n/a")
        + " / verified "
        + str(list(entry_gate.get("verified_surfaces") or [])[:4]),
        "CONTINUITY CUE: "
        + str(continuity_cue.get("severity") or "quiet")
        + " / needed "
        + str(bool(continuity_cue.get("needed")))
        + " / next "
        + str(continuity_cue.get("next_action") or "Continue Current Sequence"),
        "MISUNDERSTANDING BOX: "
        + str(misunderstanding_box.get("band") or "quiet")
        + " / kind "
        + str(misunderstanding_box.get("unknown_kind") or "n/a")
        + " / teaching "
        + str(bool(misunderstanding_box.get("operator_teaching_needed"))),
        "BOX READS: "
        + str(list(misunderstanding_box.get("required_reads") or [])[:4])
        + " / release "
        + str(misunderstanding_box.get("release_condition") or "n/a"),
        "ENTRY READS: " + str(list(entry_gate.get("required_reads") or [])[:4]),
        "TINKERBELL: "
        + str(tinkerbell_attention.get("band") or "quiet")
        + " / "
        + str(active_pointer.get("target_kind") or tinkerbell_attention.get("attention_kind") or "n/a")
        + " / "
        + str(active_pointer.get("target") or tinkerbell_attention.get("attention_target") or "n/a"),
        "POINTER WHY: "
        + str(active_pointer.get("why_now") or active_pointer.get("why_this_spot") or tinkerbell_attention.get("summary") or "n/a")
        + " / next "
        + str(active_pointer.get("expected_read") or "n/a"),
        "FIELD: "
        + str(field_disposition.get("medium_kind") or "n/a")
        + " / "
        + str(field_disposition.get("propagation_mode") or "n/a")
        + " / settle "
        + str(field_disposition.get("settling_band") or "n/a"),
        "PAN: "
        + str(pan_probe.get("band") or "n/a")
        + " / rotational "
        + str(bool(pan_probe.get("rotational_grounding")))
        + " / writer "
        + str((((pan_probe.get("writer_identity") or {}).get("last_sync_reason")) or "n/a")),
        "WATCH: "
        + str(watch_board.get("band") or "n/a")
        + " / alerts "
        + str(watch_board.get("alerts") or []),
        "WORKSPACE: "
        + str(workspace_packet.get("band") or "idle")
        + " / doc "
        + str(workspace_packet.get("active_doc") or workspace_packet.get("bag_doc_key") or "n/a")
        + " / paths "
        + str(list(workspace_packet.get("last_modified_paths") or [])[:4]),
        "OUTPUT SUMMARY: " + str(output_state.get("summary") or "n/a"),
        "PLACEMENT EVIDENCE: anchors "
        + str((((placement.get("evidence") or {}).get("anchor_row_ids")) or []))
        + " / sources "
        + str((((placement.get("evidence") or {}).get("ready_sources")) or [])),
        "PLACEMENT NEXT: "
        + str((((placement.get("next") or {}).get("reads")) or [])),
        "ANCHOR ROWS: " + str(anchor_rows or []),
        "HELP AUTHORITY: env_help",
        "HELP LANE: " + str([_format_query_lane_entry(row) for row in help_lane[:4] if isinstance(row, dict)]),
    ]


def _consult_query_evidence(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    output_state = _output_state(snapshot)
    pan_probe = output_state.get("pan_probe") if isinstance(output_state.get("pan_probe"), dict) else {}
    field_disposition = output_state.get("field_disposition") if isinstance(output_state.get("field_disposition"), dict) else {}
    watch_board = output_state.get("watch_board") if isinstance(output_state.get("watch_board"), dict) else {}
    placement = _output_state_placement(output_state)
    correlator = _output_state_correlator(output_state)
    entry_gate = _output_state_entry_gate(output_state)
    continuity_cue = _output_state_continuity_cue(output_state)
    workspace_packet = _output_state_workspace_packet(output_state)
    misunderstanding_box = _output_state_misunderstanding_box(output_state)
    tinkerbell_attention = _output_state_tinkerbell_attention(output_state)
    technolit_measure = _output_state_technolit_measure(output_state)
    technolit_distribution_packet = _output_state_technolit_distribution_packet(output_state)
    technolit_treasury_bridge_packet = _output_state_technolit_treasury_bridge_packet(output_state)
    holder_snapshot_packet = _output_state_holder_snapshot_packet(output_state)
    raid_contribution_packet = _output_state_raid_contribution_packet(output_state)
    settlement_epoch_packet = _output_state_settlement_epoch_packet(output_state)
    hold_door_raid_report_packet = _output_state_hold_door_raid_report_packet(output_state)
    hold_door_comedia_packet = _output_state_hold_door_comedia_packet(output_state)
    threat_bounty_packet = _output_state_threat_bounty_packet(output_state)
    active_pointer = (
        tinkerbell_attention.get("active_pointer")
        if isinstance(tinkerbell_attention.get("active_pointer"), dict)
        else {}
    )
    receipts = output_state.get("receipts") if isinstance(output_state.get("receipts"), dict) else {}
    freshness = output_state.get("freshness") if isinstance(output_state.get("freshness"), dict) else {}
    blackboard = snapshot.get("blackboard") if isinstance(snapshot.get("blackboard"), dict) else {}
    working = blackboard.get("working_set") if isinstance(blackboard.get("working_set"), dict) else {}
    query_thread = working.get("query_thread") if isinstance(working.get("query_thread"), dict) else {}
    next_reads = query_thread.get("next_reads") if isinstance(query_thread.get("next_reads"), list) else []
    help_lane = query_thread.get("help_lane") if isinstance(query_thread.get("help_lane"), list) else []
    lines = []
    max_next_reads = 3 if help_lane else 4
    for index, row in enumerate(next_reads[:max_next_reads], start=1):
        if not isinstance(row, dict):
            continue
        label = _format_query_lane_entry(row)
        lines.append(str(index) + ". " + label + " — " + str(row.get("reason") or ""))
    for index, row in enumerate(help_lane[:4], start=1):
        if not isinstance(row, dict):
            continue
        label = _format_query_lane_entry(row)
        lines.append("H" + str(index) + ". " + label + " — " + str(row.get("reason") or ""))
    pivot_ids = [
        str((row or {}).get("pivot_id") or "")
        for row in list(query_thread.get("priority_pivots") or [])[:4]
        if isinstance(row, dict)
    ]
    if pivot_ids:
        lines.append("PIVOTS: " + str(pivot_ids))
    if query_thread.get("session_id"):
        lines.append("SESSION: " + str(query_thread.get("session_id") or ""))
    if output_state:
        lines.append("OUTPUT SOURCES: " + str(_output_state_ready_sources(output_state)))
        lines.append(
            "PLACEMENT: "
            + str(placement.get("subject") or "n/a")
            + " / "
            + str(placement.get("objective") or "n/a")
            + " / seam "
            + str(placement.get("seam") or "n/a")
        )
        lines.append(
            "PLACEMENT DRIFT: "
            + str((((placement.get("drift") or {}).get("band")) or "n/a"))
            + " / "
            + str((((placement.get("drift") or {}).get("issues")) or []))
        )
        lines.append(
            "TRAJECTORY: "
            + str((((correlator.get("correlation") or {}).get("relation")) or "n/a"))
            + " / grade "
            + str(correlator.get("grade") or "n/a")
        )
        lines.append(
            "ENTRY GATE: "
            + str(entry_gate.get("band") or "quiet")
            + " / "
            + str(entry_gate.get("status") or "n/a")
            + " / reads "
            + str(list(entry_gate.get("required_reads") or [])[:4])
        )
        lines.append(
            "CONTINUITY CUE: "
            + str(continuity_cue.get("severity") or "quiet")
            + " / "
            + str(continuity_cue.get("reasons") or [])
        )
        lines.append(
            "MISUNDERSTANDING BOX: "
            + str(misunderstanding_box.get("band") or "quiet")
            + " / "
            + str(misunderstanding_box.get("unknown_kind") or "n/a")
            + " / reads "
            + str(list(misunderstanding_box.get("required_reads") or [])[:4])
        )
        lines.append(
            "TINKERBELL: "
            + str(tinkerbell_attention.get("band") or "quiet")
            + " / "
            + str(active_pointer.get("target_kind") or tinkerbell_attention.get("attention_kind") or "n/a")
            + " / target "
            + str(active_pointer.get("target") or tinkerbell_attention.get("attention_target") or "n/a")
        )
        lines.append(
            "TECHLIT: "
            + str(technolit_measure.get("band") or "quiet")
            + " / "
            + str(technolit_measure.get("symbol") or "n/a")
            + " / intake "
            + str(technolit_measure.get("creator_rewards_unclaimed_sol") or 0)
            + " SOL / flow "
            + str(technolit_measure.get("flow_posture") or "n/a")
            + " / burn "
            + str(technolit_measure.get("burn_gate") or "n/a")
        )
        lines.append(
            "TECHLIT POLICY: "
            + str(technolit_distribution_packet.get("stage") or "inactive")
            + " / agent "
            + str(technolit_distribution_packet.get("tokenized_agent_mode") or "n/a")
            + " / next "
            + str(technolit_distribution_packet.get("next_contract") or "n/a")
            + " / line "
            + str(technolit_distribution_packet.get("public_line") or "n/a")
        )
        lines.append(
            "TREASURY BRIDGE: "
            + str(technolit_treasury_bridge_packet.get("stage") or "inactive")
            + " / asset "
            + str(technolit_treasury_bridge_packet.get("settlement_asset") or "n/a")
            + " / next "
            + str(technolit_treasury_bridge_packet.get("next_contract") or "n/a")
            + " / line "
            + str(technolit_treasury_bridge_packet.get("public_line") or "n/a")
        )
        lines.append(
            "HOLDER SNAPSHOT: "
            + str(holder_snapshot_packet.get("stage") or "inactive")
            + " / camp "
            + str(holder_snapshot_packet.get("camp_label") or "n/a")
            + " / retention "
            + str(holder_snapshot_packet.get("retention_band") or "n/a")
            + " / anti-snipe "
            + str(holder_snapshot_packet.get("anti_snipe_band") or "n/a")
        )
        lines.append(
            "RAID CONTRIBUTION: "
            + str(raid_contribution_packet.get("stage") or "inactive")
            + " / raid "
            + str(raid_contribution_packet.get("raid_label") or "n/a")
            + " / roles "
            + str(raid_contribution_packet.get("role_families") or [])
        )
        lines.append(
            "SETTLEMENT EPOCH: "
            + str(settlement_epoch_packet.get("stage") or "inactive")
            + " / asset "
            + str(settlement_epoch_packet.get("settlement_asset") or "n/a")
            + " / clocks "
            + str(((settlement_epoch_packet.get("game_clock") or {}).get("hourly")) or "n/a")
            + " -> "
            + str(((settlement_epoch_packet.get("game_clock") or {}).get("quarterly")) or "n/a")
            + " / breaker "
            + str(settlement_epoch_packet.get("circuit_breaker_mode") or "n/a")
        )
        lines.append(
            "HOLD DOOR RAID REPORT: "
            + str(hold_door_raid_report_packet.get("stage") or "inactive")
            + " / "
            + str(hold_door_raid_report_packet.get("display_name") or "n/a")
            + " / cadence "
            + str(hold_door_raid_report_packet.get("cadence_line") or "n/a")
            + " / safety "
            + str(hold_door_raid_report_packet.get("safety_line") or "n/a")
        )
        lines.append(
            "HOLD DOOR COMEDIA: "
            + str(hold_door_comedia_packet.get("stage") or "inactive")
            + " / mood "
            + str(hold_door_comedia_packet.get("mood") or "n/a")
            + " / react "
            + str(hold_door_comedia_packet.get("reaction") or "n/a")
            + " / bpm "
            + str(hold_door_comedia_packet.get("tempo_bpm") or 0)
            + " / text "
            + str(hold_door_comedia_packet.get("caption_line") or "n/a")
        )
        lines.append(
            "THREAT BOUNTY: "
            + str(threat_bounty_packet.get("stage") or "inactive")
            + " / threats "
            + str(threat_bounty_packet.get("active_threats") or [])
            + " / adjacent "
            + str(threat_bounty_packet.get("adjacent_reward_mode") or "n/a")
        )
        lines.append(
            "POINTER WHY: "
            + str(active_pointer.get("why_now") or active_pointer.get("why_this_spot") or tinkerbell_attention.get("summary") or "n/a")
            + " / next "
            + str(active_pointer.get("expected_read") or "n/a")
            + " / hold "
            + str(bool(active_pointer.get("hold_candidate", tinkerbell_attention.get("hold_candidate"))))
        )
        lines.append("FIELD DISPOSITION: " + str(field_disposition.get("summary") or "n/a"))
        lines.append("PAN PROBE: " + str(pan_probe.get("summary") or "n/a"))
        lines.append(
            "PAN WRITER: "
            + str((((pan_probe.get("writer_identity") or {}).get("last_sync_reason")) or "n/a"))
            + " / tool "
            + str((((pan_probe.get("writer_identity") or {}).get("render_last_tool_applied")) or "n/a"))
            + " / source "
            + str((((pan_probe.get("writer_identity") or {}).get("render_last_tool_source")) or "n/a"))
        )
        lines.append(
            "PAN CAPTURES: "
            + str(
                [
                    str((row or {}).get("key") or "")
                    for row in list(pan_probe.get("capture_surfaces") or [])[:6]
                    if isinstance(row, dict)
                ]
            )
        )
        lines.append(
            "WATCH BOARD: "
            + str(watch_board.get("band") or "n/a")
            + " / tracked "
            + str(
                [
                    str((row or {}).get("kind") or "")
                    for row in list(watch_board.get("tracked_events") or [])[:4]
                    if isinstance(row, dict)
                ]
            )
        )
        lines.append(
            "OUTPUT RECEIPT: "
            + str(receipts.get("last_action") or "n/a")
            + " / sync "
            + str(receipts.get("last_sync_reason") or "n/a")
        )
        lines.append(
            "MUTATION RECEIPTS: checkpoint "
            + str(receipts.get("checkpoint_id") or "n/a")
            + " / diff "
            + str(receipts.get("diff_ref") or "n/a")
            + " / workflow "
            + str(receipts.get("workflow_id") or "n/a")
        )
        lines.append(
            "MUTATION LANE: doc "
            + str(receipts.get("bag_doc_key") or receipts.get("active_doc") or "n/a")
            + " / slot "
            + str(receipts.get("slot_experiment_id") or "n/a")
            + " / paths "
            + str(list(receipts.get("last_modified_paths") or [])[:4])
        )
        lines.append(
            "WORKSPACE PACKET: "
            + str(workspace_packet.get("band") or "idle")
            + " / doc "
            + str(workspace_packet.get("active_doc") or workspace_packet.get("bag_doc_key") or "n/a")
            + " / update "
            + str(list(workspace_packet.get("update_lane") or [])[:4])
        )
        lines.append(
            "OUTPUT FRESHNESS: age_ms "
            + str(int(freshness.get("age_ms") or 0))
            + " / mirror_lag "
            + str(bool(freshness.get("mirror_lag")))
        )
        lines.append(
            "PLACEMENT NEXT: "
            + str((((placement.get("next") or {}).get("reads")) or []))
            + " / help "
            + str((((placement.get("next") or {}).get("help")) or []))
        )
        lines.append("RETURN PATH: " + str((((correlator.get("return_path") or {}).get("reads")) or [])))
        if continuity_cue.get("prompt"):
            lines.append("CUE PROMPT: " + str(continuity_cue.get("prompt") or ""))
    lines.append("GUARDRAIL: " + str(query_thread.get("raw_state_guardrail") or "raw shared_state last"))
    lines.append("PINNED: " + str(working.get("pinned_row_ids") or []))
    return lines


def _render_profiles_section(snapshot, width):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    profiles = snapshot.get("text_theater_profiles") if isinstance(snapshot.get("text_theater_profiles"), dict) else {}
    designation = profiles.get("designation_contract") if isinstance(profiles.get("designation_contract"), dict) else {}
    families = profiles.get("families") if isinstance(profiles.get("families"), dict) else {}
    surface_defaults = profiles.get("surface_defaults") if isinstance(profiles.get("surface_defaults"), dict) else {}
    lines = [
        f"registry_version={int(profiles.get('version') or 0)} default_family={profiles.get('default_family_id', '')}",
        f"first_wave={profiles.get('first_wave_ids', [])}",
        f"surface_defaults={surface_defaults}",
        "designation="
        + str(designation.get("source") or "blackboard_row_tolerance")
        + " / states "
        + str(designation.get("tolerance_states") or [])
        + " / range "
        + str(designation.get("range_mode") or "inherit"),
    ]
    for family_id, profile in list(families.items())[:12]:
        if not isinstance(profile, dict):
            continue
        admission = profile.get("row_admission") if isinstance(profile.get("row_admission"), dict) else {}
        lines.append(
            f"{family_id}: {profile.get('family', '')} / variant {profile.get('default_variant', '')} / {profile.get('density', '')} / {profile.get('audience', '')} / wave {profile.get('rollout_wave', '')}"
        )
        lines.append(
            "  promotes "
            + str(profile.get("promoted_families") or [])
            + " / suppresses "
            + str(profile.get("suppressed_families") or [])
        )
        lines.append(
            "  admission rows="
            + str(admission.get("max_visible_rows", ""))
            + " per_family="
            + str(admission.get("max_per_family", ""))
            + " sticky_ms="
            + str(admission.get("sticky_decay_ms", ""))
            + " session_boost="
            + str(admission.get("session_weight_boost", ""))
            + " blocker_auto_promote="
            + str(bool(admission.get("blocker_auto_promote")))
        )
    return _wrap_block("\n".join(lines), width)


def _render_help_overlay(snapshot, width, height, view_mode, section_key, diagnostics_visible, surface_mode=TEXT_THEATER_SURFACE_MODE, surface_density=TEXT_THEATER_SURFACE_DENSITY):
    width = max(80, int(width or 80))
    height = max(12, int(height or 12))
    lines = []
    lines.extend(_wrap_block("Main view is split. Use m or 6 to return there from anywhere.", width - 2))
    lines.extend(_wrap_block("Views: 1 render | 2 consult | 3 theater | 4 embodiment | 5 snapshot | 6 split(main)", width - 2))
    lines.extend(_wrap_block("Diagnostics: d toggle | tab next section | g jump to blackboard | p jump to profiles | s cycle surface | -/= density | h hide help | q quit | r retry", width - 2))
    lines.extend(_wrap_block(
        "Current: view=" + str(view_mode or "split")
        + " | diagnostics=" + str(bool(diagnostics_visible))
        + " | section=" + str(section_key or "theater")
        + " | " + _surface_status_line(surface_mode, surface_density)
        + " | focus=" + str((((snapshot.get('theater') or {}).get('focus') or {}).get('id') or 'none')),
        width - 2,
    ))
    lines.append("")
    lines.extend(_wrap_block(
        "Legacy preserves the current depiction. Sharp adds a pane-wide operator substrate with finer text; granular pushes farther into glyph-field rendering without touching the raw scene lane.",
        width - 2,
    ))
    lines.extend(_wrap_block(
        "Profiles remain live in the registry. Use p for the profiles section; current text-theater spectrum state is shown in the status panel.",
        width - 2,
    ))
    lines.extend(_wrap_block(
        "Continuity / help front: env_help(topic='continuity_reacclimation'), env_help(topic='output_state'), env_help(topic='techlit_hair_control_surface').",
        width - 2,
    ))
    lines.extend(_wrap_block(
        "Live TECHLIT controls: window.envopsSetHairGlyphMessageText('TECHLIT'), window.envopsSetHairGlyphSpectrum('crayolazy'), window.envopsSetHairPreset('saiyan', 'sasquatch', or 'exhaust_buds'), window.envopsEnablePoseDrive().",
        width - 2,
    ))
    lines.extend(_wrap_block(
        "Input routing: await window.envopsStartDesktopAudioReactiveCapture(), await window.envopsStartMicHairWords(), then verify with envopsGetAudioReactiveState(), envopsGetHairSpeechDriveState(), and the active hair_msg / hair_spectrum lines.",
        width - 2,
    ))
    return _box("Help", lines, width, height, color=MAGENTA, surface_mode=surface_mode, surface_density=surface_density)


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


def _get_json(url, timeout):
    request = urllib.request.Request(url, method="GET")
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


def _env_text_theater_view(base_url, timeout, view_mode, width, height, diagnostics_visible, section_key):
    payload = _load_tool_payload(
        base_url,
        "env_read",
        {
            "query": "text_theater_view",
            "view": view_mode,
            "section": section_key,
            "width": width,
            "height": height,
            "diagnostics": bool(diagnostics_visible),
        },
        timeout,
    )
    view = payload.get("text_theater_view") if isinstance(payload, dict) else None
    if not isinstance(view, dict):
        raise RuntimeError("env_read('text_theater_view') did not return text_theater_view")
    snapshot = view.get("snapshot") if isinstance(view.get("snapshot"), dict) else {}
    ansi_frame = str(view.get("ansi_frame") or "")
    return {
        "frame": ansi_frame or str(view.get("frame") or ""),
        "snapshot": snapshot,
        "theater_text": str(view.get("theater_text") or ""),
        "embodiment_text": str(view.get("embodiment_text") or ""),
        "view_mode": str(view.get("view_mode") or view_mode or "split"),
        "section_key": str(view.get("section_key") or section_key or "theater"),
        "width": int(view.get("width") or width or 140),
        "height": int(view.get("height") or height or 44),
        "diagnostics": bool(view.get("diagnostics") if "diagnostics" in view else diagnostics_visible),
    }


def _env_text_theater_live(base_url, timeout):
    live_timeout = max(0.5, min(float(timeout or 5.0), 2.4))
    payload = _get_json(f"{base_url}/api/text-theater/live", live_timeout)
    live = payload.get("text_theater_live") if isinstance(payload, dict) else None
    if not isinstance(live, dict):
        raise RuntimeError("/api/text-theater/live did not return text_theater_live")
    return {
        "snapshot": live.get("snapshot") if isinstance(live.get("snapshot"), dict) else {},
        "theater_text": str(live.get("theater_text") or ""),
        "embodiment_text": str(live.get("embodiment_text") or ""),
        "freshness": live.get("freshness") if isinstance(live.get("freshness"), dict) else {},
    }


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
    visible = _display_width(raw)
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
            char = raw[index]
            char_width = _char_display_width(char)
            if (taken + char_width) > width:
                break
            out.append(char)
            index += 1
            taken += char_width
        clipped = "".join(out)
        if saw_ansi and not clipped.endswith(RESET):
            clipped += RESET
        return clipped
    return raw + (" " * max(0, width - visible))


def _box(title, lines, width, height, color=CYAN, body_mode="wide", surface_mode=None, surface_density=None):
    inner_width = max(1, width - 2)
    body_height = max(0, height - 2)
    top = "┌" + ("─" * inner_width) + "┐"
    out = [top]
    normalized = list(lines or [])
    mode = str(body_mode or "wide").strip().lower() or "wide"
    profile = _surface_profile(surface_mode, surface_density)
    uses_surface_field = mode != "raw" and str(profile.get("mode") or "legacy") != "legacy"
    title_mode = mode if mode == "raw" else str(profile.get("title_mode") or mode)
    body_mode_effective = mode if mode != "wide" else str(profile.get("body_mode") or mode)
    if title_mode == "wide" and body_height >= 2:
        title_rows = _render_wide_text_lines(
            [str(title or "")],
            max(6, inner_width - 2),
            max(1, min(3, body_height - 1)),
            default_style=(BOLD + str(color or CYAN)),
            align="center",
            widen=bool(profile.get("title_widen", True)),
        )
    elif title_mode == "raster" and body_height >= 2:
        title_rows = _render_raster_text_lines(
            [str(title or "")],
            max(6, inner_width - 2),
            max(1, min(3, body_height - 1)),
            default_style=color,
            preferred_px=11,
            min_px=8,
            bold=True,
            align="center",
            full_surface_style="" if uses_surface_field else str(profile.get("surface_style") or ""),
            full_surface_texture=str(profile.get("surface_texture") or "paper"),
            full_surface_texture_style="" if uses_surface_field else str(profile.get("surface_texture_style") or ""),
            full_surface_density=0.0 if uses_surface_field else float(profile.get("surface_texture_density") or 0.0),
        )
    else:
        title_rows = []
    use_display_title = bool(title_rows)
    use_display_body = mode != "raw"
    body_prefix = []
    if use_display_title:
        body_prefix.extend(title_rows)
        body_prefix.append("")
    else:
        header = f"{color}{BOLD}{title}{RESET}"
        out[0] = "┌" + _pad_line(header, inner_width) + "┐"
    remaining_body_rows = max(0, body_height - len(body_prefix))
    if use_display_body and remaining_body_rows > 0:
        if body_mode_effective == "wide":
            body_lines = _render_wide_text_lines(
                normalized,
                max(6, inner_width - 2),
                remaining_body_rows,
                default_style=str(color or LIGHT_GRAY),
                align="left",
                widen=bool(profile.get("body_widen", True)),
            )
        elif body_mode_effective == "raster":
            body_lines = _render_raster_text_lines(
                normalized,
                max(6, inner_width - 2),
                remaining_body_rows,
                default_style=color,
                preferred_px=int(profile.get("raster_preferred_px") or 10),
                min_px=int(profile.get("raster_min_px") or 7),
                align="left",
                full_surface_style="" if uses_surface_field else str(profile.get("surface_style") or ""),
                full_surface_texture=str(profile.get("surface_texture") or "paper"),
                full_surface_texture_style="" if uses_surface_field else str(profile.get("surface_texture_style") or ""),
                full_surface_density=0.0 if uses_surface_field else float(profile.get("surface_texture_density") or 0.0),
            )
        else:
            body_lines = normalized
    else:
        body_lines = normalized
    if uses_surface_field and body_height > 0:
        surface_rows = _surface_cells(
            inner_width,
            body_height,
            bg_style=str(profile.get("surface_style") or BG_GRAPHITE),
            texture=str(profile.get("surface_texture") or "paper"),
            texture_style=str(profile.get("surface_texture_style") or ""),
            density=float(profile.get("surface_texture_density") or 0.0),
        )
        row_cursor = 0
        if title_rows:
            _overlay_surface_text(surface_rows, title_rows, start_row=row_cursor)
            row_cursor += len(title_rows)
            if row_cursor < body_height:
                row_cursor += 1
        _overlay_surface_text(surface_rows, body_lines, start_row=row_cursor)
        display_lines = _surface_rows_to_text(surface_rows)
    else:
        display_lines = body_prefix + body_lines
    for idx in range(body_height):
        line = display_lines[idx] if idx < len(display_lines) else ""
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


def _style_from_hsl(hue_deg, saturation_pct, lightness_pct, brightness=1.0, solid=False, min_saturation=0.88, target_lightness=0.52):
    hue = (float(hue_deg or 0.0) % 360.0) / 360.0
    saturation = _clamp(float(saturation_pct or 0.0) / 100.0, 0.0, 1.0)
    lightness = _clamp(float(lightness_pct or 0.0) / 100.0, 0.0, 1.0)
    rf, gf, bf = colorsys.hls_to_rgb(hue, lightness, saturation)
    rgb = (
        _clamp(int(round(rf * 255.0)), 0, 255),
        _clamp(int(round(gf * 255.0)), 0, 255),
        _clamp(int(round(bf * 255.0)), 0, 255),
    )
    return _style_from_color(
        "#{:02x}{:02x}{:02x}".format(*rgb),
        rgb,
        brightness,
        solid=solid,
        min_saturation=min_saturation,
        target_lightness=target_lightness,
    )


def _v_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _v_scale(a, scalar):
    value = float(scalar or 0.0)
    return (a[0] * value, a[1] * value, a[2] * value)


def _quat4(value):
    if isinstance(value, dict):
        return (
            float(value.get("x", 0.0) or 0.0),
            float(value.get("y", 0.0) or 0.0),
            float(value.get("z", 0.0) or 0.0),
            float(value.get("w", 1.0) or 1.0),
        )
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return (
            float(value[0] or 0.0),
            float(value[1] or 0.0),
            float(value[2] or 0.0),
            float(value[3] if value[3] is not None else 1.0),
        )
    return (0.0, 0.0, 0.0, 1.0)


def _quat_norm(value):
    qx, qy, qz, qw = _quat4(value)
    length = math.sqrt((qx * qx) + (qy * qy) + (qz * qz) + (qw * qw))
    if length <= 1e-6:
        return (0.0, 0.0, 0.0, 1.0)
    return (qx / length, qy / length, qz / length, qw / length)


def _quat_rotate(quaternion, vector):
    qx, qy, qz, qw = _quat_norm(quaternion)
    vx, vy, vz = vector
    uv = (
        (qy * vz) - (qz * vy),
        (qz * vx) - (qx * vz),
        (qx * vy) - (qy * vx),
    )
    uuv = (
        (qy * uv[2]) - (qz * uv[1]),
        (qz * uv[0]) - (qx * uv[2]),
        (qx * uv[1]) - (qy * uv[0]),
    )
    return (
        vx + ((uv[0] * qw) + uuv[0]) * 2.0,
        vy + ((uv[1] * qw) + uuv[1]) * 2.0,
        vz + ((uv[2] * qw) + uuv[2]) * 2.0,
    )


def _scaffold_size_world(size_local, world_scale):
    local = _vec3(size_local)
    scale = _vec3(world_scale)
    return (
        abs(local[0] * scale[0]),
        abs(local[1] * scale[1]),
        abs(local[2] * scale[2]),
    )


def _scaffold_box_edge_segments(center, size_world, quaternion):
    cx, cy, cz = _vec3(center)
    sx, sy, sz = size_world
    hx = max(0.001, float(sx) * 0.5)
    hy = max(0.001, float(sy) * 0.5)
    hz = max(0.001, float(sz) * 0.5)
    corners = {}
    for ix in (-1.0, 1.0):
        for iy in (-1.0, 1.0):
            for iz in (-1.0, 1.0):
                local = (ix * hx, iy * hy, iz * hz)
                rotated = _quat_rotate(quaternion, local)
                corners[(ix, iy, iz)] = (cx + rotated[0], cy + rotated[1], cz + rotated[2])
    edges = []
    for iy in (-1.0, 1.0):
        for iz in (-1.0, 1.0):
            edges.append((corners[(-1.0, iy, iz)], corners[(1.0, iy, iz)]))
    for ix in (-1.0, 1.0):
        for iz in (-1.0, 1.0):
            edges.append((corners[(ix, -1.0, iz)], corners[(ix, 1.0, iz)]))
    for ix in (-1.0, 1.0):
        for iy in (-1.0, 1.0):
            edges.append((corners[(ix, iy, -1.0)], corners[(ix, iy, 1.0)]))
    return edges


def _scaffold_ellipsoid_ring_segments(center, size_world, quaternion, plane, count=18, offset_norm=0.0):
    cx, cy, cz = _vec3(center)
    sx, sy, sz = size_world
    rx = max(0.001, float(sx) * 0.5)
    ry = max(0.001, float(sy) * 0.5)
    rz = max(0.001, float(sz) * 0.5)
    total = max(10, int(count or 18))
    offset = max(-0.96, min(0.96, float(offset_norm or 0.0)))
    slice_scale = math.sqrt(max(0.0, 1.0 - (offset * offset)))
    points = []
    for idx in range(total):
        theta = (float(idx) / float(total)) * math.tau
        if plane == "xy":
            local = (
                math.cos(theta) * rx * slice_scale,
                math.sin(theta) * ry * slice_scale,
                offset * rz,
            )
        elif plane == "yz":
            local = (
                offset * rx,
                math.cos(theta) * ry * slice_scale,
                math.sin(theta) * rz * slice_scale,
            )
        else:
            local = (
                math.cos(theta) * rx * slice_scale,
                offset * ry,
                math.sin(theta) * rz * slice_scale,
            )
        rotated = _quat_rotate(quaternion, local)
        points.append((cx + rotated[0], cy + rotated[1], cz + rotated[2]))
    segments = []
    for idx in range(len(points)):
        segments.append((points[idx], points[(idx + 1) % len(points)]))
    return segments


def _scaffold_ellipsoid_orbit_segments(center, size_world, quaternion, axis_u, axis_v, count=18):
    cx, cy, cz = _vec3(center)
    sx, sy, sz = size_world
    rx = max(0.001, float(sx) * 0.5)
    ry = max(0.001, float(sy) * 0.5)
    rz = max(0.001, float(sz) * 0.5)
    total = max(10, int(count or 18))
    u = _v_norm(_vec3(axis_u), (1.0, 0.0, 0.0))
    raw_v = _vec3(axis_v)
    v = _v_sub(raw_v, _v_scale(u, _v_dot(raw_v, u)))
    v = _v_norm(v, _v_norm(_v_cross((0.0, 1.0, 0.0), u), (0.0, 0.0, 1.0)))
    points = []
    for idx in range(total):
        theta = (float(idx) / float(total)) * math.tau
        direction = _v_add(_v_scale(u, math.cos(theta)), _v_scale(v, math.sin(theta)))
        local = (
            direction[0] * rx,
            direction[1] * ry,
            direction[2] * rz,
        )
        rotated = _quat_rotate(quaternion, local)
        points.append((cx + rotated[0], cy + rotated[1], cz + rotated[2]))
    segments = []
    for idx in range(len(points)):
        segments.append((points[idx], points[(idx + 1) % len(points)]))
    return segments


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


def _snapshot_epoch_ms(value):
    try:
        number = float(value or 0.0)
    except Exception:
        return 0.0
    if number <= 0:
        return 0.0
    if number > 100000000000.0:
        return number
    if number > 100000000.0:
        return number * 1000.0
    return 0.0


def _sequence_shared_surface_motion_clock(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    sequence = snapshot.get("sequence_field") if isinstance(snapshot.get("sequence_field"), dict) else {}
    force = sequence.get("force_wave") if isinstance(sequence.get("force_wave"), dict) else {}
    surface = force.get("animation_surface") if isinstance(force.get("animation_surface"), dict) else {}
    runtime = snapshot.get("runtime") if isinstance(snapshot.get("runtime"), dict) else {}
    runtime_surface = runtime.get("surfaces") if isinstance(runtime.get("surfaces"), dict) else {}
    runtime_animation = runtime_surface.get("animation") if isinstance(runtime_surface.get("animation"), dict) else {}
    timeline = snapshot.get("timeline") if isinstance(snapshot.get("timeline"), dict) else {}

    def number_from(*values):
        for value in values:
            try:
                number = float(value)
            except Exception:
                continue
            if math.isfinite(number):
                return number
        return 0.0

    sequence_active = bool(sequence.get("active"))
    force_active = bool(force.get("active"))
    active = bool(
        sequence_active
        and (
            surface.get("active")
            or runtime_animation.get("active_clip")
            or (force_active and force.get("pose_drive_enabled"))
        )
    )
    duration = number_from(
        surface.get("timeline_duration"),
        surface.get("duration"),
        runtime_animation.get("duration"),
        timeline.get("duration"),
        4.35,
    )
    duration = max(0.25, duration)
    speed = number_from(runtime_animation.get("speed"), surface.get("speed"), 1.0)
    if speed <= 0:
        speed = 1.0
    base_progress = _clamp(number_from(surface.get("cycle_progress"), force.get("cycle_progress"), 0.0), 0.0, 1.0)
    epoch_ms = (
        _snapshot_epoch_ms(surface.get("clock_epoch_ms"))
        or _snapshot_epoch_ms(runtime_animation.get("clock_epoch_ms"))
    )
    timestamp_ms = (
        _snapshot_epoch_ms(surface.get("updated_ms"))
        or _snapshot_epoch_ms(surface.get("timestamp_ms"))
        or _snapshot_epoch_ms(runtime_animation.get("updated_ms"))
        or _snapshot_epoch_ms(runtime_animation.get("timestamp_ms"))
    )
    elapsed_seconds = 0.0
    if active:
        if epoch_ms > 0:
            elapsed_seconds = max(0.0, ((time.time() * 1000.0) - epoch_ms) / 1000.0)
        elif timestamp_ms > 0:
            elapsed_seconds = max(0.0, ((time.time() * 1000.0) - timestamp_ms) / 1000.0)
            elapsed_seconds = min(elapsed_seconds, duration * 3.0)
        else:
            elapsed_seconds = time.time()
    phase = (base_progress + ((elapsed_seconds * speed) / duration if active else 0.0)) % 1.0
    radians = phase * math.tau
    consumer_rule = str(
        surface.get("consumer_rule")
        or surface.get("bridge")
        or "text_and_web_theaters_consume_shared_surface"
    ).strip()
    authority = str(surface.get("authority") or "sequence_field.force_wave").strip()
    clip = str(runtime_animation.get("active_clip") or surface.get("active_clip") or "").strip()
    return {
        "active": active,
        "authority": authority,
        "consumer_rule": consumer_rule,
        "clip": clip,
        "duration": duration,
        "elapsed_seconds": elapsed_seconds,
        "phase": phase,
        "phase_radians": radians,
        "pulse": 0.5 + (0.5 * math.sin(radians)),
        "speed": speed,
        "drive_gain": _clamp(number_from(force.get("drive_gain"), 0.55), 0.0, 1.0),
        "rebound_damping": _clamp(number_from(force.get("rebound_damping"), 0.4), 0.0, 1.0),
    }


def _sequence_shared_surface_motion_overlay(clock, motion, support_y, span_x, span_z, guide_grid_span, styles):
    if not clock.get("active"):
        return {"segments": [], "rings": []}
    origin = _vec3((motion or {}).get("origin"))
    forward = _v_norm(_ground_vec((motion or {}).get("forward") or (0.0, 0.0, 1.0)), (0.0, 0.0, 1.0))
    right = _v_norm((forward[2], 0.0, -forward[0]), (1.0, 0.0, 0.0))
    center = (origin[0], float(support_y or 0.0) + 0.018, origin[2])
    span = float(guide_grid_span or 0.0)
    if span <= 0.1:
        span = max(float(span_x or 0.0), float(span_z or 0.0), 4.0)
    base_radius = max(1.15, min(6.4, span * 0.16))
    phase = float(clock.get("phase") or 0.0)
    pulse = float(clock.get("pulse") or 0.5)
    drive = float(clock.get("drive_gain") or 0.55)
    tau = math.tau

    def orbit(theta, radius, lift=0.0):
        return (
            center[0] + (right[0] * math.cos(theta) * radius) + (forward[0] * math.sin(theta) * radius),
            center[1] + lift,
            center[2] + (right[2] * math.cos(theta) * radius) + (forward[2] * math.sin(theta) * radius),
        )

    motion_style = styles.get("motion") or CYAN
    heading_style = styles.get("heading") or YELLOW
    rings = [
        {
            "center": center,
            "radius": base_radius * (0.72 + (0.16 * pulse) + (0.08 * drive)),
            "style": motion_style,
            "priority": 2,
            "samples": 76,
        }
    ]
    segments = []
    for idx in range(4):
        theta = tau * ((phase + (idx * 0.25)) % 1.0)
        segments.append({
            "start": orbit(theta - 0.1, base_radius * (0.28 + (0.04 * idx)), 0.012),
            "end": orbit(theta + 0.18 + (pulse * 0.12), base_radius * (0.76 + (drive * 0.18)), 0.012),
            "style": motion_style if idx % 2 else heading_style,
            "priority": 3,
            "samples": 22,
        })
    sweep_theta = tau * ((phase + 0.08) % 1.0)
    segments.append({
        "start": center,
        "end": orbit(sweep_theta, base_radius * (0.96 + (0.12 * drive)), 0.024),
        "style": heading_style,
        "priority": 3,
        "samples": 26,
    })
    return {"segments": segments, "rings": rings}


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


def _detail_scaled_count(count, drag_lod=False, minimum=6):
    steps = max(int(minimum or 2), int(count or minimum or 2))
    if not drag_lod:
        return steps
    return max(int(minimum or 2), int(round(steps * 0.58)))


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


def _scaffold_segment_thickness_band(segment):
    avg_radius = max(
        0.0,
        (float(segment.get("radius_start") or 0.0) + float(segment.get("radius_end") or 0.0)) * 0.5,
    )
    if avg_radius >= 0.05:
        return 2
    if avg_radius >= 0.016:
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
                {
                    "mask": 0,
                    "style": "",
                    "priority": 0,
                    "weight": 0,
                    "glyph_mode": "",
                    "overlay_char": "",
                    "overlay_style": "",
                    "overlay_priority": 0,
                    "bg_style": "",
                    "bg_priority": 0,
                    "bg_char": "",
                    "bg_char_style": "",
                    "bg_char_priority": 0,
                }
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


def _braille_put(canvas, x, y, priority=1, style="", glyph_mode=""):
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
        if glyph_mode:
            cell["glyph_mode"] = str(glyph_mode or "")


def _braille_overlay_char(canvas, x, y, char, priority=1, style=""):
    if not canvas:
        return
    text = str(char or "")
    if not text:
        return
    width = int(canvas.get("width") or 0)
    height = int(canvas.get("height") or 0)
    cell_x = int(round(float(x or 0.0) / 2.0))
    cell_y = int(round(float(y or 0.0) / 4.0))
    if cell_x < 0 or cell_y < 0 or cell_x >= width or cell_y >= height:
        return
    cell = canvas["cells"][cell_y][cell_x]
    if int(priority) >= int(cell.get("overlay_priority", 0)):
        cell["overlay_priority"] = int(priority)
        cell["overlay_char"] = text[0]
        cell["overlay_style"] = str(style or "")


def _braille_cluster(canvas, x, y, priority=1, style="", radius=0):
    radius = max(0, int(radius or 0))
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if (dx * dx) + (dy * dy) > max(1, radius * radius + radius):
                continue
            _braille_put(canvas, x + dx, y + dy, priority=priority, style=style)


def _braille_fill_rect(canvas, left, top, right, bottom, style="", priority=1):
    if not canvas or not style:
        return
    width = int(canvas.get("width") or 0)
    height = int(canvas.get("height") or 0)
    if width <= 0 or height <= 0:
        return
    x0 = max(0, min(width - 1, int(math.floor(min(float(left or 0), float(right or 0)) / 2.0))))
    x1 = max(0, min(width - 1, int(math.floor(max(float(left or 0), float(right or 0)) / 2.0))))
    y0 = max(0, min(height - 1, int(math.floor(min(float(top or 0), float(bottom or 0)) / 4.0))))
    y1 = max(0, min(height - 1, int(math.floor(max(float(top or 0), float(bottom or 0)) / 4.0))))
    for cell_y in range(y0, y1 + 1):
        for cell_x in range(x0, x1 + 1):
            cell = canvas["cells"][cell_y][cell_x]
            if int(priority) >= int(cell.get("bg_priority", 0)):
                cell["bg_priority"] = int(priority)
                cell["bg_style"] = str(style or "")


def _plate_texture_char(cell_x, cell_y, texture="paper", density=1.0):
    texture_id = str(texture or "paper").strip().lower()
    seed = (int(cell_x) * 17) + (int(cell_y) * 31)
    if texture_id == "paper":
        pattern = (" ", " ", " ", " ", " ", "⠂", " ", " ", " ", "⠁", " ", " ", " ", " ")
    elif texture_id == "typewriter":
        pattern = (" ", " ", " ", "⠂", " ", " ", " ", "⠄", " ", " ", " ", "⠂", " ", " ", " ")
    elif texture_id == "xray":
        pattern = (" ", " ", " ", "⠁", " ", " ", "⠂", " ", " ", "⠄", " ", " ", " ")
    else:
        pattern = (" ", " ", " ", "⠂", " ", " ", "⠄", " ", " ", " ")
    char = pattern[seed % len(pattern)]
    if not char or char == " ":
        return " "
    keep_threshold = int(round(_normalize_surface_density(density) * 100.0))
    if keep_threshold <= 0:
        return " "
    if (abs(seed) % 100) >= keep_threshold:
        return " "
    return char


def _braille_texture_rect(canvas, left, top, right, bottom, style="", priority=1, texture="paper", density=1.0):
    if not canvas:
        return
    width = int(canvas.get("width") or 0)
    height = int(canvas.get("height") or 0)
    if width <= 0 or height <= 0:
        return
    x0 = max(0, min(width - 1, int(math.floor(min(float(left or 0), float(right or 0)) / 2.0))))
    x1 = max(0, min(width - 1, int(math.floor(max(float(left or 0), float(right or 0)) / 2.0))))
    y0 = max(0, min(height - 1, int(math.floor(min(float(top or 0), float(bottom or 0)) / 4.0))))
    y1 = max(0, min(height - 1, int(math.floor(max(float(top or 0), float(bottom or 0)) / 4.0))))
    for cell_y in range(y0, y1 + 1):
        for cell_x in range(x0, x1 + 1):
            char = _plate_texture_char(cell_x, cell_y, texture=texture, density=density)
            if not char or char == " ":
                continue
            cell = canvas["cells"][cell_y][cell_x]
            if int(priority) >= int(cell.get("bg_char_priority", 0)):
                cell["bg_char_priority"] = int(priority)
                cell["bg_char"] = char
                cell["bg_char_style"] = str(style or "")


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
            glyph_mode = str((cell or {}).get("glyph_mode") or "")
            overlay_char = str((cell or {}).get("overlay_char") or "")
            overlay_style = str((cell or {}).get("overlay_style") or "")
            overlay_priority = int((cell or {}).get("overlay_priority") or 0)
            bg_style = str((cell or {}).get("bg_style") or "")
            bg_char = str((cell or {}).get("bg_char") or "")
            bg_char_style = str((cell or {}).get("bg_char_style") or "")
            # Keep raster text on the braille occupancy substrate. Remapping
            # those masks into block/quarter-block glyphs is what turned the
            # readable fuzzy letters into symbol soup.
            char = raw[col_index] if col_index < len(raw) else (" " if mask <= 0 else chr(0x2800 + mask))
            if overlay_char and (overlay_priority >= int((cell or {}).get("priority", 0)) or mask <= 0):
                char = overlay_char
            combined_style = ""
            if bg_style:
                combined_style += bg_style
            if overlay_char and overlay_style and (overlay_priority >= int((cell or {}).get("priority", 0)) or mask <= 0):
                combined_style += overlay_style
            elif style:
                combined_style += style
            if combined_style and char != " ":
                parts.append(combined_style + char + RESET)
            elif bg_style and bg_char and char == " ":
                parts.append(bg_style + bg_char_style + bg_char + RESET)
            elif bg_style and char == " ":
                parts.append(bg_style + " " + RESET)
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
            [(0, 0, "body_core", 5), (-1, 0, "body_edge", 2), (1, 0, "body_edge", 2)],
            [(0, 0, "body_core", 5), (0, -1, "body_edge", 2), (0, 1, "body_edge", 2)],
        ]
        return patterns[int(phase or 0) % len(patterns)]
    if radius >= 3:
        offsets = [(0, 0, "body_core", 7)]
        offsets.extend([
            (-1, 0, "body_core", 6),
            (1, 0, "body_core", 6),
            (0, -1, "body_core", 6),
            (0, 1, "body_core", 6),
            (-1, -1, "body_edge", 4),
            (1, -1, "body_edge", 4),
            (-1, 1, "body_edge", 4),
            (1, 1, "body_edge", 4),
            (-2, 0, "body_edge", 3),
            (2, 0, "body_edge", 3),
            (0, -2, "body_edge", 3),
            (0, 2, "body_edge", 3),
        ])
        return offsets
    offsets = [(0, 0, "body_core", 6)]
    offsets.extend([
        (-1, 0, "body_edge", 2),
        (1, 0, "body_edge", 2),
        (0, -1, "body_edge", 2),
        (0, 1, "body_edge", 2),
    ])
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


def _orthographic_scaffold_stamp_radius(radius_world):
    radius = float(radius_world or 0.0)
    if radius >= 0.12:
        return 3
    if radius >= 0.05:
        return 2
    if radius >= 0.016:
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
    for segment in model.get("scaffold_segments") or []:
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
    scoped_part_mode = bool(model.get("scoped_part_mode"))
    radius_floor = 1.25 if scoped_part_mode else 10.0
    radius = max(
        radius_floor,
        float(bounds["radius"]) * 1.7,
        _v_len(bounds["size"]) * 0.9,
    )
    lift = max(0.8 if scoped_part_mode else 5.0, radius * 0.52)
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


def _part_key_bone_id(value):
    text = str(value or "").strip()
    if not text:
        return ""
    marker = "#bone:"
    if marker in text:
        return text.split(marker, 1)[1].strip()
    return ""


def _visible_bone_ids(snapshot):
    workbench = snapshot.get("workbench") or {}
    embodiment = snapshot.get("embodiment") or {}
    bones = embodiment.get("bones") or []
    all_ids = {
        str((bone or {}).get("id") or (bone or {}).get("name") or "").strip()
        for bone in bones
        if isinstance(bone, dict)
    }
    all_ids.discard("")
    if not all_ids:
        return set()

    visible_ids = set(all_ids)
    isolated_chain = str(embodiment.get("isolated_chain") or workbench.get("isolated_chain") or "").strip()
    isolated_ids = {
        str(value or "").strip()
        for value in (
            embodiment.get("selected_chain_bone_ids")
            or workbench.get("selected_chain_bone_ids")
            or []
        )
    }
    isolated_ids.discard("")
    if isolated_chain and isolated_ids:
        visible_ids &= isolated_ids

    selected_surface = (
        workbench.get("selected_part_surface")
        if isinstance(workbench.get("selected_part_surface"), dict)
        else {}
    )
    selected_ids = {
        str(value or "").strip()
        for value in (
            workbench.get("selected_bone_ids")
            or embodiment.get("selected_bone_ids")
            or []
        )
    }
    selected_ids.discard("")
    primary_id = str(
        workbench.get("primary_bone_id")
        or selected_surface.get("bone_id")
        or ""
    ).strip()
    if primary_id:
        selected_ids.add(primary_id)

    scope = str(workbench.get("part_display_scope") or "body").strip().lower() or "body"
    scope_ids = set()
    if scope == "part_only":
        scope_ids = set(selected_ids)
    elif scope == "part_adjacent":
        scope_ids = set(selected_ids)
        for part_key in selected_surface.get("adjacent_part_keys") or []:
            bone_id = _part_key_bone_id(part_key)
            if bone_id:
                scope_ids.add(bone_id)
    elif scope == "part_chain":
        scope_ids = {
            str(value or "").strip()
            for value in (
                selected_surface.get("chain_ids")
                or embodiment.get("selected_chain_bone_ids")
                or []
            )
        }
        scope_ids.discard("")
        if not scope_ids:
            scope_ids = set(selected_ids)
    if scope != "body" and scope_ids:
        visible_ids &= scope_ids

    return visible_ids


def _selected_part_surface(snapshot):
    workbench = snapshot.get("workbench") or {}
    surface = workbench.get("selected_part_surface")
    return surface if isinstance(surface, dict) else {}


def _selected_part_camera_recipe(snapshot):
    workbench = snapshot.get("workbench") or {}
    view_key = str(workbench.get("part_view") or "iso_front").strip().lower() or "iso_front"
    recipes = workbench.get("part_camera_recipes") or []
    if not isinstance(recipes, list):
        return None
    fallback = None
    for recipe in recipes:
        if not isinstance(recipe, dict):
            continue
        key = str(recipe.get("key") or "").strip().lower()
        if key == view_key:
            return recipe
        if fallback is None and key == "iso_front":
            fallback = recipe
        if fallback is None:
            fallback = recipe
    return fallback


def _world_bounds_points(surface):
    if not isinstance(surface, dict):
        return []
    bounds = surface.get("world_bounds")
    if not isinstance(bounds, dict):
        return []
    min_point = _vec3(bounds.get("min"))
    max_point = _vec3(bounds.get("max"))
    min_x, min_y, min_z = min_point
    max_x, max_y, max_z = max_point
    return [
        (min_x, min_y, min_z),
        (min_x, min_y, max_z),
        (min_x, max_y, min_z),
        (min_x, max_y, max_z),
        (max_x, min_y, min_z),
        (max_x, min_y, max_z),
        (max_x, max_y, min_z),
        (max_x, max_y, max_z),
    ]


def _box_floor_outline(bounds, y_override=None):
    if not isinstance(bounds, dict):
        return []
    min_point = bounds.get("min") if isinstance(bounds.get("min"), dict) else None
    max_point = bounds.get("max") if isinstance(bounds.get("max"), dict) else None
    if not min_point or not max_point:
        return []
    min_x = float(min_point.get("x", 0.0) or 0.0)
    max_x = float(max_point.get("x", 0.0) or 0.0)
    min_y = float(min_point.get("y", 0.0) or 0.0)
    min_z = float(min_point.get("z", 0.0) or 0.0)
    max_z = float(max_point.get("z", 0.0) or 0.0)
    if abs(max_x - min_x) < 1e-6 and abs(max_z - min_z) < 1e-6:
        return []
    outline_y = float(min_y if y_override is None else y_override)
    return [
        (min_x, outline_y, min_z),
        (min_x, outline_y, max_z),
        (max_x, outline_y, max_z),
        (max_x, outline_y, min_z),
    ]


def _fract(value):
    number = float(value or 0.0)
    return number - math.floor(number)


def _weather_default_chars(weather):
    source = weather if isinstance(weather, dict) else {}
    kind = str(source.get("kind") or "").strip().lower()
    flow_class = str(source.get("flow_class") or "").strip().lower()
    if flow_class == "precipitation" or kind in {"rain", "drip", "hail", "sleet"}:
        return "||!'"
    if kind == "snow":
        return "*+."
    if flow_class == "current" or kind in {"current", "wind"}:
        return "~=-"
    if kind in {"mist", "fog", "smoke"}:
        return ".,:"
    if kind in {"sand", "ash"}:
        return ".:*"
    return "|~.*"


def _weather_chars(weather):
    chars = "".join(ch for ch in str((weather or {}).get("glyphs") or "") if not ch.isspace())
    glyph_profile = str((weather or {}).get("glyph_profile") or "").strip().lower()
    if chars:
        if glyph_profile == "default_alphanumeric" or chars == "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
            return _weather_default_chars(weather)
        return chars
    return _weather_default_chars(weather)


def _normalize_snapshot_weather(snapshot):
    source_snapshot = snapshot if isinstance(snapshot, dict) else {}
    weather = source_snapshot.get("weather") if isinstance(source_snapshot.get("weather"), dict) else None
    if not weather:
        return source_snapshot
    next_snapshot = dict(source_snapshot)
    next_weather = dict(weather)
    source = str(next_weather.get("source") or "").strip().lower()
    profile_active = str(next_weather.get("profile_active") or "").strip()
    profile_family = str(next_weather.get("profile_family") or "").strip()
    if bool(next_weather.get("enabled")) and source == "world_profile_field_seed" and not profile_active and not profile_family:
        next_weather["enabled"] = False
        next_weather["source"] = "none"
        next_weather["summary"] = "weather disabled without owned producer"
        next_weather["sample_count"] = 0
        next_snapshot["weather"] = next_weather
        output_state = source_snapshot.get("output_state") if isinstance(source_snapshot.get("output_state"), dict) else None
        if output_state:
            next_output_state = dict(output_state)
            field_disposition = output_state.get("field_disposition") if isinstance(output_state.get("field_disposition"), dict) else {}
            balance = source_snapshot.get("balance") if isinstance(source_snapshot.get("balance"), dict) else {}
            support_phase = str(balance.get("support_phase") or "idle")
            stability_risk = _clamp(float(balance.get("stability_risk") or 0.0), 0.0, 99.0)
            normalized_field = dict(field_disposition)
            normalized_field["medium_kind"] = "support_gravity"
            normalized_field["propagation_mode"] = "support"
            normalized_field["density"] = None
            normalized_field["speed"] = None
            normalized_field["turbulence"] = None
            normalized_field["flow_bias"] = None
            normalized_field["drift_bias"] = None
            coupled_surfaces = [str(row) for row in list(normalized_field.get("coupled_surfaces") or []) if str(row) and str(row) != "weather"]
            normalized_field["coupled_surfaces"] = coupled_surfaces
            normalized_field["summary"] = (
                "support / "
                + support_phase
                + " / settle "
                + str(normalized_field.get("settling_band") or "stable")
                + " / risk "
                + f"{stability_risk:.3f}".rstrip("0").rstrip(".")
            )
            next_output_state["field_disposition"] = normalized_field
            next_snapshot["output_state"] = next_output_state
        return next_snapshot
    legacy_glyphs = "".join(ch for ch in str(next_weather.get("glyphs") or "") if not ch.isspace())
    glyph_profile = str(next_weather.get("glyph_profile") or "").strip().lower()
    if glyph_profile == "default_alphanumeric" or legacy_glyphs == "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        next_weather["glyphs"] = _weather_default_chars(next_weather)
        next_weather["glyph_profile"] = "field_ascii"
    next_snapshot["weather"] = next_weather
    return next_snapshot


def _weather_volume_bounds(weather):
    source = weather if isinstance(weather, dict) else {}
    volume = source.get("volume") if isinstance(source.get("volume"), dict) else {}
    min_point = _vec3(volume.get("min"))
    max_point = _vec3(volume.get("max"))
    center_point = volume.get("center")
    size_point = volume.get("size")
    center = _vec3(center_point) if center_point is not None else (
        (min_point[0] + max_point[0]) * 0.5,
        (min_point[1] + max_point[1]) * 0.5,
        (min_point[2] + max_point[2]) * 0.5,
    )
    size = _vec3(size_point) if size_point is not None else (
        max(0.01, max_point[0] - min_point[0]),
        max(0.01, max_point[1] - min_point[1]),
        max(0.01, max_point[2] - min_point[2]),
    )
    corners = [
        (min_point[0], min_point[1], min_point[2]),
        (min_point[0], min_point[1], max_point[2]),
        (min_point[0], max_point[1], min_point[2]),
        (min_point[0], max_point[1], max_point[2]),
        (max_point[0], min_point[1], min_point[2]),
        (max_point[0], min_point[1], max_point[2]),
        (max_point[0], max_point[1], min_point[2]),
        (max_point[0], max_point[1], max_point[2]),
    ]
    return {
        "min": min_point,
        "max": max_point,
        "center": center,
        "size": size,
        "corners": corners,
    }


def _weather_flow_axes(direction):
    flow = _v_norm(_vec3(direction), (0.0, -1.0, 0.0))
    ref = (0.0, 1.0, 0.0) if abs(_v_dot(flow, (0.0, 1.0, 0.0))) < 0.92 else (1.0, 0.0, 0.0)
    axis_u = _v_norm(_v_cross(flow, ref), (1.0, 0.0, 0.0))
    axis_v = _v_norm(_v_cross(axis_u, flow), (0.0, 0.0, 1.0))
    return flow, axis_u, axis_v


def _weather_half_extents(volume, flow, axis_u, axis_v):
    center = volume.get("center") or (0.0, 0.0, 0.0)
    half_flow = 1.0
    half_u = 1.0
    half_v = 1.0
    for corner in volume.get("corners") or []:
        rel = _v_sub(corner, center)
        half_flow = max(half_flow, abs(_v_dot(rel, flow)))
        half_u = max(half_u, abs(_v_dot(rel, axis_u)))
        half_v = max(half_v, abs(_v_dot(rel, axis_v)))
    return half_flow, half_u, half_v


def _weather_style(weather):
    color = str((weather or {}).get("color_hint") or "#7dd3fc")
    return {
        "bright": _style_from_color(color, color, 1.04, solid=True, min_saturation=0.82, target_lightness=0.62),
        "mid": _style_from_color(color, color, 0.94, solid=True, min_saturation=0.78, target_lightness=0.52),
        "dim": _style_from_color(color, color, 0.78, solid=True, min_saturation=0.6, target_lightness=0.42),
    }


def _weather_lod_bands(weather):
    source = (weather or {}).get("lod_bands")
    source = source if isinstance(source, dict) else {}
    legacy = (weather or {}).get("lod")
    legacy = legacy if isinstance(legacy, dict) else {}
    reference = float(source.get("reference_min_subcells") or legacy.get("reference_subcells") or 6.0)
    fused = float(source.get("fused_min_subcells") or legacy.get("fused_subcells") or 3.2)
    granular = float(source.get("granular_min_subcells") or legacy.get("granular_subcells") or 1.5)
    blob = float(source.get("blob_min_subcells") or legacy.get("blob_subcells") or 0.75)
    reference = max(0.1, reference)
    fused = _clamp(fused, 0.1, reference)
    granular = _clamp(granular, 0.1, fused)
    blob = _clamp(blob, 0.0, granular)
    return {
        "reference_min_subcells": reference,
        "fused_min_subcells": fused,
        "granular_min_subcells": granular,
        "blob_min_subcells": blob,
        "medium_penalty": _clamp(float(source.get("medium_penalty") or 0.28), 0.0, 0.95),
        "orientation_floor": _clamp(float(source.get("orientation_floor") or 0.58), 0.0, 1.0),
        "depth_soft_cap": max(1.0, float(source.get("depth_soft_cap") or 18.0)),
    }


def _weather_is_precipitation(weather):
    source = weather if isinstance(weather, dict) else {}
    flow_class = str(source.get("flow_class") or "").strip().lower()
    kind = str(source.get("kind") or "").strip().lower()
    return flow_class == "precipitation" or kind in {"rain", "drip", "hail", "sleet"}


def _scene_object_marker(kind, focused=False):
    obj_kind = str(kind or "").strip().lower()
    radius = 2 if focused else 1
    if obj_kind == "panel":
        return {"char": "▮", "radius": max(2, radius), "stamp": "filled_square"}
    if obj_kind == "portal":
        return {"char": "◎", "radius": max(1, radius), "stamp": "ring"}
    if obj_kind == "tile":
        return {"char": "▭", "radius": max(1, radius), "stamp": "filled_square"}
    if obj_kind == "marker":
        return {"char": "◆", "radius": 0, "stamp": "point"}
    if obj_kind == "zone":
        return {"char": "◌", "radius": max(1, radius), "stamp": "ring"}
    if obj_kind in {"structure", "prop"}:
        return {"char": "▣", "radius": max(2, radius), "stamp": "filled_square"}
    return {"char": "•", "radius": radius, "stamp": "point"}


def _object_stamp_offsets(stamp, radius=1):
    size = max(1, int(radius or 1))
    stamp_key = str(stamp or "").strip().lower()
    if stamp_key == "filled_square":
        rows = []
        for dx in range(-size, size + 1):
            for dy in range(-size, size + 1):
                rows.append((dx, dy))
        return rows
    if stamp_key == "square":
        rows = []
        for dx in range(-size, size + 1):
            rows.append((dx, -size))
            rows.append((dx, size))
        for dy in range(-size + 1, size):
            rows.append((-size, dy))
            rows.append((size, dy))
        rows.append((0, 0))
        return rows
    if stamp_key == "ring":
        return [
            (0, -size),
            (-size, 0),
            (size, 0),
            (0, size),
            (0, 0),
        ]
    return [(0, 0)]


def _project_world_size_to_subcells(size_world, depth, render_height, camera_meta=None):
    if depth is None or depth <= 0.05:
        return 0.0
    camera = camera_meta if isinstance(camera_meta, dict) else {}
    fov_degrees = float(camera.get("fov_degrees") or 50.0)
    tan_half = math.tan(math.radians(max(1.0, min(179.0, fov_degrees))) * 0.5)
    tan_half = tan_half if tan_half > 1e-6 else math.tan(math.radians(50.0) * 0.5)
    screen_radius = ((max(0.0, float(size_world or 0.0)) * 0.5) / depth) / tan_half
    screen_radius *= max(1.0, float(render_height or 1.0) * 0.40)
    return max(0.0, screen_radius * 2.0)


def _orthographic_world_size_to_subcells(size_world, mapper_meta, render_width, render_height, padding=4):
    bounds = mapper_meta.get("bounds") if isinstance(mapper_meta, dict) else None
    if not bounds or len(bounds) != 4:
        return max(0.0, float(size_world or 0.0))
    min_x, max_x, min_y, max_y = bounds
    usable_w = max(1.0, float(render_width or 1.0) - (padding * 2.0))
    usable_h = max(1.0, float(render_height or 1.0) - (padding * 2.0))
    span_x = max(1e-6, float(max_x) - float(min_x))
    span_y = max(1e-6, float(max_y) - float(min_y))
    scale = min(usable_w / span_x, usable_h / span_y)
    return max(0.0, float(size_world or 0.0) * scale)


def _weather_band(projected_subcells, depth, medium_density, local_orientation, readability_required, lod_bands):
    bands = lod_bands if isinstance(lod_bands, dict) else {}
    effective = max(0.0, float(projected_subcells or 0.0))
    medium_penalty = _clamp(float(medium_density or 0.0), 0.0, 1.0) * float(bands.get("medium_penalty") or 0.0)
    orientation_floor = float(bands.get("orientation_floor") or 0.58)
    orientation_mix = max(orientation_floor, _clamp(float(local_orientation or 0.0), 0.0, 1.0))
    effective *= orientation_mix
    effective *= max(0.05, 1.0 - medium_penalty)
    if depth is not None:
        soft_cap = max(1.0, float(bands.get("depth_soft_cap") or 18.0))
        if depth > soft_cap:
            overflow = (float(depth) - soft_cap) / soft_cap
            effective *= max(0.4, 1.0 - min(0.55, overflow * 0.45))
    if not readability_required:
        effective *= 0.94
    if effective >= float(bands.get("reference_min_subcells") or 6.0):
        return "reference"
    if effective >= float(bands.get("fused_min_subcells") or 3.2):
        return "fused"
    if effective >= float(bands.get("granular_min_subcells") or 1.5):
        return "granular"
    if effective >= float(bands.get("blob_min_subcells") or 0.75):
        return "blob"
    return "spec"


def _weather_rows(snapshot, drag_lod=False):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    weather = snapshot.get("weather") if isinstance(snapshot.get("weather"), dict) else {}
    if not weather or not weather.get("enabled"):
        return []
    volume = _weather_volume_bounds(weather)
    flow, axis_u, axis_v = _weather_flow_axes(weather.get("direction"))
    half_flow, half_u, half_v = _weather_half_extents(volume, flow, axis_u, axis_v)
    drift = _vec3(weather.get("drift"))
    glyphs = _weather_chars(weather)
    density = float(weather.get("density") or 0.0)
    base_count = int(weather.get("sample_count") or max(24, round(42 + (density * 72.0))))
    count = max(12, int(round(base_count * (0.58 if drag_lod else 1.0))))
    speed = max(0.02, float(weather.get("speed") or 1.0))
    turbulence = max(0.0, float(weather.get("turbulence") or 0.0))
    glyph_world_size = max(0.08, float(weather.get("glyph_world_size") or 0.44))
    glyph_world_jitter = max(0.0, float(weather.get("glyph_world_jitter") or (glyph_world_size * 0.45)))
    flow_hint = _v_norm(_v_add(flow, _v_scale(drift, 0.35)), flow)
    trail_scale = 0.72 + (speed * 0.48) + (turbulence * 0.35)
    if str(weather.get("flow_class") or "").strip().lower() == "current":
        trail_scale *= 1.35
    if str(weather.get("kind") or "").strip().lower() in {"mist", "fog", "smoke"}:
        trail_scale *= 0.58
    timestamp_s = float(snapshot.get("snapshot_timestamp") or 0.0) / 1000.0
    seed_text = "|".join([
        str(weather.get("profile_active") or ""),
        str(weather.get("profile_family") or ""),
        str(weather.get("kind") or ""),
        str(weather.get("flow_class") or ""),
    ])
    seed_base = sum((idx + 1) * ord(ch) for idx, ch in enumerate(seed_text))
    rows = []
    center = volume.get("center") or (0.0, 0.0, 0.0)
    for idx in range(count):
        h1 = _fract(math.sin((seed_base + (idx * 13) + 1) * 12.9898) * 43758.5453)
        h2 = _fract(math.sin((seed_base + (idx * 17) + 3) * 78.233) * 19642.3491)
        h3 = _fract(math.sin((seed_base + (idx * 19) + 5) * 54.127) * 30219.8164)
        h4 = _fract(math.sin((seed_base + (idx * 23) + 7) * 93.221) * 15731.9487)
        phase = _fract(h3 + (timestamp_s * speed * (0.22 + (h4 * 0.86))))
        travel = (0.5 - phase) * (half_flow * 2.0)
        lateral_u = ((h1 * 2.0) - 1.0) * half_u
        lateral_v = ((h2 * 2.0) - 1.0) * half_v
        drift_wave = math.sin((timestamp_s * speed * 1.7) + (idx * 0.41)) * turbulence
        point = _v_add(
            center,
            _v_add(
                _v_scale(axis_u, lateral_u + (drift[0] * drift_wave)),
                _v_add(
                    _v_scale(axis_v, lateral_v + (drift[1] * drift_wave)),
                    _v_add(
                        _v_scale(flow, travel),
                        _v_scale(drift, drift_wave * 0.75),
                    ),
                ),
            ),
        )
        size_world = glyph_world_size + (((h4 * 2.0) - 1.0) * glyph_world_jitter)
        trail_length = max(0.14, abs(size_world) * trail_scale)
        rows.append({
            "glyph": glyphs[int(math.floor(h2 * len(glyphs))) % max(1, len(glyphs))],
            "point": point,
            "world_size": max(0.08, size_world),
            "trail_start": _v_sub(point, _v_scale(flow_hint, trail_length)),
        })
    return rows


def _hair_field_styles(hair):
    source = hair if isinstance(hair, dict) else {}
    topology = source.get("topology") if isinstance(source.get("topology"), dict) else {}
    equilibrium = str(source.get("equilibrium_mode") or "").strip().lower()
    response = str(source.get("response_mode") or "").strip().lower()
    strategy = str(source.get("color_strategy") or "").strip().lower()
    charge = _clamp(float(topology.get("surface_charge_gain") or source.get("flare_gain") or 0.0), 0.0, 1.0)
    if equilibrium == "super_saiyan_blonde" or strategy == "saiyan_equilibrium":
        bright_hex = "#fff2ad" if response == "audio_reactive_saiyan" else "#ffe36a"
        mid_hex = "#ffd04f"
        dim_hex = "#b77e1f"
        root_hex = "#fff7d5"
    else:
        bright_hex = "#b5f4e7"
        mid_hex = "#7ce0ce"
        dim_hex = "#2b8f85"
        root_hex = "#d7fff8"
    return {
        "bright": _style_from_color(bright_hex, bright_hex, 1.0, solid=True, min_saturation=0.56, target_lightness=0.82),
        "mid": _style_from_color(mid_hex, mid_hex, 0.94 + (charge * 0.04), solid=True, min_saturation=0.52, target_lightness=0.72),
        "dim": _style_from_color(dim_hex, dim_hex, 0.86, solid=True, min_saturation=0.48, target_lightness=0.5),
        "root": _style_from_color(root_hex, root_hex, 1.0, solid=True, min_saturation=0.4, target_lightness=0.9),
    }


def _hair_field_glyph(slot_name, sample_t, clump_mass):
    slot = str(slot_name or "").strip().lower()
    t = _clamp(float(sample_t or 0.0), 0.0, 1.0)
    mass = _clamp(float(clump_mass or 0.0), 0.0, 1.0)
    if "frill" in slot:
        if t >= 0.86:
            return "⣽"
        if t >= 0.58:
            return "⣿"
        if t >= 0.28:
            return "⣾" if mass >= 0.8 else "⣷"
        return "⣶"
    if "mane" in slot or "temple" in slot or "arc" in slot:
        if t >= 0.88:
            return "⣽" if ("back" in slot or "rear" in slot) else "⢿"
        if t >= 0.62:
            return "⣾" if mass >= 0.78 else "⣷"
        if t >= 0.34:
            return "⣷" if mass >= 0.8 or "front" in slot else "⣶"
        return "⣤" if mass < 0.74 else "⣶"
    if t >= 0.88:
        return "⢿" if ("back" in slot or "rear" in slot) else "⡿"
    if t >= 0.62:
        return "⣯" if "side" in slot else "⣻"
    if t >= 0.34:
        return "⣿" if mass >= 0.8 or "front" in slot else "⣾"
    return "⣶" if mass < 0.74 else "⣷"


def _glyph_message_text(text):
    return "".join(ch for ch in str(text or "").upper() if ch.isalnum())


def _glyph_message_seed(text):
    seed = 0
    for idx, ch in enumerate(str(text or "")):
        seed = (seed + ((idx + 1) * ord(ch))) % 104729
    return seed


def _hair_field_message_glyph(manifold, slot_name, sample_t, tuft_index, time_ms, fallback_glyph):
    packet = manifold if isinstance(manifold, dict) else {}
    message = _glyph_message_text(packet.get("message_text") or packet.get("message_seed_text") or "PANVITRUVIAN9K")
    packet_active = bool(packet.get("active")) or bool(packet.get("grid_active")) or bool(packet.get("mutation_active")) or bool(packet.get("perturbance_active"))
    if not packet_active or not message:
        return fallback_glyph
    slot = str(slot_name or "").strip().lower()
    t = _clamp(float(sample_t or 0.0), 0.0, 1.0)
    tuft = max(0.0, float(tuft_index or 0.0))
    time_seconds = max(0.0, float(time_ms or 0.0)) / 1000.0
    message_length = max(1, len(message))
    phase_rate = max(0.08, float(packet.get("phase_rate") or 0.65))
    repeat_count = max(1.0, float(packet.get("repeat_count") or 1.8))
    slot_stride = max(0.05, float(packet.get("slot_phase_stride") or 0.42))
    sample_stride = max(0.05, float(packet.get("sample_phase_stride") or 0.88))
    tuft_stride = max(0.05, float(packet.get("tuft_phase_stride") or 0.32))
    inertia_gain = _clamp(float(packet.get("inertia_gain") or 0.0), 0.0, 1.0)
    cohesion_gain = _clamp(float(packet.get("cohesion_gain") or 0.0), 0.0, 1.0)
    legibility_gain = _clamp(float(packet.get("legibility_gain") or 0.0), 0.0, 1.0)
    sharpness_gain = _clamp(float(packet.get("sharpness_gain") or 0.0), 0.0, 1.0)
    camera_gain = _clamp(float(packet.get("camera_alignment_gain") or 0.0), 0.0, 1.0)
    gravity_bias = _clamp(float(packet.get("gravity_bias") if packet.get("gravity_bias") is not None else 0.5), 0.0, 1.0)
    grid_columns = max(3, min(16, int(round(float(packet.get("grid_columns") or 8)))))
    grid_rows = max(4, min(24, int(round(float(packet.get("grid_rows") or 16)))))
    mutation_gain = _clamp(float(packet.get("mutation_gain") if packet.get("mutation_gain") is not None else 0.46), 0.0, 1.0)
    perturbance_gain = _clamp(float(packet.get("perturbance_gain") if packet.get("perturbance_gain") is not None else 0.58), 0.0, 1.0)
    offset_gain = _clamp(float(packet.get("offset_gain") if packet.get("offset_gain") is not None else 0.62), 0.0, 1.0)
    slot_seed = _glyph_message_seed(slot)
    slot_phase = ((slot_seed % 211) / 211.0) * slot_stride * message_length
    sample_phase = t * repeat_count * sample_stride * message_length
    tuft_phase = tuft * tuft_stride
    grid_column = max(0, min(grid_columns - 1, int(math.floor(t * grid_columns))))
    grid_row = max(0, min(grid_rows - 1, int(math.floor(tuft % grid_rows))))
    grid_phase = (
        ((grid_column / float(max(1, grid_columns - 1))) * (0.18 + (offset_gain * 0.46)))
        + ((grid_row / float(max(1, grid_rows - 1))) * (0.12 + (mutation_gain * 0.34)))
    ) * message_length
    inertial_lag = (1.0 - t) * inertia_gain * 0.85
    gravity_phase = gravity_bias * (1.0 - t) * 0.42
    cadence_phase = time_seconds * phase_rate * (0.72 + (sharpness_gain * 0.56) + (cohesion_gain * 0.22))
    mutation_phase = math.sin(
        (time_seconds * (1.6 + (perturbance_gain * 2.4)))
        + (grid_column * (0.42 + (offset_gain * 0.2)))
        + (grid_row * (0.26 + (mutation_gain * 0.18)))
        + slot_phase
    ) * (0.12 + (mutation_gain * 0.88)) * message_length
    carrier_index = int(math.floor(cadence_phase + slot_phase + sample_phase + tuft_phase + grid_phase + mutation_phase + gravity_phase - inertial_lag))
    emergence = _clamp(
        (t * (0.48 + (sharpness_gain * 0.12)))
        + (legibility_gain * 0.22)
        + (camera_gain * 0.12)
        + (cohesion_gain * 0.10),
        0.0,
        1.0,
    )
    emergence = _clamp(
        emergence
        + (perturbance_gain * 0.18)
        + (offset_gain * 0.08),
        0.0,
        1.0,
    )
    if emergence < 0.24:
        return fallback_glyph
    if emergence < 0.42 and (abs(carrier_index + int(math.floor(tuft))) % 4) == 1:
        return fallback_glyph
    return message[carrier_index % message_length]


def _hair_field_visual_styles(hair_state, slot_name, sample_t, tuft_index, time_ms, fallback_styles):
    source = hair_state if isinstance(hair_state, dict) else {}
    manifold = source.get("glyph_message_manifold") if isinstance(source.get("glyph_message_manifold"), dict) else {}
    granulation = source.get("granulation") if isinstance(source.get("granulation"), dict) else {}
    fallback = {
        "bright": fallback_styles.get("bright"),
        "mid": fallback_styles.get("mid"),
        "dim": fallback_styles.get("dim"),
        "trail": fallback_styles.get("dim"),
        "root": fallback_styles.get("root"),
    }
    if not manifold.get("active"):
        return fallback
    spectrum_mode = str(manifold.get("spectrum_mode") or "").strip().lower()
    spectrum_gain = _clamp(
        float(manifold.get("spectrum_gain") if manifold.get("spectrum_gain") is not None else (granulation.get("color_octave_gain") or 0.0)),
        0.0,
        1.0,
    )
    if not spectrum_mode or spectrum_mode == "off" or spectrum_gain <= 0.01:
        return fallback
    pop_gain = _clamp(float(manifold.get("pop_gain") if manifold.get("pop_gain") is not None else spectrum_gain), 0.0, 1.0)
    glow_gain = _clamp(
        float(manifold.get("glow_gain") if manifold.get("glow_gain") is not None else min(1.0, pop_gain + 0.18)),
        0.0,
        1.0,
    )
    hue_rate = max(0.01, float(manifold.get("hue_rate") or 0.22))
    hue_stride = max(0.01, float(manifold.get("hue_stride") or 0.12))
    slot_seed = _glyph_message_seed(str(slot_name or "hair"))
    time_seconds = max(0.0, float(time_ms or 0.0)) / 1000.0
    t = _clamp(float(sample_t or 0.0), 0.0, 1.0)
    tuft = max(0.0, float(tuft_index or 0.0))
    hue = (((slot_seed % 360) / 360.0) + (time_seconds * hue_rate) + (t * hue_stride) + (tuft * 0.031)) % 1.0
    if spectrum_mode == "crayolazy":
        hue = (hue + (0.06 * math.sin((time_seconds * 1.8) + (tuft * 0.7) + (t * 3.1)))) % 1.0
    hue_deg = int(round(hue * 360.0))
    glow_hue_deg = int(round((((hue + 0.08) % 1.0) + 1.0) % 1.0 * 360.0))
    saturation = int(round(max(68.0, min(100.0, 74.0 + (spectrum_gain * 18.0) + (8.0 if spectrum_mode == "crayolazy" else 0.0)))))
    lightness = int(round(max(58.0, min(78.0, 62.0 + (pop_gain * 10.0) + (t * 4.0) + (2.0 if spectrum_mode == "crayolazy" else 0.0)))))
    glow_lightness = int(round(max(52.0, min(82.0, lightness + 8.0 + (glow_gain * 6.0)))))
    return {
        "bright": _style_from_hsl(
            hue_deg,
            saturation,
            min(86, lightness + 6),
            1.0 + (pop_gain * 0.06),
            solid=True,
            min_saturation=0.80,
            target_lightness=0.68,
        ),
        "mid": _style_from_hsl(
            hue_deg,
            max(64, saturation - 4),
            lightness,
            0.98 + (pop_gain * 0.04),
            solid=True,
            min_saturation=0.72,
            target_lightness=0.58,
        ),
        "dim": _style_from_hsl(
            glow_hue_deg,
            max(58, saturation - 10),
            max(46, lightness - 10),
            0.86 + (glow_gain * 0.06),
            solid=True,
            min_saturation=0.62,
            target_lightness=0.46,
        ),
        "trail": _style_from_hsl(
            glow_hue_deg,
            max(52, saturation - 14),
            max(42, glow_lightness - 16),
            0.82 + (glow_gain * 0.08),
            solid=True,
            min_saturation=0.56,
            target_lightness=0.42,
        ),
        "root": fallback_styles.get("root"),
    }


def _hair_field_band(projected_subcells, sample_t, clump_mass):
    density = float(projected_subcells or 0.0)
    density *= 0.92 + (_clamp(float(clump_mass or 0.0), 0.0, 1.0) * 0.42)
    density *= 1.08 - (_clamp(float(sample_t or 0.0), 0.0, 1.0) * 0.26)
    if density >= 1.55:
        return "reference"
    if density >= 0.98:
        return "fused"
    if density >= 0.52:
        return "granular"
    if density >= 0.24:
        return "blob"
    return "trace"


def _hair_default_slots():
    return [
        "hair_cap", "hair_side_l", "hair_side_r", "hair_back",
        "hair_crown_fill_l", "hair_crown_fill_r",
        "hair_front_core", "hair_front_arc_l", "hair_front_arc_r",
        "hair_front_fill_l", "hair_front_fill_r",
        "hair_frill_front_inner_l", "hair_frill_front_inner_r",
        "hair_frill_front_mid_l", "hair_frill_front_mid_r",
        "hair_frill_front_outer_l", "hair_frill_front_outer_r",
        "hair_frill_front_low_l", "hair_frill_front_low_r",
        "hair_temple_l", "hair_temple_r",
        "hair_mane_l", "hair_mane_r",
        "hair_mid_fill_l", "hair_mid_fill_r",
        "hair_rear_l", "hair_rear_r",
        "hair_rear_fill_l", "hair_rear_fill_r",
        "hair_spike_crown", "hair_spike_crown_l", "hair_spike_crown_r",
        "hair_spike_front_l", "hair_spike_front_r",
        "hair_spike_mid_l", "hair_spike_mid_r",
        "hair_spike_back_l", "hair_spike_back_r", "hair_spike_rear",
    ]


def _hair_slot_profile(slot_name):
    key = str(slot_name or "").strip().lower()
    profile = {
        "slot": key,
        "active": True,
        "kind": "sheet",
        "region": "crown",
        "phase": 0.0,
        "rear_weight": 0.0,
    }
    if key == "hair_back":
        profile["region"] = "back"
        profile["phase"] = 1.35
        profile["rear_weight"] = 1.0
    elif key.startswith("hair_side_"):
        profile["region"] = "side"
        profile["phase"] = -0.8 if key.endswith("_l") else 0.8
    elif key.startswith("hair_crown_fill_"):
        profile["region"] = "crown"
        profile["phase"] = -0.12 if key.endswith("_l") else 0.12
    elif key == "hair_front_core":
        profile["region"] = "front_core"
    elif key.startswith("hair_front_arc_"):
        profile["region"] = "front"
        profile["phase"] = -0.18 if key.endswith("_l") else 0.18
    elif key.startswith("hair_front_fill_"):
        profile["region"] = "front"
        profile["phase"] = -0.38 if key.endswith("_l") else 0.38
    elif key.startswith("hair_frill_front_inner_"):
        profile["region"] = "front_frill"
        profile["phase"] = -0.28 if key.endswith("_l") else 0.28
    elif key.startswith("hair_frill_front_mid_"):
        profile["region"] = "front_frill"
        profile["phase"] = -0.46 if key.endswith("_l") else 0.46
    elif key.startswith("hair_frill_front_outer_"):
        profile["region"] = "front_frill"
        profile["phase"] = -0.68 if key.endswith("_l") else 0.68
    elif key.startswith("hair_frill_front_low_"):
        profile["region"] = "front_frill"
        profile["phase"] = -0.9 if key.endswith("_l") else 0.9
    elif key.startswith("hair_temple_"):
        profile["region"] = "temple"
        profile["phase"] = -1.04 if key.endswith("_l") else 1.04
    elif key.startswith("hair_mane_"):
        profile["region"] = "mane"
        profile["phase"] = -1.32 if key.endswith("_l") else 1.32
    elif key.startswith("hair_mid_fill_"):
        profile["region"] = "mid"
        profile["phase"] = -1.08 if key.endswith("_l") else 1.08
    elif key.startswith("hair_rear_fill_"):
        profile["region"] = "rear"
        profile["phase"] = -1.5 if key.endswith("_l") else 1.5
        profile["rear_weight"] = 0.88
    elif key.startswith("hair_rear_"):
        profile["region"] = "rear"
        profile["phase"] = -1.68 if key.endswith("_l") else 1.68
        profile["rear_weight"] = 0.82
    elif key.startswith("hair_spike_"):
        profile["kind"] = "spike"
        profile["region"] = "accent"
        if key == "hair_spike_crown_l":
            profile["phase"] = -0.16
        elif key == "hair_spike_crown_r":
            profile["phase"] = 0.16
        elif key == "hair_spike_front_l":
            profile["phase"] = -0.35
        elif key == "hair_spike_front_r":
            profile["phase"] = 0.35
        elif key == "hair_spike_mid_l":
            profile["phase"] = -0.92
        elif key == "hair_spike_mid_r":
            profile["phase"] = 0.92
        elif key == "hair_spike_back_l":
            profile["phase"] = -1.38
            profile["rear_weight"] = 0.88
        elif key == "hair_spike_back_r":
            profile["phase"] = 1.38
            profile["rear_weight"] = 0.88
        elif key == "hair_spike_rear":
            profile["phase"] = 1.84
            profile["rear_weight"] = 0.88
    return profile


def _hair_resolved_slots(hair_state):
    source = hair_state if isinstance(hair_state, dict) else {}
    explicit = source.get("resolved_slots")
    if isinstance(explicit, dict) and explicit:
        return explicit
    base_cut = source.get("base_cut") if isinstance(source.get("base_cut"), dict) else {}
    transform = source.get("blowout_transform") if isinstance(source.get("blowout_transform"), dict) else {}
    allow_spikes = bool(base_cut.get("allow_spikes")) and _clamp(float(transform.get("spike_gain") or 0.0), 0.0, 1.0) >= 0.72
    slots = source.get("source_slots") if isinstance(source.get("source_slots"), list) and source.get("source_slots") else _hair_default_slots()
    resolved = {}
    for slot_name in slots:
        profile = _hair_slot_profile(slot_name)
        if not profile.get("slot"):
            continue
        if profile.get("kind") == "spike":
            profile["active"] = allow_spikes
        resolved[profile["slot"]] = profile
    return resolved


def _hair_field_rows(snapshot, visible_bone_ids=None, drag_lod=False):
    embodiment = snapshot.get("embodiment") or {}
    if not bool(embodiment.get("scaffold_visible", False)):
        return []
    sequence = snapshot.get("sequence_field") if isinstance(snapshot.get("sequence_field"), dict) else {}
    force = sequence.get("force_wave") if isinstance(sequence.get("force_wave"), dict) else {}
    hair = force.get("hair_reactivity") if isinstance(force.get("hair_reactivity"), dict) else {}
    resolved_slots = _hair_resolved_slots(hair)
    glyph_manifold = hair.get("glyph_message_manifold") if isinstance(hair.get("glyph_message_manifold"), dict) else {}
    topology = hair.get("topology") if isinstance(hair.get("topology"), dict) else {}
    granulation = hair.get("granulation") if isinstance(hair.get("granulation"), dict) else {}
    if not hair and not topology:
        return []

    balance = snapshot.get("balance") or {}
    gravity_down = _vec3(balance.get("gravity_vector"))
    if _v_len(gravity_down) <= 1e-6:
        gravity_down = (0.0, -1.0, 0.0)
    gravity_down = _v_norm(gravity_down, (0.0, -1.0, 0.0))
    gravity_up = _v_scale(gravity_down, -1.0)
    field_vector = _vec3(force.get("field_vector"))
    if _v_len(field_vector) <= 1e-6:
        field_vector = (0.0, 0.0, 0.0)
    else:
        field_vector = _v_norm(field_vector, (0.0, 0.0, 0.0))

    lift_gain = _clamp(float(hair.get("lift_gain") or 0.0), 0.0, 1.0)
    sweep_gain = _clamp(float(hair.get("sweep_gain") or 0.0), 0.0, 1.0)
    flare_gain = _clamp(float(hair.get("flare_gain") or 0.0), 0.0, 1.0)
    simian_gain = _clamp(float(granulation.get("simian_ramp_gain") or 0.0), 0.0, 1.0)
    exhaust_bud_gain = _clamp(float(granulation.get("exhaust_bud_gain") or 0.0), 0.0, 1.0)
    gravity_follow_gain = _clamp(float(topology.get("gravity_follow_gain") or hair.get("gravity_dominance") or 0.64), 0.0, 1.0)
    root_lock_gain = _clamp(float(topology.get("root_lock_gain") or 0.74), 0.0, 1.0)
    tip_flex_gain = _clamp(float(topology.get("tip_flex_gain") or 0.22) + (exhaust_bud_gain * 0.08), 0.0, 1.0)
    radial_spread_gain = _clamp(float(topology.get("radial_spread_gain") or 0.28) + (exhaust_bud_gain * 0.08), 0.0, 1.0)
    surface_charge_gain = _clamp(float(topology.get("surface_charge_gain") or flare_gain) + (exhaust_bud_gain * 0.08), 0.0, 1.0)
    clump_count = max(6, int(round(float(topology.get("virtual_clump_count") or 9) + (simian_gain * 1.5) + (exhaust_bud_gain * 2.0))))
    topography_mode = str(topology.get("topography_mode") or topology.get("silhouette") or "").strip().lower()
    topographic_field = any(token in topography_mode for token in ("topographic", "ridge", "contour"))
    primary_peak_count = max(10, min(24, int(round(float(topology.get("primary_peak_count") or (16 if topographic_field else 12))))))
    interleave_peak_count = max(6, min(24, int(round(float(topology.get("interleave_peak_count") or max(8, primary_peak_count - 2))))))
    scalp_band_count = max(2, min(6, int(round(float(topology.get("scalp_band_count") or (4 if topographic_field else 3))))))
    trough_depth_gain = _clamp(float(topology.get("trough_depth_gain") or 0.28), 0.0, 1.0)
    crest_sharpness_gain = _clamp(float(topology.get("crest_sharpness_gain") or 0.52), 0.0, 1.0)
    ridge_noise_gain = _clamp(float(topology.get("ridge_noise_gain") or 0.24), 0.0, 1.0)
    contour_wrap_gain = _clamp(float(topology.get("contour_wrap_gain") or 0.38), 0.0, 1.0)
    scalp_coverage_gain = _clamp(float(topology.get("scalp_coverage_gain") or 0.58), 0.0, 1.0)
    primary_length_gain = _clamp(float(topology.get("primary_length_gain") or 0.56), 0.0, 1.0)
    interleave_length_gain = _clamp(float(topology.get("interleave_length_gain") or 0.42), 0.0, 1.0)
    front_panel_breakup_gain = _clamp(float(topology.get("front_panel_breakup_gain") or 0.44), 0.0, 1.0)
    lane_cascade_gain = _clamp(float(topology.get("lane_cascade_gain") or 0.34), 0.0, 1.0)
    glyph_time_ms = float(glyph_manifold.get("phase_timestamp_ms") or snapshot.get("snapshot_timestamp") or 0.0)
    field_styles = _hair_field_styles(hair)
    rows = []

    def mix(a, b, t):
        return _v_add(a, _v_scale(_v_sub(b, a), t))

    def clamp_signed(value, limit):
        cap = max(0.0, float(limit or 0.0))
        return max(-cap, min(cap, float(value or 0.0)))

    def contour_noise(seed, band_index):
        return math.sin((float(seed or 0.0) * (2.2 + (ridge_noise_gain * 2.8))) + (float(band_index or 0.0) * 0.91))

    def contour_tip_direction(normal, length_gain, crest_gain, front_bias):
        normal = _v_norm(normal, (0.0, 1.0, 0.0))
        return _v_norm(
            (
                (normal[0] * (0.68 + (radial_spread_gain * 0.22) + (contour_wrap_gain * 0.16) + (float(crest_gain or 0.0) * 0.14)))
                + (field_vector[0] * (0.08 + (sweep_gain * 0.18))),
                (normal[1] * (0.54 + (crest_sharpness_gain * 0.18) + (lift_gain * 0.12)))
                + 0.42
                + (surface_charge_gain * 0.16)
                + (lift_gain * 0.14)
                - (gravity_follow_gain * 0.04),
                (normal[2] * (0.56 + (contour_wrap_gain * 0.22) + (float(length_gain or 0.0) * 0.12)))
                + (float(front_bias or 0.0) * (0.08 + (sweep_gain * 0.12)))
                + (field_vector[2] * (0.08 + (sweep_gain * 0.18))),
            ),
            (0.0, 1.0, 0.0),
        )

    def contour_length_scalar(length_gain):
        return max(
            0.42,
            min(
                1.68,
                0.76
                + (float(length_gain or 0.0) * 0.38)
                + (surface_charge_gain * 0.12)
                + (lift_gain * 0.08)
                + (flare_gain * 0.08)
                + (simian_gain * 0.08)
                - (gravity_follow_gain * 0.05),
            ),
        )

    def append_tuft(slot_name, root, tip, bend, sample_count, tuft_index, clump_mass, field_scale):
        previous = root
        for sample_index in range(max(2, int(sample_count))):
            sample_t = float(sample_index + 1) / float(max(1, int(sample_count)))
            curve = math.sin(sample_t * math.pi)
            point = mix(root, tip, sample_t)
            point = _v_add(point, _v_scale(bend, curve))
            trail_start = previous if sample_index > 0 else root
            previous = point
            fallback_glyph = _hair_field_glyph(slot_name, sample_t, clump_mass)
            visual_styles = _hair_field_visual_styles(hair, slot_name, sample_t, tuft_index, glyph_time_ms, field_styles)
            rows.append({
                "point": point,
                "trail_start": trail_start,
                "world_size": max(0.045, float(field_scale or 0.08) * (0.28 + ((1.0 - sample_t) * 0.18) + (clump_mass * 0.1) + (exhaust_bud_gain * 0.06))),
                "glyph": _hair_field_message_glyph(glyph_manifold, slot_name, sample_t, tuft_index, glyph_time_ms, fallback_glyph),
                "sample_t": sample_t,
                "sample_index": sample_index,
                "clump_mass": clump_mass,
                "slot": slot_name,
                "tuft_index": tuft_index,
                "styles": visual_styles,
            })

    for row in embodiment.get("scaffold_pieces") or []:
        if not isinstance(row, dict) or row.get("visible") is False:
            continue
        slot_id = str(row.get("slot") or row.get("joint") or "").strip()
        joint_id = str(row.get("joint") or "").strip()
        if not slot_id.lower().startswith("hair_"):
            continue
        slot_profile = resolved_slots.get(slot_id.lower()) or _hair_slot_profile(slot_id)
        if not slot_profile.get("active", True):
            continue
        if visible_bone_ids and slot_id not in visible_bone_ids and joint_id not in visible_bone_ids:
            continue

        geometry = str(row.get("geometry") or "").strip().lower()
        center = _vec3(row.get("center"))
        size_world = _scaffold_size_world(row.get("size_local"), row.get("world_scale"))
        size_x = max(0.03, float(size_world[0] or 0.08))
        size_y = max(0.03, float(size_world[1] or 0.08))
        size_z = max(0.03, float(size_world[2] or 0.08))
        quaternion = _quat_norm(row.get("quaternion"))
        up_axis = _v_norm(_quat_rotate(quaternion, (0.0, 1.0, 0.0)), (0.0, 1.0, 0.0))
        right_axis = _v_norm(_quat_rotate(quaternion, (1.0, 0.0, 0.0)), (1.0, 0.0, 0.0))
        forward_axis = _v_norm(_quat_rotate(quaternion, (0.0, 0.0, 1.0)), (0.0, 0.0, 1.0))
        field_scale = max(size_x, size_y, size_z, 0.08)

        if slot_id.lower() == "hair_cap" or geometry in {"ellipsoid", "sphere"}:
            cap_band_count = scalp_band_count if topographic_field else max(2, scalp_band_count - 1)
            tuft_cursor = 0
            for band_index in range(cap_band_count):
                band_t = 0.5 if cap_band_count <= 1 else (float(band_index) / float(max(1, cap_band_count - 1)))
                band_front_bias = 0.58 - (band_t * 1.16)
                band_primary = band_index == (cap_band_count // 2)
                band_peak_count = (
                    primary_peak_count
                    if band_primary
                    else max(8, min(20, interleave_peak_count - max(0, band_index - 1)))
                )
                band_phase = 0.0 if band_primary else (math.pi / float(max(2, band_peak_count)))
                for cap_index in range(band_peak_count):
                    angle = band_phase + (float(cap_index) / float(max(1, band_peak_count))) * math.pi * 2.0
                    side = math.sin(angle)
                    orbit_front = math.cos(angle)
                    ridge_wave = contour_noise(angle + (band_front_bias * 0.62), band_index)
                    contour_front = clamp_signed(
                        (orbit_front * (0.28 + (contour_wrap_gain * 0.18)))
                        + band_front_bias
                        + (ridge_wave * 0.08 * ridge_noise_gain),
                        0.96,
                    )
                    root_normal = _v_norm(
                        _v_add(
                            _v_scale(right_axis, side * (0.84 - (abs(contour_front) * 0.08) + (0.06 if band_primary else 0.0))),
                            _v_add(
                                _v_scale(
                                    up_axis,
                                    0.54
                                    + ((1.0 - abs(contour_front)) * 0.16)
                                    + ((0.08 if band_primary else 0.02) * crest_sharpness_gain)
                                    + (ridge_wave * 0.04 * ridge_noise_gain),
                                ),
                                _v_scale(forward_axis, contour_front * (0.88 - (abs(side) * 0.08))),
                            ),
                        ),
                        up_axis,
                    )
                    root = _v_add(
                        center,
                        _v_add(
                            _v_scale(right_axis, root_normal[0] * size_x * (0.2 + (scalp_coverage_gain * 0.08))),
                            _v_add(
                                _v_scale(
                                    up_axis,
                                    (-size_y * 0.18)
                                    + (root_normal[1] * size_y * (0.18 + (scalp_coverage_gain * 0.08)))
                                    - (max(0.0, -ridge_wave) * size_y * 0.04 * trough_depth_gain),
                                ),
                                _v_scale(forward_axis, root_normal[2] * size_z * (0.14 + (contour_wrap_gain * 0.1))),
                            ),
                        ),
                    )
                    peak_wave = math.cos((angle * max(4, int(round(band_peak_count * 0.5)))) + (band_index * 0.78))
                    crest_gain = max(0.0, peak_wave) * (0.18 + (crest_sharpness_gain * 0.24))
                    length_gain = (
                        (primary_length_gain if band_primary else interleave_length_gain)
                        + crest_gain
                        - (max(0.0, -peak_wave) * trough_depth_gain * 0.08)
                    )
                    tip_dir = contour_tip_direction(root_normal, length_gain, crest_gain, contour_front)
                    tip = _v_add(
                        root,
                        _v_scale(
                            tip_dir,
                            field_scale * (0.92 + (contour_length_scalar(length_gain) * 0.28) + (crest_gain * 0.14)),
                        ),
                    )
                    bend = _v_add(
                        _v_scale(right_axis, side * (0.02 + (radial_spread_gain * 0.06) + (exhaust_bud_gain * 0.015))),
                        _v_scale(forward_axis, contour_front * (0.018 + (contour_wrap_gain * 0.02))),
                    )
                    append_tuft(
                        slot_id,
                        root,
                        tip,
                        bend,
                        (4 if drag_lod else 6) if band_primary else (4 if drag_lod else 5),
                        tuft_cursor,
                        0.92 + (crest_gain * 0.18) - (abs(side) * 0.06),
                        field_scale,
                    )
                    tuft_cursor += 1
            continue

        start = _vec3(row.get("segment_start"))
        end = _vec3(row.get("segment_end"))
        axis = _v_sub(end, start)
        axis_length = _v_len(axis)
        if axis_length <= 1e-6:
            axis = _v_scale(up_axis, size_y)
            axis_length = _v_len(axis)
            start = _v_add(center, _v_scale(axis, -0.5))
            end = _v_add(center, _v_scale(axis, 0.5))
        axis_dir = _v_norm(axis, up_axis)
        side_axis = _v_cross(axis_dir, gravity_down)
        if _v_len(side_axis) <= 1e-6:
            side_axis = right_axis
        side_axis = _v_norm(side_axis, right_axis)
        depth_axis = _v_cross(side_axis, axis_dir)
        if _v_len(depth_axis) <= 1e-6:
            depth_axis = forward_axis
        depth_axis = _v_norm(depth_axis, forward_axis)
        slot_text = slot_id.lower()
        slot_side = -1.0 if slot_text.endswith("_l") else (1.0 if slot_text.endswith("_r") else 0.0)
        rear_bias = -1.0 if slot_profile.get("region") in {"back", "rear"} or float(slot_profile.get("rear_weight") or 0.0) > 0.5 else (0.24 if slot_profile.get("region") in {"front", "front_core", "front_frill"} else 0.0)
        slot_is_spike = slot_profile.get("kind") == "spike"
        slot_is_side = slot_profile.get("region") == "side"
        slot_is_front = slot_profile.get("region") in {"front", "front_core", "front_frill"}
        slot_is_frill = slot_profile.get("region") == "front_frill"
        slot_is_temple = slot_profile.get("region") == "temple"
        slot_is_mane = slot_profile.get("region") == "mane"
        slot_is_arc = "arc" in slot_text
        slot_is_medusa_lane = (not slot_is_spike) and (not slot_is_side) and (slot_is_front or slot_is_frill or slot_is_temple or slot_is_mane or slot_is_arc)
        if slot_is_spike:
            spike_spread_count = max(3, min(7, 3 + int(round((simian_gain * 1.2) + (exhaust_bud_gain * 0.8)))))
            for spike_index in range(spike_spread_count):
                spread = 0.0 if spike_spread_count <= 1 else (-0.34 + ((float(spike_index) / float(max(1, spike_spread_count - 1))) * 0.68))
                spike_wave = contour_noise(spread + (slot_side * 0.6), spike_index)
                spike_front = clamp_signed(((-0.56 if rear_bias < 0 else 0.08) + (spread * 0.12) + (spike_wave * 0.06 * front_panel_breakup_gain)), 0.88)
                root = _v_add(
                    center,
                    _v_add(
                        _v_scale(right_axis, spread * size_x * 0.16),
                        _v_add(
                            _v_scale(up_axis, -size_y * 0.42 + ((1.0 - abs(spread)) * size_y * 0.06)),
                            _v_scale(forward_axis, spike_front * size_z * 0.06),
                        ),
                    ),
                )
                spike_normal = _v_norm(
                    _v_add(
                        _v_scale(right_axis, spread + (slot_side * (0.34 + (lane_cascade_gain * 0.1)))),
                        _v_add(
                            _v_scale(up_axis, 0.82 + ((1.0 - abs(spread)) * 0.14) + (spike_wave * 0.03 * ridge_noise_gain)),
                            _v_scale(forward_axis, spike_front),
                        ),
                    ),
                    up_axis,
                )
                tip_dir = contour_tip_direction(
                    spike_normal,
                    (primary_length_gain * 0.88) + (tip_flex_gain * 0.08),
                    0.1 + (crest_sharpness_gain * 0.18) - (abs(spread) * 0.05),
                    spike_front,
                )
                tip = _v_add(
                    root,
                    _v_scale(
                        tip_dir,
                        axis_length * (0.9 + (contour_length_scalar((primary_length_gain * 0.88) + (tip_flex_gain * 0.08)) * 0.2)),
                    ),
                )
                bend = _v_add(
                    _v_scale(side_axis, spread * (0.018 + (radial_spread_gain * 0.05))),
                    _v_scale(depth_axis, spike_front * (0.014 + (contour_wrap_gain * 0.02))),
                )
                append_tuft(
                    slot_id,
                    root,
                    tip,
                    bend,
                    4 if drag_lod else 5,
                    spike_index,
                    0.96 - (abs(spread) * 0.08),
                    field_scale,
                )
            continue
        if slot_is_medusa_lane:
            lane_depth_bias_base = -0.72 if rear_bias < 0 else (0.62 if slot_is_frill else (0.46 if slot_is_front else (0.08 if slot_is_temple else -0.18)))
            lane_cascade_count = max(2, min(5 if slot_is_frill else 4, 2 + int(round((lane_cascade_gain * 2.0) + (1.0 if slot_is_frill else 0.0)))))
            lane_spread_base = 0.54 if slot_is_frill else 0.42
            lane_spread_count_base = 4 if slot_is_frill else 3
            lane_tuft_index = 0
            for layer_index in range(lane_cascade_count):
                layer_t = 0.5 if lane_cascade_count <= 1 else (float(layer_index) / float(max(1, lane_cascade_count - 1)))
                layer_spread_count = lane_spread_count_base + int(round(front_panel_breakup_gain * 2.0)) - (1 if layer_index > 1 else 0)
                layer_spread_count = max(3, min(6 if slot_is_frill else 5, layer_spread_count))
                layer_phase = 0.0 if layer_index % 2 == 0 else ((1.0 / float(max(3, layer_spread_count))) * front_panel_breakup_gain)
                for spread_index in range(layer_spread_count):
                    spread_t = 0.5 if layer_spread_count <= 1 else (float(spread_index) / float(max(1, layer_spread_count - 1)))
                    spread = ((spread_t * 2.0) - 1.0) * lane_spread_base
                    spread += ((layer_phase - 0.5) * 0.12) * front_panel_breakup_gain
                    ridge_wave = contour_noise((layer_index * 0.78) + (spread * 1.9), spread_index)
                    contour_spread = clamp_signed(spread + (ridge_wave * 0.08 * ridge_noise_gain), 0.72 if slot_is_frill else 0.56)
                    scalp_curve = max(0.0, 1.0 - (abs(contour_spread) * abs(contour_spread)))
                    depth_bias = lane_depth_bias_base + (contour_spread * (0.1 if slot_is_frill else 0.14)) + ((layer_t - 0.5) * 0.18 * lane_cascade_gain)
                    root = _v_add(
                        center,
                        _v_add(
                            _v_scale(
                                right_axis,
                                (contour_spread + (slot_side * (0.08 if slot_is_frill else 0.14))) * size_x * (0.22 if slot_is_frill else 0.18),
                            ),
                            _v_add(
                                _v_scale(
                                    up_axis,
                                    -size_y * (0.24 if slot_is_frill else (0.34 if slot_is_temple else 0.32))
                                    + (layer_t * size_y * (0.1 if slot_is_frill else 0.06))
                                    + (scalp_curve * size_y * (0.08 if layer_index == 0 else 0.04))
                                    - (max(0.0, -ridge_wave) * size_y * 0.04 * trough_depth_gain),
                                ),
                                _v_scale(
                                    forward_axis,
                                    (depth_bias * size_z * 0.1)
                                    + (scalp_curve * size_z * (0.06 if (slot_is_front or slot_is_frill) else (-0.04 if rear_bias < 0 else 0.0))),
                                ),
                            ),
                        ),
                    )
                    lane_normal = _v_norm(
                        _v_add(
                            _v_scale(right_axis, (contour_spread * (0.82 + (contour_wrap_gain * 0.16))) + (slot_side * (0.34 if slot_is_temple else 0.18))),
                            _v_add(
                                _v_scale(up_axis, 0.68 + (scalp_curve * 0.18) + ((0.06 if layer_index == 0 else 0.02) * crest_sharpness_gain)),
                                _v_scale(forward_axis, (depth_bias * (0.86 + (contour_wrap_gain * 0.1))) + ((0.22 if (slot_is_front or slot_is_frill) else 0.0) - (0.12 if rear_bias < 0 else 0.0))),
                            ),
                        ),
                        up_axis,
                    )
                    crest_gain = max(0.0, ((ridge_wave + 1.0) * 0.5) * (0.12 + (crest_sharpness_gain * 0.2))) + (0.06 if layer_index == 0 else 0.0)
                    length_gain = (
                        (primary_length_gain if layer_index == 0 else interleave_length_gain)
                        + (scalp_curve * 0.08)
                        + (0.08 if slot_is_frill else 0.0)
                        + (0.04 if slot_is_temple else 0.0)
                        - (max(0.0, -ridge_wave) * trough_depth_gain * 0.08)
                    )
                    tip_dir = contour_tip_direction(lane_normal, length_gain, crest_gain, depth_bias)
                    tip = _v_add(
                        root,
                        _v_scale(
                            tip_dir,
                            axis_length * (0.96 + (contour_length_scalar(length_gain) * 0.22) + (crest_gain * 0.1)),
                        ),
                    )
                    bend = _v_add(
                        _v_scale(side_axis, contour_spread * (0.018 + (radial_spread_gain * 0.06))),
                        _v_scale(depth_axis, depth_bias * (0.016 + (contour_wrap_gain * 0.02))),
                    )
                    append_tuft(
                        slot_id,
                        root,
                        tip,
                        bend,
                        (5 if drag_lod else 7) if slot_is_frill and layer_index == 0 else ((4 if drag_lod else 6) if layer_index == 0 else (4 if drag_lod else 5)),
                        lane_tuft_index,
                        0.92 + (crest_gain * 0.14) - (abs(contour_spread) * 0.08),
                        field_scale,
                    )
                    lane_tuft_index += 1
            continue
        spreads = (
            ([-0.56, -0.28, 0.0, 0.28, 0.56] if slot_is_frill else [-0.46, -0.24, 0.0, 0.24, 0.46])
            if slot_is_medusa_lane
            else ([-0.22, 0.22] if slot_is_side else ([-0.38, 0.0, 0.38] if slot_is_spike else [-0.28, 0.0, 0.28]))
        )
        root_center = _v_add(
            start,
            _v_scale(axis_dir, axis_length * (((0.1 if slot_is_frill else 0.08) if slot_is_medusa_lane else 0.04) + (root_lock_gain * 0.08))),
        )
        for tuft_index, spread in enumerate(spreads):
            depth_bias = (rear_bias * size_z * (0.16 if slot_is_medusa_lane else 0.12)) + (((0.12 if slot_is_frill else 0.08) if slot_is_front or slot_is_frill else 0.0) * size_z)
            root = _v_add(
                root_center,
                _v_add(
                    _v_scale(side_axis, spread * size_x * ((0.48 if slot_is_frill else 0.42) if slot_is_medusa_lane else (0.34 + (abs(slot_side) * 0.12)))),
                    _v_scale(depth_axis, depth_bias),
                ),
            )
            scalp_curve = max(0.0, 1.0 - min(1.0, abs(float(spread))) ** 2)
            root = _v_add(
                root,
                _v_add(
                    _v_scale(axis_dir, size_z * scalp_curve * (0.04 + (0.04 if slot_is_medusa_lane else 0.0) + (0.03 if slot_is_frill else 0.0))),
                    _v_scale(depth_axis, size_z * scalp_curve * ((0.05 if slot_is_front or slot_is_frill else (-0.03 if rear_bias < 0 else 0.0)))),
                ),
            )
            tip_dir = _v_add(
                _v_add(
                    _v_scale(axis_dir, 1.0 + (surface_charge_gain * 0.42) + (lift_gain * 0.22) + ((0.16 if slot_is_frill else 0.1) if slot_is_medusa_lane else 0.0)),
                    _v_scale(gravity_up, 0.08 + ((1.0 - gravity_follow_gain) * 0.34) + (lift_gain * 0.18) + ((0.1 if slot_is_frill else 0.06) if slot_is_medusa_lane else 0.0)),
                ),
                _v_add(
                    _v_scale(side_axis, (spread + (slot_side * ((0.22 if slot_is_frill else 0.34) if slot_is_medusa_lane else 0.24))) * (0.22 + (radial_spread_gain * ((0.68 if slot_is_frill else 0.56) if slot_is_medusa_lane else 0.44)))),
                    _v_add(
                        _v_scale(depth_axis, (rear_bias * (0.08 + (tip_flex_gain * ((0.34 if slot_is_frill else 0.3) if slot_is_medusa_lane else 0.22)))) + ((((0.18 if slot_is_frill else 0.14) if slot_is_front or slot_is_frill else 0.0) + (0.04 if slot_is_temple else 0.0)))),
                        _v_add(
                            _v_scale(field_vector, 0.1 + (sweep_gain * ((0.62 if slot_is_frill else 0.52) if slot_is_medusa_lane else 0.42))),
                            _v_scale(gravity_down, 0.03 + (gravity_follow_gain * 0.18)),
                        ),
                    ),
                ),
            )
            tip_dir = _v_norm(tip_dir, axis_dir)
            rear_exhaust = exhaust_bud_gain * (0.18 if ("back" in slot_text or "rear" in slot_text or slot_is_spike) else (0.12 if slot_is_medusa_lane else 0.08))
            tip = _v_add(root, _v_scale(tip_dir, axis_length * (0.92 + (lift_gain * 0.28) + (surface_charge_gain * 0.34) + (flare_gain * 0.14) + rear_exhaust + (((0.16 if slot_is_frill else 0.1) if slot_is_medusa_lane else 0.0)) + (0.08 if slot_is_spike else 0.0))))
            bend = _v_add(
                _v_scale(side_axis, spread * (0.02 + (radial_spread_gain * ((0.11 if slot_is_frill else 0.09) if slot_is_medusa_lane else 0.06)) + (exhaust_bud_gain * 0.015))),
                _v_scale(depth_axis, rear_bias * (0.018 + (exhaust_bud_gain * (0.024 if slot_is_medusa_lane else 0.018)))),
            )
            append_tuft(
                slot_id,
                root,
                tip,
                bend,
                ((5 if drag_lod else 7) if slot_is_frill else ((4 if drag_lod else 6) if slot_is_medusa_lane else (3 if drag_lod else 4))),
                tuft_index,
                0.82 + (0.08 if slot_is_spike else 0.0) + (((0.1 if slot_is_frill else 0.06) if slot_is_medusa_lane else 0.0)) - (abs(spread) * 0.08),
                field_scale,
            )
    return rows


def _collect_render_model(snapshot):
    drag_lod = _snapshot_has_active_camera_motion(snapshot)
    embodiment = snapshot.get("embodiment") or {}
    balance = snapshot.get("balance") or {}
    contacts = snapshot.get("contacts") or []
    scene = snapshot.get("scene") or {}
    theater = snapshot.get("theater") or {}
    weather = snapshot.get("weather") if isinstance(snapshot.get("weather"), dict) else {}
    render = snapshot.get("render") or {}
    workbench = snapshot.get("workbench") or {}
    bones = embodiment.get("bones") or []
    connections = embodiment.get("connections") or []
    bone_map = {str(bone.get("id") or bone.get("name") or ""): bone for bone in bones}
    visible_bone_ids = _visible_bone_ids(snapshot)
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
    quiet_workbench_stage = bool(render.get("workbench_stage_quiet")) if isinstance(render, dict) else False
    guide_palette = (guide.get("palette") or {}) if isinstance(guide, dict) else {}
    selection_palette = (
        (render.get("selection_palette") or {})
        if isinstance(render, dict)
        else {}
    ) or (workbench.get("selection_visual_state") or {})
    scene_substrate = scene.get("substrate") if isinstance(scene.get("substrate"), dict) else {}
    scene_grid = scene_substrate.get("grid") if isinstance(scene_substrate.get("grid"), dict) else {}
    environment_scene_mode = str(theater.get("mode") or "").strip().lower() == "environment"
    focus_visual = (
        (scene.get("focus_object_visual") or {})
        if isinstance(scene, dict)
        else {}
    ) or ((render.get("focus_object_visual") or {}) if isinstance(render, dict) else {})
    show_bones = bool(embodiment.get("skeleton_visible", True))
    show_scaffold = bool(embodiment.get("scaffold_visible", False))
    selected_surface = _selected_part_surface(snapshot)
    scoped_part_mode = bool(visible_bone_ids) and str(workbench.get("part_display_scope") or "body").strip().lower() != "body"
    selected_part_recipe = _selected_part_camera_recipe(snapshot) if scoped_part_mode else None

    body_base_color = "#f0f3f7"
    body_style = _style_from_color(
        body_base_color,
        "#f0f3f7",
        0.98,
        solid=True,
        min_saturation=0.0,
        target_lightness=0.95,
    )
    body_front_style = _style_from_color(
        body_base_color,
        "#ffffff",
        1.0,
        solid=True,
        min_saturation=0.0,
        target_lightness=0.98,
    )
    body_back_style = _style_from_color(
        body_base_color,
        "#adb5bf",
        0.82,
        solid=True,
        min_saturation=0.0,
        target_lightness=0.74,
    )
    body_edge_style = _style_from_color(
        body_base_color,
        "#d5dbe3",
        0.88,
        solid=True,
        min_saturation=0.0,
        target_lightness=0.84,
    )
    bone_line_style = _style_from_color(
        "#c7ced7",
        "#c7ced7",
        0.8,
        solid=True,
        min_saturation=0.0,
        target_lightness=0.72,
    )
    support_trace_style = _style_from_color(
        "#d2d8e0",
        "#d2d8e0",
        0.84,
        solid=True,
        min_saturation=0.0,
        target_lightness=0.8,
    )
    posed_style = _style_from_color(
        "#dde3ea",
        "#dde3ea",
        0.96,
        solid=True,
        min_saturation=0.0,
        target_lightness=0.86,
    )
    selected_style = _style_from_color(
        "#ffffff",
        "#ffffff",
        1.0,
        solid=True,
        min_saturation=0.0,
        target_lightness=0.98,
    )
    support_style = _style_from_color(
        "#e1e6ec",
        "#e1e6ec",
        0.92,
        solid=True,
        min_saturation=0.0,
        target_lightness=0.86,
    )
    airborne_style = support_style
    sliding_style = support_style
    minor_grid_style = _style_from_color(
        guide_palette.get("grid_minor") or "#203544",
        "#203544",
        1.7,
        solid=True,
        min_saturation=0.76,
        target_lightness=0.36,
    )
    major_grid_style = _style_from_color(
        guide_palette.get("grid_major") or "#4fe9d0",
        "#4fe9d0",
        1.08,
        solid=True,
        min_saturation=0.94,
        target_lightness=0.52,
    )
    crosshair_style = _style_from_color(
        guide_palette.get("crosshair") or guide_palette.get("halo") or "#8bf3de",
        "#8bf3de",
        1.08,
        solid=True,
        min_saturation=0.92,
        target_lightness=0.62,
    )
    frame_style = _style_from_color(
        guide_palette.get("frame") or guide_palette.get("inner_ring") or "#75c6ff",
        "#75c6ff",
        1.08,
        solid=True,
        min_saturation=0.92,
        target_lightness=0.58,
    )
    floor_minor_style = _style_from_color(
        "#6f756f",
        "#6f756f",
        0.82,
        solid=True,
        min_saturation=0.1,
        target_lightness=0.42,
    )
    floor_major_style = _style_from_color(
        "#988a74",
        "#988a74",
        0.94,
        solid=True,
        min_saturation=0.2,
        target_lightness=0.54,
    )
    halo_style = _style_from_color(
        guide_palette.get("halo") or "#6fe9d9",
        "#6fe9d9",
        1.08,
        solid=True,
        min_saturation=0.86,
        target_lightness=0.48,
    )
    pad_fill_style = _style_from_color(
        guide_palette.get("pad_fill") or "#0d141d",
        "#0d141d",
        1.5,
        solid=True,
        min_saturation=0.45,
        target_lightness=0.22,
    )
    inner_ring_style = _style_from_color(
        guide_palette.get("inner_ring") or "#5ac8ff",
        "#5ac8ff",
        1.08,
        solid=True,
        min_saturation=0.9,
        target_lightness=0.56,
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
    if environment_scene_mode:
        try:
            support_y = float(scene_substrate.get("ground_y") or support_y)
        except Exception:
            pass
    else:
        try:
            guide_floor = float(guide.get("floor_y") or support_y)
            support_y = guide_floor
        except Exception:
            pass
    focus_point = _snapshot_focus_point(snapshot)
    selected_anchor = _vec3(
        (selected_surface.get("world_center") if isinstance(selected_surface, dict) else None)
        or (selected_surface.get("world_anchor") if isinstance(selected_surface, dict) else None)
    ) if selected_surface else None
    if scoped_part_mode and selected_anchor and _v_len(selected_anchor) > 0.001:
        focus_point = selected_anchor

    scene_bounds = scene.get("bounds") or {}
    min_bound = scene_bounds.get("min") or {}
    max_bound = scene_bounds.get("max") or {}
    guide_grid_span = float(guide.get("grid_span") or 0.0) if isinstance(guide, dict) else 0.0
    grid_box = scene_grid.get("box") if isinstance(scene_grid.get("box"), dict) else {}
    selected_bounds_points = _world_bounds_points(selected_surface) if scoped_part_mode else []
    if scoped_part_mode and selected_bounds_points:
        scoped_bounds = _bounds3(selected_bounds_points)
        min_x = float(scoped_bounds["min"][0]) - max(0.3, float(scoped_bounds["size"][0]) * 0.18)
        max_x = float(scoped_bounds["max"][0]) + max(0.3, float(scoped_bounds["size"][0]) * 0.18)
        min_z = float(scoped_bounds["min"][2]) - max(0.3, float(scoped_bounds["size"][2]) * 0.18)
        max_z = float(scoped_bounds["max"][2]) + max(0.3, float(scoped_bounds["size"][2]) * 0.18)
    elif environment_scene_mode and isinstance(grid_box.get("min"), dict) and isinstance(grid_box.get("max"), dict):
        min_x = float((grid_box.get("min") or {}).get("x", focus_point[0] - 8) or (focus_point[0] - 8))
        max_x = float((grid_box.get("max") or {}).get("x", focus_point[0] + 8) or (focus_point[0] + 8))
        min_z = float((grid_box.get("min") or {}).get("z", focus_point[2] - 8) or (focus_point[2] - 8))
        max_z = float((grid_box.get("max") or {}).get("z", focus_point[2] + 8) or (focus_point[2] + 8))
    elif guide_grid_span > 0.1:
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
    sequence_motion = _sequence_shared_surface_motion_clock(snapshot)
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
    object_outlines = []

    if quiet_workbench_stage:
        pass
    elif environment_scene_mode and isinstance(grid_box.get("min"), dict) and isinstance(grid_box.get("max"), dict):
        first_x = float((grid_box.get("min") or {}).get("x", min_x) or min_x)
        first_z = float((grid_box.get("min") or {}).get("z", min_z) or min_z)
        last_x = float((grid_box.get("max") or {}).get("x", max_x) or max_x)
        last_z = float((grid_box.get("max") or {}).get("z", max_z) or max_z)
        grid_divisions = max(1, int(scene_grid.get("divisions") or 0) or 40)
        grid_step_x = max(0.25, abs(last_x - first_x) / float(grid_divisions))
        grid_step_z = max(0.25, abs(last_z - first_z) / float(grid_divisions))
        for xi in range(grid_divisions + 1):
            x_cursor = first_x + (grid_step_x * xi)
            is_edge_x = xi == 0 or xi == grid_divisions
            is_major_x = (xi % 5) == 0
            guide_grid_lines.append({
                "start": (x_cursor, support_y, first_z),
                "end": (x_cursor, support_y, last_z),
                "style": frame_style if is_edge_x else (major_grid_style if is_major_x else minor_grid_style),
                "priority": 2 if is_edge_x else (1 if is_major_x else 0),
                "samples": 34 if is_edge_x else (26 if is_major_x else 18),
            })
        for zi in range(grid_divisions + 1):
            z_cursor = first_z + (grid_step_z * zi)
            is_edge_z = zi == 0 or zi == grid_divisions
            is_major_z = (zi % 5) == 0
            guide_grid_lines.append({
                "start": (first_x, support_y, z_cursor),
                "end": (last_x, support_y, z_cursor),
                "style": frame_style if is_edge_z else (major_grid_style if is_major_z else minor_grid_style),
                "priority": 2 if is_edge_z else (1 if is_major_z else 0),
                "samples": 34 if is_edge_z else (26 if is_major_z else 18),
            })
    elif guide_grid_span > 0.1:
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
        first_x = math.floor(min_x / grid_step) * grid_step
        first_z = math.floor(min_z / grid_step) * grid_step
        x_cursor = first_x
        last_x = math.ceil(max_x / grid_step) * grid_step
        last_z = math.ceil(max_z / grid_step) * grid_step
        while x_cursor <= last_x + 1e-6:
            is_edge_x = abs(x_cursor - first_x) < 1e-6 or abs(x_cursor - last_x) < 1e-6
            x_index = int(round((x_cursor - first_x) / grid_step))
            is_major_x = (x_index % 4) == 0
            guide_grid_lines.append({
                "start": (x_cursor, support_y, first_z),
                "end": (x_cursor, support_y, last_z),
                "style": frame_style if is_edge_x else (major_grid_style if is_major_x else minor_grid_style),
                "priority": 2 if is_edge_x else (1 if is_major_x else 0),
                "samples": 34 if is_edge_x else (26 if is_major_x else 18),
            })
            z_cursor = first_z
            while z_cursor <= last_z + 1e-6:
                z_index = int(round((z_cursor - first_z) / grid_step))
                is_edge_z = abs(z_cursor - first_z) < 1e-6 or abs(z_cursor - last_z) < 1e-6
                is_corner = is_edge_x and is_edge_z
                is_major = is_major_x or ((z_index % 4) == 0)
                floor_points.append({
                    "point": (x_cursor, support_y, z_cursor),
                    "style": frame_style if is_corner else (major_grid_style if is_major else minor_grid_style),
                    "priority": 2 if is_corner else (1 if is_major else 0),
                    "radius": 1 if is_corner else (1 if is_major else 0),
                })
                z_cursor += grid_step
            x_cursor += grid_step
        z_cursor = first_z
        while z_cursor <= last_z + 1e-6:
            z_index = int(round((z_cursor - first_z) / grid_step))
            is_edge_z = abs(z_cursor - first_z) < 1e-6 or abs(z_cursor - last_z) < 1e-6
            is_major_z = (z_index % 4) == 0
            guide_grid_lines.append({
                "start": (first_x, support_y, z_cursor),
                "end": (last_x, support_y, z_cursor),
                "style": frame_style if is_edge_z else (major_grid_style if is_major_z else minor_grid_style),
                "priority": 2 if is_edge_z else (1 if is_major_z else 0),
                "samples": 34 if is_edge_z else (26 if is_major_z else 18),
            })
            z_cursor += grid_step

    if not scoped_part_mode and not quiet_workbench_stage:
        shared_motion_overlay = _sequence_shared_surface_motion_overlay(
            sequence_motion,
            motion,
            support_y,
            span_x,
            span_z,
            guide_grid_span,
            {
                "motion": motion_style,
                "heading": heading_style,
            },
        )
        guide_segments.extend(shared_motion_overlay.get("segments") or [])
        guide_rings.extend(shared_motion_overlay.get("rings") or [])

    segments = []
    projected_points = []
    if show_bones:
        for start_id, end_id in connections:
            if visible_bone_ids and (str(start_id) not in visible_bone_ids or str(end_id) not in visible_bone_ids):
                continue
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

    scaffold_segments = []
    hair_fields = _hair_field_rows(snapshot, visible_bone_ids=visible_bone_ids, drag_lod=drag_lod)
    sequence = snapshot.get("sequence_field") if isinstance(snapshot.get("sequence_field"), dict) else {}
    force = sequence.get("force_wave") if isinstance(sequence.get("force_wave"), dict) else {}
    hair_state = force.get("hair_reactivity") if isinstance(force.get("hair_reactivity"), dict) else {}
    hair_styles = _hair_field_styles(hair_state)
    if show_scaffold:
        for row in embodiment.get("scaffold_pieces") or []:
            if not isinstance(row, dict) or row.get("visible") is False:
                continue
            slot_id = str(row.get("slot") or row.get("joint") or "").strip()
            joint_id = str(row.get("joint") or "").strip()
            if visible_bone_ids and slot_id and slot_id not in visible_bone_ids and joint_id not in visible_bone_ids:
                continue
            start = _vec3(row.get("segment_start"))
            end = _vec3(row.get("segment_end"))
            center = _vec3(row.get("center"))
            size_world = _scaffold_size_world(row.get("size_local"), row.get("world_scale"))
            quaternion = _quat_norm(row.get("quaternion"))
            geometry = str(row.get("geometry") or "").strip().lower()
            color_value = str(row.get("color") or "#bfb7aa")
            text_surface_only = slot_id.lower().startswith("hair_")
            if text_surface_only:
                continue
            segment_common = {
                "slot": str(row.get("slot") or row.get("joint") or ""),
                "geometry": geometry,
                "body_style": _style_from_color(
                    color_value,
                    color_value or "#bfb7aa",
                    1.08,
                    solid=True,
                    min_saturation=0.34,
                    target_lightness=0.7,
                ),
                "edge_style": _style_from_color(
                    color_value,
                    color_value or "#a59b8d",
                    0.92,
                    solid=True,
                    min_saturation=0.24,
                    target_lightness=0.56,
                ),
                "priority": 5 if "foot" in str(row.get("slot") or "") else 4,
            }
            if geometry == "box":
                for box_start, box_end in _scaffold_box_edge_segments(center, size_world, quaternion):
                    scaffold_segments.append({
                        **segment_common,
                        "start": box_start,
                        "end": box_end,
                        "radius_start": 0.0,
                        "radius_end": 0.0,
                        "render_mode": "wire",
                    })
                    projected_points.extend([box_start, box_end])
                continue
            if geometry in {"ellipsoid", "sphere"}:
                # Use six atom-like orbital contours so torso/head volumes feel
                # carved in 3D instead of flat-filled or transparently hollow.
                orbit_layouts = (
                    ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), 14 if drag_lod else 20),
                    ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), 12 if drag_lod else 18),
                    ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), 12 if drag_lod else 18),
                    ((math.cos(math.radians(36.0)), 0.0, math.sin(math.radians(36.0))), (0.0, 1.0, 0.0), 12 if drag_lod else 18),
                    ((math.cos(math.radians(72.0)), 0.0, math.sin(math.radians(72.0))), (0.0, 1.0, 0.0), 12 if drag_lod else 18),
                    ((math.cos(math.radians(108.0)), 0.0, math.sin(math.radians(108.0))), (0.0, 1.0, 0.0), 12 if drag_lod else 18),
                )
                for axis_u, axis_v, sample_count in orbit_layouts:
                    for ring_start, ring_end in _scaffold_ellipsoid_orbit_segments(
                        center,
                        size_world,
                        quaternion,
                        axis_u,
                        axis_v,
                        sample_count,
                    ):
                        scaffold_segments.append({
                            **segment_common,
                            "start": ring_start,
                            "end": ring_end,
                            "radius_start": 0.0,
                            "radius_end": 0.0,
                            "render_mode": "wire",
                        })
                        projected_points.extend([ring_start, ring_end])
                continue
            scaffold_segments.append({
                **segment_common,
                "start": start,
                "end": end,
                "radius_start": max(0.008, float(row.get("radius_start") or 0.02)),
                "radius_end": max(0.008, float(row.get("radius_end") or 0.02)),
                "render_mode": "wire" if text_surface_only else "solid",
            })
            projected_points.extend([start, end])

    contact_states = {str(row.get("joint") or ""): row for row in contacts}
    markers = []
    if show_bones:
        for bone in bones:
            bone_id = str(bone.get("id") or bone.get("name") or "")
            if visible_bone_ids and bone_id not in visible_bone_ids:
                continue
            point = _vec3(bone.get("world_pos"))
            state = contact_states.get(bone_id)
            landmark = _landmark_kind(bone_id)
            label = "•"
            if state:
                label = CONTACT_MARKERS.get(str(state.get("state") or "").lower(), "o")
            marker_style = selected_style if bool(bone.get("selected")) else (posed_style if bool(bone.get("posed")) else body_style)
            marker_radius = 0
            marker_priority = 5 if state else 4
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
    contact_patches = []
    diagnostic_contacts = (((workbench.get("motion_diagnostics") or {}).get("contacts")) or [])
    if not scoped_part_mode and not quiet_workbench_stage:
        for row in balance.get("support_polygon") or []:
            support_polygon.append((float(row.get("x") or 0), support_y, float(row.get("z") or 0)))
        projected_points.extend(support_polygon)
        for row in diagnostic_contacts:
            patch = ((row or {}).get("contact_patch")) or {}
            footprint_world = patch.get("active_manifold_world") or patch.get("footprint_world") or []
            points = [_vec3(point) for point in footprint_world if isinstance(point, dict)]
            if len(points) >= 1:
                contact_patches.append({
                    "points": points,
                    "style": support_style if row.get("supporting") else posed_style,
                    "priority": 4 if row.get("supporting") else 3,
                })
                projected_points.extend(points)

    com = _vec3(balance.get("com")) if not scoped_part_mode else focus_point
    if not scoped_part_mode:
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
    scene_object_rows = []
    if _scene_proximity_enabled(snapshot):
        scene_object_rows = scene.get("objects") if isinstance(scene.get("objects"), list) else []
        if not scene_object_rows:
            scene_object_rows = scene.get("focus_neighborhood") if isinstance(scene.get("focus_neighborhood"), list) else []
    if not scoped_part_mode and scene_object_rows:
        for index, obj in enumerate(scene_object_rows):
            if not isinstance(obj, dict):
                continue
            point = _vec3(obj.get("position"))
            spatial = obj.get("spatial") if isinstance(obj.get("spatial"), dict) else {}
            outline_points = _box_floor_outline(spatial.get("box"), y_override=support_y)
            obj_kind = str(obj.get("kind") or "").strip().lower()
            marker = _scene_object_marker(obj_kind, focused=bool(obj.get("focused")))
            objects.append({
                "char": marker["char"],
                "label": str(obj.get("label") or obj.get("id") or obj.get("kind") or f"object_{index + 1}"),
                "point": point,
                "distance": obj.get("distance"),
                "radius": 0 if outline_points else int(marker["radius"]),
                "stamp": "point" if outline_points else str(marker.get("stamp") or "point"),
                "focused": bool(obj.get("focused")),
                "style": _style_from_color(
                    obj.get("color") or ((obj.get("colors") or {}).get("edge")) or "#66b8ff",
                    "#66b8ff",
                    1.18 if bool(obj.get("focused")) else 1.0,
                ),
            })
            projected_points.append(point)
            if outline_points:
                object_outlines.append({
                    "points": outline_points,
                    "style": _style_from_color(
                        obj.get("color") or ((obj.get("colors") or {}).get("edge")) or "#66b8ff",
                        "#66b8ff",
                        1.08 if bool(obj.get("focused")) else 0.96,
                    ),
                    "priority": 5 if bool(obj.get("focused")) else 4,
                })
                projected_points.extend(outline_points)

    perspective_points = [focus_point]
    if not scoped_part_mode:
        perspective_points.extend([com, heading_origin, heading_tip])
        perspective_points.extend(support_polygon)
    for segment in segments:
        perspective_points.extend([segment["start"], segment["end"]])
    for segment in scaffold_segments:
        perspective_points.extend([segment["start"], segment["end"]])
    for hair_row in hair_fields:
        perspective_points.append(hair_row["point"])
        if hair_row.get("trail_start") is not None:
            perspective_points.append(hair_row["trail_start"])
    for patch in contact_patches:
        perspective_points.extend(patch.get("points") or [])
    for marker in markers:
        perspective_points.append(marker["point"])
    for obj in objects:
        perspective_points.append(obj["point"])
    for outline in object_outlines:
        perspective_points.extend(outline.get("points") or [])
    if weather.get("enabled"):
        weather_volume = _weather_volume_bounds(weather)
        projected_points.extend(weather_volume.get("corners") or [])
        perspective_points.extend(weather_volume.get("corners") or [])
    for hair_row in hair_fields:
        projected_points.append(hair_row["point"])
        if hair_row.get("trail_start") is not None:
            projected_points.append(hair_row["trail_start"])

    return {
        "drag_lod": drag_lod,
        "segments": segments,
        "scaffold_segments": scaffold_segments,
        "hair_fields": hair_fields,
        "hair_styles": hair_styles,
        "markers": markers,
        "support_polygon": support_polygon,
        "contact_patches": contact_patches,
        "com": com,
        "focus_point": focus_point,
        "motion": motion,
        "sequence_motion": sequence_motion,
        "weather": weather if weather.get("enabled") else {},
        "heading_origin": heading_origin,
        "heading_length": heading_length,
        "heading_tip": heading_tip,
        "scoped_part_mode": scoped_part_mode,
        "selected_part_surface": selected_surface,
        "part_camera_recipe": selected_part_recipe,
        "objects": objects,
        "floor_points": floor_points,
        "pad_fill_points": pad_fill_points,
        "guide_segments": guide_segments,
        "guide_triangles": guide_triangles,
        "guide_grid_lines": guide_grid_lines,
        "guide_rings": guide_rings,
        "object_outlines": object_outlines,
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


def _render_projection(snapshot, width, height, mode, history=None, surface_mode=TEXT_THEATER_SURFACE_MODE):
    width = max(20, width)
    height = max(8, height)
    model = _collect_render_model(snapshot)
    drag_lod = bool(model.get("drag_lod"))
    motion = model.get("motion") or {}
    legend = []
    if mode == "perspective":
        legend.append("Perspective · fixed camera/stage/body projection")
    elif mode == "quarter":
        legend.append("Quarter view · companion orbit")
    elif mode == "profile":
        legend.append("Profile view · companion orbit")
    elif mode == "top":
        legend.append("Top view · paired body/floor projection")
    else:
        legend.append("Front view · paired body/floor projection")
    object_bits = [f"· {obj['label']}" for obj in model["objects"][:6]]
    if object_bits:
        legend.append("Objects: " + " | ".join(object_bits))
    scene_height = max(4, height - len(legend))
    # Keep the main body/environment read on the braille backend until the
    # broader sharp/granular projection work is finished. Weather gets its
    # own sharper glyph handling below without switching the whole scene.
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
            ring_samples = _detail_scaled_count(ring["samples"], drag_lod, 18)
            for point in _sample_circle_points(ring["center"], ring["radius"], ring_samples):
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
            for point in _sample_segment_points(
                guide_row["start"],
                guide_row["end"],
                _detail_scaled_count(guide_row["samples"], drag_lod, 12),
            ):
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
        for guide_row in model["guide_grid_lines"]:
            for point in _sample_segment_points(
                guide_row["start"],
                guide_row["end"],
                _detail_scaled_count(guide_row.get("samples", 18), drag_lod, 10),
            ):
                coords = project(point)
                if coords is None:
                    continue
                x, y = mapper(coords)
                guide_priority = int(guide_row.get("priority", 0))
                guide_style = guide_row.get("style") or model["styles"]["floor_minor"]
                _braille_put(
                    canvas,
                    x,
                    y,
                    priority=guide_priority,
                    style=guide_style,
                )

    if mode not in {"perspective", "quarter", "profile"} and not use_cell_canvas:
        for guide_row in model["guide_grid_lines"]:
            for point in _sample_segment_points(
                guide_row["start"],
                guide_row["end"],
                _detail_scaled_count(guide_row["samples"], drag_lod, 12),
            ):
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
            ring_samples = _detail_scaled_count(ring["samples"], drag_lod, 18)
            for point in _sample_circle_points(ring["center"], ring["radius"], ring_samples):
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
            for point in _sample_segment_points(
                guide_row["start"],
                guide_row["end"],
                _detail_scaled_count(guide_row["samples"], drag_lod, 12),
            ):
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
    perspective_scaffold_edge_layer = {}
    perspective_scaffold_body_layer = {}
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
            sample_count = _detail_scaled_count(sample_count, drag_lod, 10)
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
                sample_count = _detail_scaled_count(sample_count, drag_lod, 10)
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
            sample_count = _detail_scaled_count(28, drag_lod, 12)
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

    for segment in model.get("scaffold_segments") or []:
        start = segment["start"]
        end = segment["end"]
        body_style = segment.get("body_style") or model["styles"]["body"]
        edge_style = segment.get("edge_style") or model["styles"]["body_edge"]
        render_mode = str(segment.get("render_mode") or "solid").strip().lower()
        if use_cell_canvas:
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
            thickness = 0 if render_mode == "wire" else _scaffold_segment_thickness_band(segment)
            sample_count = 20 if render_mode == "wire" else (20 if thickness <= 0 else (24 if thickness == 1 else 30))
            sample_count = _detail_scaled_count(sample_count, drag_lod, 10)
            for point in _sample_segment_points(start, end, sample_count):
                coords = project(point)
                if coords is None:
                    continue
                x, y = mapper(coords)
                if render_mode == "wire":
                    put_mark(x, y, "·", priority=5, style=edge_style)
                    continue
                depth_char = _depth_char(point_depth(point), near_depth, far_depth, dense=True)
                put_mark(x, y, depth_char, priority=5, style=body_style)
                if thickness >= 1 and dir_len > 1e-6:
                    put_mark(x + normal_x, y + normal_y, depth_char, priority=5, style=body_style)
                    put_mark(x - normal_x, y - normal_y, depth_char, priority=5, style=body_style)
                if thickness >= 2 and dir_len > 1e-6:
                    put_mark(x + (normal_x * 2), y + (normal_y * 2), depth_char, priority=4, style=body_style)
                    put_mark(x - (normal_x * 2), y - (normal_y * 2), depth_char, priority=4, style=body_style)
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
                if render_mode == "wire":
                    sample_count = max(18, _perspective_segment_sample_count(mapped_start, mapped_end, 0))
                    sample_count = _detail_scaled_count(sample_count, drag_lod, 10)
                    for point in _sample_segment_points(start, end, sample_count):
                        coords = project(point)
                        if coords is None:
                            continue
                        x, y = mapper(coords)
                        depth = point_depth(point)
                        if depth is None or depth <= 0.05:
                            continue
                        _depth_buffer_put(
                            perspective_scaffold_edge_layer,
                            x,
                            y,
                            depth + 0.0005,
                            edge_style,
                            priority=6,
                        )
                    continue
                projected_radius = max(
                    _project_radius_to_subcells(float(segment.get("radius_start") or 0.02), start_depth, render_height, camera_meta),
                    _project_radius_to_subcells(float(segment.get("radius_end") or 0.02), end_depth, render_height, camera_meta),
                )
                sample_count = _perspective_segment_sample_count(mapped_start, mapped_end, projected_radius)
                sample_count = _detail_scaled_count(sample_count, drag_lod, 10)
                for idx, point in enumerate(_sample_segment_points(start, end, sample_count)):
                    coords = project(point)
                    if coords is None:
                        continue
                    x, y = mapper(coords)
                    depth = point_depth(point)
                    if depth is None or depth <= 0.05:
                        continue
                    _depth_buffer_put(
                        perspective_scaffold_edge_layer,
                        x,
                        y,
                        depth + 0.0005,
                        edge_style,
                        priority=6,
                    )
                    t = float(idx) / float(max(1, sample_count))
                    radius_world = float(segment.get("radius_start") or 0.02) + (
                        (float(segment.get("radius_end") or 0.02) - float(segment.get("radius_start") or 0.02)) * t
                    )
                    radius = _project_radius_to_subcells(radius_world, depth, render_height, camera_meta)
                    if projected_radius >= 1 or radius_world >= 0.016:
                        radius = max(1, radius)
                    if projected_radius >= 2 or radius_world >= 0.12:
                        radius = max(2, radius)
                    if projected_radius >= 3 or radius_world >= 0.6:
                        radius = max(3, radius)
                    radius = int(_clamp(radius, 0, 3))
                    for dx, dy, style_slot, priority in _body_stamp_offsets(radius, idx):
                        _depth_buffer_put(
                            perspective_scaffold_body_layer,
                            x + dx,
                            y + dy,
                            depth + ((abs(dx) + abs(dy)) * 0.0004),
                            body_style,
                            priority=max(4, priority + 1),
                        )
                continue
            sample_count = 24 if render_mode == "wire" else 30
            sample_count = _detail_scaled_count(sample_count, drag_lod, 10)
            for idx, point in enumerate(_sample_segment_points(start, end, sample_count)):
                coords = project(point)
                if coords is None:
                    continue
                x, y = mapper(coords)
                if render_mode == "wire":
                    _braille_put(canvas, x, y, priority=4, style=edge_style)
                    continue
                _braille_put(canvas, x, y, priority=3, style=edge_style)
                t = float(idx) / float(max(1, sample_count))
                radius_world = float(segment.get("radius_start") or 0.02) + (
                    (float(segment.get("radius_end") or 0.02) - float(segment.get("radius_start") or 0.02)) * t
                )
                radius = _orthographic_scaffold_stamp_radius(radius_world)
                if radius_world >= 0.12:
                    radius = max(2, radius)
                if radius_world >= 0.6:
                    radius = max(3, radius)
                for dx, dy, style_slot, priority in _body_stamp_offsets(radius, idx):
                    _braille_put(canvas, x + dx, y + dy, priority=max(3, priority + 1), style=body_style)

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
        for (x, y), sample in sorted(
            perspective_scaffold_body_layer.items(),
            key=lambda item: (item[1].get("depth", 1e9), item[1].get("priority", 0)),
            reverse=True,
        ):
            _braille_put(
                canvas,
                x,
                y,
                priority=int(sample.get("priority", 4)),
                style=sample.get("style") or model["styles"]["body"],
            )
        for (x, y), sample in sorted(
            perspective_scaffold_edge_layer.items(),
            key=lambda item: (item[1].get("depth", 1e9), item[1].get("priority", 0)),
            reverse=True,
        ):
            _braille_put(
                canvas,
                x,
                y,
                priority=int(sample.get("priority", 6)),
                style=sample.get("style") or model["styles"]["body_edge"],
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

    for outline in model.get("object_outlines") or []:
        points = outline.get("points") or []
        if len(points) < 2:
            continue
        outline_style = outline.get("style") or BLUE
        outline_priority = int(outline.get("priority", 4))
        for idx in range(len(points)):
            start = points[idx]
            end = points[(idx + 1) % len(points)]
            for point in _sample_segment_points(start, end, _detail_scaled_count(18, drag_lod, 10)):
                coords = project(point)
                if coords is None:
                    continue
                x, y = mapper(coords)
                if use_cell_canvas:
                    put_mark(x, y, "·", priority=outline_priority, style=outline_style)
                else:
                    _braille_put(canvas, x, y, priority=outline_priority, style=outline_style)

    heading_tip_coords = project(model["heading_tip"])
    current_origin_coords = project(model.get("heading_origin"))

    weather = model.get("weather") if isinstance(model.get("weather"), dict) else {}
    if weather.get("enabled"):
        weather_rows = _weather_rows(snapshot, drag_lod=drag_lod)
        weather_styles = _weather_style(weather)
        lod_bands = _weather_lod_bands(weather)
        medium_density = float(weather.get("density") or 0.0)
        readability_required = bool(weather.get("readability_required"))
        precipitation_like = _weather_is_precipitation(weather)
        flow = _v_norm(_vec3(weather.get("direction")), (0.0, -1.0, 0.0))
        if depth_basis is not None:
            view_forward = _v_norm(depth_basis[3], (0.0, 0.0, 1.0))
            local_orientation = 1.0 - abs(_v_dot(flow, view_forward))
        else:
            local_orientation = 1.0 - abs(float(flow[1]))
        local_orientation = _clamp(local_orientation, 0.0, 1.0)
        for row in weather_rows:
            point = row.get("point")
            coords = project(point)
            if coords is None:
                continue
            x, y = mapper(coords)
            trail_start = row.get("trail_start")
            if trail_start is not None:
                trail_points = []
                trail_samples = 4 if use_cell_canvas else (10 if precipitation_like else 6)
                for sample_point in _sample_segment_points(trail_start, point, trail_samples):
                    sample_coords = project(sample_point)
                    if sample_coords is None:
                        continue
                    trail_points.append(mapper(sample_coords))
                if use_cell_canvas:
                    for trail_x, trail_y in trail_points[:-1]:
                        put_mark(trail_x, trail_y, "|" if precipitation_like else "·", priority=1, style=weather_styles["dim"])
                else:
                    for trail_x, trail_y in trail_points[:-1]:
                        _braille_put(canvas, trail_x, trail_y, priority=1, style=weather_styles["dim"])
            depth = point_depth(point)
            if depth_basis is not None:
                projected_subcells = _project_world_size_to_subcells(
                    row.get("world_size"),
                    depth,
                    render_height,
                    camera_meta,
                )
            else:
                projected_subcells = _orthographic_world_size_to_subcells(
                    row.get("world_size"),
                    mapper_meta,
                    render_width,
                    render_height,
                )
            band = _weather_band(
                projected_subcells,
                depth,
                medium_density,
                local_orientation,
                readability_required,
                lod_bands,
            )
            glyph = str(row.get("glyph") or "A")[:1]
            if use_cell_canvas:
                if precipitation_like:
                    if band == "reference":
                        head_char = glyph
                        head_priority = 4
                        head_style = weather_styles["bright"]
                    elif band in {"fused", "granular"}:
                        head_char = "|"
                        head_priority = 3
                        head_style = weather_styles["mid"]
                    elif band == "blob":
                        head_char = "'"
                        head_priority = 2
                        head_style = weather_styles["mid"]
                    else:
                        head_char = "."
                        head_priority = 1
                        head_style = weather_styles["dim"]
                    put_mark(x, y, head_char, priority=head_priority, style=head_style)
                elif band == "reference":
                    put_mark(x, y, glyph, priority=4, style=weather_styles["bright"])
                elif band == "fused":
                    put_mark(x, y, glyph, priority=3, style=weather_styles["mid"])
                elif band == "granular":
                    put_mark(x, y, glyph, priority=2, style=weather_styles["dim"])
                elif band == "blob":
                    put_mark(x, y, "•", priority=2, style=weather_styles["mid"])
                else:
                    put_mark(x, y, "·", priority=1, style=weather_styles["dim"])
                continue
            if precipitation_like:
                head_priority = 4 if band == "reference" else (3 if band in {"fused", "granular"} else 2)
                head_style = weather_styles["bright"] if band in {"reference", "fused"} else weather_styles["mid"]
                _braille_put(canvas, x, y, priority=head_priority, style=head_style)
                if band == "reference":
                    _braille_overlay_char(canvas, x, y, glyph, priority=5, style=weather_styles["bright"])
                elif band == "fused":
                    _braille_overlay_char(canvas, x, y, "│", priority=4, style=weather_styles["mid"])
                elif band == "granular":
                    _braille_overlay_char(canvas, x, y, "│", priority=3, style=weather_styles["mid"])
                elif band == "blob":
                    _braille_overlay_char(canvas, x, y, "'", priority=2, style=weather_styles["mid"])
                else:
                    _braille_overlay_char(canvas, x, y, ".", priority=1, style=weather_styles["dim"])
                continue
            if band == "reference":
                _braille_cluster(canvas, x, y, priority=1, style=weather_styles["mid"], radius=1)
                _braille_overlay_char(canvas, x, y, glyph, priority=4, style=weather_styles["bright"])
            elif band == "fused":
                _braille_cluster(canvas, x, y, priority=1, style=weather_styles["mid"], radius=1)
                _braille_overlay_char(canvas, x, y, glyph, priority=3, style=weather_styles["mid"])
            elif band == "granular":
                _braille_cluster(canvas, x, y, priority=2, style=weather_styles["dim"], radius=1)
                _braille_overlay_char(canvas, x, y, glyph, priority=2, style=weather_styles["dim"])
            elif band == "blob":
                _braille_cluster(
                    canvas,
                    x,
                    y,
                    priority=2,
                    style=weather_styles["mid"],
                    radius=1 if projected_subcells < 1.25 else 2,
                )
            else:
                _braille_put(canvas, x, y, priority=2, style=weather_styles["dim"])

    hair_fields = model.get("hair_fields") if isinstance(model.get("hair_fields"), list) else []
    hair_styles = model.get("hair_styles") if isinstance(model.get("hair_styles"), dict) else {}
    if hair_fields:
        for row in hair_fields:
            row_styles = row.get("styles") if isinstance(row.get("styles"), dict) else {}
            point = row.get("point")
            coords = project(point)
            if coords is None:
                continue
            x, y = mapper(coords)
            trail_start = row.get("trail_start")
            if trail_start is not None:
                trail_points = []
                for sample_point in _sample_segment_points(trail_start, point, 4 if use_cell_canvas else 5):
                    sample_coords = project(sample_point)
                    if sample_coords is None:
                        continue
                    trail_points.append(mapper(sample_coords))
                if use_cell_canvas:
                    for trail_x, trail_y in trail_points[:-1]:
                        put_mark(
                            trail_x,
                            trail_y,
                            "·",
                            priority=1,
                            style=row_styles.get("trail") or hair_styles.get("dim") or model["styles"]["focus"],
                        )
                else:
                    for trail_x, trail_y in trail_points[:-1]:
                        _braille_put(
                            canvas,
                            trail_x,
                            trail_y,
                            priority=1,
                            style=row_styles.get("trail") or hair_styles.get("dim") or model["styles"]["focus"],
                        )
            depth = point_depth(point)
            if depth_basis is not None:
                projected_subcells = _project_world_size_to_subcells(
                    row.get("world_size"),
                    depth,
                    render_height,
                    camera_meta,
                )
            else:
                projected_subcells = _orthographic_world_size_to_subcells(
                    row.get("world_size"),
                    mapper_meta,
                    render_width,
                    render_height,
                )
            band = _hair_field_band(projected_subcells, row.get("sample_t"), row.get("clump_mass"))
            glyph = str(row.get("glyph") or "⣿")[:1]
            if use_cell_canvas:
                if band == "reference":
                    put_mark(x, y, glyph, priority=4, style=row_styles.get("bright") or hair_styles.get("bright") or model["styles"]["focus"])
                elif band == "fused":
                    put_mark(x, y, glyph, priority=3, style=row_styles.get("mid") or hair_styles.get("mid") or model["styles"]["focus"])
                elif band == "granular":
                    put_mark(x, y, "⣶", priority=2, style=row_styles.get("mid") or hair_styles.get("mid") or model["styles"]["focus"])
                elif band == "blob":
                    put_mark(x, y, "•", priority=2, style=row_styles.get("dim") or hair_styles.get("dim") or model["styles"]["focus"])
                else:
                    put_mark(x, y, "·", priority=1, style=row_styles.get("dim") or hair_styles.get("dim") or model["styles"]["focus"])
                continue
            if band == "reference":
                _braille_cluster(canvas, x, y, priority=2, style=row_styles.get("mid") or hair_styles.get("mid") or model["styles"]["focus"], radius=1)
                _braille_overlay_char(canvas, x, y, glyph, priority=5, style=row_styles.get("bright") or hair_styles.get("bright") or model["styles"]["focus"])
            elif band == "fused":
                _braille_cluster(canvas, x, y, priority=2, style=row_styles.get("mid") or hair_styles.get("mid") or model["styles"]["focus"], radius=1)
                _braille_overlay_char(canvas, x, y, glyph, priority=4, style=row_styles.get("mid") or hair_styles.get("mid") or model["styles"]["focus"])
            elif band == "granular":
                _braille_cluster(canvas, x, y, priority=2, style=row_styles.get("dim") or hair_styles.get("dim") or model["styles"]["focus"], radius=1)
                _braille_overlay_char(canvas, x, y, glyph, priority=3, style=row_styles.get("mid") or hair_styles.get("mid") or model["styles"]["focus"])
            elif band == "blob":
                _braille_cluster(canvas, x, y, priority=2, style=row_styles.get("dim") or hair_styles.get("dim") or model["styles"]["focus"], radius=1)
            else:
                _braille_put(canvas, x, y, priority=1, style=row_styles.get("dim") or hair_styles.get("dim") or model["styles"]["focus"])

    for obj in model["objects"]:
        coords = project(obj["point"])
        if coords is None:
            continue
        x, y = mapper(coords)
        obj_char = str(obj.get("char") or "•")[:1]
        obj_priority = 6 if obj.get("focused") else 5
        obj_style = obj.get("style") or BLUE
        obj_radius = int(obj.get("radius", 0))
        obj_stamp = str(obj.get("stamp") or "point")
        if use_cell_canvas:
            put_mark(
                x,
                y,
                obj_char,
                priority=obj_priority,
                style=obj_style,
                radius=obj_radius,
            )
        else:
            if obj_stamp in {"square", "ring"}:
                for dx, dy in _object_stamp_offsets(obj_stamp, max(1, obj_radius)):
                    _braille_put(
                        canvas,
                        x + dx,
                        y + dy,
                        priority=max(1, obj_priority - 1),
                        style=obj_style,
                    )
            elif obj_radius > 0:
                _braille_cluster(canvas, x, y, priority=max(1, obj_priority - 1), style=obj_style, radius=obj_radius)
            _braille_overlay_char(canvas, x, y, obj_char, priority=obj_priority, style=obj_style)

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


def _profile_status_line(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    profiles = snapshot.get("text_theater_profiles") if isinstance(snapshot.get("text_theater_profiles"), dict) else {}
    defaults = profiles.get("surface_defaults") if isinstance(profiles.get("surface_defaults"), dict) else {}
    text_profile = str(defaults.get("text_theater") or profiles.get("default_family_id") or "operator_default")
    blackboard_profile = str(defaults.get("blackboard") or "mechanics_telemetry")
    chrome_profile = str(defaults.get("chrome") or "spectacle_showcase")
    return (
        "profiles text=" + text_profile
        + " blackboard=" + blackboard_profile
        + " chrome=" + chrome_profile
    )


def _parity_status_line(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    parity = snapshot.get("parity") if isinstance(snapshot.get("parity"), dict) else {}
    theater = snapshot.get("theater") if isinstance(snapshot.get("theater"), dict) else {}
    mode = str(parity.get("mode") or theater.get("mode") or "unknown")
    summary = str(parity.get("summary") or "").strip()
    return "parity=" + mode + ((" " + summary) if summary else "")


def _scene_proximity_enabled(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    parity = snapshot.get("parity") if isinstance(snapshot.get("parity"), dict) else {}
    theater = snapshot.get("theater") if isinstance(snapshot.get("theater"), dict) else {}
    mode = str(parity.get("mode") or theater.get("mode") or "").strip().lower()
    return mode == "environment"


def _compact_status_lines(snapshot, width, surface_mode=TEXT_THEATER_SURFACE_MODE, surface_density=TEXT_THEATER_SURFACE_DENSITY):
    balance = snapshot.get("balance") or {}
    runtime = snapshot.get("runtime") or {}
    theater = snapshot.get("theater") or {}
    base_rows = [
        f"focus={((theater.get('focus') or {}).get('id') or 'none')} phase={balance.get('support_phase', 'unknown')} risk={balance.get('stability_risk', '?')} grounded={runtime.get('grounded', '?')} bundle={snapshot.get('bundle_version', '?')}",
        _parity_status_line(snapshot),
        _motion_status_line(snapshot),
        _profile_status_line(snapshot),
        _surface_status_line(surface_mode, surface_density),
    ]
    lines = _stack_wrapped_rows(base_rows, width)
    menu_lines = _control_menu_lines(width)
    if menu_lines:
        if lines:
            lines.append("")
        lines.extend(menu_lines)
    return lines


def _split_status_lines(snapshot, width, surface_mode=TEXT_THEATER_SURFACE_MODE, surface_density=TEXT_THEATER_SURFACE_DENSITY):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    balance = snapshot.get("balance") or {}
    runtime = snapshot.get("runtime") or {}
    theater = snapshot.get("theater") or {}
    rows = [
        f"focus={((theater.get('focus') or {}).get('id') or 'none')}",
        f"phase={balance.get('support_phase', 'unknown')}",
        f"risk={balance.get('stability_risk', '?')} grd={runtime.get('grounded', '?')} b={snapshot.get('bundle_version', '?')}",
        "views m/6 2 3 4 5",
        "board d tab g p",
        "surface s - =",
        _surface_status_line(surface_mode, surface_density),
        "help h q r",
    ]
    return _stack_wrapped_rows(rows, width)


def _snapshot_is_live_camera(snapshot):
    if not isinstance(snapshot, dict):
        return False
    reason = str(snapshot.get("last_sync_reason") or "").strip().lower()
    return reason.startswith("camera:")


def _snapshot_has_active_camera_motion(snapshot):
    if not isinstance(snapshot, dict):
        return False
    reason = str(snapshot.get("last_sync_reason") or "").strip().lower()
    return (
        reason.startswith("camera:manual:change")
        or reason.startswith("camera:manual:wheel")
        or reason.startswith("camera:turntable")
    )


def _section_lines(snapshot, section_key, width):
    if section_key == "theater":
        theater = snapshot.get("theater") or {}
        camera = theater.get("camera") or {}
        focus = theater.get("focus") or {}
        parity = snapshot.get("parity") or {}
        rows = [
            f"mode={theater.get('mode', '')} visual_mode={theater.get('visual_mode', '')}",
            f"focus kind={focus.get('kind', '')} id={focus.get('id', '')} class={focus.get('target_class', '')}",
            f"camera mode={camera.get('mode', '')} dist={camera.get('distance', 0)} az={camera.get('azimuth', 0)} pol={camera.get('polar', 0)}",
            f"camera pos={camera.get('position', {})}",
            f"camera target={camera.get('target', {})}",
            f"camera forward={camera.get('forward', {})} up={camera.get('up', {})}",
        ]
        if parity:
            rows.append(f"parity mode={parity.get('mode', '')} summary={parity.get('summary', '')}")
            rows.append(f"admitted={parity.get('admitted_surfaces', [])}")
            rows.append(f"suppressed={parity.get('suppressed_surfaces', [])}")
            rows.append(f"contaminated={parity.get('contaminated_surfaces', [])}")
            rows.append(f"missing={parity.get('missing_surfaces', [])}")
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
            f"load_field_enabled={workbench.get('load_field_enabled', False)}",
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
    if section_key == "timeline":
        timeline = snapshot.get("timeline") or {}
        rows = [
            f"cursor={timeline.get('cursor', 0)} duration={timeline.get('duration', 0)}",
            f"key_pose_count={timeline.get('key_pose_count', 0)} interpolation={timeline.get('interpolation', '')}",
        ]
        return _wrap_block("\n".join(rows), width)
    if section_key == "blackboard":
        return _render_blackboard_section(snapshot, width)
    if section_key == "profiles":
        return _render_profiles_section(snapshot, width)
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


def _build_status_lines(snapshot, section_key, width, surface_mode=TEXT_THEATER_SURFACE_MODE, surface_density=TEXT_THEATER_SURFACE_DENSITY):
    balance = snapshot.get("balance") or {}
    stale = snapshot.get("stale_flags") or {}
    runtime = snapshot.get("runtime") or {}
    base_rows = [
        f"phase={balance.get('support_phase', 'unknown')} risk={balance.get('stability_risk', '?')} margin={balance.get('stability_margin', '?')}",
        f"runtime={runtime.get('mode', '?')} grounded={runtime.get('grounded', '?')} sync_reason={snapshot.get('last_sync_reason', '')}",
        _parity_status_line(snapshot),
        _motion_status_line(snapshot),
        f"section={section_key} mirror_lag={bool(stale.get('mirror_lag'))} bundle={snapshot.get('bundle_version', '?')}",
        _profile_status_line(snapshot),
        _surface_status_line(surface_mode, surface_density),
    ]
    lines = _stack_wrapped_rows(base_rows, width)
    menu_lines = _control_menu_lines(width)
    if menu_lines:
        if lines:
            lines.append("")
        lines.extend(menu_lines)
    return lines


def _render_local_theater_text(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    theater = snapshot.get("theater") if isinstance(snapshot.get("theater"), dict) else {}
    scene = snapshot.get("scene") if isinstance(snapshot.get("scene"), dict) else {}
    weather = snapshot.get("weather") if isinstance(snapshot.get("weather"), dict) else {}
    runtime = snapshot.get("runtime") if isinstance(snapshot.get("runtime"), dict) else {}
    parity = snapshot.get("parity") if isinstance(snapshot.get("parity"), dict) else {}
    stale_flags = snapshot.get("stale_flags") if isinstance(snapshot.get("stale_flags"), dict) else {}
    focus = theater.get("focus") if isinstance(theater.get("focus"), dict) else {}
    camera = theater.get("camera") if isinstance(theater.get("camera"), dict) else {}
    bounds = scene.get("bounds") if isinstance(scene.get("bounds"), dict) else {}
    bounds_min = bounds.get("min") if isinstance(bounds.get("min"), dict) else {}
    bounds_max = bounds.get("max") if isinstance(bounds.get("max"), dict) else {}
    position = camera.get("position") if isinstance(camera.get("position"), dict) else {}
    neighborhood = scene.get("focus_neighborhood") if _scene_proximity_enabled(snapshot) and isinstance(scene.get("focus_neighborhood"), list) else []
    snapshot_ts = float(snapshot.get("snapshot_timestamp") or 0.0)
    source_ts = float(snapshot.get("source_timestamp") or 0.0)
    sync_age = max(0.0, (snapshot_ts - source_ts) / 1000.0) if snapshot_ts > 0.0 and source_ts > 0.0 else 0.0
    nearby = ", ".join(
        f"{str(row.get('label') or row.get('object_key') or '?')} ({float(row.get('distance') or 0.0):.2f}m)"
        for row in neighborhood[:8]
        if isinstance(row, dict)
    ) or "none"
    weather_line = "none"
    if weather.get("enabled"):
        direction = weather.get("direction") if isinstance(weather.get("direction"), dict) else {}
        weather_line = (
            str(weather.get("kind") or "weather")
            + " / "
            + str(weather.get("flow_class") or "")
            + " / dens "
            + f"{float(weather.get('density') or 0.0):.2f}"
            + " / speed "
            + f"{float(weather.get('speed') or 0.0):.2f}"
            + " / dir ("
            + f"{float(direction.get('x') or 0.0):.2f}, "
            + f"{float(direction.get('y') or 0.0):.2f}, "
            + f"{float(direction.get('z') or 0.0):.2f})"
        )
    lines = [
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
        "PARITY: "
        + str(parity.get("mode") or theater.get("mode") or "unknown")
        + " / "
        + str(parity.get("summary") or "unknown"),
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
        "WEATHER: " + weather_line,
        "RUNTIME: "
        + ("enabled" if runtime.get("enabled") else "disabled")
        + " / "
        + str(runtime.get("mode") or "")
        + " / behavior "
        + str(runtime.get("behavior") or "")
        + " / activity "
        + str(runtime.get("activity") or ""),
        "NEARBY: " + nearby,
    ]
    lines.extend(_sequence_field_text_lines(snapshot, prefix="", upper=True, fallback_hint=True))
    return "\n".join(lines)


def _short_float(value, digits=2):
    try:
        number = float(value)
    except Exception:
        number = 0.0
    return f"{number:.{int(digits)}f}".rstrip("0").rstrip(".")


def _sequence_field_text_lines(snapshot, prefix="", upper=True, fallback_hint=False):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    sequence = snapshot.get("sequence_field") if isinstance(snapshot.get("sequence_field"), dict) else {}
    semantic = snapshot.get("semantic") if isinstance(snapshot.get("semantic"), dict) else {}
    summary = str(semantic.get("summary") or "").strip()
    label_sequence = "SEQUENCE" if upper else "sequence"
    label_force = "FORCE" if upper else "force"
    label_hair = "HAIR" if upper else "hair"
    label_topology = "HAIR-TOPO" if upper else "hair_topology"
    lead = str(prefix or "")
    lines = []
    if not sequence.get("active"):
        if fallback_hint and "The Cage" in summary:
            lines.append(lead + label_sequence + ": The Cage / semantic-only / force-wave packet not mirrored")
            lines.append(lead + label_hair + ": pending mirror / refresh sequence_field to expose topology")
        return lines

    resource = str(sequence.get("resource_label") or sequence.get("resource_id") or sequence.get("summary") or "sequence active")
    phase = str(sequence.get("resource_phase_label") or sequence.get("resource_phase_id") or "").strip()
    seq_line = lead + label_sequence + ": " + resource
    if phase:
        seq_line += " / " + phase
    if sequence.get("summary"):
        seq_line += " / " + str(sequence.get("summary") or "")
    lines.append(seq_line)

    force = sequence.get("force_wave") if isinstance(sequence.get("force_wave"), dict) else {}
    if not force.get("active"):
        return lines
    lines.append(
        lead
        + label_force
        + ": "
        + str(force.get("wave_band") or "primed")
        + " / anchor "
        + str(force.get("neutral_anchor") or "neutral_center")
        + " / drive "
        + _short_float(force.get("drive_gain"), 2)
        + " / rebound "
        + _short_float(force.get("rebound_damping"), 2)
        + " / pose "
        + ("on" if force.get("pose_drive_enabled") else "off")
    )
    motion_clock = _sequence_shared_surface_motion_clock(snapshot)
    if motion_clock.get("active"):
        clip_name = str(motion_clock.get("clip") or "phase_wave").strip()
        if len(clip_name) > 38:
            clip_name = clip_name[:35] + "..."
        lines.append(
            lead
            + ("MOTION" if upper else "motion")
            + ": shared surface"
            + " / authority "
            + str(motion_clock.get("authority") or "sequence_field.force_wave")
            + " / phase "
            + _short_float(motion_clock.get("phase"), 2)
            + " / speed "
            + _short_float(motion_clock.get("speed"), 2)
            + " / clip "
            + clip_name
        )

    skin = force.get("skin_service") if isinstance(force.get("skin_service"), dict) else {}
    if skin.get("active"):
        lines.append(
            lead
            + ("SKIN" if upper else "skin")
            + ": "
            + str(skin.get("profile") or "neutral_field")
            + " / medium "
            + str(skin.get("medium_kind") or "gravity_only")
            + " / route "
            + str(skin.get("routing_mode") or "pacman_wrap")
            + " / wrap "
            + str(skin.get("wrap_mode") or "neutral_center_return")
        )

    hair = force.get("hair_reactivity") if isinstance(force.get("hair_reactivity"), dict) else {}
    if hair.get("active"):
        lines.append(
            lead
            + label_hair
            + ": "
            + str(hair.get("band") or "composed_flow")
            + " / mode "
            + str(hair.get("equilibrium_mode") or hair.get("color_strategy") or "field_tint")
            + " / response "
            + str(hair.get("response_mode") or "gravity_realist")
            + " / grav "
            + _short_float(hair.get("gravity_dominance"), 2)
            + " / lift "
            + _short_float(hair.get("lift_gain"), 2)
            + " / sweep "
            + _short_float(hair.get("sweep_gain"), 2)
        )
        topology = hair.get("topology") if isinstance(hair.get("topology"), dict) else {}
        if topology.get("active"):
            lines.append(
                lead
                + label_topology
                + ": "
                + str(topology.get("silhouette") or "crown_sweep")
                + " / clumps "
                + str(int(float(topology.get("virtual_clump_count") or 0)))
                + " / lock "
                + _short_float(topology.get("root_lock_gain"), 2)
                + " / tip "
                + _short_float(topology.get("tip_flex_gain"), 2)
                + " / charge "
                + _short_float(topology.get("surface_charge_gain"), 2)
            )
        granulation = hair.get("granulation") if isinstance(hair.get("granulation"), dict) else {}
        if granulation.get("active"):
            lines.append(
                lead
                + ("HAIR-GROWTH" if upper else "hair_growth")
                + ": "
                + str(granulation.get("preset_label") or "saiyan_mode")
                + " / growth "
                + _short_float(granulation.get("growth_gain"), 2)
                + " / density "
                + _short_float(granulation.get("strand_density_gain"), 2)
                + " / simian "
                + _short_float(granulation.get("simian_ramp_gain"), 2)
                + " / exhaust "
                + _short_float(granulation.get("exhaust_bud_gain"), 2)
                + " / counter "
                + _short_float(granulation.get("counterweight_gain"), 2)
                + " / ape x"
                + _short_float(granulation.get("ape_scale_factor"), 2)
                + " / budget "
                + str(int(float(granulation.get("max_sample_budget") or 0)))
            )
        manifold = hair.get("glyph_message_manifold") if isinstance(hair.get("glyph_message_manifold"), dict) else {}
        if manifold.get("active"):
            lines.append(
                lead
                + ("HAIR-MSG" if upper else "hair_msg")
                + ": "
                + str(manifold.get("message_text") or "FLOW")
                + " / mode "
                + str(manifold.get("mode") or "inertial_word_caterpillar")
                + " / leg "
                + _short_float(manifold.get("legibility_gain"), 2)
                + " / sharp "
                + _short_float(manifold.get("sharpness_gain"), 2)
            )
            lines.append(
                lead
                + ("HAIR-SPECTRUM" if upper else "hair_spectrum")
                + ": "
                + str(manifold.get("spectrum_mode") or "spectral_pop")
                + " / pop "
                + _short_float(manifold.get("pop_gain"), 2)
                + " / glow "
                + _short_float(manifold.get("glow_gain"), 2)
                + " / hue "
                + _short_float(manifold.get("hue_rate"), 2)
            )
        zones = hair.get("expression_zones") if isinstance(hair.get("expression_zones"), dict) else {}
        if zones.get("active"):
            lines.append(
                lead
                + ("HAIR-ZONES" if upper else "hair_zones")
                + ": "
                + str(zones.get("active_zone") or "crown_core")
                + " / crown "
                + _short_float(zones.get("crown_core_gain"), 2)
                + " / front "
                + _short_float(zones.get("front_arc_gain"), 2)
                + " / tip "
                + _short_float(zones.get("tip_charge_gain"), 2)
            )

    punch = force.get("punch_dynamics") if isinstance(force.get("punch_dynamics"), dict) else {}
    if punch.get("active"):
        lines.append(
            lead
            + ("PUNCH" if upper else "punch")
            + ": "
            + str(punch.get("composure") or "ready")
            + " / burst "
            + _short_float(punch.get("burst_gain"), 2)
            + " / focus "
            + _short_float(punch.get("focus_gain"), 2)
            + " / line "
            + _short_float(punch.get("camera_line_gain"), 2)
            + ((" / lead " + str(punch.get("lead_side") or "")) if str(punch.get("lead_side") or "").strip() else "")
        )
    aura = force.get("aura_envelope") if isinstance(force.get("aura_envelope"), dict) else {}
    if aura.get("active"):
        lines.append(
            lead
            + ("AURA" if upper else "aura")
            + ": "
            + str(aura.get("mode") or "field")
            + " / shell "
            + _short_float(aura.get("shell_gain"), 2)
            + " / flare "
            + _short_float(aura.get("flare_gain"), 2)
            + " / pulse "
            + _short_float(aura.get("pulse_gain"), 2)
        )
    acoustic = force.get("acoustic_feedback") if isinstance(force.get("acoustic_feedback"), dict) else {}
    if acoustic.get("active"):
        lines.append(
            lead
            + ("ACOUSTIC" if upper else "acoustic")
            + ": "
            + str(acoustic.get("acoustic_emission_band") or "quiet")
            + " / target "
            + str(int(float(acoustic.get("target_tempo_bpm") or 0)))
            + " bpm / observed "
            + str(int(float(acoustic.get("observed_contact_tempo_bpm") or 0)))
            + " bpm / align "
            + _short_float(acoustic.get("cadence_alignment"), 2)
        )
    split_loop = force.get("split_loop_dynamics") if isinstance(force.get("split_loop_dynamics"), dict) else {}
    if split_loop.get("active"):
        lines.append(
            lead
            + ("LEGS" if upper else "legs")
            + ": "
            + str(split_loop.get("loop_family") or "jcvd_split_rep")
            + " / phase "
            + str(split_loop.get("phase_kind") or "guard")
            + " / split "
            + _short_float(split_loop.get("split_ratio"), 2)
            + " / heel "
            + _short_float((((split_loop.get("left_leg") or {}).get("heel_drive_gain"))), 2)
        )
    body = force.get("body_orientation") if isinstance(force.get("body_orientation"), dict) else {}
    if body.get("active"):
        lines.append(
            lead
            + ("POSE" if upper else "pose")
            + ": camera "
            + _short_float(body.get("full_body_answer_gain"), 2)
            + " / pelvis "
            + _short_float(body.get("pelvis_yaw_gain"), 2)
            + " / chest "
            + _short_float(body.get("chest_track_gain"), 2)
            + " / head "
            + _short_float(body.get("head_track_gain"), 2)
        )
    return lines


def _sequence_field_blackboard_lines(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    sequence = snapshot.get("sequence_field") if isinstance(snapshot.get("sequence_field"), dict) else {}
    semantic = snapshot.get("semantic") if isinstance(snapshot.get("semantic"), dict) else {}
    summary = str(semantic.get("summary") or "").strip()
    if not sequence.get("active"):
        if "The Cage" in summary:
            return [
                "sequence_field=semantic_only resource=the_cage force_wave=missing",
                "hair_topology=missing reason=force_wave_packet_not_mirrored",
            ]
        return []
    lines = [
        "sequence_field="
        + str(sequence.get("mode") or "strike_corridor")
        + " resource="
        + str(sequence.get("resource_id") or "")
        + " phase="
        + str(sequence.get("resource_phase_id") or "")
        + " stage="
        + str(sequence.get("stage") or ""),
    ]
    force = sequence.get("force_wave") if isinstance(sequence.get("force_wave"), dict) else {}
    if force.get("active"):
        lines.append(
            "force_wave="
            + str(force.get("wave_band") or "primed")
            + " anchor="
            + str(force.get("neutral_anchor") or "neutral_center")
            + " drive="
            + _short_float(force.get("drive_gain"), 2)
            + " rebound="
            + _short_float(force.get("rebound_damping"), 2)
            + " pose="
            + ("on" if force.get("pose_drive_enabled") else "off")
        )
        motion_clock = _sequence_shared_surface_motion_clock(snapshot)
        if motion_clock.get("active"):
            lines.append(
                "animation_surface="
                + str(motion_clock.get("authority") or "sequence_field.force_wave")
                + " consumer="
                + str(motion_clock.get("consumer_rule") or "text_and_web_theaters_consume_shared_surface")
                + " phase="
                + _short_float(motion_clock.get("phase"), 2)
                + " speed="
                + _short_float(motion_clock.get("speed"), 2)
            )
        skin = force.get("skin_service") if isinstance(force.get("skin_service"), dict) else {}
        if skin.get("active"):
            lines.append(
                "skin_service="
                + str(skin.get("profile") or "neutral_field")
                + " medium="
                + str(skin.get("medium_kind") or "gravity_only")
                + " routing="
                + str(skin.get("routing_mode") or "pacman_wrap")
                + " wrap="
                + str(skin.get("wrap_mode") or "neutral_center_return")
            )
        hair = force.get("hair_reactivity") if isinstance(force.get("hair_reactivity"), dict) else {}
        topology = hair.get("topology") if isinstance(hair.get("topology"), dict) else {}
        if hair.get("active"):
            lines.append(
                "hair_surface="
                + str(hair.get("band") or "composed_flow")
                + " mode="
                + str(hair.get("equilibrium_mode") or hair.get("color_strategy") or "field_tint")
                + " response="
                + str(hair.get("response_mode") or "gravity_realist")
            )
        manifold = hair.get("glyph_message_manifold") if isinstance(hair.get("glyph_message_manifold"), dict) else {}
        if manifold.get("active"):
            lines.append(
                "hair_message="
                + str(manifold.get("message_text") or "FLOW")
                + " mode="
                + str(manifold.get("mode") or "inertial_word_caterpillar")
                + " legibility="
                + _short_float(manifold.get("legibility_gain"), 2)
                + " sharpness="
                + _short_float(manifold.get("sharpness_gain"), 2)
            )
            lines.append(
                "hair_spectrum="
                + str(manifold.get("spectrum_mode") or "spectral_pop")
                + " pop="
                + _short_float(manifold.get("pop_gain"), 2)
                + " glow="
                + _short_float(manifold.get("glow_gain"), 2)
                + " hue="
                + _short_float(manifold.get("hue_rate"), 2)
            )
        granulation = hair.get("granulation") if isinstance(hair.get("granulation"), dict) else {}
        if granulation.get("active"):
            lines.append(
                "hair_growth="
                + str(granulation.get("preset_label") or "saiyan_mode")
                + " growth="
                + _short_float(granulation.get("growth_gain"), 2)
                + " density="
                + _short_float(granulation.get("strand_density_gain"), 2)
                + " simian="
                + _short_float(granulation.get("simian_ramp_gain"), 2)
                + " exhaust="
                + _short_float(granulation.get("exhaust_bud_gain"), 2)
                + " counter="
                + _short_float(granulation.get("counterweight_gain"), 2)
                + " ape=x"
                + _short_float(granulation.get("ape_scale_factor"), 2)
                + " budget="
                + str(int(float(granulation.get("max_sample_budget") or 0)))
            )
        if topology.get("active"):
            lines.append(
                "hair_topology="
                + str(topology.get("silhouette") or "crown_sweep")
                + " clumps="
                + str(int(float(topology.get("virtual_clump_count") or 0)))
                + " root_lock="
                + _short_float(topology.get("root_lock_gain"), 2)
                + " tip_flex="
                + _short_float(topology.get("tip_flex_gain"), 2)
                + " charge="
                + _short_float(topology.get("surface_charge_gain"), 2)
            )
        zones = hair.get("expression_zones") if isinstance(hair.get("expression_zones"), dict) else {}
        if zones.get("active"):
            lines.append(
                "hair_zones="
                + str(zones.get("active_zone") or "crown_core")
                + " crown="
                + _short_float(zones.get("crown_core_gain"), 2)
                + " front="
                + _short_float(zones.get("front_arc_gain"), 2)
                + " tip="
                + _short_float(zones.get("tip_charge_gain"), 2)
            )
        punch = force.get("punch_dynamics") if isinstance(force.get("punch_dynamics"), dict) else {}
        if punch.get("active"):
            lines.append(
                "punch_surface="
                + str(punch.get("composure") or "ready")
                + " burst="
                + _short_float(punch.get("burst_gain"), 2)
                + " line="
                + _short_float(punch.get("camera_line_gain"), 2)
                + ((" lead=" + str(punch.get("lead_side") or "")) if str(punch.get("lead_side") or "").strip() else "")
            )
        aura = force.get("aura_envelope") if isinstance(force.get("aura_envelope"), dict) else {}
        if aura.get("active"):
            lines.append(
                "aura_surface="
                + str(aura.get("mode") or "field")
                + " shell="
                + _short_float(aura.get("shell_gain"), 2)
                + " flare="
                + _short_float(aura.get("flare_gain"), 2)
                + " pulse="
                + _short_float(aura.get("pulse_gain"), 2)
            )
        split_loop = force.get("split_loop_dynamics") if isinstance(force.get("split_loop_dynamics"), dict) else {}
        if split_loop.get("active"):
            lines.append(
                "split_loop="
                + str(split_loop.get("loop_family") or "jcvd_split_rep")
                + " phase="
                + str(split_loop.get("phase_kind") or "guard")
                + " split="
                + _short_float(split_loop.get("split_ratio"), 2)
                + " heel="
                + _short_float((((split_loop.get("left_leg") or {}).get("heel_drive_gain"))), 2)
            )
        body = force.get("body_orientation") if isinstance(force.get("body_orientation"), dict) else {}
        if body.get("active"):
            lines.append(
                "body_orientation=camera_answer"
                + " full="
                + _short_float(body.get("full_body_answer_gain"), 2)
                + " pelvis="
                + _short_float(body.get("pelvis_yaw_gain"), 2)
                + " chest="
                + _short_float(body.get("chest_track_gain"), 2)
                + " head="
                + _short_float(body.get("head_track_gain"), 2)
            )
    return lines


def _render_consult_orientation_text(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    theater = snapshot.get("theater") if isinstance(snapshot.get("theater"), dict) else {}
    scene = snapshot.get("scene") if isinstance(snapshot.get("scene"), dict) else {}
    weather = snapshot.get("weather") if isinstance(snapshot.get("weather"), dict) else {}
    parity = snapshot.get("parity") if isinstance(snapshot.get("parity"), dict) else {}
    focus = theater.get("focus") if isinstance(theater.get("focus"), dict) else {}
    camera = theater.get("camera") if isinstance(theater.get("camera"), dict) else {}
    target = camera.get("target") if isinstance(camera.get("target"), dict) else {}
    position = camera.get("position") if isinstance(camera.get("position"), dict) else {}
    neighborhood = scene.get("focus_neighborhood") if _scene_proximity_enabled(snapshot) and isinstance(scene.get("focus_neighborhood"), list) else []
    nearby = ", ".join(
        f"{str(row.get('label') or row.get('object_key') or '?')} {float(row.get('distance') or 0.0):.2f}m"
        for row in neighborhood[:6]
        if isinstance(row, dict)
    ) or "none"
    weather_line = "none"
    if weather.get("enabled"):
        weather_line = (
            str(weather.get("kind") or "weather")
            + " / "
            + str(weather.get("flow_class") or "")
            + " / dens "
            + f"{float(weather.get('density') or 0.0):.2f}"
            + " / speed "
            + f"{float(weather.get('speed') or 0.0):.2f}"
        )
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
        "PARITY: "
        + str(parity.get("mode") or theater.get("mode") or "unknown")
        + " / "
        + str(parity.get("summary") or "unknown"),
        "WEATHER: " + weather_line,
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
    active_controller = workbench.get("active_controller") if isinstance(workbench.get("active_controller"), dict) else {}
    route_report = workbench.get("route_report") if isinstance(workbench.get("route_report"), dict) else {}
    maneuver_probe_history = workbench.get("maneuver_probe_history") if isinstance(workbench.get("maneuver_probe_history"), list) else []
    pivot = active_controller.get("pivot_world") if isinstance(active_controller.get("pivot_world"), dict) else {}
    leaders = [str(v) for v in (active_controller.get("leader_bone_ids") or []) if str(v)]
    anchors = [str(v) for v in (active_controller.get("anchor_bone_ids") or []) if str(v)]
    carriers = [str(v) for v in (active_controller.get("carrier_bone_ids") or []) if str(v)]
    propagation_mode = str(active_controller.get("propagation_mode") or "follow")
    lines = [
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
        "CONTROLLER: "
        + str(active_controller.get("controller_id") or active_controller.get("label") or "none")
        + " / "
        + str(active_controller.get("controller_kind") or "none")
        + " / members "
        + str(len(active_controller.get("member_bone_ids") or []))
        + " / "
        + propagation_mode
        + " / leader "
        + (",".join(leaders) if leaders else "none")
        + " / anchor "
        + (",".join(anchors) if anchors else "none")
        + " / carrier "
        + (",".join(carriers) if carriers else "none")
        + " / pivot ("
        + f"{float(pivot.get('x') or 0.0):.2f}, "
        + f"{float(pivot.get('y') or 0.0):.2f}, "
        + f"{float(pivot.get('z') or 0.0):.2f})"
        + " / preview "
        + ("active" if active_controller.get("preview_active") else "idle"),
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
    ]
    if route_report:
        intended = ", ".join(str(v) for v in (route_report.get("intended_support_set") or [])) or "none"
        realized = ", ".join(str(v) for v in (route_report.get("realized_support_set") or [])) or "none"
        missing = ", ".join(str(v) for v in (route_report.get("missing_support_participants") or [])) or "none"
        lines.append(
            "ROUTE: "
            + str(route_report.get("support_topology_label") or route_report.get("pose_macro_id") or "support intent")
            + " / intended "
            + intended
            + " / realized "
            + realized
            + " / missing "
            + missing
        )
        if route_report.get("operational_state_label"):
            state_line = "STATE: " + str(route_report.get("operational_state_label") or "")
            if route_report.get("operational_state_summary"):
                state_line += " / " + str(route_report.get("operational_state_summary") or "")
            lines.append(state_line)
        if route_report.get("active_phase_label"):
            lines.append(
                "PHASE: "
                + str(route_report.get("active_phase_label") or "")
                + " / "
                + str(route_report.get("phase_status") or "pending")
                + " / "
                + str(len(route_report.get("completed_phase_ids") or []))
                + "/"
                + str(len(route_report.get("phase_sequence") or []))
                + " complete"
            )
        if route_report.get("phase_gate_summary") and route_report.get("phase_status") != "complete":
            lines.append("GATE: " + str(route_report.get("phase_gate_summary") or ""))
        if route_report.get("blocker_summary"):
            lines.append("BLOCKER: " + str(route_report.get("blocker_summary") or ""))
        if route_report.get("next_suggested_adjustment"):
            lines.append("NEXT: " + str(route_report.get("next_suggested_adjustment") or ""))
    if maneuver_probe_history:
        recent = maneuver_probe_history[:2]
        for idx, probe in enumerate(recent, start=1):
            if not isinstance(probe, dict):
                continue
            lines.append(
                "TRACE "
                + str(idx)
                + ": "
                + str(probe.get("action") or "probe")
                + " / "
                + str(probe.get("support_topology_label") or probe.get("pose_macro_id") or probe.get("controller_id") or "maneuver")
                + " / realized "
                + (", ".join(str(v) for v in (probe.get("realized_support_set") or [])) or "none")
                + " / missing "
                + (", ".join(str(v) for v in (probe.get("missing_support_participants") or [])) or "none")
            )
            if probe.get("blocker_summary"):
                lines.append("TRACE " + str(idx) + " BLOCKER: " + str(probe.get("blocker_summary") or ""))
    return "\n".join(lines)


def _render_consult_motion_text(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    workbench = snapshot.get("workbench") if isinstance(snapshot.get("workbench"), dict) else {}
    balance = snapshot.get("balance") if isinstance(snapshot.get("balance"), dict) else {}
    timeline = snapshot.get("timeline") if isinstance(snapshot.get("timeline"), dict) else {}
    assertion = balance.get("assertion") if isinstance(balance.get("assertion"), dict) else {}
    contacts = snapshot.get("contacts") if isinstance(snapshot.get("contacts"), list) else []
    maneuver_probe_history = workbench.get("maneuver_probe_history") if isinstance(workbench.get("maneuver_probe_history"), list) else []
    projected_com = balance.get("projected_com") if isinstance(balance.get("projected_com"), dict) else {}
    supporting = ", ".join(str(v) for v in (balance.get("supporting_joint_ids") or [])) or "none"
    alerts = ", ".join(str(v) for v in (balance.get("alert_ids") or [])) or "none"
    contact_summary = ", ".join(
        (
            f"{str(row.get('joint') or '?')}="
            + str(row.get("state") or "?")
            + ("/" + str(row.get("contact_mode") or "") if str(row.get("contact_mode") or "").strip() else "")
            + ("/" + str(row.get("contact_bias") or "") if str(row.get("contact_bias") or "").strip() else "")
        )
        for row in contacts[:6]
        if isinstance(row, dict)
    ) or "none"
    side_loads = balance.get("support_side_loads") if isinstance(balance.get("support_side_loads"), dict) else {}
    foot_loads = balance.get("foot_support_loads") if isinstance(balance.get("foot_support_loads"), dict) else {}
    nearest_edge = balance.get("nearest_edge") if isinstance(balance.get("nearest_edge"), dict) else {}
    midpoint = nearest_edge.get("midpoint") if isinstance(nearest_edge.get("midpoint"), dict) else {}
    band = _balance_load_band(balance)
    return "\n".join([
        _style_inline("BALANCE: phase "
        + str(balance.get("support_phase") or "unknown")
        + " / risk "
        + f"{float(balance.get('stability_risk') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / margin "
        + f"{float(balance.get('stability_margin') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / "
        + ("inside polygon" if balance.get("inside_polygon") else "outside polygon")
        + " / "
        + str(band.get("label") or "STABLE"), band.get("style")),
        "SUPPORT: "
        + supporting
        + " / dominant "
        + str(balance.get("dominant_side") or "balanced")
        + " / CoM ("
        + f"{float(projected_com.get('x') or 0.0):.2f}, "
        + f"{float(projected_com.get('z') or 0.0):.2f})",
        "SURFACE: "
        + str(balance.get("support_kind") or balance.get("support_key") or "unknown")
        + " / supports "
        + str(int(balance.get("support_count") or 0))
        + " / span "
        + f"{float(balance.get('support_span') or 0.0):.2f}".rstrip("0").rstrip(".")
        + (
            " / edge "
            + str(nearest_edge.get("kind") or "edge")
            + " #"
            + str(int(nearest_edge.get("index") or 0))
            + " @ "
            + f"{float(nearest_edge.get('distance') or 0.0):.3f}".rstrip("0").rstrip(".")
            + " near ("
            + f"{float(midpoint.get('x') or 0.0):.2f}, "
            + f"{float(midpoint.get('z') or 0.0):.2f})"
            if nearest_edge
            else ""
        ),
        _style_inline("LOADS: left "
        + f"{float(side_loads.get('left') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / right "
        + f"{float(side_loads.get('right') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / center "
        + f"{float(side_loads.get('center') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / feet L "
        + f"{float(foot_loads.get('foot_l') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " R "
        + f"{float(foot_loads.get('foot_r') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / "
        + str(band.get("label") or "STABLE"), band.get("style")),
        "CONTACTS: " + contact_summary,
        "ALERTS: " + alerts,
        "ASSERT: "
        + (
            (str(assertion.get("summary") or "unchecked") + (" / stale" if assertion.get("stale") else ""))
            if assertion.get("active")
            else "unchecked"
        ),
        "TIMELINE: cursor "
        + f"{float(timeline.get('cursor') or 0.0):.3f}".rstrip("0").rstrip(".")
        + " / duration "
        + f"{float(timeline.get('duration') or 0.0):.3f}".rstrip("0").rstrip(".")
        + " / key poses "
        + str(int(timeline.get("key_pose_count") or 0))
        + " / key poses "
        + str(int(timeline.get("key_pose_count") or 0)),
    ])


def _render_consult_view(snapshot, width, height, diagnostics_visible, section_key, surface_mode=TEXT_THEATER_SURFACE_MODE, surface_density=TEXT_THEATER_SURFACE_DENSITY):
    width = max(80, width)
    height = max(24, height)
    main_height = max(12, height - (15 if diagnostics_visible else 8))
    top_height = max(6, min(9, main_height // 3))
    middle_height = max(8, min(11, (main_height - top_height) // 2))
    bottom_height = max(8, main_height - top_height - middle_height)
    lines = []
    lines.extend(_box("Orientation", _wrap_block(_render_consult_orientation_text(snapshot), width - 2), width, top_height, color=CYAN, surface_mode=surface_mode, surface_density=surface_density))
    lines.extend(_box("Query Work", _wrap_block("\n".join(_consult_query_thread(snapshot)), width - 2), width, middle_height, color=GREEN, surface_mode=surface_mode, surface_density=surface_density))
    lines.extend(_box("Evidence Lane", _wrap_block("\n".join(_consult_query_evidence(snapshot)), width - 2), width, bottom_height, color=ORANGE, surface_mode=surface_mode, surface_density=surface_density))
    if diagnostics_visible:
        lines.extend(_box(
            f"Diagnostics · {dict(PANE_SECTIONS).get(section_key, section_key)}",
            _section_lines(snapshot, section_key, width - 2),
            width,
            max(7, min(12, height - len(lines) - 3)),
            color=GREEN,
            surface_mode=surface_mode,
            surface_density=surface_density,
        ))
        lines.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2, surface_mode=surface_mode, surface_density=surface_density), width, max(3, height - len(lines)), color=YELLOW, surface_mode=surface_mode, surface_density=surface_density))
    else:
        lines.extend(_box("Status", _compact_status_lines(snapshot, width - 2, surface_mode=surface_mode, surface_density=surface_density), width, max(3, height - len(lines)), color=YELLOW, surface_mode=surface_mode, surface_density=surface_density))
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


def _format_local_contact_line(contact):
    if not isinstance(contact, dict):
        return ""
    role = str(contact.get("support_role") or "").strip()
    mode = str(contact.get("contact_mode") or "").strip()
    bias = str(contact.get("contact_bias") or "").strip()
    planted_alignment = contact.get("planted_alignment")
    normal_alignment = contact.get("normal_alignment")
    line = (
        "  "
        + str(contact.get("joint") or "")
        + ": "
        + str(contact.get("state") or "")
    )
    if role:
        line += " / " + role
    if mode:
        line += " / " + mode
    if bias:
        line += " / " + bias
    if planted_alignment is not None or normal_alignment is not None:
        planted_text = (
            f"{float(planted_alignment or 0.0):.2f}".rstrip("0").rstrip(".")
            if planted_alignment is not None
            else "-"
        )
        normal_text = (
            f"{float(normal_alignment or 0.0):.2f}".rstrip("0").rstrip(".")
            if normal_alignment is not None
            else "-"
        )
        line += " / align p" + planted_text + " n" + normal_text
    if mode == "inverted":
        line += " / wrong-way"
    line += (
        " (gap "
        + f"{float(contact.get('gap') or 0.0):.3f}".rstrip("0").rstrip(".")
        + " / heel "
        + f"{float(contact.get('heel_clearance') or 0.0):.3f}".rstrip("0").rstrip(".")
        + " / toe "
        + f"{float(contact.get('toe_clearance') or 0.0):.3f}".rstrip("0").rstrip(".")
        + " / manifold "
        + str(int(contact.get("manifold_points") or 0))
        + ")"
    )
    band = _contact_load_band(contact)
    return _style_inline(line + " / " + str(band.get("label") or "STABLE"), band.get("style"))


def _render_local_embodiment_text(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    embodiment = snapshot.get("embodiment") if isinstance(snapshot.get("embodiment"), dict) else {}
    workbench = snapshot.get("workbench") if isinstance(snapshot.get("workbench"), dict) else {}
    balance = snapshot.get("balance") if isinstance(snapshot.get("balance"), dict) else {}
    assertion = balance.get("assertion") if isinstance(balance.get("assertion"), dict) else {}
    timeline = snapshot.get("timeline") if isinstance(snapshot.get("timeline"), dict) else {}
    semantic = snapshot.get("semantic") if isinstance(snapshot.get("semantic"), dict) else {}
    gizmo = workbench.get("gizmo") if isinstance(workbench.get("gizmo"), dict) else {}
    active_controller = workbench.get("active_controller") if isinstance(workbench.get("active_controller"), dict) else {}
    route_report = workbench.get("route_report") if isinstance(workbench.get("route_report"), dict) else {}
    maneuver_probe_history = workbench.get("maneuver_probe_history") if isinstance(workbench.get("maneuver_probe_history"), list) else []
    pivot = active_controller.get("pivot_world") if isinstance(active_controller.get("pivot_world"), dict) else {}
    projected_com = balance.get("projected_com") if isinstance(balance.get("projected_com"), dict) else {}
    contacts = snapshot.get("contacts") if isinstance(snapshot.get("contacts"), list) else []
    band = _balance_load_band(balance)
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
    if active_controller:
        leaders = [str(v) for v in (active_controller.get("leader_bone_ids") or []) if str(v)]
        anchors = [str(v) for v in (active_controller.get("anchor_bone_ids") or []) if str(v)]
        carriers = [str(v) for v in (active_controller.get("carrier_bone_ids") or []) if str(v)]
        propagation_mode = str(active_controller.get("propagation_mode") or "follow")
        lines.append(
            "CONTROLLER: "
            + str(active_controller.get("controller_id") or active_controller.get("label") or "selection")
            + " / "
            + str(active_controller.get("controller_kind") or "group")
            + " / members "
            + str(len(active_controller.get("member_bone_ids") or []))
            + " / "
            + propagation_mode
            + " / leader "
            + (",".join(leaders) if leaders else "none")
            + " / anchor "
            + (",".join(anchors) if anchors else "none")
            + " / carrier "
            + (",".join(carriers) if carriers else "none")
            + " / preview "
            + ("active" if active_controller.get("preview_active") else "idle")
            + " / pivot ("
            + f"{float(pivot.get('x') or 0.0):.2f}, "
            + f"{float(pivot.get('y') or 0.0):.2f}, "
            + f"{float(pivot.get('z') or 0.0):.2f})"
        )
    for line in _build_local_bone_tree_lines(snapshot):
        lines.append("  " + line)
    lines.append("  (* selected, + posed, [STATE] contact)")
    lines.append(
        _style_inline("BALANCE: "
        + str(balance.get("support_phase") or "unknown")
        + " / risk "
        + f"{float(balance.get('stability_risk') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / margin "
        + f"{float(balance.get('stability_margin') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / "
        + ("inside polygon" if balance.get("inside_polygon") else "outside polygon")
        + " / "
        + str(band.get("label") or "STABLE"), band.get("style"))
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
    lines.append(
        "  surface: "
        + str(balance.get("support_kind") or balance.get("support_key") or "unknown")
        + " / y "
        + f"{float(balance.get('support_y') or 0.0):.3f}".rstrip("0").rstrip(".")
        + " / supports "
        + str(int(balance.get("support_count") or 0))
        + " / span "
        + f"{float(balance.get('support_span') or 0.0):.2f}".rstrip("0").rstrip(".")
    )
    side_loads = balance.get("support_side_loads") if isinstance(balance.get("support_side_loads"), dict) else {}
    foot_loads = balance.get("foot_support_loads") if isinstance(balance.get("foot_support_loads"), dict) else {}
    lines.append(
        _style_inline("  loads: left "
        + f"{float(side_loads.get('left') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / right "
        + f"{float(side_loads.get('right') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / center "
        + f"{float(side_loads.get('center') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / feet L "
        + f"{float(foot_loads.get('foot_l') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " R "
        + f"{float(foot_loads.get('foot_r') or 0.0):.2f}".rstrip("0").rstrip(".")
        + " / "
        + str(band.get("label") or "STABLE"), band.get("style"))
    )
    nearest_edge = balance.get("nearest_edge") if isinstance(balance.get("nearest_edge"), dict) else {}
    midpoint = nearest_edge.get("midpoint") if isinstance(nearest_edge.get("midpoint"), dict) else {}
    if nearest_edge:
        lines.append(
            "  polygon edge: "
            + str(nearest_edge.get("kind") or "edge")
            + " #"
            + str(int(nearest_edge.get("index") or 0))
            + " / dist "
            + f"{float(nearest_edge.get('distance') or 0.0):.3f}".rstrip("0").rstrip(".")
            + " / mid ("
            + f"{float(midpoint.get('x') or 0.0):.2f}, "
            + f"{float(midpoint.get('z') or 0.0):.2f})"
        )
    for contact in contacts:
        detail = _format_local_contact_line(contact)
        if detail:
            lines.append(detail)
    lines.append("  alerts: " + (", ".join(str(v) for v in (balance.get("alert_ids") or [])) if balance.get("alert_ids") else "none"))
    if route_report:
        intended = ", ".join(str(v) for v in (route_report.get("intended_support_set") or [])) or "none"
        realized = ", ".join(str(v) for v in (route_report.get("realized_support_set") or [])) or "none"
        missing = ", ".join(str(v) for v in (route_report.get("missing_support_participants") or [])) or "none"
        lines.append(
            "ROUTE: "
            + str(route_report.get("support_topology_label") or route_report.get("pose_macro_id") or "support intent")
            + " / intended "
            + intended
            + " / realized "
            + realized
            + " / missing "
            + missing
        )
        if route_report.get("operational_state_label"):
            state_line = "  state: " + str(route_report.get("operational_state_label") or "")
            if route_report.get("operational_state_summary"):
                state_line += " / " + str(route_report.get("operational_state_summary") or "")
            lines.append(state_line)
        if route_report.get("active_phase_label"):
            lines.append(
                "  phase: "
                + str(route_report.get("active_phase_label") or "")
                + " / "
                + str(route_report.get("phase_status") or "pending")
                + " / "
                + str(len(route_report.get("completed_phase_ids") or []))
                + "/"
                + str(len(route_report.get("phase_sequence") or []))
                + " complete"
            )
        if route_report.get("phase_gate_summary") and route_report.get("phase_status") != "complete":
            lines.append("  gate: " + str(route_report.get("phase_gate_summary") or ""))
        if route_report.get("blocker_summary"):
            lines.append("  blocker: " + str(route_report.get("blocker_summary") or ""))
        if route_report.get("next_suggested_adjustment"):
            lines.append("  next: " + str(route_report.get("next_suggested_adjustment") or ""))
    if maneuver_probe_history:
        latest = maneuver_probe_history[0] if maneuver_probe_history else {}
        if isinstance(latest, dict):
            lines.append(
                "TRACE: "
                + str(latest.get("action") or "probe")
                + " / "
                + str(latest.get("support_topology_label") or latest.get("pose_macro_id") or latest.get("controller_id") or "maneuver")
                + " / support_phase "
                + str(latest.get("support_phase") or "unknown")
                + " / risk "
                + str(latest.get("stability_risk") or 0)
            )
            if latest.get("blocker_summary"):
                lines.append("  trace_blocker: " + str(latest.get("blocker_summary") or ""))
    lines.append(
        "ASSERT: "
        + (
            (str(assertion.get("summary") or "unchecked") + (" / stale" if assertion.get("stale") else ""))
            if assertion.get("active")
            else "unchecked"
        )
    )
    lines.append(
        "TIMELINE: cursor "
        + f"{float(timeline.get('cursor') or 0.0):.3f}".rstrip("0").rstrip(".")
        + " / duration "
        + f"{float(timeline.get('duration') or 0.0):.3f}".rstrip("0").rstrip(".")
        + " / "
        + str(int(timeline.get("key_pose_count") or 0))
        + " key poses"
    )
    lines.extend(_sequence_field_text_lines(snapshot, prefix="  ", upper=False, fallback_hint=True))
    if semantic.get("summary"):
        lines.append("SUMMARY: " + str(semantic.get("summary") or ""))
    return "\n".join(lines)


def _local_text_outputs(snapshot, view_mode):
    if not isinstance(snapshot, dict):
        return "", ""
    mode = str(view_mode or "split").strip().lower()
    theater = _render_local_theater_text(snapshot) if mode in ("theater", "split", "render", "consult") else ""
    embodiment = _render_local_embodiment_text(snapshot) if mode in ("embodiment", "split", "render", "consult") else ""
    return theater, embodiment


def _projection_title(snapshot):
    if not isinstance(snapshot, dict):
        return "Scene"
    theater = snapshot.get("theater") or {}
    mode = str(theater.get("mode") or "").strip().lower()
    return "Workbench" if mode == "character" else "Scene"


def _render_render_view(snapshot, theater_text, width, height, diagnostics_visible, section_key, history=None, surface_mode=TEXT_THEATER_SURFACE_MODE, surface_density=TEXT_THEATER_SURFACE_DENSITY):
    width = max(80, width)
    height = max(24, height)
    content_height = max(10, height - 8)
    if diagnostics_visible:
        content_height = max(10, height - 17)

    lines = []
    live_camera = _snapshot_is_live_camera(snapshot)
    render_history = None if live_camera else history
    projection_title = _projection_title(snapshot)
    if live_camera and width >= 120 and content_height >= 18:
        left_width = max(48, int(width * 0.66))
        right_width = max(24, width - left_width - 1)
        main_box = _box(projection_title, _render_projection(snapshot, left_width - 2, content_height - 2, "perspective", history=render_history, surface_mode=surface_mode), left_width, content_height, body_mode="raw")
        right_box = _box("Theater", _wrap_block(theater_text, right_width - 2), right_width, content_height, body_mode="wide", surface_mode=surface_mode, surface_density=surface_density)
        row_count = max(len(main_box), len(right_box))
        for idx in range(row_count):
            left_line = main_box[idx] if idx < len(main_box) else (" " * left_width)
            right_line = right_box[idx] if idx < len(right_box) else (" " * right_width)
            lines.append(left_line + " " + right_line)
    elif width >= 120 and content_height >= 18:
        left_width = max(48, int(width * 0.66))
        right_width = max(24, width - left_width - 1)
        main_box = _box(projection_title, _render_projection(snapshot, left_width - 2, content_height - 2, "perspective", history=render_history, surface_mode=surface_mode), left_width, content_height, body_mode="raw")
        top_height = max(8, content_height // 2)
        front_height = content_height - top_height
        top_box = _box("Quarter", _render_projection(snapshot, right_width - 2, top_height - 2, "quarter", history=render_history, surface_mode=surface_mode), right_width, top_height, body_mode="raw")
        front_box = _box("Profile", _render_projection(snapshot, right_width - 2, front_height - 2, "profile", history=render_history, surface_mode=surface_mode), right_width, front_height, body_mode="raw")
        right_lines = top_box + front_box
        row_count = max(len(main_box), len(right_lines))
        for idx in range(row_count):
            left_line = main_box[idx] if idx < len(main_box) else (" " * left_width)
            right_line = right_lines[idx] if idx < len(right_lines) else (" " * right_width)
            lines.append(left_line + " " + right_line)
    else:
        lines.extend(_box(projection_title, _render_projection(snapshot, width - 2, content_height - 2, "perspective", history=render_history, surface_mode=surface_mode), width, content_height, body_mode="raw"))

    if diagnostics_visible:
        lines.extend(_box(
            f"Diagnostics · {dict(PANE_SECTIONS).get(section_key, section_key)}",
            _section_lines(snapshot, section_key, width - 2),
            width,
            max(7, min(12, height - len(lines) - 3)),
            color=GREEN,
            surface_mode=surface_mode,
            surface_density=surface_density,
        ))
        lines.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2, surface_mode=surface_mode, surface_density=surface_density), width, max(3, height - len(lines)), color=YELLOW, surface_mode=surface_mode, surface_density=surface_density))
    else:
        lines.extend(_box("Status", _compact_status_lines(snapshot, width - 2, surface_mode=surface_mode, surface_density=surface_density), width, max(3, height - len(lines)), color=YELLOW, surface_mode=surface_mode, surface_density=surface_density))
    return lines


def _render_removed_view(width, height, diagnostics_visible, section_key, surface_mode=TEXT_THEATER_SURFACE_MODE, surface_density=TEXT_THEATER_SURFACE_DENSITY):
    width = max(80, width)
    height = max(24, height)
    main_height = max(10, height - (15 if diagnostics_visible else 8))
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
    out = _box("Render Removed", lines, width, main_height, color=RED, surface_mode=surface_mode, surface_density=surface_density)
    if diagnostics_visible:
        out.extend(_box(
            f"Diagnostics · {dict(PANE_SECTIONS).get(section_key, section_key)}",
            _section_lines(snapshot, section_key, width - 2),
            width,
            max(7, min(12, height - len(out) - 3)),
            color=GREEN,
            surface_mode=surface_mode,
            surface_density=surface_density,
        ))
        out.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2, surface_mode=surface_mode, surface_density=surface_density), width, max(3, height - len(out)), color=YELLOW, surface_mode=surface_mode, surface_density=surface_density))
    else:
        out.extend(_box("Status", _compact_status_lines(snapshot, width - 2, surface_mode=surface_mode, surface_density=surface_density), width, max(3, height - len(out)), color=YELLOW, surface_mode=surface_mode, surface_density=surface_density))
    return out


def _render_frame(snapshot, theater_text, embodiment_text, view_mode, section_key, width, height, diagnostics_visible, help_visible=False, history=None, surface_mode=TEXT_THEATER_SURFACE_MODE, surface_density=TEXT_THEATER_SURFACE_DENSITY):
    width = max(80, width)
    height = max(24, height)
    focus_id = (((snapshot.get('theater') or {}).get('focus') or {}).get('id') or 'none')
    banner_text = "MAIN SPLIT" if view_mode == "split" else str(view_mode or "render")
    header_rows = [_style_inline("VIEW " + banner_text, MAGENTA)]
    if diagnostics_visible:
        section_label = dict(PANE_SECTIONS).get(section_key, str(section_key or "theater"))
        header_rows.append(_style_inline("SECTION " + section_label, CYAN))
    header_rows.append(_style_inline(
        "FOCUS " + str(focus_id or "none") + " DIAG " + ("ON" if diagnostics_visible else "OFF"),
        LIGHT_GRAY,
    ))
    lines = _render_wide_text_lines(
        header_rows,
        width - 2,
        max(3, min(8, height // 4)),
        default_style=LIGHT_GRAY,
        align="left",
    )

    if help_visible:
        remaining_height = max(3, height - len(lines))
        lines.extend(_render_help_overlay(snapshot, width, remaining_height, view_mode, section_key, diagnostics_visible, surface_mode=surface_mode, surface_density=surface_density))
        return "\n".join(lines[:height])

    remaining_height = max(6, height - len(lines))
    if view_mode == "render":
        lines.extend(_render_render_view(snapshot, theater_text, width, remaining_height, diagnostics_visible, section_key, history=history, surface_mode=surface_mode, surface_density=surface_density))
    elif view_mode == "consult":
        lines.extend(_render_consult_view(snapshot, width, remaining_height, diagnostics_visible, section_key, surface_mode=surface_mode, surface_density=surface_density))
    elif view_mode == "theater":
        main_height = max(10, remaining_height - (15 if diagnostics_visible else 8))
        lines.extend(_box("Theater", _wrap_block(theater_text, width - 2), width, main_height, body_mode="wide", surface_mode=surface_mode, surface_density=surface_density))
        if diagnostics_visible:
            lines.extend(_box(
                f"Diagnostics · {dict(PANE_SECTIONS).get(section_key, section_key)}",
                _section_lines(snapshot, section_key, width - 2),
                width,
                max(7, min(12, height - len(lines) - 3)),
                color=GREEN,
                surface_mode=surface_mode,
                surface_density=surface_density,
            ))
            lines.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2, surface_mode=surface_mode, surface_density=surface_density), width, max(3, height - len(lines)), color=YELLOW, surface_mode=surface_mode, surface_density=surface_density))
        else:
            lines.extend(_box("Status", _compact_status_lines(snapshot, width - 2, surface_mode=surface_mode, surface_density=surface_density), width, max(3, height - len(lines)), color=YELLOW, surface_mode=surface_mode, surface_density=surface_density))
    elif view_mode == "embodiment":
        main_height = max(10, remaining_height - (15 if diagnostics_visible else 8))
        lines.extend(_box("Embodiment", _wrap_block(embodiment_text, width - 2), width, main_height, body_mode="wide", surface_mode=surface_mode, surface_density=surface_density))
        if diagnostics_visible:
            lines.extend(_box(
                f"Diagnostics · {dict(PANE_SECTIONS).get(section_key, section_key)}",
                _section_lines(snapshot, section_key, width - 2),
                width,
                max(7, min(12, height - len(lines) - 3)),
                color=GREEN,
                surface_mode=surface_mode,
                surface_density=surface_density,
            ))
            lines.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2, surface_mode=surface_mode, surface_density=surface_density), width, max(3, height - len(lines)), color=YELLOW, surface_mode=surface_mode, surface_density=surface_density))
        else:
            lines.extend(_box("Status", _compact_status_lines(snapshot, width - 2, surface_mode=surface_mode, surface_density=surface_density), width, max(3, height - len(lines)), color=YELLOW, surface_mode=surface_mode, surface_density=surface_density))
    elif view_mode == "snapshot":
        main_height = max(10, remaining_height - (15 if diagnostics_visible else 8))
        snapshot_lines = _safe_json_lines(snapshot, width - 2)
        lines.extend(_box("Snapshot", snapshot_lines, width, main_height, body_mode="wide", surface_mode=surface_mode, surface_density=surface_density))
        if diagnostics_visible:
            lines.extend(_box("Status", _build_status_lines(snapshot, section_key, width - 2, surface_mode=surface_mode, surface_density=surface_density), width, max(3, height - len(lines)), color=YELLOW, surface_mode=surface_mode, surface_density=surface_density))
        else:
            lines.extend(_box("Status", _compact_status_lines(snapshot, width - 2, surface_mode=surface_mode, surface_density=surface_density), width, max(3, height - len(lines)), color=YELLOW, surface_mode=surface_mode, surface_density=surface_density))
    else:
        main_height = max(12, remaining_height)
        left_width = max(48, int(width * 0.62))
        right_width = max(28, width - left_width - 1)
        info_height = min(12, max(11, main_height // 3))
        right_top_height = max(4, main_height - info_height)
        left_box = _box("Theater", _wrap_block(theater_text, left_width - 2), left_width, main_height, body_mode="wide", surface_mode=surface_mode, surface_density=surface_density)
        right_top = _box("Embodiment", _wrap_block(embodiment_text, right_width - 2), right_width, right_top_height, body_mode="wide", surface_mode=surface_mode, surface_density=surface_density)
        if diagnostics_visible:
            info_title = f"Diagnostics · {dict(PANE_SECTIONS).get(section_key, section_key)}"
            info_lines = list(_section_lines(snapshot, section_key, right_width - 2))
            status_lines = _build_status_lines(snapshot, section_key, right_width - 2, surface_mode=surface_mode, surface_density=surface_density)
            if info_lines and status_lines:
                info_lines.append("")
            info_lines.extend(status_lines)
            right_bottom = _box(info_title, info_lines, right_width, info_height, color=GREEN, body_mode="wide", surface_mode=surface_mode, surface_density=surface_density)
        else:
            right_bottom = _box("Status", _split_status_lines(snapshot, right_width - 2, surface_mode=surface_mode, surface_density=surface_density), right_width, info_height, color=YELLOW, body_mode="wide", surface_mode=surface_mode, surface_density=surface_density)
        right_lines = right_top + right_bottom
        row_count = max(len(left_box), len(right_lines))
        for idx in range(row_count):
            left_line = left_box[idx] if idx < len(left_box) else (" " * left_width)
            right_line = right_lines[idx] if idx < len(right_lines) else (" " * right_width)
            lines.append(left_line + " " + right_line)
    return "\n".join(lines[:height])


def _fetch_all(base_url, timeout, view_mode):
    snapshot = _env_read(base_url, "text_theater_snapshot", timeout)
    if isinstance(snapshot, dict):
        theater, embodiment = _local_text_outputs(snapshot, view_mode)
        return snapshot, theater, embodiment

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
    surface_mode=TEXT_THEATER_SURFACE_MODE,
    surface_density=TEXT_THEATER_SURFACE_DENSITY,
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
    try:
        rendered = _env_text_theater_view(
            base_url=base_url,
            timeout=timeout,
            view_mode=mode,
            width=width,
            height=height,
            diagnostics_visible=diagnostics_visible,
            section_key=section_name,
        )
        requested_surface_mode = _normalize_surface_mode(surface_mode)
        requested_surface_density = _normalize_surface_density(surface_density)
        if (
            str(rendered.get("frame") or "").strip()
            and requested_surface_mode == TEXT_THEATER_SURFACE_MODE
            and abs(requested_surface_density - TEXT_THEATER_SURFACE_DENSITY) < 0.001
        ):
            return rendered
    except Exception:
        pass
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
        surface_mode=surface_mode,
        surface_density=surface_density,
    )
    return {
        "frame": ANSI_RE.sub("", frame),
        "ansi_frame": frame,
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
    surface_mode=TEXT_THEATER_SURFACE_MODE,
    surface_density=TEXT_THEATER_SURFACE_DENSITY,
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
    cached_theater_text = str(text_theater.get("theater") or "") if mode in {"theater", "split", "render", "consult"} else ""
    cached_embodiment_text = str(text_theater.get("embodiment") or "") if mode in {"embodiment", "split", "render", "consult"} else ""
    if isinstance(snapshot, dict) and snapshot:
        live_state = {"shared_state": shared}
        if synced_at is not None:
            live_state["synced_at"] = synced_at
        snapshot = _merge_live_camera_into_snapshot(snapshot, live_state)
        snapshot = _normalize_snapshot_weather(snapshot)
        local_theater_text, local_embodiment_text = _local_text_outputs(snapshot, mode)
        theater_text = local_theater_text or cached_theater_text
        embodiment_text = local_embodiment_text or cached_embodiment_text
    else:
        snapshot = {}
        theater_text = cached_theater_text
        embodiment_text = cached_embodiment_text
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
        surface_mode=surface_mode,
        surface_density=surface_density,
    )
    return {
        "frame": ANSI_RE.sub("", frame),
        "ansi_frame": frame,
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
    last_error = ""
    motion_history = []
    last_frame = None
    last_snapshot = None
    last_theater_text = ""
    last_embodiment_text = ""
    ui_lock = threading.Lock()
    ui_state = {
        "view_mode": str(args.view or "render").strip().lower() or "render",
        "section_index": 0,
        "diagnostics_visible": bool(args.diagnostics),
        "help_visible": False,
        "surface_mode": _normalize_surface_mode(getattr(args, "surface_mode", TEXT_THEATER_SURFACE_MODE)),
        "surface_density": _normalize_surface_density(getattr(args, "surface_density", TEXT_THEATER_SURFACE_DENSITY)),
        "remote_revision": 0,
    }
    live_cache = {
        "lock": threading.Lock(),
        "ready": False,
        "snapshot": None,
        "theater_text": "",
        "embodiment_text": "",
        "error": "",
    }
    stop_event = threading.Event()

    def _get_ui_state():
        with ui_lock:
            return dict(ui_state)

    def _update_ui_state(**changes):
        with ui_lock:
            for key, value in changes.items():
                if key in ui_state:
                    ui_state[key] = value
            return dict(ui_state)

    def _apply_remote_control(snapshot):
        if not isinstance(snapshot, dict):
            return False
        control = snapshot.get("text_theater_control") if isinstance(snapshot.get("text_theater_control"), dict) else {}
        revision = int(control.get("revision") or 0)
        if revision <= 0:
            return False
        with ui_lock:
            if revision <= int(ui_state.get("remote_revision") or 0):
                return False
            next_view_mode = str(control.get("view_mode") or ui_state["view_mode"]).strip().lower() or ui_state["view_mode"]
            if next_view_mode not in VIEW_MODES:
                next_view_mode = ui_state["view_mode"]
            next_section_key = str(control.get("section_key") or "").strip().lower()
            next_section_index = ui_state["section_index"]
            if next_section_key in SECTION_INDEX_BY_KEY:
                next_section_index = SECTION_INDEX_BY_KEY[next_section_key]
            next_diagnostics_visible = ui_state["diagnostics_visible"]
            if "diagnostics_visible" in control or "diagnostics" in control:
                next_diagnostics_visible = bool(control.get("diagnostics_visible") if "diagnostics_visible" in control else control.get("diagnostics"))
            next_surface_mode = ui_state["surface_mode"]
            if "surface_mode" in control:
                next_surface_mode = _normalize_surface_mode(control.get("surface_mode"), default=ui_state["surface_mode"])
            next_surface_density = ui_state["surface_density"]
            if "surface_density" in control:
                next_surface_density = _normalize_surface_density(control.get("surface_density"), default=ui_state["surface_density"])
            changed = (
                next_view_mode != ui_state["view_mode"]
                or next_section_index != ui_state["section_index"]
                or next_diagnostics_visible != ui_state["diagnostics_visible"]
                or next_surface_mode != ui_state["surface_mode"]
                or next_surface_density != ui_state["surface_density"]
            )
            ui_state["view_mode"] = next_view_mode
            ui_state["section_index"] = next_section_index
            ui_state["diagnostics_visible"] = next_diagnostics_visible
            ui_state["surface_mode"] = next_surface_mode
            ui_state["surface_density"] = next_surface_density
            ui_state["remote_revision"] = revision
            return changed

    def _handle_keypress(key):
        if key is None:
            return ""
        lower = key.lower() if isinstance(key, str) else key
        if lower == "q":
            return "quit"
        if lower == "r":
            return "handled"
        if lower == "h" or key == "?":
            current_ui = _get_ui_state()
            _update_ui_state(help_visible=not current_ui["help_visible"])
            return "handled"
        if key == "\t":
            current_ui = _get_ui_state()
            _update_ui_state(section_index=(current_ui["section_index"] + 1) % len(PANE_SECTIONS))
            return "handled"
        if lower == "m" or key == "0":
            _update_ui_state(view_mode="split", help_visible=False)
            return "handled"
        if key == "1":
            _update_ui_state(view_mode="render", help_visible=False)
            return "handled"
        if key == "2":
            _update_ui_state(view_mode="consult", help_visible=False)
            return "handled"
        if key == "3":
            _update_ui_state(view_mode="theater", help_visible=False)
            return "handled"
        if key == "4":
            _update_ui_state(view_mode="embodiment", help_visible=False)
            return "handled"
        if key == "5":
            _update_ui_state(view_mode="snapshot", help_visible=False)
            return "handled"
        if key == "6":
            _update_ui_state(view_mode="split", help_visible=False)
            return "handled"
        if lower == "d":
            current_ui = _get_ui_state()
            _update_ui_state(diagnostics_visible=not current_ui["diagnostics_visible"])
            return "handled"
        if lower == "s":
            current_ui = _get_ui_state()
            _update_ui_state(surface_mode=_cycle_surface_mode(current_ui["surface_mode"]))
            return "handled"
        if key == "-" or key == "_":
            current_ui = _get_ui_state()
            _update_ui_state(surface_density=max(0.0, round(current_ui["surface_density"] - 0.12, 2)))
            return "handled"
        if key == "=" or key == "+":
            current_ui = _get_ui_state()
            _update_ui_state(surface_density=min(1.0, round(current_ui["surface_density"] + 0.12, 2)))
            return "handled"
        if lower == "b":
            _update_ui_state(section_index=0)
            return "handled"
        if lower == "c":
            _update_ui_state(section_index=1)
            return "handled"
        if lower == "w":
            _update_ui_state(section_index=2)
            return "handled"
        if lower == "e":
            _update_ui_state(section_index=3)
            return "handled"
        if lower == "u":
            _update_ui_state(section_index=4)
            return "handled"
        if lower == "o":
            _update_ui_state(section_index=5)
            return "handled"
        if lower == "g":
            _update_ui_state(
                diagnostics_visible=True,
                help_visible=False,
                section_index=SECTION_INDEX_BY_KEY.get("blackboard", 0),
            )
            return "handled"
        if lower == "p":
            _update_ui_state(
                diagnostics_visible=True,
                help_visible=False,
                section_index=SECTION_INDEX_BY_KEY.get("profiles", 0),
            )
            return "handled"
        return ""

    def _set_live_cache(snapshot=None, theater_text="", embodiment_text="", error="", ready=False):
        with live_cache["lock"]:
            if ready:
                live_cache["snapshot"] = snapshot if isinstance(snapshot, dict) else {}
                live_cache["theater_text"] = str(theater_text or "")
                live_cache["embodiment_text"] = str(embodiment_text or "")
                live_cache["ready"] = True
            live_cache["error"] = str(error or "")

    def _get_live_cache():
        with live_cache["lock"]:
            return {
                "ready": bool(live_cache["ready"]),
                "snapshot": live_cache["snapshot"] if isinstance(live_cache["snapshot"], dict) else None,
                "theater_text": str(live_cache["theater_text"] or ""),
                "embodiment_text": str(live_cache["embodiment_text"] or ""),
                "error": str(live_cache["error"] or ""),
            }

    def _bootstrap_live_cache():
        try:
            rendered = _env_text_theater_view(
                base_url=base_url,
                timeout=args.timeout,
                view_mode="split",
                width=140,
                height=44,
                diagnostics_visible=False,
                section_key="theater",
            )
            _set_live_cache(
                snapshot=rendered.get("snapshot") if isinstance(rendered.get("snapshot"), dict) else {},
                theater_text=str(rendered.get("theater_text") or ""),
                embodiment_text=str(rendered.get("embodiment_text") or ""),
                error="",
                ready=True,
            )
            return True
        except Exception as exc:
            _set_live_cache(error=str(exc))
            return False

    def _live_worker():
        base_poll_delay = max(0.02, min(float(args.interval or 0.04), 0.05))
        failure_streak = 0
        while not stop_event.is_set():
            next_delay = base_poll_delay
            try:
                live_payload = _env_text_theater_live(
                    base_url=base_url,
                    timeout=args.timeout,
                )
                snapshot = live_payload.get("snapshot") if isinstance(live_payload.get("snapshot"), dict) else {}
                _apply_remote_control(snapshot)
                current_ui = _get_ui_state()
                local_theater_text, local_embodiment_text = _local_text_outputs(snapshot, current_ui["view_mode"])
                _set_live_cache(
                    snapshot=snapshot,
                    theater_text=local_theater_text or str(live_payload.get("theater_text") or ""),
                    embodiment_text=local_embodiment_text or str(live_payload.get("embodiment_text") or ""),
                    error="",
                    ready=True,
                )
                failure_streak = 0
            except Exception as exc:
                failure_streak = min(failure_streak + 1, 8)
                _set_live_cache(error=str(exc))
                if not _get_live_cache()["ready"]:
                    _bootstrap_live_cache()
                next_delay = min(0.35, base_poll_delay * (1.0 + (failure_streak * 0.8)))
            stop_event.wait(next_delay)

    _bootstrap_live_cache()
    live_thread = threading.Thread(target=_live_worker, name="text-theater-live", daemon=True)
    live_thread.start()

    sys.stdout.write(ALT_SCREEN_ON + HIDE_CURSOR + CLEAR_SCREEN)
    sys.stdout.flush()
    try:
        while True:
            cycle_started = time.time()
            width, height = shutil.get_terminal_size((140, 44))
            try:
                live_state = _get_live_cache()
                if live_state["ready"]:
                    snapshot = live_state["snapshot"] if isinstance(live_state["snapshot"], dict) else {}
                    _apply_remote_control(snapshot)
                    current_ui = _get_ui_state()
                    theater_text = live_state["theater_text"]
                    embodiment_text = live_state["embodiment_text"]
                    frame = _render_frame(
                        snapshot=snapshot,
                        theater_text=theater_text,
                        embodiment_text=embodiment_text,
                        view_mode=current_ui["view_mode"],
                        section_key=PANE_SECTIONS[current_ui["section_index"]][0],
                        width=width,
                        height=height,
                        diagnostics_visible=current_ui["diagnostics_visible"],
                        help_visible=current_ui["help_visible"],
                        history=motion_history,
                        surface_mode=current_ui["surface_mode"],
                        surface_density=current_ui["surface_density"],
                    )
                    last_error = ""
                else:
                    current_ui = _get_ui_state()
                    rendered = _env_text_theater_view(
                        base_url=base_url,
                        timeout=args.timeout,
                        view_mode=current_ui["view_mode"],
                        width=width,
                        height=height,
                        diagnostics_visible=current_ui["diagnostics_visible"],
                        section_key=PANE_SECTIONS[current_ui["section_index"]][0],
                    )
                    snapshot = rendered.get("snapshot") if isinstance(rendered.get("snapshot"), dict) else {}
                    theater_text = str(rendered.get("theater_text") or "")
                    embodiment_text = str(rendered.get("embodiment_text") or "")
                    if isinstance(snapshot, dict) and snapshot:
                        frame = _render_frame(
                            snapshot=snapshot,
                            theater_text=theater_text,
                            embodiment_text=embodiment_text,
                            view_mode=current_ui["view_mode"],
                            section_key=PANE_SECTIONS[current_ui["section_index"]][0],
                            width=width,
                            height=height,
                            diagnostics_visible=current_ui["diagnostics_visible"],
                            help_visible=current_ui["help_visible"],
                            history=motion_history,
                            surface_mode=current_ui["surface_mode"],
                            surface_density=current_ui["surface_density"],
                        )
                    else:
                        frame = str(rendered.get("frame") or "")
                last_snapshot = snapshot
                last_theater_text = theater_text
                last_embodiment_text = embodiment_text
                if isinstance(snapshot, dict) and snapshot:
                    motion_history = _append_motion_history(motion_history, snapshot)
                if not frame:
                    raise RuntimeError("text_theater_live returned an empty frame")
            except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
                live_state = _get_live_cache()
                last_error = str(live_state.get("error") or exc)
                if isinstance(last_snapshot, dict):
                    error_snapshot = copy.deepcopy(last_snapshot)
                    stale_flags = error_snapshot.get("stale_flags") if isinstance(error_snapshot.get("stale_flags"), dict) else {}
                    next_stale = dict(stale_flags)
                    next_stale["fetch_error"] = last_error
                    error_snapshot["stale_flags"] = next_stale
                    current_ui = _get_ui_state()
                    frame = _render_frame(
                        snapshot=error_snapshot,
                        theater_text=last_theater_text,
                        embodiment_text=last_embodiment_text,
                        view_mode=current_ui["view_mode"],
                        section_key=PANE_SECTIONS[current_ui["section_index"]][0],
                        width=width,
                        height=height,
                        diagnostics_visible=current_ui["diagnostics_visible"],
                        help_visible=current_ui["help_visible"],
                        history=motion_history,
                        surface_mode=current_ui["surface_mode"],
                        surface_density=current_ui["surface_density"],
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

            immediate = _handle_keypress(_read_key_nonblocking())
            if immediate == "quit":
                return 0
            if immediate == "handled":
                if args.once:
                    return 0
                continue
            remaining = max(0.0, float(args.interval) - (time.time() - cycle_started))
            started = time.time()
            while time.time() - started < remaining:
                outcome = _handle_keypress(_read_key_nonblocking())
                if outcome == "quit":
                    return 0
                if outcome == "handled":
                    break
                time.sleep(0.005)
            if args.once:
                return 0
    finally:
        stop_event.set()
        if live_thread.is_alive():
            live_thread.join(timeout=0.3)
        sys.stdout.write(RESET + SHOW_CURSOR + ALT_SCREEN_OFF)
        sys.stdout.flush()
        if last_error:
            print(last_error, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Terminal-native Text Theater view for Champion Council.")
    parser.add_argument("--host", default=os.environ.get("WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("WEB_PORT", "7866")))
    parser.add_argument("--interval", type=float, default=0.02, help="Refresh interval in seconds.")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout in seconds.")
    parser.add_argument("--view", choices=["render", "consult", "split", "theater", "embodiment", "snapshot"], default="render")
    parser.add_argument("--diagnostics", action="store_true", help="Show diagnostics panes by default.")
    parser.add_argument("--surface-mode", choices=list(TEXT_THEATER_SURFACE_MODES), default=TEXT_THEATER_SURFACE_MODE, help="Operator surface spectrum mode. Raw scene projection remains untouched.")
    parser.add_argument("--surface-density", type=float, default=TEXT_THEATER_SURFACE_DENSITY, help="Operator surface substrate density from 0.0 to 1.0.")
    parser.add_argument("--once", action="store_true", help="Render once and exit.")
    raise SystemExit(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
