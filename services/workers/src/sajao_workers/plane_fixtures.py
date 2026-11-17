"""Planes documents of a room whose true sizes are known.

Synthetic input for the AR measurement code and its report: the room as a
phone sees it, a patch of each wall and never the whole wall, in the
capture package's planes format (sajao-planes-1). Nothing here is a
measurement of a real room.
"""

import math
from typing import Any

# A 4.2 by 3.4 m room, ceiling 2.9 m, floor 1.4 m below where the phone started.
WIDTH, DEPTH, HEIGHT, FLOOR_Y = 4.2, 3.4, 2.9, -1.4


def vertical(
    centre: tuple[float, float],
    facing_deg: float,
    wide: float,
    bottom: float,
    top: float,
    classification: str | None = None,
) -> dict[str, Any]:
    """An upright rectangle: `centre` is (x, z), `facing_deg` the way its normal points."""
    a = math.radians(facing_deg)
    nx, nz = math.cos(a), math.sin(a)
    tx, tz = -nz, nx
    middle = FLOOR_Y + (bottom + top) / 2
    half_w, half_h = wide / 2, (top - bottom) / 2
    plane: dict[str, Any] = {
        "type": "vertical",
        # Column-major: x axis along the wall, y axis the normal, z axis up.
        "transform": [tx, 0, tz, 0, nx, 0, nz, 0, 0, 1, 0, 0, centre[0], middle, centre[1], 1],
        "extent": [wide, top - bottom],
        "polygon_xz": [-half_w, -half_h, half_w, -half_h, half_w, half_h, -half_w, half_h],
    }
    if classification:
        plane["classification"] = classification
    return plane


def horizontal(
    centre: tuple[float, float],
    size: tuple[float, float],
    y: float,
    kind: str = "horizontal_up",
    classification: str | None = None,
) -> dict[str, Any]:
    half_x, half_z = size[0] / 2, size[1] / 2
    up = -1 if kind == "horizontal_down" else 1
    plane: dict[str, Any] = {
        "type": kind,
        "transform": [1, 0, 0, 0, 0, up, 0, 0, 0, 0, 1, 0, centre[0], y, centre[1], 1],
        "extent": [size[0], size[1]],
        "polygon_xz": [-half_x, -half_z, half_x, -half_z, half_x, half_z, -half_x, half_z],
    }
    if classification:
        plane["classification"] = classification
    return plane


def room(*extra: dict[str, Any], classed: bool = True) -> dict[str, Any]:
    """The room as a phone sees it: a patch of each wall, never the whole wall."""
    wall = "wall" if classed else None
    planes = [
        horizontal((2.0, 1.6), (2.5, 2.0), FLOOR_Y, classification="floor" if classed else None),
        # The wall along z = 0, seen in two patches that face opposite ways.
        vertical((1.2, 0.0), 90, 1.6, 0.2, 2.4, wall),
        vertical((3.2, 0.0), -90, 1.0, 0.5, 2.0, wall),
        vertical((WIDTH, 1.5), 180, 2.0, 0.3, 2.5, wall),
        vertical((2.4, DEPTH), -90, 2.6, 0.0, 2.6, wall),
        vertical((0.0, 2.0), 0, 1.8, 0.4, 2.2, wall),
        *extra,
    ]
    return {"format": "sajao-planes-1", "planes": planes}
