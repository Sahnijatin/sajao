"""The twin's space frame and room shell, fitted by code to depth points.

The AR world is metric and gravity aligned with y up. The space frame
(packages/schemas: SpaceTwin) has z up from the floor and x, y on the floor.
This module turns the AR world into it, square to the room's walls with the
floor's corner at the origin, and fits a first shell: the floor rectangle, four
walls and the ceiling height, each length an estimated Dimension with an error
band. Doors, windows, fixtures and textures come from the shell task.
"""

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from sajao_workers.twin.geometry import min_area_rect

DepthSource = Literal["lidar", "image"]
# (floor in metres, fraction of the length). Room-scale LiDAR and AR scale are good
# to a few centimetres; image depth is looser. Provisional until the golden set.
SHELL_BANDS: dict[DepthSource, tuple[float, float]] = {
    "lidar": (0.03, 0.02),
    "image": (0.06, 0.05),
}
# AR world (x, y up, z) to a z-up frame (x, -z, y): right-handed.
AR_TO_Z_UP = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
WALL_COVERAGE_FOR_WHOLE_ROOM = 0.5
# With `unseen_open`, an edge with less of its length seen than this is marked open: a
# stretch the photo did not show, passable and never a surface to place against.
WALL_COVERAGE_FOR_WALL = 0.3


def shell_dimension(value_m: float, depth_source: DepthSource) -> dict[str, Any]:
    floor, fraction = SHELL_BANDS[depth_source]
    return {
        "value_m": round(value_m, 3),
        "source": "estimated",
        "error_band_m": round(max(floor, fraction * value_m), 3),
    }


@dataclass(frozen=True)
class Space:
    rotation: np.ndarray  # 3x3, AR world to space frame
    origin: np.ndarray  # the space origin, in the turned (not yet shifted) frame
    turn_deg: float  # how far the room was turned about z to square it to the axes
    shell: dict[str, Any]
    extent: Literal["whole_room", "part"]

    def point(self, p: Any) -> tuple[float, float, float]:
        q = self.rotation @ np.asarray(p, dtype=np.float64) - self.origin
        return (float(q[0]), float(q[1]), float(q[2]))

    def direction(self, v: Any) -> np.ndarray:
        result: np.ndarray = self.rotation @ np.asarray(v, dtype=np.float64)
        return result

    def yaw_deg(self, ar_yaw_deg: float) -> float:
        """A box yaw about the AR up axis (from AR +x toward +z), in the space frame."""
        a = math.radians(ar_yaw_deg)
        d = self.direction([math.cos(a), 0.0, math.sin(a)])
        return math.degrees(math.atan2(d[1], d[0])) % 180.0

    def bearing_of_ar_minus_z(self) -> float:
        """Where the AR world's -Z points in the space frame, clockwise from +y, degrees."""
        d = self.direction([0.0, 0.0, -1.0])
        return math.degrees(math.atan2(d[0], d[1])) % 360.0

    def north_deg(self, ar_minus_z_heading_deg: float) -> float:
        """Compass bearing of the space frame's +y, from the bearing of AR -Z."""
        return (ar_minus_z_heading_deg - self.bearing_of_ar_minus_z()) % 360.0


def _turn(deg: float) -> np.ndarray:
    t = math.radians(deg)
    return np.array(
        [[math.cos(t), -math.sin(t), 0.0], [math.sin(t), math.cos(t), 0.0], [0, 0, 1.0]]
    )


def _wall_coverage(xy: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
    """Share of a wall's length with points within 15 cm of it, in 25 cm bins."""
    edge = end - start
    length = float(np.linalg.norm(edge))
    along = (xy - start) @ (edge / length)
    normal = np.array([-edge[1], edge[0]]) / length
    near = np.abs((xy - start) @ normal) < 0.15
    inside = near & (along >= 0) & (along <= length)
    bins = max(1, int(length / 0.25))
    hit = np.unique(np.minimum((along[inside] / length * bins).astype(int), bins - 1))
    return len(hit) / bins


def fit_space(
    points: np.ndarray,
    depth_source: DepthSource,
    mark_unseen: bool = False,
    stood_at: np.ndarray | None = None,
) -> Space:
    """Space frame and shell from depth points in the AR world (N, 3).

    `mark_unseen` (photos): edges the depth barely reaches, such as the side behind the
    camera, are marked unseen instead of claimed as walls (never called open: whether a
    wall stands there is not known). With more photos the depth of each is pooled, so a
    wall another photo covers is a wall again. `stood_at`: where
    the photo was taken from (AR world); the floor reaches at least there, because the
    person stood on it, even where the photo does not show it."""
    up = points @ AR_TO_Z_UP.T
    floor, ceiling = np.percentile(up[:, 2], [2.0, 98.0])
    band = up[(up[:, 2] > floor + 0.3) & (up[:, 2] < ceiling - 0.3)]
    xy = band[:, :2]
    centre = np.median(xy, axis=0)
    distance = np.linalg.norm(xy - centre, axis=1)
    core = xy[distance <= np.percentile(distance, 98.0)]
    step = max(1, len(core) // 5000)
    _, _, _, _, angle = min_area_rect([(float(x), float(y)) for x, y in core[::step]])
    turn_deg = -math.degrees(angle)
    rotation = _turn(turn_deg) @ AR_TO_Z_UP
    squared = band @ _turn(turn_deg).T
    x0, x1 = np.percentile(squared[:, 0], [1.0, 99.0])
    y0, y1 = np.percentile(squared[:, 1], [1.0, 99.0])
    if stood_at is not None:
        spots = np.atleast_2d(np.asarray(stood_at, dtype=np.float64))
        flat = spots @ AR_TO_Z_UP.T @ _turn(turn_deg).T
        x0, x1 = min(x0, float(flat[:, 0].min())), max(x1, float(flat[:, 0].max()))
        y0, y1 = min(y0, float(flat[:, 1].min())), max(y1, float(flat[:, 1].max()))
    origin = np.array([x0, y0, floor])
    length, width = float(x1 - x0), float(y1 - y0)

    corners = [(0.0, 0.0), (length, 0.0), (length, width), (0.0, width)]
    walls, coverage = [], []
    local = squared[:, :2] - origin[:2]
    for i in range(4):
        start, end = np.array(corners[i]), np.array(corners[(i + 1) % 4])
        walls.append(
            {
                "id": f"w{i + 1}",
                "start": {"x_m": round(corners[i][0], 3), "y_m": round(corners[i][1], 3)},
                "end": {
                    "x_m": round(corners[(i + 1) % 4][0], 3),
                    "y_m": round(corners[(i + 1) % 4][1], 3),
                },
                "length": shell_dimension(float(np.linalg.norm(end - start)), depth_source),
            }
        )
        coverage.append(_wall_coverage(local, start, end))
        if mark_unseen and coverage[-1] < WALL_COVERAGE_FOR_WALL:
            walls[-1]["kind"] = "unseen"
    shell = {
        "floor_polygon": [{"x_m": round(x, 3), "y_m": round(y, 3)} for x, y in corners],
        "walls": walls,
        "ceiling_height": shell_dimension(float(ceiling - floor), depth_source),
        "openings": [],
        "fixtures": [],
        "surfaces": [
            {"id": w["id"], "kind": "wall"} for w in walls if w.get("kind", "wall") == "wall"
        ]
        + [{"id": "floor", "kind": "floor"}, {"id": "ceiling", "kind": "ceiling"}],
    }
    whole = min(coverage) >= WALL_COVERAGE_FOR_WHOLE_ROOM
    return Space(rotation, origin, turn_deg, shell, "whole_room" if whole else "part")
