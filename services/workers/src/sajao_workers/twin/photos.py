"""The photos path, for phones without AR: a measured room from photos and one tape value.

A pose model gives each photo a camera and a depth map, in its own frame and
scale. These pure functions turn that into the frames manifest the twin steps
read, in an AR-like world (metres, y up):

- `metric_scale`: the pose model's scale against a metric depth model (MoGe-3);
- `level_rotation`: which way is up, from the cameras (photos are held about level);
- `tape_factor`: one tape value (a wall length) corrects the scale that is left.

The scale and the walls are only as good as those three, so the photos path
carries wider error bands than a scan (depth source "photos").
"""

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

# A tape value this far from every wall (as a ratio) is a wrong entry, not a correction.
MAX_TAPE_RATIO = 1.6


def metric_scale(
    model_depths: Sequence[np.ndarray], metric_depths: Sequence[np.ndarray], min_pixels: int = 500
) -> float:
    """Median over photos of the median ratio of metric depth to the pose model's depth."""
    ratios = []
    for model, metric in zip(model_depths, metric_depths, strict=True):
        ok = (model > 0.05) & (metric > 0.05)
        if ok.sum() >= min_pixels:
            ratios.append(float(np.median(metric[ok] / model[ok])))
    if not ratios:
        raise ValueError("no photo has both depths: the scale cannot be measured")
    return float(np.median(ratios))


def level_rotation(c2w: Sequence[np.ndarray]) -> np.ndarray:
    """Rotation that turns the cameras' average up (OpenCV: minus the y axis) into +y."""
    ups = np.array([-np.asarray(c)[:3, 1] for c in c2w], dtype=np.float64)
    a = ups.mean(axis=0)
    a /= np.linalg.norm(a)
    b = np.array([0.0, 1.0, 0.0])
    v, c = np.cross(a, b), float(a @ b)
    if c < -0.999:  # upside down: half a turn about x
        return np.diag([1.0, -1.0, -1.0])
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    rotation: np.ndarray = np.eye(3) + vx + vx @ vx / (1.0 + c)
    return rotation


def tape_factor(
    walls: Sequence[Mapping[str, Any]], tape: Sequence[Mapping[str, Any]]
) -> tuple[float, str | None]:
    """The scale correction from the first wall-length tape value, and the wall it matched.

    The wall it matches is the one nearest to it in length; a value further than
    `MAX_TAPE_RATIO` from every wall is refused as a wrong entry."""
    value = next((t["value_m"] for t in tape if t["target"] == "wall_length"), None)
    if value is None or not walls:
        return 1.0, None
    best = min(walls, key=lambda w: abs(w["length"]["value_m"] - value))
    ratio = value / best["length"]["value_m"]
    if not 1 / MAX_TAPE_RATIO <= ratio <= MAX_TAPE_RATIO:
        raise ValueError(f"the tape value {value} m matches no wall")
    return float(ratio), str(best["id"])


# The floor may correct the cameras' up by at most this; more is a different surface.
MAX_UP_CORRECTION_DEG = 25.0
# Points within this of the floor plane are on it.
FLOOR_TOLERANCE_M = 0.03
# Fewer points than this, or a floor plane holding less than this share of the
# lowest points, give no correction.
MIN_FLOOR_POINTS = 500
MIN_FLOOR_SHARE = 0.3
FLOOR_TRIES = 300


def floor_normal(points: np.ndarray, up: np.ndarray) -> np.ndarray | None:
    """The floor's unit normal (pointing up), or None when no floor is clear.

    The floor is the plane holding most of the lowest points (the lowest 30% along
    `up`), found by RANSAC with a fixed seed, and trusted only within
    MAX_UP_CORRECTION_DEG of `up`."""
    pts = np.asarray(points, dtype=np.float64)
    up = np.asarray(up, dtype=np.float64) / np.linalg.norm(up)
    if len(pts) < MIN_FLOOR_POINTS:
        return None
    heights = pts @ up
    low = pts[heights <= np.percentile(heights, 30)]
    limit = np.cos(np.radians(MAX_UP_CORRECTION_DEG))
    rng = np.random.default_rng(0)
    best: np.ndarray | None = None
    best_count = 0
    for _ in range(FLOOR_TRIES):
        a, b, c = low[rng.choice(len(low), 3, replace=False)]
        normal = np.cross(b - a, c - a)
        norm = np.linalg.norm(normal)
        if norm < 1e-9:
            continue
        normal /= norm
        if abs(normal @ up) < limit:
            continue
        inside = np.abs((low - a) @ normal) <= FLOOR_TOLERANCE_M
        count = int(inside.sum())
        if count > best_count:
            best, best_count = inside, count
    if best is None or best_count < MIN_FLOOR_SHARE * len(low):
        return None
    on_floor = low[best]
    normal = np.linalg.svd(on_floor - on_floor.mean(axis=0), full_matrices=False)[2][-1]
    if normal @ up < 0:
        normal = -normal
    if normal @ up < limit:
        return None
    found: np.ndarray = normal
    return found


def _turn(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The smallest rotation taking unit vector a to unit vector b."""
    v, c = np.cross(a, b), float(a @ b)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    rotation: np.ndarray = np.eye(3) + vx + vx @ vx / (1.0 + c)
    return rotation


def floor_up_correction(points: np.ndarray, up: np.ndarray) -> np.ndarray | None:
    """A rotation that turns the floor's normal into `up`, or None to keep `up` as it is.

    Photos are mostly taken looking down, so the cameras' average up leans; the floor
    does not."""
    up = np.asarray(up, dtype=np.float64) / np.linalg.norm(up)
    normal = floor_normal(points, up)
    return None if normal is None else _turn(normal, up)


# Photos whose floors agree within this of their median make the floor's up; at least
# MIN_FLOOR_PHOTOS of them.
FLOOR_AGREEMENT_DEG = 5.0
MIN_FLOOR_PHOTOS = 2


def up_from_floor_normals(normals: Sequence[np.ndarray], up: np.ndarray) -> np.ndarray | None:
    """A rotation from the floor normals found in single photos (each photo's depth is
    consistent with itself even where the cameras are not quite right with each other):
    their mean, after leaving out the ones far from the median, turned into `up`."""
    up = np.asarray(up, dtype=np.float64) / np.linalg.norm(up)
    found = np.array([n / np.linalg.norm(n) for n in normals], dtype=np.float64)
    if len(found) < MIN_FLOOR_PHOTOS:
        return None
    median = np.median(found, axis=0)
    median /= np.linalg.norm(median)
    close = found[found @ median >= np.cos(np.radians(FLOOR_AGREEMENT_DEG))]
    if len(close) < MIN_FLOOR_PHOTOS:
        return None
    mean = close.mean(axis=0)
    mean /= np.linalg.norm(mean)
    return _turn(mean, up)
