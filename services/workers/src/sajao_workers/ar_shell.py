"""The measured shell: a floor polygon built from the walls the phone saw.

A room is not assumed to be a box, or closed, or even one room. The shell is
a ring of edges around the floor. An edge is a `wall` where the phone tracked
a wall, and `open` where the ring passes from the end of one wall to the
start of the next with no wall seen between them: a doorway, an opening into
the next area, or a stretch nobody pointed the phone at.

Rules, all in code (no model sets a length):

- A wall runs from near the floor to near the ceiling. A vertical plane that
  stops short is furniture: a fridge side, a cabinet front, a counter.
- Vertical planes that belong to inventory objects are removed first, by the
  function the caller passes as `drop`.
- Patches in one plane are one wall while the gap between them is small; a
  doorway in a wall is found later as an opening, not as a break in the wall.
- The room is on the side of a wall the phone walked on, so each wall has a
  direction along the ring. Two walls meet in a corner where their lines cross
  close to what was seen of both; otherwise an open edge joins them.

Every length is a dimension with its source and error band.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sajao_workers.ar_measurements import BAND, Plane, _ceiling, _floor, read_planes

FORMAT = "sajao-ar-shell-1"
# Patches closer than this in direction and distance lie in one plane.
SAME_PLANE_DEGREES = 12.0
SAME_PLANE_OFFSET_M = 0.2
# Two stretches of one plane are one wall while the gap between them is at
# most this: wider than a door, so a doorway does not split its wall.
SAME_WALL_GAP_M = 1.2
# A wall starts within this of the floor and ends within this of the ceiling.
NEAR_FLOOR_M = 0.5
NEAR_CEILING_M = 0.5
# Without a ceiling plane, a wall is a plane seen up to at least this height.
MIN_WALL_TOP_M = 2.0
MIN_WALL_M = 0.6
# Two walls meet in a corner only at a real angle, and only where their lines
# cross within this of what was seen of each.
MIN_CORNER_DEGREES = 30.0
MAX_CORNER_REACH_M = 1.0
# A wall further than this from the rest of the ring belongs to something else.
MAX_OPEN_EDGE_M = 6.0
# The room side of a wall is judged from where the phone was within this of it.
SIDE_RANGE_M = 4.0

Point2 = tuple[float, float]  # (x, z) in the AR world, metres
Drop = Callable[[Sequence[Plane]], Sequence[Plane]]


def _dimension(value_m: float) -> dict[str, Any]:
    floor, fraction = BAND
    return {
        "value_m": round(abs(value_m), 3),
        "source": "estimated",
        "error_band_m": round(max(floor, fraction * abs(value_m)), 3),
    }


def _plan(point: Point2) -> dict[str, float]:
    """A floor plan point: x as in the AR world, y pointing the opposite way to AR z."""
    return {"x_m": round(point[0], 3), "y_m": round(-point[1], 3)}


@dataclass
class _Stretch:
    """What was seen of one wall: a straight piece of a vertical plane."""

    normal: Point2  # unit, horizontal; turned to point into the room once that is known
    offset: float  # normal . point
    low: float  # along the tangent
    high: float
    bottom: float  # metres, AR world y
    top: float
    weight: float
    patches: int = 1

    @property
    def tangent(self) -> Point2:
        return (-self.normal[1], self.normal[0])

    def at(self, along: float) -> Point2:
        t = self.tangent
        return (
            self.normal[0] * self.offset + t[0] * along,
            self.normal[1] * self.offset + t[1] * along,
        )

    def along(self, p: Point2) -> float:
        t = self.tangent
        return p[0] * t[0] + p[1] * t[1]

    @property
    def start(self) -> Point2:
        return self.at(self.low)

    @property
    def end(self) -> Point2:
        return self.at(self.high)

    @property
    def length(self) -> float:
        return self.high - self.low

    def flipped(self) -> "_Stretch":
        return _Stretch(
            (-self.normal[0], -self.normal[1]),
            -self.offset,
            -self.high,
            -self.low,
            self.bottom,
            self.top,
            self.weight,
            self.patches,
        )


def _stretch(plane: Plane) -> _Stretch | None:
    length = math.hypot(plane.normal[0], plane.normal[2])
    if length < 0.5:  # not vertical after all
        return None
    n = (plane.normal[0] / length, plane.normal[2] / length)
    c = plane.centre
    one = _Stretch(n, n[0] * c[0] + n[1] * c[2], 0, 0, 0, 0, max(plane.area, 1e-6))
    positions = [one.along((p[0], p[2])) for p in plane.points]
    heights = [p[1] for p in plane.points]
    one.low, one.high = min(positions), max(positions)
    one.bottom, one.top = min(heights), max(heights)
    return one


def _same_plane(a: _Stretch, b: _Stretch) -> _Stretch | None:
    """`b` as seen along `a`'s direction if both lie in one plane and are close; else None."""
    dot = a.normal[0] * b.normal[0] + a.normal[1] * b.normal[1]
    if dot < 0:  # planes face either way
        b, dot = b.flipped(), -dot
    if math.degrees(math.acos(min(1.0, dot))) > SAME_PLANE_DEGREES:
        return None
    # Distance of b's middle from a's plane, and b's ends along a.
    middle = b.at((b.low + b.high) / 2)
    if abs(a.normal[0] * middle[0] + a.normal[1] * middle[1] - a.offset) > SAME_PLANE_OFFSET_M:
        return None
    ends = sorted((a.along(b.start), a.along(b.end)))
    if ends[0] - a.high > SAME_WALL_GAP_M or a.low - ends[1] > SAME_WALL_GAP_M:
        return None
    return _Stretch(a.normal, a.offset, ends[0], ends[1], b.bottom, b.top, b.weight)


def _join(stretches: Sequence[_Stretch]) -> list[_Stretch]:
    """Patches of one wall joined, largest first; repeated until nothing more joins."""
    walls = sorted(stretches, key=lambda s: -s.weight)
    joined = True
    while joined:
        joined = False
        out: list[_Stretch] = []
        for piece in walls:
            for wall in out:
                seen = _same_plane(wall, piece)
                if seen is None:
                    continue
                total = wall.weight + seen.weight
                # The larger patch sets the plane; the smaller one only extends it.
                wall.low, wall.high = min(wall.low, seen.low), max(wall.high, seen.high)
                wall.bottom, wall.top = min(wall.bottom, seen.bottom), max(wall.top, seen.top)
                wall.weight, wall.patches = total, wall.patches + piece.patches
                joined = True
                break
            else:
                out.append(piece)
        walls = out
    return walls


def _faces_room(wall: _Stretch, path: Sequence[Point2], fallback: Point2 | None) -> _Stretch:
    """The wall with its normal pointing to the side the phone was on."""
    middle = wall.at((wall.low + wall.high) / 2)
    near = [p for p in path if math.dist(p, middle) <= SIDE_RANGE_M] or list(path)
    if not near and fallback is not None:
        near = [fallback]
    side = sum(
        (1 if wall.normal[0] * p[0] + wall.normal[1] * p[1] - wall.offset > 0 else -1) for p in near
    )
    return wall if side >= 0 else wall.flipped()


def _corner(a: _Stretch, b: _Stretch) -> Point2 | None:
    """Where wall `a`'s end meets wall `b`'s start, if their lines cross close to both."""
    dot = a.normal[0] * b.normal[0] + a.normal[1] * b.normal[1]
    angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
    if angle < MIN_CORNER_DEGREES or angle > 180 - MIN_CORNER_DEGREES:
        return None
    det = a.normal[0] * b.normal[1] - a.normal[1] * b.normal[0]
    x = (a.offset * b.normal[1] - b.offset * a.normal[1]) / det
    z = (b.offset * a.normal[0] - a.offset * b.normal[0]) / det
    # The corner must lie near a's end and near b's start, and leave both walls a length.
    at_a, at_b = a.along((x, z)), b.along((x, z))
    if abs(at_a - a.high) > MAX_CORNER_REACH_M or abs(at_b - b.low) > MAX_CORNER_REACH_M:
        return None
    if at_a - a.low < MIN_WALL_M / 2 or b.high - at_b < MIN_WALL_M / 2:
        return None
    return (x, z)


def _step(a: _Stretch, b: _Stretch) -> float:
    """How far the ring travels off the walls going from `a`'s end to `b`'s start."""
    corner = _corner(a, b)
    if corner is not None:
        return math.dist(a.end, corner) + math.dist(corner, b.start)
    return math.dist(a.end, b.start)


def _ring(walls: Sequence[_Stretch]) -> tuple[list[_Stretch], list[_Stretch]]:
    """The walls in order around the floor, and the ones too far away to belong."""
    left = sorted(walls, key=lambda w: -w.length)
    ring = [left.pop(0)]
    while left:
        nearest = min(left, key=lambda w: _step(ring[-1], w))
        if _step(ring[-1], nearest) > MAX_OPEN_EDGE_M:
            break
        ring.append(nearest)
        left.remove(nearest)
    return ring, left


def _crosses(points: Sequence[Point2]) -> bool:
    def turn(a: Point2, b: Point2, c: Point2) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    n = len(points)
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        for j in range(i + 2, n):
            if (j + 1) % n == i:
                continue
            c, d = points[j], points[(j + 1) % n]
            if turn(a, b, c) * turn(a, b, d) < -1e-9 and turn(c, d, a) * turn(c, d, b) < -1e-9:
                return True
    return False


def measured_shell(
    doc: Mapping[str, Any],
    path: Sequence[Point2] = (),
    drop: Drop | None = None,
) -> dict[str, Any]:
    """The floor polygon and its edges from a planes document.

    `path` is where the phone was, as (x, z) in the AR world: keyframe and
    pose-log positions. `drop` removes the vertical planes that belong to
    inventory objects.
    """
    planes = read_planes(doc)
    notes: list[str] = []
    result: dict[str, Any] = {
        "format": FORMAT,
        "floor_polygon": None,
        "edges": [],
        "floor_area_m2": None,
        "ceiling_height": None,
        "closed": False,
        "dropped": {},
        "notes": notes,
    }
    floor_y, floor_planes = _floor(planes)
    ceiling_y = _ceiling(planes, floor_y)
    if floor_y is not None and ceiling_y is not None:
        result["ceiling_height"] = _dimension(ceiling_y - floor_y)

    upright = [
        p for p in planes if p.kind == "vertical" and p.classification not in ("door", "window")
    ]
    kept = list(drop(upright)) if drop is not None else upright
    stretches = [s for s in (_stretch(p) for p in kept) if s is not None]
    joined = _join(stretches)

    def is_wall(wall: _Stretch) -> bool:
        if floor_y is None:
            return wall.top - wall.bottom >= MIN_WALL_TOP_M
        if wall.bottom - floor_y > NEAR_FLOOR_M:
            return False
        if ceiling_y is not None:
            return ceiling_y - wall.top <= NEAR_CEILING_M
        return wall.top - floor_y >= MIN_WALL_TOP_M

    tall = [w for w in joined if is_wall(w)]
    walls = [w for w in tall if w.length >= MIN_WALL_M]
    result["dropped"] = {
        "object_planes": len(upright) - len(kept),
        "not_floor_to_ceiling": len(joined) - len(tall),
        "too_short": len(tall) - len(walls),
    }
    if floor_y is None:
        notes.append("No floor plane was found: walls are judged by their own height.")
    if ceiling_y is None:
        notes.append("No ceiling plane was found: the ceiling height is not known.")
    if not walls:
        notes.append("No wall was seen from near the floor to near the ceiling.")
        return result

    spots = [q for p in floor_planes for q in p.points]
    fallback = (
        (sum(q[0] for q in spots) / len(spots), sum(q[2] for q in spots) / len(spots))
        if spots
        else None
    )
    # With the room on its normal's side, a wall is walked from low to high
    # along its tangent, so every wall runs the same way round the ring.
    ring, far = _ring([_faces_room(w, path, fallback) for w in walls])
    if far:
        notes.append(
            f"{len(far)} wall(s) lie more than {MAX_OPEN_EDGE_M:g} m from the rest "
            "and were left out."
        )
    result["dropped"]["far_from_the_rest"] = len(far)

    n = len(ring)
    # The point where wall i hands over to wall i + 1: a corner, or None for an open edge.
    corners = [_corner(ring[i], ring[(i + 1) % n]) if n > 1 else None for i in range(n)]
    points: list[Point2] = []
    edges: list[dict[str, Any]] = []
    for i, wall in enumerate(ring):
        before, after = corners[i - 1] if n > 1 else None, corners[i]
        start = before if before is not None else wall.start
        end = after if after is not None else wall.end
        points.append(start)
        edges.append(
            {
                "id": f"w{len(edges) + 1}",
                "kind": "wall",
                "start": _plan(start),
                "end": _plan(end),
                "length": _dimension(math.dist(start, end)),
                # corner_to_corner: both ends are corners, so this is the wall's full
                # length. seen: at least one end is only where the phone stopped seeing it.
                "basis": "corner_to_corner" if before is not None and after is not None else "seen",
                "seen_m": round(wall.length, 3),
                "patches": wall.patches,
            }
        )
        if after is None:
            target = ring[(i + 1) % n].start
            if math.dist(end, target) > 1e-6:
                points.append(end)
                edges.append(
                    {
                        "id": f"w{len(edges) + 1}",
                        "kind": "open",
                        "start": _plan(end),
                        "end": _plan(target),
                        "length": _dimension(math.dist(end, target)),
                        "basis": "between_walls",
                    }
                )
    if len(points) < 3:
        notes.append("Too few walls were seen to enclose a floor.")
        result["edges"] = edges
        return result
    result["edges"] = edges
    result["floor_polygon"] = [_plan(p) for p in points]
    area = 0.5 * abs(
        sum(
            points[i][0] * points[(i + 1) % len(points)][1]
            - points[(i + 1) % len(points)][0] * points[i][1]
            for i in range(len(points))
        )
    )
    result["floor_area_m2"] = round(area, 2)
    result["closed"] = all(e["kind"] == "wall" for e in edges)
    if _crosses(points):
        notes.append("The ring crosses itself: the walls seen do not yet make one clear outline.")
        result["floor_area_m2"] = None
    open_m = sum(e["length"]["value_m"] for e in edges if e["kind"] == "open")
    if open_m:
        notes.append(
            f"{open_m:.2f} m of the outline is open: no wall was seen there. "
            "It may be a doorway, the way into the next area, or a wall not scanned."
        )
    return result
