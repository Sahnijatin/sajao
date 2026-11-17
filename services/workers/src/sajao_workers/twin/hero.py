"""Hero viewpoints and the safe viewing region of a twin.

Every plan for showing a room starts from its best photos: six to ten hero
views, each a real keyframe that shows a lot of the room and is sharp. They
are the photos a redesign is rendered on, and the poses a 3D view is shown
from. A 3D view only holds up near where the phone stood, so the twin also
names a safe region around the capture path. The viewer and the reveal use
nothing else.

Everything here is code on measured data: depth says what each keyframe sees,
the image says how sharp it is, the poses say where the phone stood.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np

HERO_MIN, HERO_MAX = 6, 10
# How far from a keyframe position the camera may stand. In review, renders a
# short step off the capture path already streaked; this keeps views beside real photos.
SAFE_RADIUS_M = 0.3
# A hero view may turn this far either way without leaving what its keyframe saw.
ORBIT_YAW_DEG = 15.0
VOXEL_M = 0.10
# After HERO_MIN views, another is added only if it shows this share of new room.
MIN_GAIN = 0.02
# Two hero views are at least this far apart, in position or in direction.
MIN_APART_M, MIN_APART_DEG = 0.4, 25.0
# Framing: a view this far from what it looks at shows the room, not one object.
ROOM_VIEW_DEPTH_M = 2.0
LEVEL_PITCH_DEG = 20.0
# Looking up shows ceiling, so a view may tilt up far less than down.
LEVEL_PITCH_UP_DEG = 5.0
# Only the part of the room people live in counts as shown: from the floor to
# this height. Ceiling and the top of the walls earn a view nothing.
LIVING_HEIGHT_M = 1.8
# The blurriest keyframes are never hero views.
BLURRY_SHARE = 0.3


@dataclass(frozen=True)
class FrameView:
    """What one keyframe shows, measured from its depth, image and pose."""

    keyframe_id: str
    voxels: np.ndarray  # sorted unique keys of the 10 cm cells its depth lands in
    heights: np.ndarray  # each cell's height along the up axis, metres (world)
    sharpness: float
    median_depth_m: float
    position: np.ndarray  # world, metres
    forward: np.ndarray  # world, unit
    pitch_deg: float  # up is positive


def sharpness(grey: np.ndarray) -> float:
    """Variance of the Laplacian of a grey image: higher is sharper."""
    g = grey.astype(np.float64)
    lap = g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] - 4.0 * g[1:-1, 1:-1]
    return float(lap.var())


def frame_view(
    keyframe_id: str,
    depth: np.ndarray,
    grey: np.ndarray,
    intrinsics: Sequence[Sequence[float]],
    image_width: int,
    c2w: Sequence[Sequence[float]],
    up_axis: int,
    stride: int = 4,
) -> FrameView:
    """`depth` is in metres (0 where unknown) and may be smaller than the image."""
    pose = np.asarray(c2w, dtype=np.float64)
    k = np.asarray(intrinsics, dtype=np.float64)
    scale = depth.shape[1] / image_width
    d = depth[::stride, ::stride]
    ys, xs = np.nonzero(d > 0.05)
    z = d[ys, xs].astype(np.float64)
    u, v = xs * stride, ys * stride
    cam = np.stack(
        [
            (u - k[0, 2] * scale) * z / (k[0, 0] * scale),
            (v - k[1, 2] * scale) * z / (k[1, 1] * scale),
            z,
        ],
        axis=1,
    )
    world = cam @ pose[:3, :3].T + pose[:3, 3]
    cells = np.floor(world / VOXEL_M).astype(np.int64)
    # One key per cell: rooms are far smaller than 2^20 cells of 10 cm on a side.
    keys = ((cells[:, 0] + 2**20) << 42) | ((cells[:, 1] + 2**20) << 21) | (cells[:, 2] + 2**20)
    forward = pose[:3, 2] / np.linalg.norm(pose[:3, 2])
    voxels, first = np.unique(keys, return_index=True)
    return FrameView(
        keyframe_id=keyframe_id,
        voxels=voxels,
        heights=cells[first, up_axis] * VOXEL_M,
        sharpness=sharpness(grey),
        median_depth_m=float(np.median(z)) if len(z) else 0.0,
        position=pose[:3, 3].copy(),
        forward=forward,
        pitch_deg=float(np.degrees(np.arcsin(np.clip(forward[up_axis], -1.0, 1.0)))),
    )


def framing(view: FrameView) -> float:
    """1 for a level view across the room, less for close-ups and steep tilts."""
    depth = float(np.clip(view.median_depth_m / ROOM_VIEW_DEPTH_M, 0.25, 1.0))
    level = LEVEL_PITCH_UP_DEG if view.pitch_deg > 0 else LEVEL_PITCH_DEG
    tilt = max(0.0, abs(view.pitch_deg) - level)
    return depth * max(0.25, 1.0 - tilt / 40.0)


def _apart(a: FrameView, b: FrameView) -> bool:
    metres = float(np.linalg.norm(a.position - b.position))
    degrees = float(np.degrees(np.arccos(np.clip(a.forward @ b.forward, -1.0, 1.0))))
    return metres >= MIN_APART_M or degrees >= MIN_APART_DEG


def pick_hero_views(views: Sequence[FrameView]) -> list[dict[str, float | str]]:
    """Up to HERO_MAX keyframes, best first: each adds the most room not yet
    shown, weighted by framing, among the sharp keyframes. Room means the
    living zone, floor to LIVING_HEIGHT_M; coverage is a share of that."""
    if not any(len(v.voxels) for v in views):
        return []
    # The floor is the low end of everything seen (not the minimum: depth has outliers).
    floor = float(np.quantile(np.concatenate([v.heights for v in views]), 0.02))
    usable = []
    for v in views:
        living = v.heights <= floor + LIVING_HEIGHT_M
        if living.any():
            usable.append(replace(v, voxels=v.voxels[living], heights=v.heights[living]))
    room = np.unique(np.concatenate([v.voxels for v in usable]))
    cut = float(np.quantile([v.sharpness for v in usable], BLURRY_SHARE))
    sharp = [v for v in usable if v.sharpness >= cut]
    shown = np.zeros(0, dtype=np.int64)
    picked: list[FrameView] = []
    while len(picked) < HERO_MAX:
        best: tuple[float, float, FrameView] | None = None
        for view in sharp:
            if any(view is p or not _apart(view, p) for p in picked):
                continue
            gain = len(np.setdiff1d(view.voxels, shown, assume_unique=True)) / len(room)
            # Once nothing new is left to show, the widest remaining view goes next.
            score = (gain * framing(view), len(view.voxels) * framing(view))
            if best is None or score > best[:2]:
                best = (*score, view)
        if best is None:
            break
        view = best[2]
        gain = len(np.setdiff1d(view.voxels, shown, assume_unique=True)) / len(room)
        if len(picked) >= HERO_MIN and gain < MIN_GAIN:
            break
        picked.append(view)
        shown = np.union1d(shown, view.voxels)
    return [
        {
            "keyframe_id": v.keyframe_id,
            "coverage": round(len(v.voxels) / len(room), 3),
            "sharpness": round(v.sharpness, 1),
        }
        for v in picked
    ]


def inside_safe_region(
    position: Sequence[float], anchors: np.ndarray, radius_m: float = SAFE_RADIUS_M
) -> bool:
    """Whether a camera position is within the safe radius of a keyframe position."""
    gaps = np.linalg.norm(anchors - np.asarray(position, dtype=np.float64), axis=1)
    return bool(gaps.min() <= radius_m + 1e-9)
