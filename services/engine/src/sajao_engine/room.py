"""The measured room as the engine sees it: floor, walls, openings, fixtures, what stays.

Built from a ``SpaceTwin`` by code. Every zone that must stay clear is grown by
the error bands of the numbers behind it, so the band is margin, never slack.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from sajao_engine.geometry import (
    Point,
    Poly,
    Rect,
    ccw,
    normalise_deg,
    point_in_polygon,
    point_segment_distance,
    sector,
)
from sajao_schemas.generated.v1 import Dimension, Fixture, SpaceTwin
from sajao_schemas.generated.v1 import Opening as SchemaOpening

# Clear zone depths, in metres. Hard rules: never relaxed.
DOOR_APPROACH_DEPTH_M = 0.60
WINDOW_ACCESS_DEPTH_M = 0.50
SWITCHBOARD_ZONE_DEPTH_M = 0.50
SWITCHBOARD_ZONE_WIDTH_M = 0.30
SWITCHBOARD_REACH_BELOW_M = 0.20
AC_ZONE_DEPTH_M = 1.00
AC_ZONE_WIDTH_M = 1.00
AC_AIRFLOW_BELOW_M = 0.30
# Two wall ends closer than this meet at a corner.
CORNER_JOIN_M = 0.05
# A wall this close to a floor edge runs along it.
ON_EDGE_M = 0.10
# A stretch of floor edge with no wall along it is open when at least this long.
OPEN_MIN_M = 0.30
# Narrower open stretches cannot be walked through at the 60 cm minimum.
PASSABLE_M = 0.60

# How the room's sizes were obtained. Fit claims ("fits with 12 cm to spare") are
# made only for taped and AR-measured rooms; estimated rooms are still verified
# with their bands as margin, but the design never claims a fit.
Confidence = Literal["taped", "ar_measured", "estimated"]
FIT_CLAIM_LEVELS: tuple[Confidence, ...] = ("taped", "ar_measured")


def low(d: Dimension) -> float:
    """The smallest the true value is expected to be."""
    return max(0.0, d.value_m - d.error_band_m)


def high(d: Dimension) -> float:
    """The largest the true value is expected to be."""
    return d.value_m + d.error_band_m


@dataclass(frozen=True)
class WallLine:
    id: str
    a: Point
    b: Point
    # Unit normal pointing into the room.
    inward: Point
    # How far the wall itself may sit from where it was drawn.
    margin_m: float

    @property
    def length(self) -> float:
        return math.dist(self.a, self.b)

    @property
    def direction(self) -> Point:
        length = self.length or 1.0
        return ((self.b[0] - self.a[0]) / length, (self.b[1] - self.a[1]) / length)

    @property
    def facing_deg(self) -> float:
        """Rotation that makes a footprint's front face into the room from this wall."""
        return normalise_deg(math.degrees(math.atan2(self.inward[1], self.inward[0])) - 90.0)

    def at(self, s: float) -> Point:
        dx, dy = self.direction
        return (self.a[0] + dx * s, self.a[1] + dy * s)


@dataclass(frozen=True)
class OpenEdge:
    """A stretch of the floor's edge with no wall: the area runs on into the next one.

    Nothing is placed against it as if it were a wall, and people walk through it.
    Items still stay inside the area, by the edge's margin.
    """

    a: Point
    b: Point
    inward: Point
    margin_m: float

    @property
    def length(self) -> float:
        return math.dist(self.a, self.b)

    @property
    def passable(self) -> bool:
        return self.length >= PASSABLE_M

    def approach(self) -> Rect:
        """The strip inside the edge where a person steps in from the next area."""
        mid = ((self.a[0] + self.b[0]) / 2.0, (self.a[1] + self.b[1]) / 2.0)
        depth = DOOR_APPROACH_DEPTH_M
        facing = normalise_deg(math.degrees(math.atan2(self.inward[1], self.inward[0])) - 90.0)
        off = self.margin_m + depth / 2.0
        return Rect(
            mid[0] + self.inward[0] * off, mid[1] + self.inward[1] * off, self.length, depth, facing
        )


@dataclass(frozen=True)
class Opening:
    id: str
    kind: Literal["door", "window"]
    wall_id: str
    # Distance along the wall, widened by the bands.
    s0: float
    s1: float
    # Zones inside the room that must stay clear.
    swing: Poly | None
    approach: Rect
    # Items taller than this may not stand in ``approach`` (windows only).
    clear_above_m: float


@dataclass(frozen=True)
class FixtureZone:
    id: str
    kind: str
    wall_id: str
    zone: Rect
    # Items taller than this may not stand in the zone.
    clear_above_m: float


@dataclass(frozen=True)
class Obstacle:
    """Something already in the room that stays: a kept item or a built-in."""

    id: str
    label: str
    category: str
    footprint: Rect
    height_m: float
    mount: Literal["floor", "rug"]
    # A built-in is part of the shell; nobody needs to reach it from the design.
    built_in: bool = False


@dataclass(frozen=True)
class Room:
    floor: Poly
    walls: tuple[WallLine, ...]
    openings: tuple[Opening, ...]
    fixtures: tuple[FixtureZone, ...]
    obstacles: tuple[Obstacle, ...]
    ceiling_m: float
    # New items go only inside this area when the user chose "just a part".
    redo: Poly | None = None
    # On a photo-first room, the floor the photo shows: a new item's centre must be on it,
    # so the render shows what the list sells (sajao_engine.photo.visible_floor).
    in_view: Poly | None = None
    wall_by_id: dict[str, WallLine] = field(default_factory=dict, compare=False)
    open_edges: tuple[OpenEdge, ...] = ()
    confidence: Confidence = "estimated"

    @property
    def fit_claims(self) -> bool:
        """Whether the design may say an item fits, and by how much."""
        return self.confidence in FIT_CLAIM_LEVELS

    @property
    def entrances(self) -> tuple[Rect, ...]:
        """Where people come in: every door and every open edge wide enough to walk through."""
        return tuple(d.approach for d in self.doors) + tuple(
            e.approach() for e in self.open_edges if e.passable
        )

    @property
    def doors(self) -> tuple[Opening, ...]:
        return tuple(o for o in self.openings if o.kind == "door")

    @property
    def windows(self) -> tuple[Opening, ...]:
        return tuple(o for o in self.openings if o.kind == "window")

    @property
    def area_m2(self) -> float:
        from sajao_engine.geometry import polygon_area

        return abs(polygon_area(self.floor))


def _inward(a: Point, b: Point, floor: Poly) -> Point:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    n = (-dy / length, dx / length)
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    probe = (mid[0] + n[0] * 0.05, mid[1] + n[1] * 0.05)
    return n if point_in_polygon(probe, floor) else (-n[0], -n[1])


def _wall_lines(twin: SpaceTwin, floor: Poly) -> tuple[WallLine, ...]:
    # An edge marked open (a doorway, the way on, or a stretch not seen) is no wall:
    # it becomes an open edge, passable and never a surface to place against.
    raw = [
        (w.id, (w.start.x_m, w.start.y_m), (w.end.x_m, w.end.y_m), w.length.error_band_m)
        for w in twin.shell.walls
    ]
    solid = {w.id for w in twin.shell.walls if w.kind != "open"}
    lines = []
    for wid, a, b, band in raw:
        if wid not in solid:
            continue
        # A wall's position is fixed by the lengths of the walls that meet it.
        neighbours = [
            nb
            for nid, na, nbb, nb in raw
            if nid != wid
            and min(math.dist(p, q) for p in (a, b) for q in (na, nbb)) <= CORNER_JOIN_M
        ]
        margin = max(neighbours) if neighbours else band
        lines.append(WallLine(wid, a, b, _inward(a, b, floor), margin))
    return tuple(lines)


def _open_edges(floor: Poly, walls: Sequence[WallLine]) -> tuple[OpenEdge, ...]:
    """Stretches of the floor's edge that no wall runs along."""
    out = []
    widest = max((w.margin_m for w in walls), default=0.0)
    for i, a in enumerate(floor):
        b = floor[(i + 1) % len(floor)]
        length = math.dist(a, b)
        if length < OPEN_MIN_M:
            continue
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        covered: list[tuple[float, float]] = []
        for w in walls:
            if (
                point_segment_distance(w.a, a, b) > ON_EDGE_M
                or point_segment_distance(w.b, a, b) > ON_EDGE_M
            ):
                continue
            s0 = (w.a[0] - a[0]) * ux + (w.a[1] - a[1]) * uy
            s1 = (w.b[0] - a[0]) * ux + (w.b[1] - a[1]) * uy
            covered.append((max(0.0, min(s0, s1)), min(length, max(s0, s1))))
        covered.sort()
        gaps = []
        at = 0.0
        for s0, s1 in covered:
            if s0 - at >= OPEN_MIN_M:
                gaps.append((at, s0))
            at = max(at, s1)
        if length - at >= OPEN_MIN_M:
            gaps.append((at, length))
        for g0, g1 in gaps:
            p = (a[0] + ux * g0, a[1] + uy * g0)
            q = (a[0] + ux * g1, a[1] + uy * g1)
            near = [
                w.margin_m
                for w in walls
                if min(math.dist(e, x) for e in (p, q) for x in (w.a, w.b))
                <= ON_EDGE_M + CORNER_JOIN_M
            ]
            out.append(OpenEdge(p, q, _inward(p, q, floor), max(near) if near else widest))
    return tuple(out)


def confidence_of(twin: SpaceTwin) -> Confidence:
    """The room's measurement level: the twin's own level when the pipeline set it.

    Older twins carry no level; for those a room counts as taped only when every wall
    and the ceiling are measured, and as estimated otherwise.
    """
    if twin.confidence is not None:
        return twin.confidence.level
    lengths = [w.length for w in twin.shell.walls] + [twin.shell.ceiling_height]
    return "taped" if all(d.source == "measured" for d in lengths) else "estimated"


def _opening(o: SchemaOpening, wall: WallLine) -> Opening:
    slack = o.offset.error_band_m + o.width.error_band_m
    s0 = max(0.0, o.offset.value_m - slack)
    s1 = min(wall.length, o.offset.value_m + o.width.value_m + slack)
    width = high(o.width)
    kind: Literal["door", "window"] = "door" if o.kind == "door" else "window"
    depth = DOOR_APPROACH_DEPTH_M if kind == "door" else WINDOW_ACCESS_DEPTH_M
    mid = wall.at((s0 + s1) / 2.0)
    approach = Rect(
        mid[0] + wall.inward[0] * (wall.margin_m + depth / 2.0),
        mid[1] + wall.inward[1] * (wall.margin_m + depth / 2.0),
        s1 - s0,
        depth + 2 * wall.margin_m,
        wall.facing_deg,
    )
    swing: Poly | None = None
    if kind == "door" and o.swing is not None and o.swing.opens == "inward":
        hinge_at_start = o.swing.hinge == "start"
        hinge_s = s0 if hinge_at_start else s1
        apex = wall.at(hinge_s)
        towards = wall.direction if hinge_at_start else (-wall.direction[0], -wall.direction[1])
        start_deg = math.degrees(math.atan2(towards[1], towards[0]))
        into_deg = math.degrees(math.atan2(wall.inward[1], wall.inward[0]))
        sweep = ((into_deg - start_deg + 180.0) % 360.0) - 180.0
        swing = sector(apex, width + (s1 - s0 - o.width.value_m) / 2.0, start_deg, sweep)
    clear_above = 0.0
    if kind == "window":
        clear_above = low(o.sill_height) - 0.02 if o.sill_height is not None else 0.0
    return Opening(o.id, kind, wall.id, s0, s1, swing, approach, max(0.0, clear_above))


def _fixture(f: Fixture, wall: WallLine) -> FixtureZone | None:
    kind = f.kind
    if kind == "socket":
        return None  # Sockets sit low and are normally behind furniture.
    width = (
        high(f.width)
        if f.width is not None
        else (SWITCHBOARD_ZONE_WIDTH_M if kind == "switchboard" else AC_ZONE_WIDTH_M)
    )
    pad = f.offset.error_band_m
    depth = SWITCHBOARD_ZONE_DEPTH_M if kind == "switchboard" else AC_ZONE_DEPTH_M
    below = SWITCHBOARD_REACH_BELOW_M if kind == "switchboard" else AC_AIRFLOW_BELOW_M
    mid = wall.at(f.offset.value_m + width / 2.0)
    zone = Rect(
        mid[0] + wall.inward[0] * (wall.margin_m + depth / 2.0),
        mid[1] + wall.inward[1] * (wall.margin_m + depth / 2.0),
        width + 2 * pad,
        depth + 2 * wall.margin_m,
        wall.facing_deg,
    )
    return FixtureZone(f.id, kind, wall.id, zone, max(0.0, low(f.mount_height) - below))


@dataclass(frozen=True)
class ObjectOverride:
    """A kept object moved, turned or swapped for a product of another size by a twin edit."""

    x_m: float | None = None
    y_m: float | None = None
    yaw_deg: float | None = None
    size: tuple[Dimension, Dimension, Dimension] | None = None


def _obstacles(
    twin: SpaceTwin, removed: set[str], overrides: Mapping[str, ObjectOverride]
) -> tuple[Obstacle, ...]:
    out: list[Obstacle] = []
    for b in twin.shell.built_ins or []:
        box = b.box
        out.append(
            Obstacle(
                b.id,
                b.label,
                b.category,
                Rect(box.center.x_m, box.center.y_m, high(box.width), high(box.depth), box.yaw_deg),
                high(box.height),
                "floor",
                built_in=True,
            )
        )
    for o in twin.objects:
        if o.id in removed:
            continue
        kind = o.object_type if o.object_type is not None else "furniture"
        if kind in ("wall_item", "decor"):
            continue
        if o.footprint is not None and not o.footprint.on_floor:
            continue  # a ceiling light or a wall-mounted TV takes no floor
        box = o.box
        ov = overrides.get(o.id, ObjectOverride())
        width, depth, height = ov.size or (box.width, box.depth, box.height)
        rug = kind == "textile" and high(height) <= 0.05
        out.append(
            Obstacle(
                o.id,
                o.label,
                o.category,
                Rect(
                    box.center.x_m if ov.x_m is None else ov.x_m,
                    box.center.y_m if ov.y_m is None else ov.y_m,
                    high(width),
                    high(depth),
                    box.yaw_deg if ov.yaw_deg is None else ov.yaw_deg,
                ),
                high(height),
                "rug" if rug else "floor",
            )
        )
    return tuple(out)


# Estimated rooms (a depth model's guess) are placed at nominal sizes: a band of 13 to
# 17% as margin would eat a third of a small room for a number that is a guess either
# way. Each wall keeps this fixed clearance instead (just over the verifier's 5 cm
# tight-spot strip, so a piece against a wall is not a tight spot by construction), and
# no fit is claimed (Decision,
# 19 Nov, amending engineering rule 5). Measured and taped rooms keep the full band.
ESTIMATED_CLEARANCE_M = 0.06


def _nominal(twin: SpaceTwin) -> SpaceTwin:
    """The twin with every measured length at its value and no error band."""

    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            if {"value_m", "error_band_m", "source"} <= node.keys():
                return {**node, "error_band_m": 0.0}
            return {k: strip(v) for k, v in node.items()}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    data = twin.model_dump(mode="json", exclude_unset=True)
    for key in ("shell", "objects"):
        data[key] = strip(data[key])
    return SpaceTwin.model_validate(data)


def room_from_twin(
    twin: SpaceTwin,
    *,
    removed: Sequence[str] = (),
    overrides: Mapping[str, ObjectOverride] | None = None,
    redo: Sequence[Point] | None = None,
    confidence: Confidence | None = None,
    in_view: Sequence[Point] | None = None,
) -> Room:
    """The room with every twin object kept except those in ``removed``. An estimated
    room is taken at nominal sizes, each wall with a fixed clearance (see _nominal)."""
    level = confidence or confidence_of(twin)
    if level == "estimated":
        twin = _nominal(twin)
    floor = ccw([(p.x_m, p.y_m) for p in twin.shell.floor_polygon])
    walls = _wall_lines(twin, floor)
    if level == "estimated":
        walls = tuple(replace(w, margin_m=ESTIMATED_CLEARANCE_M) for w in walls)
    by_id = {w.id: w for w in walls}
    openings = tuple(
        _opening(o, by_id[o.wall_id]) for o in twin.shell.openings if o.wall_id in by_id
    )
    fixtures = tuple(
        z
        for f in twin.shell.fixtures
        if f.wall_id in by_id
        for z in [_fixture(f, by_id[f.wall_id])]
        if z is not None
    )
    return Room(
        floor=floor,
        walls=walls,
        openings=openings,
        fixtures=fixtures,
        obstacles=_obstacles(twin, set(removed), overrides or {}),
        ceiling_m=low(twin.shell.ceiling_height),
        redo=ccw(list(redo)) if redo else None,
        in_view=ccw(list(in_view)) if in_view else None,
        wall_by_id=by_id,
        open_edges=_open_edges(floor, walls),
        confidence=level,
    )
