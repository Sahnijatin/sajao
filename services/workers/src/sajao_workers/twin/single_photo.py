"""One landscape photo to a camera standing on the floor, at the estimated level.

The photo-first path (SJ-SCOPE-32) starts from a single photo with no AR and no
pose model. Metric depth (MoGe-3, which also estimates the field of view when the
photo carries none) gives every pixel a point in the camera's frame. These pure
functions turn that into the AR-like world the twin steps read (metres, y up,
floor at y = 0, the camera looking along -z):

- `level_camera`: the floor plane from depth, and the camera's height above it;
- `ceiling_height`, `door_height`: two lengths the depth model measured that have
  known ranges in Indian homes;
- `check_scale`: those lengths against their priors. The depth model's scale is
  kept when they agree, corrected when they agree with each other but not with
  it, and the error band says how far the room can be trusted either way.

Nothing here claims a fit: a single photo is always `estimated`, and the design
engine uses the band as margin. Code measures every length; no model sets one.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from sajao_workers.twin.photos import floor_normal

# Priors for Indian flats, provisional until the golden set: door leaves are 7 ft
# (2.03 to 2.13 m, frames included); floor to ceiling 2.6 to 3.3 m.
DOOR_HEIGHT_M = (2.0, 2.15)
CEILING_HEIGHT_M = (2.6, 3.3)
# The most a prior may move the depth model's scale. Further off, the photo is
# wrong (a mirror, a photo of a photo), not the scale.
MAX_CORRECTION = 1.35
# Error bands as a fraction of every length. Estimated sizes from one photo are off
# by about 17% (SJ-DEC-87); a cue that confirms the scale narrows that.
BAND_UNCHECKED = 0.17
BAND_ONE_CUE = 0.13
BAND_TWO_CUES = 0.10
# Floor search: the photo may look down at most this far, tried in steps, because
# `floor_normal` trusts a plane only near the up it is given.
TILTS_DEG = (0.0, 20.0, 40.0)
FLOOR_BIN_M = 0.02
MIN_CAMERA_HEIGHT_M = 0.3
MAX_CAMERA_HEIGHT_M = 2.5
# The ceiling must cover this share of the photo's points (and at least 50 of them).
MIN_CEILING_SHARE = 0.02
MIN_CEILING_POINTS = 50
# A door mask must reach this close to the floor and stay this far off the top edge
# of the photo, or its top is not its real top.
DOOR_FOOT_M = 0.15
DOOR_TOP_MARGIN_PX = 3


def intrinsics_from_fov(width: int, height: int, fov_x_deg: float) -> list[list[float]]:
    """Pinhole intrinsics with square pixels and the principal point at the centre."""
    f = width / (2.0 * math.tan(math.radians(fov_x_deg) / 2.0))
    return [[f, 0.0, width / 2.0], [0.0, f, height / 2.0], [0.0, 0.0, 1.0]]


def lift(depth: np.ndarray, intrinsics: Any, stride: int = 4) -> np.ndarray:
    """Depth (metres, 0 = none) to camera points (N, 3), OpenCV axes, every `stride` px."""
    k = np.asarray(intrinsics, dtype=np.float64)
    ys, xs = np.mgrid[0 : depth.shape[0] : stride, 0 : depth.shape[1] : stride]
    z = depth[ys, xs].astype(np.float64)
    ok = z > 0.05
    xs, ys, z = xs[ok], ys[ok], z[ok]
    x = (xs + 0.5 - k[0, 2]) / k[0, 0] * z
    y = (ys + 0.5 - k[1, 2]) / k[1, 1] * z
    points: np.ndarray = np.stack([x, y, z], axis=1)
    return points


def _mode(values: np.ndarray, bin_m: float) -> float:
    """The centre of the fullest `bin_m` bin, refined to the median of its points."""
    lo = float(values.min())
    bins = np.floor((values - lo) / bin_m).astype(int)
    best = int(np.bincount(bins).argmax())
    inside = values[(bins >= best - 1) & (bins <= best + 1)]
    return float(np.median(inside))


@dataclass(frozen=True)
class Camera:
    """The photo's camera in the world: OpenCV camera to world (y up, floor at 0)."""

    c2w: np.ndarray
    height_m: float
    tilt_deg: float  # how far the camera looks down (negative: up)


def level_camera(points: np.ndarray) -> Camera | None:
    """The camera standing on the floor the photo shows, or None when no floor is clear.

    `points` are camera points (OpenCV: +y down, +z forward). The world's +y is the
    floor's normal, its -z the camera's forward direction laid flat on the floor."""
    pts = np.asarray(points, dtype=np.float64)
    normal = None
    for tilt in TILTS_DEG:
        t = math.radians(tilt)
        # Camera up is -y; looking down by `t` turns the floor's up toward -z.
        guess = np.array([0.0, -math.cos(t), -math.sin(t)])
        normal = floor_normal(pts, guess)
        if normal is not None:
            break
    if normal is None:
        return None
    levels = pts @ normal
    low = levels[levels <= np.percentile(levels, 30)]
    height = -_mode(low, FLOOR_BIN_M)
    if not MIN_CAMERA_HEIGHT_M <= height <= MAX_CAMERA_HEIGHT_M:
        return None
    forward = np.array([0.0, 0.0, 1.0])
    flat = forward - (forward @ normal) * normal
    if np.linalg.norm(flat) < 1e-6:
        return None  # looking straight down: there is no room in the photo
    z_axis = -flat / np.linalg.norm(flat)
    x_axis = np.cross(normal, z_axis)
    rotation = np.stack([x_axis, normal, z_axis])  # rows: world axes in camera coordinates
    c2w = np.eye(4)
    c2w[:3, :3] = rotation
    c2w[:3, 3] = [0.0, height, 0.0]
    tilt_deg = math.degrees(math.asin(float(np.clip(-(forward @ normal), -1.0, 1.0))))
    return Camera(c2w, height, tilt_deg)


def to_world(points: np.ndarray, camera: Camera) -> np.ndarray:
    world: np.ndarray = points @ camera.c2w[:3, :3].T + camera.c2w[:3, 3]
    return world


def ceiling_height(world: np.ndarray, camera: Camera) -> float | None:
    """Floor to ceiling, when the photo shows enough of a level ceiling above the camera."""
    heights = world[:, 1]
    need = max(MIN_CEILING_POINTS, MIN_CEILING_SHARE * len(heights))
    above = heights[heights > camera.height_m + 0.5]
    if len(above) < need:
        return None
    level = _mode(above[above >= np.percentile(above, 50)], FLOOR_BIN_M)
    near = np.abs(above - level) <= 0.04
    if near.sum() < need or level < np.percentile(above, 95) - 0.04:
        return None  # a sloping or broken top: beams, a loft, a lamp
    return level


def door_height(
    mask: np.ndarray, depth: np.ndarray, intrinsics: Any, camera: Camera
) -> float | None:
    """Floor to the top of a door seen whole in the photo, or None.

    The door must reach the floor and its top must be inside the photo, so the mask's
    highest point is the door's real top."""
    rows = np.nonzero(mask.any(axis=1))[0]
    if len(rows) == 0 or rows[0] < DOOR_TOP_MARGIN_PX:
        return None
    masked = np.where(mask, depth, 0.0)
    points = lift(masked, intrinsics, stride=2)
    if len(points) < 50:
        return None
    heights = to_world(points, camera)[:, 1]
    if np.percentile(heights, 2) > DOOR_FOOT_M:
        return None
    return float(np.percentile(heights, 99.5))


Cue = Literal["ceiling", "door"]


@dataclass(frozen=True)
class ScaleCheck:
    """What the priors said about the depth model's scale, and what was done."""

    factor: float  # multiply every length by this
    band_fraction: float  # the error band of every length, as a fraction of it
    outcome: Literal["unchecked", "confirmed", "corrected", "conflict", "implausible"]
    cues: dict[str, float] = field(default_factory=dict)  # measured lengths, metres

    def band_m(self, value_m: float, floor_m: float = 0.05) -> float:
        return max(floor_m, self.band_fraction * value_m)


PRIORS: dict[Cue, tuple[float, float]] = {"ceiling": CEILING_HEIGHT_M, "door": DOOR_HEIGHT_M}


def check_scale(ceiling_m: float | None, doors_m: Sequence[float]) -> ScaleCheck:
    """The depth model's scale against the ceiling and door priors.

    Each cue allows the factors that put its length inside its prior range. No cue:
    the scale stands, unchecked. 1 allowed by every cue: confirmed, and the band
    narrows. Some factor allowed by every cue: corrected by the one closest to 1.
    No factor allowed by every cue: the cues disagree and the scale stands at the
    widest band. A correction beyond MAX_CORRECTION means the photo is not of a room
    at a usable scale, and the scale stands."""
    cues: dict[str, float] = {}
    lo, hi = 0.0, math.inf
    if ceiling_m is not None and ceiling_m > 0:
        cues["ceiling"] = round(ceiling_m, 3)
        lo = max(lo, PRIORS["ceiling"][0] / ceiling_m)
        hi = min(hi, PRIORS["ceiling"][1] / ceiling_m)
    if doors_m:
        door = float(np.median(doors_m))
        cues["door"] = round(door, 3)
        lo = max(lo, PRIORS["door"][0] / door)
        hi = min(hi, PRIORS["door"][1] / door)
    if not cues:
        return ScaleCheck(1.0, BAND_UNCHECKED, "unchecked", cues)
    if lo <= 1.0 <= hi:
        band = BAND_TWO_CUES if len(cues) > 1 else BAND_ONE_CUE
        return ScaleCheck(1.0, band, "confirmed", cues)
    if lo > hi:
        return ScaleCheck(1.0, BAND_UNCHECKED, "conflict", cues)
    factor = lo if lo > 1.0 else hi
    if not 1.0 / MAX_CORRECTION <= factor <= MAX_CORRECTION:
        return ScaleCheck(1.0, BAND_UNCHECKED, "implausible", cues)
    # A corrected scale rests on the priors' own width, so it is no tighter than one cue.
    return ScaleCheck(factor, BAND_ONE_CUE, "corrected", cues)
