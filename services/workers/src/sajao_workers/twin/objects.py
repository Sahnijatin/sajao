"""Objects in the twin: masks lifted with depth, fused across frames, boxed by code.

The detector names an object and the segmenter outlines it; depth (LiDAR, or a
depth model on phones without it) places the outline's pixels in 3D. Code fuses
those points across frames and fits an upright box. No model sets a size.

Boxes are in the capture's world frame (gravity aligned, `up_axis` up). Every
size is a Dimension with an error band calibrated on the SJ-116 rooms and the
no-LiDAR benchmark; the golden-set evals recalibrate it.
"""

import io
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np
from PIL import Image

from sajao_workers.twin.fusion import (
    GROUPS,
    MIN_SHARED_FRAMES,
    Instance,
    Observation,
    fuse,
    merge_instances,
    voxelize,
)
from sajao_workers.twin.geometry import UprightBox, fit_upright_box, horizontal_axes

DepthSource = Literal["lidar", "image"]

# (floor in metres, fraction of the size). Median size errors measured: LiDAR 21%,
# image depth 19% to 22%, centre 14 to 17 cm; the band is set wider than the median
# so most objects fall inside it. The solver uses the band as margin; tape decides fit.
ERROR_BANDS: dict[DepthSource, tuple[float, float]] = {
    "lidar": (0.05, 0.25),
    "image": (0.07, 0.30),
}
VOXEL_M = 0.05
MAX_POINTS_PER_MASK = 4000
MIN_POINTS_PER_MASK = 50
MIN_FRAMES = 3
# Core voxels an instance needs for a box; small items (a clock, a switchboard) cover few.
MIN_CORE_POINTS, MIN_CORE_POINTS_SMALL = 8, 3
# A box outside these sizes is not a piece of furniture or decor: a fusion error.
MIN_SIZE_M, MAX_SIZE_M = 0.15, 4.0
# Large furniture that views often see in pieces (the arms of an L-shaped sofa).
# Same-class pieces whose footprints touch are joined while the result stays
# within these sizes (length, width in metres). Chairs are never joined.
JOINABLE: dict[str, tuple[float, float]] = {
    "sofa": (3.5, 2.2),
    "bed": (2.6, 2.4),
    "table": (3.2, 1.6),
    "cabinet": (3.0, 1.0),
}
TOUCH_M = 0.10


@dataclass(frozen=True)
class FrameMasks:
    keyframe_id: str
    c2w: Sequence[Sequence[float]]  # 4x4, OpenCV camera (x right, y down, z forward) to world
    intrinsics: Sequence[Sequence[float]]  # 3x3
    depth: np.ndarray  # metres, 0 where unknown, same size as the masks
    masks: Sequence[tuple[str, float, np.ndarray, str]]  # (label, score, mask, mask blob)


def decode_depth_mm(png: bytes) -> np.ndarray:
    """16-bit PNG depth in millimetres to float metres."""
    return np.asarray(Image.open(io.BytesIO(png)), dtype=np.float32) / 1000.0


def depth_at(depth: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Depth resampled to an image size by nearest neighbour (LiDAR depth is about
    256 x 192; masks are at keyframe resolution). Never blends depths across an edge."""
    if depth.shape == shape:
        return depth
    h, w = shape
    rows = np.minimum((np.arange(h) * depth.shape[0] / h).astype(int), depth.shape[0] - 1)
    cols = np.minimum((np.arange(w) * depth.shape[1] / w).astype(int), depth.shape[1] - 1)
    resampled: np.ndarray = depth[rows[:, None], cols[None, :]]
    return resampled


def decode_mask(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("L")) > 127


def _erode(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask
    padded = np.pad(mask, radius, constant_values=False)
    out = np.ones_like(mask)
    h, w = mask.shape
    for dy in range(2 * radius + 1):
        for dx in range(2 * radius + 1):
            out &= padded[dy : dy + h, dx : dx + w]
    return out


def lift_mask(
    mask: np.ndarray,
    depth: np.ndarray,
    intrinsics: Sequence[Sequence[float]],
    c2w: Sequence[Sequence[float]],
    erode: int = 2,
    seed: int = 0,
) -> np.ndarray:
    """World points (N, 3) for a mask's pixels with depth; empty when too few.

    The mask is eroded so edge pixels, which often pick up the background's
    depth, are left out; depths far from the mask's median are dropped.
    """
    ys, xs = np.nonzero(_erode(mask, erode) & (depth > 0.05))
    if len(ys) < MIN_POINTS_PER_MASK:
        return np.zeros((0, 3))
    if len(ys) > MAX_POINTS_PER_MASK:
        pick = np.random.default_rng(seed).choice(len(ys), MAX_POINTS_PER_MASK, replace=False)
        ys, xs = ys[pick], xs[pick]
    z = depth[ys, xs].astype(np.float64)
    median = np.median(z)
    spread = np.median(np.abs(z - median)) * 1.4826
    keep = np.abs(z - median) <= 3 * spread + 0.05 * median
    ys, xs, z = ys[keep], xs[keep], z[keep]
    k = np.asarray(intrinsics, dtype=np.float64)
    cam = np.stack([(xs - k[0, 2]) * z / k[0, 0], (ys - k[1, 2]) * z / k[1, 1], z], axis=1)
    pose = np.asarray(c2w, dtype=np.float64)
    points: np.ndarray = cam @ pose[:3, :3].T + pose[:3, 3]
    return points


def dimension(value_m: float, depth_source: DepthSource) -> dict[str, Any]:
    floor, fraction = ERROR_BANDS[depth_source]
    return {
        "value_m": round(value_m, 3),
        "source": "estimated",
        "error_band_m": round(max(floor, fraction * value_m), 3),
    }


@dataclass
class _Fitted:
    label: str
    frames: set[int]
    keys: list[int]
    points: np.ndarray  # core points, (N, 3)
    box: UprightBox


def _group(label: str) -> str:
    key = label.lower().strip()
    return GROUPS.get(key, key)


def _footprint_cells(points: np.ndarray, up_axis: int) -> set[tuple[int, int]]:
    h = list(horizontal_axes(up_axis))
    cells = np.floor(points[:, h] / VOXEL_M).astype(int)
    return {(int(u), int(v)) for u, v in np.unique(cells, axis=0)}


def _touching(a: _Fitted, b: _Fitted, up_axis: int) -> bool:
    """Heights overlap and the footprints come within TOUCH_M of each other."""
    lo_a, hi_a = a.box.vertical_range()
    lo_b, hi_b = b.box.vertical_range()
    if hi_a < lo_b or hi_b < lo_a:
        return False
    cells_a = _footprint_cells(a.points, up_axis)
    reach = math.ceil(TOUCH_M / VOXEL_M)
    near = range(-reach, reach + 1)
    return any(
        (u + du, v + dv) in cells_a
        for u, v in _footprint_cells(b.points, up_axis)
        for du in near
        for dv in near
    )


def _join_pieces(
    fitted: list[_Fitted], up_axis: int, stats: dict[str, int] | None = None
) -> list[_Fitted]:
    pool = list(fitted)
    joined = True
    while joined:
        joined = False
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                a, b = pool[i], pool[j]
                group = _group(a.label)
                if group != _group(b.label) or group not in JOINABLE:
                    continue
                if len(a.frames & b.frames) >= MIN_SHARED_FRAMES:
                    if stats is not None and _touching(a, b, up_axis):
                        stats["joins_blocked"] = stats.get("joins_blocked", 0) + 1
                    continue  # seen as separate objects: two sofas side by side
                if not _touching(a, b, up_axis):
                    continue
                points = np.concatenate([a.points, b.points])
                box = fit_upright_box(points.tolist(), up_axis)
                max_length, max_width = JOINABLE[group]
                if box.length > max_length or box.width > max_width:
                    continue
                label = a.label if len(a.frames) >= len(b.frames) else b.label
                pool[i] = _Fitted(label, a.frames | b.frames, a.keys + b.keys, points, box)
                if stats is not None:
                    stats["pieces_joined"] = stats.get("pieces_joined", 0) + 1
                del pool[j]
                joined = True
                break
            if joined:
                break
    return pool


def _count(per_label: dict[str, dict[str, int]] | None, label: str, what: str) -> None:
    if per_label is not None:
        counts = per_label.setdefault(
            label, {"detected": 0, "lifted": 0, "few_frames": 0, "implausible": 0}
        )
        counts[what] += 1


def fitted_objects(
    instances: Sequence[Instance],
    up_axis: int,
    stats: dict[str, int] | None = None,
    min_size: Mapping[str, float] | None = None,
    per_label: dict[str, dict[str, int]] | None = None,
) -> list[tuple[str, UprightBox, int, list[int]]]:
    """Boxes for instances seen often enough, with touching pieces joined and
    implausible sizes dropped: (label, box, frames seen, observation keys).

    `min_size` lowers the smallest plausible size for some labels (a clock, a
    switchboard); `per_label` counts the instances dropped for each reason."""
    fitted = []
    for instance in instances:
        seen = len(instance.frames)
        if seen < MIN_FRAMES:
            _count(per_label, instance.label, "few_frames")
            continue
        core = instance.core_points(max(2, math.ceil(0.15 * seen)))
        small = (min_size or {}).get(instance.label, MIN_SIZE_M) < MIN_SIZE_M
        if len(core) < (MIN_CORE_POINTS_SMALL if small else MIN_CORE_POINTS):
            _count(per_label, instance.label, "implausible")  # seen enough, too small for a box
            continue
        box = fit_upright_box(core, up_axis)
        if small:
            # Core points are voxel centroids, half a voxel in from each face: on a
            # small item that is a large share of its size, so add the voxel back.
            box = replace(
                box,
                length=box.length + VOXEL_M,
                width=box.width + VOXEL_M,
                height=box.height + VOXEL_M,
            )
        fitted.append(
            _Fitted(
                instance.label,
                set(instance.frames),
                sorted(key for _, key in instance.members),
                np.asarray(core),
                box,
            )
        )
    out = []
    for item in _join_pieces(fitted, up_axis, stats):
        smallest = (min_size or {}).get(item.label, MIN_SIZE_M)
        if smallest <= max(item.box.length, item.box.height) <= MAX_SIZE_M:
            out.append((item.label, item.box, len(item.frames), sorted(item.keys)))
        else:
            _count(per_label, item.label, "implausible")
    return out


def build_objects(
    frames: Sequence[FrameMasks],
    up_axis: int,
    depth_source: DepthSource,
    stats: dict[str, int] | None = None,
    min_size: Mapping[str, float] | None = None,
    per_label: dict[str, dict[str, int]] | None = None,
) -> list[dict[str, Any]]:
    """Fuse every frame's masks into objects with boxes, most-seen first.

    `stats`, when given, counts how fusion separated and joined objects
    (ambiguous views dropped, merges and joins blocked, pieces joined), so the
    golden-set evals can track both kinds of error. `per_label` counts, per
    label, masks detected and lifted and instances dropped (too few frames,
    implausible size), so an item that was listed but not placed has a reason.
    """
    views: list[tuple[str, str]] = []
    observations = []
    for index, frame in enumerate(frames):
        for label, score, mask, blob in frame.masks:
            _count(per_label, label, "detected")
            points = lift_mask(mask, frame.depth, frame.intrinsics, frame.c2w, seed=len(views))
            if len(points) == 0:
                continue
            _count(per_label, label, "lifted")
            observations.append(
                Observation(index, label, score, voxelize(points, VOXEL_M), key=len(views))
            )
            views.append((frame.keyframe_id, blob))
    scores = {obs.key: obs.score for obs in observations}

    objects: list[dict[str, Any]] = []
    instances = merge_instances(fuse(observations, stats=stats), stats=stats)
    for label, box, seen, keys in fitted_objects(instances, up_axis, stats, min_size, per_label):
        objects.append(
            {
                "category": label,
                "label": label.capitalize(),
                "confidence": round(sum(scores[k] for k in keys) / len(keys), 3),
                "frames": seen,
                "up_axis": up_axis,
                "box": {
                    "center": [round(c, 3) for c in box.center],
                    "yaw_deg": round(math.degrees(box.yaw) % 180.0, 2),
                    "length": dimension(box.length, depth_source),
                    "width": dimension(box.width, depth_source),
                    "height": dimension(box.height, depth_source),
                },
                "views": [{"keyframe_id": views[k][0], "mask": views[k][1]} for k in keys],
            }
        )
    objects.sort(key=lambda o: -int(o["frames"]))
    return objects
