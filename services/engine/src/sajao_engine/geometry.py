"""Plane geometry on the floor, in metres, in the space frame.

Every footprint is a convex polygon (a rotated rectangle or a door-swing
sector), so overlap is the separating axis test. The floor itself may be any
simple polygon. Touching is not overlapping: two footprints overlap only when
they share area deeper than ``EPS``.

Pose convention for a footprint: ``rotation_deg`` turns counterclockwise from
the x axis. At rotation 0 the width runs along +x, the depth along +y, the back
faces -y and the front faces +y.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

EPS = 1e-6

Point = tuple[float, float]
Poly = tuple[Point, ...]


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def unit(deg: float) -> Point:
    rad = math.radians(deg)
    return (math.cos(rad), math.sin(rad))


@dataclass(frozen=True)
class Rect:
    """A rotated rectangle: center, width (local x), depth (local y), rotation."""

    cx: float
    cy: float
    width: float
    depth: float
    rotation_deg: float = 0.0

    @property
    def center(self) -> Point:
        return (self.cx, self.cy)

    @property
    def axis_x(self) -> Point:
        return unit(self.rotation_deg)

    @property
    def front(self) -> Point:
        """Unit vector the front faces."""
        return unit(self.rotation_deg + 90.0)

    def corners(self) -> Poly:
        ux, uy = self.axis_x
        fx, fy = self.front
        hw, hd = self.width / 2.0, self.depth / 2.0
        return (
            (self.cx - ux * hw - fx * hd, self.cy - uy * hw - fy * hd),  # back left
            (self.cx + ux * hw - fx * hd, self.cy + uy * hw - fy * hd),  # back right
            (self.cx + ux * hw + fx * hd, self.cy + uy * hw + fy * hd),  # front right
            (self.cx - ux * hw + fx * hd, self.cy - uy * hw + fy * hd),  # front left
        )

    def grown(self, margin: float) -> Rect:
        """The same rectangle with ``margin`` added on every side."""
        return Rect(
            self.cx, self.cy, self.width + 2 * margin, self.depth + 2 * margin, self.rotation_deg
        )

    def strip(self, side: str, depth: float, *, extend: float = 0.0) -> Rect:
        """A strip of ``depth`` outside one side: front, back, left or right."""
        fx, fy = self.front
        ux, uy = self.axis_x
        if side == "front":
            off = self.depth / 2.0 + depth / 2.0
            return Rect(
                self.cx + fx * off,
                self.cy + fy * off,
                self.width + 2 * extend,
                depth,
                self.rotation_deg,
            )
        if side == "back":
            off = self.depth / 2.0 + depth / 2.0
            return Rect(
                self.cx - fx * off,
                self.cy - fy * off,
                self.width + 2 * extend,
                depth,
                self.rotation_deg,
            )
        off = self.width / 2.0 + depth / 2.0
        sign = 1.0 if side == "right" else -1.0
        return Rect(
            self.cx + sign * ux * off,
            self.cy + sign * uy * off,
            depth,
            self.depth + 2 * extend,
            self.rotation_deg,
        )


def polygon_area(poly: Sequence[Point]) -> float:
    """Signed area: positive when the points run counterclockwise."""
    total = 0.0
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        total += a[0] * b[1] - b[0] * a[1]
    return total / 2.0


def ccw(poly: Sequence[Point]) -> Poly:
    """The polygon with its points counterclockwise."""
    pts = tuple(poly)
    return pts if polygon_area(pts) >= 0 else tuple(reversed(pts))


def edges(poly: Sequence[Point]) -> Iterable[tuple[Point, Point]]:
    for i, a in enumerate(poly):
        yield a, poly[(i + 1) % len(poly)]


def _axes(poly: Sequence[Point]) -> Iterable[Point]:
    for a, b in edges(poly):
        ex, ey = _sub(b, a)
        length = math.hypot(ex, ey)
        if length > EPS:
            yield (-ey / length, ex / length)


def _project(poly: Sequence[Point], axis: Point) -> tuple[float, float]:
    values = [_dot(p, axis) for p in poly]
    return min(values), max(values)


def penetration(a: Sequence[Point], b: Sequence[Point]) -> float:
    """Smallest overlap depth of two convex polygons along any separating axis; 0 if apart."""
    depth = math.inf
    for axis in (*_axes(a), *_axes(b)):
        a0, a1 = _project(a, axis)
        b0, b1 = _project(b, axis)
        overlap = min(a1, b1) - max(a0, b0)
        if overlap <= 0:
            return 0.0
        depth = min(depth, overlap)
    return 0.0 if depth is math.inf else depth


def overlaps(a: Sequence[Point], b: Sequence[Point], eps: float = EPS) -> bool:
    """True when two convex polygons share area deeper than ``eps``."""
    return penetration(a, b) > eps


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    ab = _sub(b, a)
    length2 = _dot(ab, ab)
    if length2 <= EPS * EPS:
        return math.dist(p, a)
    t = max(0.0, min(1.0, _dot(_sub(p, a), ab) / length2))
    return math.dist(p, (a[0] + ab[0] * t, a[1] + ab[1] * t))


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Proper or touching intersection of two closed segments."""
    d1 = _cross(_sub(b, a), _sub(c, a))
    d2 = _cross(_sub(b, a), _sub(d, a))
    d3 = _cross(_sub(d, c), _sub(a, c))
    d4 = _cross(_sub(d, c), _sub(b, c))
    if ((d1 > EPS and d2 < -EPS) or (d1 < -EPS and d2 > EPS)) and (
        (d3 > EPS and d4 < -EPS) or (d3 < -EPS and d4 > EPS)
    ):
        return True
    return (
        (abs(d1) <= EPS and point_segment_distance(c, a, b) <= EPS)
        or (abs(d2) <= EPS and point_segment_distance(d, a, b) <= EPS)
        or (abs(d3) <= EPS and point_segment_distance(a, c, d) <= EPS)
        or (abs(d4) <= EPS and point_segment_distance(b, c, d) <= EPS)
    )


def segment_distance(a: Point, b: Point, c: Point, d: Point) -> float:
    if segments_intersect(a, b, c, d):
        return 0.0
    return min(
        point_segment_distance(a, c, d),
        point_segment_distance(b, c, d),
        point_segment_distance(c, a, b),
        point_segment_distance(d, a, b),
    )


def point_in_polygon(p: Point, poly: Sequence[Point]) -> bool:
    """Even-odd rule; points on the boundary count as inside."""
    for a, b in edges(poly):
        if point_segment_distance(p, a, b) <= EPS:
            return True
    inside = False
    x, y = p
    for a, b in edges(poly):
        if (a[1] > y) != (b[1] > y):
            xi = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if xi > x:
                inside = not inside
    return inside


def point_polygon_distance(p: Point, poly: Sequence[Point]) -> float:
    """0 inside a convex or simple polygon, else the distance to its boundary."""
    if point_in_polygon(p, poly):
        return 0.0
    return min(point_segment_distance(p, a, b) for a, b in edges(poly))


def polygon_distance(a: Sequence[Point], b: Sequence[Point]) -> float:
    """Gap between two convex polygons; 0 when they touch or overlap."""
    if penetration(a, b) > 0:
        return 0.0
    return min(segment_distance(p, q, r, s) for p, q in edges(a) for r, s in edges(b))


def polygon_inside(inner: Sequence[Point], outer: Sequence[Point]) -> bool:
    """True when the convex polygon ``inner`` lies inside the simple polygon ``outer``.

    Every vertex of ``inner`` is inside ``outer`` and no edge of ``outer`` passes
    through the interior of ``inner``. Touching the boundary is allowed.
    """
    if not all(point_in_polygon(p, outer) for p in inner):
        return False
    for a, b in edges(outer):
        # A reflex corner of the floor poking into the footprint.
        if _strictly_inside(a, inner):
            return False
        for c, d in edges(inner):
            if _proper_cross(a, b, c, d):
                return False
    # A floor edge running exactly through two corners leaves one side outside;
    # points just inside each corner catch it.
    gx = sum(p[0] for p in inner) / len(inner)
    gy = sum(p[1] for p in inner) / len(inner)
    probes = [(p[0] + (gx - p[0]) * 1e-3, p[1] + (gy - p[1]) * 1e-3) for p in inner]
    return all(point_in_polygon(p, outer) for p in probes)


def _strictly_inside(p: Point, convex: Sequence[Point]) -> bool:
    pts = ccw(convex)
    return all(_cross(_sub(b, a), _sub(p, a)) > EPS for a, b in edges(pts))


def _proper_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    d1 = _cross(_sub(b, a), _sub(c, a))
    d2 = _cross(_sub(b, a), _sub(d, a))
    d3 = _cross(_sub(d, c), _sub(a, c))
    d4 = _cross(_sub(d, c), _sub(b, c))
    return ((d1 > EPS and d2 < -EPS) or (d1 < -EPS and d2 > EPS)) and (
        (d3 > EPS and d4 < -EPS) or (d3 < -EPS and d4 > EPS)
    )


def sector(apex: Point, radius: float, start_deg: float, sweep_deg: float, steps: int = 8) -> Poly:
    """A convex polygon covering a circular sector (sweep up to 90 degrees).

    The arc is approximated from outside: chords are pushed out so that the
    polygon contains the true sector, which is the safe side for a door swing.
    """
    step = sweep_deg / steps
    outer = radius / math.cos(math.radians(abs(step) / 2.0))
    pts: list[Point] = [apex]
    pts.append((apex[0] + radius * unit(start_deg)[0], apex[1] + radius * unit(start_deg)[1]))
    for i in range(steps):
        mid = start_deg + step * (i + 0.5)
        pts.append((apex[0] + outer * unit(mid)[0], apex[1] + outer * unit(mid)[1]))
    end = start_deg + sweep_deg
    pts.append((apex[0] + radius * unit(end)[0], apex[1] + radius * unit(end)[1]))
    return ccw(pts)


def normalise_deg(deg: float) -> float:
    """An angle in [0, 360), as the schema's AngleDeg requires."""
    value = deg % 360.0
    return 0.0 if abs(value - 360.0) < 1e-9 else value


def clip_convex(subject: list[Point], clip: list[Point]) -> list[Point]:
    """Sutherland-Hodgman: `subject` clipped to the convex, counterclockwise `clip`."""

    def inside(p: Point, a: Point, b: Point) -> bool:
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-9

    def cut(p: Point, q: Point, a: Point, b: Point) -> Point:
        dx, dy = q[0] - p[0], q[1] - p[1]
        ex, ey = b[0] - a[0], b[1] - a[1]
        den = dx * ey - dy * ex
        t = ((a[0] - p[0]) * ey - (a[1] - p[1]) * ex) / den if abs(den) > 1e-12 else 0.0
        return (p[0] + t * dx, p[1] + t * dy)

    out = subject
    for i, a in enumerate(clip):
        b = clip[(i + 1) % len(clip)]
        if not out:
            break
        points, out = out, []
        for j, p in enumerate(points):
            q = points[(j + 1) % len(points)]
            if inside(q, a, b):
                if not inside(p, a, b):
                    out.append(cut(p, q, a, b))
                out.append(q)
            elif inside(p, a, b):
                out.append(cut(p, q, a, b))
    return out
