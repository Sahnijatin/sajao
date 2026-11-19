"""Where a photo shows the floor: the part of a room a photo redesign may furnish.

A design shown on a photo must show everything it sells, so on a photo-first room
new items go only where that photo sees the floor. That region is the camera's
view cut by the floor plane (z = 0 in the space frame), clipped to the room's floor
polygon. The rest of the floor (the strip the person stood on) stays passable, so
walkways may use it. Pure geometry from the twin's keyframe pose and intrinsics.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from sajao_engine.geometry import Point, ccw, clip_convex, polygon_area
from sajao_schemas.generated.v1 import SpaceTwin

# Rays at or above the horizon reach the floor this far away (metres, horizontally).
FAR_M = 12.0
# Image border samples per side.
SAMPLES = 24
# A visible floor smaller than this (square metres) cannot take a design.
MIN_AREA_M2 = 1.0


def _rotation(q: Sequence[float]) -> list[list[float]]:
    x, y, z, w = q
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]


def _convex_hull(points: list[Point]) -> list[Point]:
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def half(seq: list[Point]) -> list[Point]:
        out: list[Point] = []
        for p in seq:
            while (
                len(out) >= 2
                and (
                    (out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                    - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])
                )
                <= 0
            ):
                out.pop()
            out.append(p)
        return out

    lower, upper = half(pts), half(pts[::-1])
    return lower[:-1] + upper[:-1]


def visible_floor(twin: SpaceTwin, keyframe_id: str | None = None) -> list[Point] | None:
    """The floor the photo shows, counterclockwise in the space frame, or None when it
    shows too little. `keyframe_id` defaults to the first hero view, else the first
    keyframe."""
    if keyframe_id is None:
        heroes = twin.viewing.hero_views if twin.viewing is not None else []
        keyframe_id = _id(heroes[0].keyframe_id) if heroes else _id(twin.keyframes[0].id)
    frame = next(k for k in twin.keyframes if _id(k.id) == keyframe_id)
    if frame.intrinsics is None:
        return None
    k = frame.intrinsics
    r = _rotation([float(v.root) for v in frame.pose.rotation])
    p = frame.pose.position
    border: list[tuple[float, float]] = []
    w, h = k.width_px, k.height_px
    for i in range(SAMPLES):
        s = i / SAMPLES
        border += [(s * w, 0.0), (w, s * h), ((1 - s) * w, h), (0.0, (1 - s) * h)]
    hits: list[Point] = []
    grounded = False
    for u, v in border:
        d_cam = ((u - k.cx) / k.fx, (v - k.cy) / k.fy, 1.0)
        d = [sum(r[i][j] * d_cam[j] for j in range(3)) for i in range(3)]
        flat = math.hypot(d[0], d[1])
        if flat < 1e-9:
            continue
        if d[2] < -1e-9:
            t = -p.z_m / d[2]
            grounded = True
            if t * flat <= FAR_M:
                hits.append((p.x_m + t * d[0], p.y_m + t * d[1]))
                continue
        # At or above the horizon, or beyond FAR_M: the floor runs on to FAR_M.
        hits.append((p.x_m + FAR_M * d[0] / flat, p.y_m + FAR_M * d[1] / flat))
    if not grounded:
        return None  # no part of the photo looks down at the floor
    # The footprint is convex: the hull also closes the corner at the camera's feet.
    view = ccw(_convex_hull(hits))
    floor = ccw([(q.x_m, q.y_m) for q in twin.shell.floor_polygon])
    region = clip_convex(list(view), list(floor)) if _is_convex(floor) else None
    if region is None or len(region) < 3 or polygon_area(region) < MIN_AREA_M2:
        return None
    return [(round(x, 3), round(y, 3)) for x, y in region]


def _id(value: object) -> str:
    return str(getattr(value, "root", value))


def _is_convex(poly: Sequence[Point]) -> bool:
    signs = set()
    n = len(poly)
    for i in range(n):
        a, b, c = poly[i], poly[(i + 1) % n], poly[(i + 2) % n]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cross) > 1e-9:
            signs.add(cross > 0)
    return len(signs) <= 1
