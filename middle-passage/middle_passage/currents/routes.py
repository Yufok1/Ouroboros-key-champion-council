from __future__ import annotations


CORRIDOR_BEARINGS = {
    "west_africa_caribbean": 275.0,
    "west_africa_brazil": 235.0,
    "west_africa_north_america": 295.0,
    "doldrums_zone": 270.0,
}


def corridor_bearing_degrees(corridor: str | None) -> float:
    if not corridor:
        return CORRIDOR_BEARINGS["doldrums_zone"]
    return CORRIDOR_BEARINGS.get(corridor.strip().lower(), CORRIDOR_BEARINGS["doldrums_zone"])

