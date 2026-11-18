"""Areas: a capture through several spaces, split where the floor narrows to a doorway.

One walk can pass through a dining room, a kitchen and a living room. The
measured floor polygon then covers all three. This module cuts it where it
narrows to the width of a doorway, so each space is its own area with its
floor polygon, the things in it and a photo that shows it. An open-plan L is
wide where its arms meet, so it stays one area.

Geometry only. A cut is a chord across the polygon, between two points on its
outline, that is doorway-wide (0.6 to 1.4 m) and leaves a real space on both
sides (2 m2 or more each, and each side wider than the cut). The shortest
such cut is made first, then each side is cut again.

Pure: plan coordinates in, plan coordinates out. The caller turns the twin's
or the shell's frame into plan points ({x_m, y_m}).
"""

import math
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

# A doorway, an arch or a wide opening between two spaces.
MIN_DOOR_M = 0.6
MAX_DOOR_M = 1.4
# Each side of a cut is a space of at least this floor area...
MIN_AREA_M2 = 2.0
# ...and at least this many times the cut's width deep, so a cut is a narrowing.
MIN_DEPTH_FACTOR = 1.5
# The photo of an area sees most of its floor: what lies in the camera's view
# (this wide, this far) and in a straight line inside the floor.
FOV_DEGREES = 65.0
VIEW_RANGE_M = 8.0
GRID_M = 0.2

P = tuple[float, float]


class Area(TypedDict):
    id: str
    floor_polygon: list[dict[str, float]]
    floor_area_m2: float
    object_ids: list[str]
    keyframe_ids: list[str]
    photo_keyframe_id: str | None


class Split(TypedDict):
    start: dict[str, float]
    end: dict[str, float]
    width_m: float


class Areas(TypedDict):
    areas: list[Area]
    splits: list[Split]
    unassigned_object_ids: list[str]


def _signed_area(poly: Sequence[P]) -> float:
    return (
        sum(
            poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
            for i in range(len(poly))
        )
        / 2
    )


def _inside(p: P, poly: Sequence[P]) -> bool:
    """Even-odd rule."""
    inside = False
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if p[0] < x:
                inside = not inside
    return inside


def _cross(o: P, a: P, b: P) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _proper_cross(a: P, b: P, c: P, d: P) -> bool:
    """Segments ab and cd cross at a point inside both (touching ends does not count)."""
    eps = 1e-9
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    return d1 * d2 < -eps and d3 * d4 < -eps


def _closest_on_segment(p: P, a: P, b: P) -> tuple[P, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    span = dx * dx + dy * dy
    t = 0.0 if span == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / span))
    return (a[0] + t * dx, a[1] + t * dy), t


def _with_neck_points(poly: list[P]) -> list[P]:
    """The outline with a point added on each edge where a corner across from it comes
    within a doorway's width, so a cut can run from a door jamb to a flat wall."""
    n = len(poly)
    extra: dict[int, list[tuple[float, P]]] = {}
    for i, v in enumerate(poly):
        for j in range(n):
            if j in (i, (i - 1) % n):
                continue
            q, t = _closest_on_segment(v, poly[j], poly[(j + 1) % n])
            if 1e-3 < t < 1 - 1e-3 and math.dist(v, q) <= MAX_DOOR_M:
                extra.setdefault(j, []).append((t, q))
    out: list[P] = []
    for j, p in enumerate(poly):
        out.append(p)
        for _, q in sorted(extra.get(j, [])):
            if math.dist(q, out[-1]) > 1e-3:
                out.append(q)
    return out


def _chord_inside(poly: Sequence[P], i: int, j: int) -> bool:
    a, b = poly[i], poly[j]
    n = len(poly)
    for k in range(n):
        c, d = poly[k], poly[(k + 1) % n]
        if k in (i, j) or (k + 1) % n in (i, j):
            continue
        if _proper_cross(a, b, c, d):
            return False
    # Not along the outline, and through the floor.
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return _inside(mid, poly) and all(
        abs(_cross(poly[k], poly[(k + 1) % n], mid)) > 1e-6
        or math.dist(poly[k], mid) + math.dist(mid, poly[(k + 1) % n])
        > math.dist(poly[k], poly[(k + 1) % n]) + 1e-6
        for k in range(n)
    )


def _depth(part: Sequence[P], a: P, b: P) -> float:
    """How far the part reaches away from the cut ab."""
    length = math.dist(a, b)
    return max(abs(_cross(a, b, p)) / length for p in part)


def _best_cut(poly: list[P]) -> tuple[list[P], list[P], P, P] | None:
    pts = _with_neck_points(poly)
    n = len(pts)
    best: tuple[float, list[P], list[P], P, P] | None = None
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            width = math.dist(pts[i], pts[j])
            if not MIN_DOOR_M <= width <= MAX_DOOR_M or (best and width >= best[0]):
                continue
            if not _chord_inside(pts, i, j):
                continue
            one, two = pts[i : j + 1], pts[j:] + pts[: i + 1]
            ok = all(
                abs(_signed_area(part)) >= MIN_AREA_M2
                and _depth(part, pts[i], pts[j]) >= MIN_DEPTH_FACTOR * width
                for part in (one, two)
            )
            if ok:
                best = (width, one, two, pts[i], pts[j])
    return None if best is None else best[1:]


def _clean(poly: list[P]) -> list[P]:
    """Without points that lie on a straight run of the outline (the added neck points)."""
    out = list(poly)
    changed = True
    while changed and len(out) > 3:
        changed = False
        for k in range(len(out)):
            a, b, c = out[k - 1], out[k], out[(k + 1) % len(out)]
            if abs(_cross(a, b, c)) < 1e-9 or math.dist(a, b) < 1e-6:
                out.pop(k)
                changed = True
                break
    return out


def _cut(poly: list[P], cuts: list[tuple[P, P]]) -> list[list[P]]:
    found = _best_cut(poly)
    if found is None:
        return [_clean(poly)]
    one, two, a, b = found
    cuts.append((a, b))
    return _cut(one, cuts) + _cut(two, cuts)


def _sees(cam: Mapping[str, Any], area: Sequence[P], whole: Sequence[P]) -> float:
    """Floor of `area` (m2) in the camera's view and in a straight line inside `whole`."""
    x0, y0 = cam["x_m"], cam["y_m"]
    fx, fy = cam["forward"][0], cam["forward"][1]
    norm = math.hypot(fx, fy) or 1.0
    fx, fy = fx / norm, fy / norm
    half = math.radians(FOV_DEGREES / 2)
    xs, ys = [p[0] for p in area], [p[1] for p in area]
    seen = 0
    x = min(xs) + GRID_M / 2
    while x < max(xs):
        y = min(ys) + GRID_M / 2
        while y < max(ys):
            dx, dy = x - x0, y - y0
            dist = math.hypot(dx, dy)
            if (
                0.3 < dist <= VIEW_RANGE_M
                and math.acos(max(-1.0, min(1.0, (dx * fx + dy * fy) / dist))) <= half
                and _inside((x, y), area)
                and not any(
                    _proper_cross((x0, y0), (x, y), whole[k], whole[(k + 1) % len(whole)])
                    for k in range(len(whole))
                )
            ):
                seen += 1
            y += GRID_M
        x += GRID_M
    return seen * GRID_M * GRID_M


def _plan(p: P) -> dict[str, float]:
    return {"x_m": round(p[0], 3), "y_m": round(p[1], 3)}


def split_areas(
    floor_polygon: Sequence[Mapping[str, float]],
    objects: Sequence[Mapping[str, Any]] = (),
    keyframes: Sequence[Mapping[str, Any]] = (),
) -> Areas:
    """Areas of a floor polygon (plan points), with the objects and keyframes in each.

    `objects`: {id, x_m, y_m}, a footprint's centre. `keyframes`: {id, x_m, y_m,
    forward: [dx, dy], sharpness}, the camera's position and horizontal direction."""
    poly = [(float(p["x_m"]), float(p["y_m"])) for p in floor_polygon]
    if len(poly) < 3:
        raise ValueError("a floor polygon needs at least three points")
    n = len(poly)
    if any(
        _proper_cross(poly[i], poly[(i + 1) % n], poly[j], poly[(j + 1) % n])
        for i in range(n)
        for j in range(i + 2, n)
    ):
        raise ValueError("the floor outline crosses itself: there is no floor to split")
    if abs(_signed_area(poly)) < 1e-6:
        raise ValueError("the floor polygon encloses no floor")
    if _signed_area(poly) < 0:
        poly.reverse()
    cuts: list[tuple[P, P]] = []
    parts = _cut(poly, cuts)

    areas: list[Area] = []
    placed: set[str] = set()
    for index, part in enumerate(parts):
        inside_objects = [str(o["id"]) for o in objects if _inside((o["x_m"], o["y_m"]), part)]
        placed.update(inside_objects)
        inside_frames = [str(k["id"]) for k in keyframes if _inside((k["x_m"], k["y_m"]), part)]
        # The photo: from a camera standing in the area if there is one (a view
        # through a doorway shows the door frame), the one that sees most of its floor.
        own = [k for k in keyframes if str(k["id"]) in inside_frames] or list(keyframes)
        scored = [(_sees(k, part, poly), float(k.get("sharpness", 0)), str(k["id"])) for k in own]
        best = max(scored, default=(0.0, 0.0, ""))
        photo = best[2] if best[0] > 0 else None
        areas.append(
            {
                "id": f"a{index + 1}",
                "floor_polygon": [_plan(p) for p in part],
                "floor_area_m2": round(abs(_signed_area(part)), 2),
                "object_ids": inside_objects,
                "keyframe_ids": inside_frames,
                "photo_keyframe_id": photo,
            }
        )
    return {
        "areas": areas,
        "splits": [
            {"start": _plan(a), "end": _plan(b), "width_m": round(math.dist(a, b), 3)}
            for a, b in cuts
        ],
        "unassigned_object_ids": [str(o["id"]) for o in objects if str(o["id"]) not in placed],
    }
