"""Gravity-aligned (upright) 3D boxes in plain Python.

Ported from the SJ-116 spike (services/spikes/twin-risk), where it was tested
against ARKitScenes boxes. Boxes are upright: one axis is the world up axis and
the box may only turn about it (yaw). Code fits every box; no model sets a size.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]


def horizontal_axes(up_axis: int) -> tuple[int, int]:
    if up_axis not in (0, 1, 2):
        raise ValueError("up_axis must be 0, 1 or 2")
    a, b = (i for i in range(3) if i != up_axis)
    return a, b


@dataclass(frozen=True)
class UprightBox:
    """Gravity-aligned box. `length` >= `width` are horizontal sizes in metres."""

    center: Vec3
    length: float
    width: float
    height: float
    yaw: float
    up_axis: int

    def footprint(self) -> list[Vec2]:
        """Four horizontal corners, counter-clockwise."""
        a, b = horizontal_axes(self.up_axis)
        cu, cv = self.center[a], self.center[b]
        du = (math.cos(self.yaw), math.sin(self.yaw))
        dv = (-du[1], du[0])
        hl, hw = self.length / 2.0, self.width / 2.0
        return [
            (cu + su * hl * du[0] + sv * hw * dv[0], cv + su * hl * du[1] + sv * hw * dv[1])
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))
        ]

    def vertical_range(self) -> tuple[float, float]:
        z = self.center[self.up_axis]
        return z - self.height / 2.0, z + self.height / 2.0

    def sorted_sizes(self) -> tuple[float, float, float]:
        return (self.length, self.width, self.height)

    def volume(self) -> float:
        return self.length * self.width * self.height


def _make_box(
    cu: float, cv: float, cz: float, ln: float, w: float, h: float, yaw: float, up: int
) -> UprightBox:
    if w > ln:
        ln, w = w, ln
        yaw += math.pi / 2.0
    yaw = math.atan2(math.sin(yaw), math.cos(yaw))
    if yaw < 0:  # a box is symmetric under a half turn
        yaw += math.pi
    if yaw >= math.pi:
        yaw -= math.pi
    a, b = horizontal_axes(up)
    center = [0.0, 0.0, 0.0]
    center[a], center[b], center[up] = cu, cv, cz
    return UprightBox((center[0], center[1], center[2]), ln, w, h, yaw, up)


def _cross(o: Vec2, p: Vec2, q: Vec2) -> float:
    return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])


def convex_hull(points: Sequence[Vec2]) -> list[Vec2]:
    """Counter-clockwise convex hull (monotone chain)."""
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) <= 2:
        return pts
    lower: list[Vec2] = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[Vec2] = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def min_area_rect(points: Sequence[Vec2]) -> tuple[float, float, float, float, float]:
    """Smallest enclosing rectangle: (cu, cv, length, width, yaw)."""
    hull = convex_hull(points)
    if not hull:
        raise ValueError("no points")
    if len(hull) == 1:
        return hull[0][0], hull[0][1], 0.0, 0.0, 0.0
    best: tuple[float, float, float, float, float] | None = None
    best_area = math.inf
    for i in range(len(hull)):
        p, q = hull[i], hull[(i + 1) % len(hull)]
        ang = math.atan2(q[1] - p[1], q[0] - p[0])
        c, s = math.cos(ang), math.sin(ang)
        us = [c * x + s * y for x, y in hull]
        vs = [-s * x + c * y for x, y in hull]
        u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
        area = (u1 - u0) * (v1 - v0)
        if area < best_area - 1e-12:
            best_area = area
            mu, mv = (u0 + u1) / 2.0, (v0 + v1) / 2.0
            best = (c * mu - s * mv, s * mu + c * mv, u1 - u0, v1 - v0, ang)
    if best is None:
        raise RuntimeError("degenerate hull")
    return best


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("empty")
    pos = q * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def fit_upright_box(
    points: Sequence[Sequence[float]], up_axis: int, trim: float = 0.02
) -> UprightBox:
    """Fit an upright box to a point set, trimming `trim` of outliers per axis."""
    if len(points) < 3:
        raise ValueError("need at least 3 points")
    a, b = horizontal_axes(up_axis)
    zs = sorted(float(p[up_axis]) for p in points)
    us = sorted(float(p[a]) for p in points)
    vs = sorted(float(p[b]) for p in points)
    z0, z1 = _quantile(zs, trim), _quantile(zs, 1.0 - trim)
    u0, u1 = _quantile(us, trim), _quantile(us, 1.0 - trim)
    v0, v1 = _quantile(vs, trim), _quantile(vs, 1.0 - trim)
    kept = [
        (float(p[a]), float(p[b]))
        for p in points
        if z0 <= p[up_axis] <= z1 and u0 <= p[a] <= u1 and v0 <= p[b] <= v1
    ]
    if len(kept) < 3:
        kept = [(float(p[a]), float(p[b])) for p in points]
    cu, cv, length, width, yaw = min_area_rect(kept)
    return _make_box(cu, cv, (z0 + z1) / 2.0, length, width, z1 - z0, yaw, up_axis)
