"""Room measurements from the capture package's AR planes.

The phone's planes file (format sajao-planes-1, docs/06-room-capture.md) holds
every plane ARKit or ARCore found: where it is, which way it faces and its
outline. This module turns those planes into the measurements fit is checked
against: each wall's length, the floor's size, the ceiling height, and each
door and window with its width, height, sill and distance from the corner.

Geometry only, no model: wall patches that lie in one plane are joined into a
wall, neighbouring walls are intersected to find the corners, and a wall's
length is the distance between its two corners. A wall with a missing
neighbour only has the stretch the phone saw, which is a lower bound, and is
marked as such. Every value is an estimated Dimension with an error band;
the tape verifies, and the golden-room report says how far off each one is.

Doors and windows come from the planes the phone itself classed as a door or
a window. ARKit does that; ARCore does not, so an Android capture has none.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

FORMAT = "sajao-ar-measurements-1"
# (floor in metres, fraction of the length). Provisional until the golden set
# says how good AR planes are on each kind of phone.
BAND = (0.05, 0.03)
# Wall patches closer than this in direction and distance are one wall.
SAME_WALL_DEGREES = 12.0
SAME_WALL_OFFSET_M = 0.2
# A vertical surface shorter than this along its length is furniture, not a wall.
MIN_WALL_M = 0.6
# Neighbouring walls meet in a corner only at a real angle.
MIN_CORNER_DEGREES = 30.0
# A corner further than this beyond what the phone saw of a wall is a guess, not a corner.
MAX_CORNER_REACH_M = 2.5
# A door or window belongs to a wall this close in direction and distance.
OPENING_WALL_DEGREES = 20.0
OPENING_WALL_OFFSET_M = 0.35
# Horizontal planes within this of the lowest one are the floor.
FLOOR_BAND_M = 0.15
MIN_FLOOR_AREA_M2 = 0.5

Point = tuple[float, float, float]


def dimension(value_m: float) -> dict[str, Any]:
    floor, fraction = BAND
    return {
        "value_m": round(value_m, 3),
        "source": "estimated",
        "error_band_m": round(max(floor, fraction * abs(value_m)), 3),
    }


@dataclass(frozen=True)
class Plane:
    kind: str  # "vertical", "horizontal_up" or "horizontal_down"
    classification: str  # ARKit's class, or "none"
    points: tuple[Point, ...]  # the outline in the AR world (metres, y up)
    normal: Point

    @property
    def centre(self) -> Point:
        n = len(self.points)
        return (
            sum(p[0] for p in self.points) / n,
            sum(p[1] for p in self.points) / n,
            sum(p[2] for p in self.points) / n,
        )

    @property
    def area(self) -> float:
        """Area of the outline, by the cross products of a fan from its first point."""
        total = (0.0, 0.0, 0.0)
        a = self.points[0]
        for b, c in zip(self.points[1:], self.points[2:], strict=False):
            u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            total = (
                total[0] + u[1] * v[2] - u[2] * v[1],
                total[1] + u[2] * v[0] - u[0] * v[2],
                total[2] + u[0] * v[1] - u[1] * v[0],
            )
        return 0.5 * math.sqrt(sum(t * t for t in total))


def read_planes(doc: Mapping[str, Any]) -> list[Plane]:
    """Planes from a sajao-planes-1 document, outlines in the AR world."""
    planes = []
    for raw in doc.get("planes", []):
        m = raw.get("transform", [])
        polygon = raw.get("polygon_xz", [])
        if len(m) != 16 or len(polygon) < 6:
            continue
        # Column-major: the plane's own x and z axes span it, its y axis is the normal.
        points = tuple(
            (
                m[0] * x + m[8] * z + m[12],
                m[1] * x + m[9] * z + m[13],
                m[2] * x + m[10] * z + m[14],
            )
            for x, z in zip(polygon[0::2], polygon[1::2], strict=False)
        )
        if not all(math.isfinite(v) for p in points for v in p):
            continue
        planes.append(
            Plane(
                kind=str(raw.get("type", "")),
                classification=str(raw.get("classification", "none")),
                points=points,
                normal=(m[4], m[5], m[6]),
            )
        )
    return planes


@dataclass
class _Wall:
    """Wall patches that lie in one plane. `normal` is horizontal and points into the room."""

    normal: tuple[float, float]  # (x, z), unit
    offset: float  # normal . point, metres
    weight: float
    points: list[Point] = field(default_factory=list)

    @property
    def tangent(self) -> tuple[float, float]:
        return (-self.normal[1], self.normal[0])

    def along(self, p: Sequence[float]) -> float:
        t = self.tangent
        return p[0] * t[0] + p[-1] * t[1]

    @property
    def seen(self) -> tuple[float, float]:
        values = [self.along(p) for p in self.points]
        return min(values), max(values)

    def at(self, along: float) -> tuple[float, float]:
        """The point on the wall's line at a position along it, as (x, z)."""
        t = self.tangent
        return (
            self.normal[0] * self.offset + t[0] * along,
            self.normal[1] * self.offset + t[1] * along,
        )


def _angle_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    dot = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))
    return math.degrees(math.acos(dot))


def _floor(planes: Sequence[Plane]) -> tuple[float | None, list[Plane]]:
    """The floor's height and its planes: the lowest sizeable upward planes."""
    up = [
        p
        for p in planes
        if p.kind == "horizontal_up" and p.classification not in ("ceiling", "table", "seat")
    ]
    named = [p for p in up if p.classification == "floor"]
    sizeable = named or [p for p in up if p.area >= MIN_FLOOR_AREA_M2]
    if not sizeable:
        return None, []
    lowest = min(p.centre[1] for p in sizeable)
    floor = [p for p in sizeable if p.centre[1] <= lowest + FLOOR_BAND_M]
    area = sum(p.area for p in floor)
    return sum(p.centre[1] * p.area for p in floor) / area, floor


def _ceiling(planes: Sequence[Plane], floor_y: float | None) -> float | None:
    found = [
        p
        for p in planes
        if p.classification == "ceiling"
        or (p.kind == "horizontal_down" and p.classification == "none")
    ]
    if floor_y is not None:
        # A downward plane a little above the floor is the underside of a table.
        found = [p for p in found if p.centre[1] - floor_y >= 1.8]
    if not found:
        return None
    area = sum(p.area for p in found)
    return sum(p.centre[1] * p.area for p in found) / area if area > 0 else None


def _join_walls(patches: Sequence[Plane], centre: tuple[float, float]) -> list[_Wall]:
    walls: list[_Wall] = []
    for patch in sorted(patches, key=lambda p: -p.area):
        length = math.hypot(patch.normal[0], patch.normal[2])
        if length < 0.5:  # not vertical after all
            continue
        n = (patch.normal[0] / length, patch.normal[2] / length)
        c = patch.centre
        # Planes face either way: turn every normal to point into the room.
        if n[0] * (centre[0] - c[0]) + n[1] * (centre[1] - c[2]) < 0:
            n = (-n[0], -n[1])
        offset = n[0] * c[0] + n[1] * c[2]
        weight = max(patch.area, 1e-6)
        for wall in walls:
            if (
                _angle_between(wall.normal, n) <= SAME_WALL_DEGREES
                and abs(wall.offset - offset) <= SAME_WALL_OFFSET_M
            ):
                total = wall.weight + weight
                mixed = (
                    (wall.normal[0] * wall.weight + n[0] * weight) / total,
                    (wall.normal[1] * wall.weight + n[1] * weight) / total,
                )
                norm = math.hypot(*mixed)
                wall.normal = (mixed[0] / norm, mixed[1] / norm)
                wall.offset = (wall.offset * wall.weight + offset * weight) / total
                wall.weight = total
                wall.points.extend(patch.points)
                break
        else:
            walls.append(_Wall(n, offset, weight, list(patch.points)))
    return [w for w in walls if w.seen[1] - w.seen[0] >= MIN_WALL_M]


def _corner(a: _Wall, b: _Wall) -> tuple[float, float] | None:
    """Where two walls' lines meet, as (x, z); None when they are near parallel."""
    angle = _angle_between(a.normal, b.normal)
    if angle < MIN_CORNER_DEGREES or angle > 180 - MIN_CORNER_DEGREES:
        return None
    det = a.normal[0] * b.normal[1] - a.normal[1] * b.normal[0]
    x = (a.offset * b.normal[1] - b.offset * a.normal[1]) / det
    z = (b.offset * a.normal[0] - a.offset * b.normal[0]) / det
    for wall in (a, b):
        low, high = wall.seen
        position = wall.along((x, z))
        if position < low - MAX_CORNER_REACH_M or position > high + MAX_CORNER_REACH_M:
            return None
    return (x, z)


def _plan(point: tuple[float, float]) -> dict[str, float]:
    """A floor plan point: x as in the AR world, y pointing the opposite way to AR z."""
    return {"x_m": round(point[0], 3), "y_m": round(-point[1], 3)}


def measure(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Walls, floor, ceiling height, doors and windows from a planes document."""
    planes = read_planes(doc)
    notes: list[str] = []
    result: dict[str, Any] = {
        "format": FORMAT,
        "planes": len(planes),
        "walls": [],
        "floor": None,
        "ceiling_height": None,
        "openings": [],
        "notes": notes,
    }
    if not planes:
        notes.append("The phone found no planes: there are no AR measurements for this scan.")
        return result

    floor_y, floor_planes = _floor(planes)
    ceiling_y = _ceiling(planes, floor_y)
    if floor_y is None:
        notes.append("No floor plane was found: heights above the floor are not known.")
    if floor_y is not None and ceiling_y is not None:
        result["ceiling_height"] = dimension(ceiling_y - floor_y)
    else:
        notes.append("No ceiling plane was found: the ceiling height is not known.")

    vertical = [p for p in planes if p.kind == "vertical"]
    patches = [p for p in vertical if p.classification not in ("door", "window")]
    everything = [q for p in (floor_planes or patches or planes) for q in p.points]
    centre = (
        sum(q[0] for q in everything) / len(everything),
        sum(q[2] for q in everything) / len(everything),
    )
    walls = _join_walls(patches, centre)
    if not walls:
        notes.append("No wall plane was found: wall lengths and the floor size are not known.")
    # Around the room, in order of the direction each wall lies in from the middle.
    walls.sort(
        key=lambda w: math.atan2(
            w.at(sum(w.seen) / 2)[1] - centre[1], w.at(sum(w.seen) / 2)[0] - centre[0]
        )
    )

    n = len(walls)
    corners: list[tuple[float, float] | None] = [
        _corner(walls[i], walls[(i + 1) % n]) if n >= 2 and (n > 2 or i == 0) else None
        for i in range(n)
    ]
    ends: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for i, wall in enumerate(walls):
        before, after = corners[i - 1] if n > 1 else None, corners[i]
        low, high = wall.seen
        positions = sorted(
            [
                wall.along(before) if before else None,
                wall.along(after) if after else None,
            ],
            key=lambda v: (v is None, v),
        )
        known = [p for p in positions if p is not None]
        both = len(known) == 2 and abs(known[1] - known[0]) > 1e-6
        if both:
            start, end = known[0], known[1]
        elif len(known) == 1:
            # One corner: the wall runs from it to the far end of what was seen.
            start, end = sorted(
                (known[0], high if abs(high - known[0]) > abs(low - known[0]) else low)
            )
        else:
            start, end = low, high
        ends.append((wall.at(start), wall.at(end)))
        heights = [p[1] for p in wall.points]
        entry: dict[str, Any] = {
            "id": f"w{i + 1}",
            "start": _plan(wall.at(start)),
            "end": _plan(wall.at(end)),
            "length": dimension(end - start),
            # corner_to_corner: both neighbours were found, so this is the wall's
            # full length. seen: a lower bound, the stretch the phone saw.
            "basis": "corner_to_corner" if both else "seen",
            "seen_m": round(high - low, 3),
        }
        if floor_y is not None:
            entry["seen_height_m"] = round(max(heights) - floor_y, 3)
        result["walls"].append(entry)
    partial = [w["id"] for w in result["walls"] if w["basis"] == "seen"]
    if partial:
        notes.append(
            f"{', '.join(partial)}: a neighbouring wall was not found, so the length is only "
            "the stretch the phone saw (a lower bound)."
        )

    closed = n >= 3 and all(c is not None for c in corners)
    if closed:
        ring = [c for c in corners if c is not None]
        area = 0.5 * abs(
            sum(
                ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1]
                for i in range(n)
            )
        )
        floor: dict[str, Any] = {
            "basis": "corner_to_corner",
            "polygon": [_plan(c) for c in ring],
            "area_m2": round(area, 2),
        }
        if n == 4:
            lengths = [w["length"]["value_m"] for w in result["walls"]]
            sides = sorted(((lengths[0] + lengths[2]) / 2, (lengths[1] + lengths[3]) / 2))
            floor["width"] = dimension(sides[1])
            floor["depth"] = dimension(sides[0])
        result["floor"] = floor
    elif floor_planes:
        result["floor"] = {
            "basis": "seen",
            "area_m2": round(sum(p.area for p in floor_planes), 2),
        }
        notes.append(
            "The walls do not close into a room, so the floor size is only the floor the "
            "phone saw (a lower bound)."
        )

    doors = windows = 0
    for plane in vertical:
        if plane.classification not in ("door", "window"):
            continue
        length = math.hypot(plane.normal[0], plane.normal[2])
        if length < 0.5:
            continue
        normal = (plane.normal[0] / length, plane.normal[2] / length)
        best: tuple[float, int] | None = None
        for i, wall in enumerate(walls):
            angle = _angle_between(wall.normal, normal)
            angle = min(angle, 180 - angle)
            c = plane.centre
            gap = abs(wall.normal[0] * c[0] + wall.normal[1] * c[2] - wall.offset)
            near = angle <= OPENING_WALL_DEGREES and gap <= OPENING_WALL_OFFSET_M
            if near and (best is None or gap < best[0]):
                best = (gap, i)
        if plane.classification == "door":
            doors += 1
            name = f"d{doors}"
        else:
            windows += 1
            name = f"n{windows}"
        ys = [p[1] for p in plane.points]
        opening: dict[str, Any] = {
            "id": name,
            "kind": plane.classification,
            "wall_id": None,
            "height": dimension(max(ys) - min(ys)),
        }
        if best is None:
            # Without a wall, the width is the longest side of the outline's footprint.
            xs = [p[0] for p in plane.points]
            zs = [p[2] for p in plane.points]
            opening["width"] = dimension(math.hypot(max(xs) - min(xs), max(zs) - min(zs)))
        else:
            wall = walls[best[1]]
            spans = [wall.along(p) for p in plane.points]
            low, high = min(spans), max(spans)
            opening["wall_id"] = f"w{best[1] + 1}"
            opening["width"] = dimension(high - low)
            if result["walls"][best[1]]["basis"] == "corner_to_corner":
                start, end = sorted(wall.along(e) for e in ends[best[1]])
                # From the nearest corner to the opening's nearest edge, as the tape sheet has it.
                opening["offset"] = dimension(max(0.0, min(low - start, end - high)))
        if floor_y is not None and plane.classification == "window":
            opening["sill_height"] = dimension(max(0.0, min(ys) - floor_y))
        result["openings"].append(opening)
    if not result["openings"]:
        classed = any(p.classification != "none" for p in planes)
        notes.append(
            "The phone classed no plane as a door or a window."
            if classed
            else "This phone's AR does not class planes, so doors and windows are not in "
            "its AR measurements."
        )
    return result
