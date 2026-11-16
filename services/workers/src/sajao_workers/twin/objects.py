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
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from PIL import Image

from sajao_workers.twin.fusion import Observation, fuse, merge_instances, voxelize
from sajao_workers.twin.geometry import fit_upright_box

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
# A box outside these sizes is not a piece of furniture or decor: a fusion error.
MIN_SIZE_M, MAX_SIZE_M = 0.15, 4.0


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


def build_objects(
    frames: Sequence[FrameMasks], up_axis: int, depth_source: DepthSource
) -> list[dict[str, Any]]:
    """Fuse every frame's masks into objects with boxes, most-seen first."""
    views: list[tuple[str, str]] = []
    observations = []
    for index, frame in enumerate(frames):
        for label, score, mask, blob in frame.masks:
            points = lift_mask(mask, frame.depth, frame.intrinsics, frame.c2w, seed=len(views))
            if len(points) == 0:
                continue
            observations.append(
                Observation(index, label, score, voxelize(points, VOXEL_M), key=len(views))
            )
            views.append((frame.keyframe_id, blob))
    scores = {obs.key: obs.score for obs in observations}

    objects: list[dict[str, Any]] = []
    for instance in merge_instances(fuse(observations)):
        seen = len(instance.frames)
        if seen < MIN_FRAMES:
            continue
        core = instance.core_points(max(2, math.ceil(0.15 * seen)))
        if len(core) < 8:
            continue
        box = fit_upright_box(core, up_axis)
        if not MIN_SIZE_M <= max(box.length, box.height) <= MAX_SIZE_M:
            continue
        keys = sorted(key for _, key in instance.members)
        objects.append(
            {
                "category": instance.label,
                "label": instance.label.capitalize(),
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
