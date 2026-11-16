"""Poses and gravity-aligned (upright) 3D boxes in plain Python.

Conventions: cameras are OpenCV (x right, y down, z forward) and poses are
camera-to-world 4x4 matrices stored as nested lists. Boxes are upright: one
axis is the world up axis and the box may only rotate about it (yaw).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]
Mat3 = tuple[Vec3, Vec3, Vec3]
Mat4 = list[list[float]]


def rodrigues(axis_angle: Sequence[float]) -> Mat3:
    """Rotation matrix from an axis-angle vector (radians)."""
    rx, ry, rz = (float(v) for v in axis_angle)
    theta = math.sqrt(rx * rx + ry * ry + rz * rz)
    if theta < 1e-12:
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    x, y, z = rx / theta, ry / theta, rz / theta
    c, s = math.cos(theta), math.sin(theta)
    t = 1.0 - c
    return (
        (t * x * x + c, t * x * y - s * z, t * x * z + s * y),
        (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
        (t * x * z - s * y, t * y * z + s * x, t * z * z + c),
    )


def rigid(rotation: Mat3, translation: Sequence[float]) -> Mat4:
    return [
        [rotation[0][0], rotation[0][1], rotation[0][2], float(translation[0])],
        [rotation[1][0], rotation[1][1], rotation[1][2], float(translation[1])],
        [rotation[2][0], rotation[2][1], rotation[2][2], float(translation[2])],
        [0.0, 0.0, 0.0, 1.0],
    ]


def invert_rigid(m: Mat4) -> Mat4:
    """Inverse of a rotation plus translation matrix."""
    rt = ((m[0][0], m[1][0], m[2][0]), (m[0][1], m[1][1], m[2][1]), (m[0][2], m[1][2], m[2][2]))
    t = (m[0][3], m[1][3], m[2][3])
    nt = tuple(-(rt[i][0] * t[0] + rt[i][1] * t[1] + rt[i][2] * t[2]) for i in range(3))
    return rigid(rt, nt)


def transform_point(m: Mat4, p: Sequence[float]) -> Vec3:
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    return (
        m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
        m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
        m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3],
    )


def parse_arkit_traj_line(line: str) -> tuple[float, Mat4]:
    """Parse one ARKitScenes `.traj` line into (timestamp, camera-to-world).

    The file stores world-to-camera as axis-angle rotation plus translation; the
    dataset's own loader inverts it to get camera-to-world.
    """
    tokens = line.split()
    if len(tokens) != 7:
        raise ValueError(f"expected 7 fields, got {len(tokens)}")
    ts = float(tokens[0])
    world_to_cam = rigid(
        rodrigues([float(v) for v in tokens[1:4]]), [float(v) for v in tokens[4:7]]
    )
    return ts, invert_rigid(world_to_cam)


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


def box_from_obb(
    center: Sequence[float],
    axes_columns: Sequence[Sequence[float]],
    lengths: Sequence[float],
    up_axis: int,
) -> UprightBox:
    """Upright box from an oriented box given as rotation columns and full lengths.

    The box axis most aligned with up becomes the height; the yaw comes from the
    remaining axis with the largest horizontal component.
    """
    if len(axes_columns) != 3 or len(lengths) != 3:
        raise ValueError("need three axes and three lengths")
    up_scores = [abs(float(axes_columns[i][up_axis])) for i in range(3)]
    k_up = max(range(3), key=lambda i: up_scores[i])
    a, b = horizontal_axes(up_axis)
    others = [i for i in range(3) if i != k_up]
    k_len = max(others, key=lambda i: math.hypot(axes_columns[i][a], axes_columns[i][b]))
    k_wid = others[0] if others[1] == k_len else others[1]
    yaw = math.atan2(float(axes_columns[k_len][b]), float(axes_columns[k_len][a]))
    return _make_box(
        float(center[a]),
        float(center[b]),
        float(center[up_axis]),
        float(lengths[k_len]),
        float(lengths[k_wid]),
        float(lengths[k_up]),
        yaw,
        up_axis,
    )


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


def polygon_area(poly: Sequence[Vec2]) -> float:
    n = len(poly)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def clip_convex(subject: Sequence[Vec2], clip: Sequence[Vec2]) -> list[Vec2]:
    """Sutherland-Hodgman clip of `subject` by a counter-clockwise convex `clip`."""
    output = list(subject)
    for i in range(len(clip)):
        if not output:
            break
        c0, c1 = clip[i], clip[(i + 1) % len(clip)]
        inp, output = output, []
        for j in range(len(inp)):
            cur, prev = inp[j], inp[j - 1]
            cur_in = _cross(c0, c1, cur) >= 0
            prev_in = _cross(c0, c1, prev) >= 0
            if cur_in != prev_in:
                dx, dy = cur[0] - prev[0], cur[1] - prev[1]
                ex, ey = c1[0] - c0[0], c1[1] - c0[1]
                denom = dx * ey - dy * ex
                if abs(denom) > 1e-15:
                    t = ((c0[0] - prev[0]) * ey - (c0[1] - prev[1]) * ex) / denom
                    output.append((prev[0] + t * dx, prev[1] + t * dy))
            if cur_in:
                output.append(cur)
    return output


def iou_3d(p: UprightBox, q: UprightBox) -> float:
    """Volume intersection over union of two upright boxes."""
    if p.up_axis != q.up_axis:
        raise ValueError("boxes use different up axes")
    p0, p1 = p.vertical_range()
    q0, q1 = q.vertical_range()
    dz = min(p1, q1) - max(p0, q0)
    if dz <= 0:
        return 0.0
    inter = polygon_area(clip_convex(p.footprint(), q.footprint())) * dz
    union = p.volume() + q.volume() - inter
    return inter / union if union > 0 else 0.0


def center_distance(p: UprightBox, q: UprightBox) -> float:
    return math.dist(p.center, q.center)
