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
