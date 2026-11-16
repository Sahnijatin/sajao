"""Inputs for splat training: initial points from depth, and held-out views."""

from collections.abc import Sequence

import numpy as np

# One frame: RGB (H, W, 3) uint8, depth in metres (0 where unknown), 3x3 intrinsics,
# 4x4 camera-to-world (OpenCV camera).
Frame = tuple[np.ndarray, np.ndarray, Sequence[Sequence[float]], Sequence[Sequence[float]]]
HOLD_OUT_EVERY = 8


def initial_points(
    frames: Sequence[Frame], stride: int = 4, max_points: int = 300_000
) -> np.ndarray:
    """(N, 6) points with RGB in 0..1 from every `stride`-th depth pixel, capped evenly."""
    chunks = []
    for rgb, depth, intrinsics, c2w in frames:
        d = depth[::stride, ::stride]
        ys, xs = np.nonzero(d > 0.05)
        z = d[ys, xs].astype(np.float64)
        px, py = xs * stride, ys * stride
        k = np.asarray(intrinsics, dtype=np.float64)
        cam = np.stack([(px - k[0, 2]) * z / k[0, 0], (py - k[1, 2]) * z / k[1, 1], z], axis=1)
        pose = np.asarray(c2w, dtype=np.float64)
        world = cam @ pose[:3, :3].T + pose[:3, 3]
        chunks.append(np.concatenate([world, rgb[py, px].astype(np.float64) / 255.0], axis=1))
    points = np.concatenate(chunks) if chunks else np.zeros((0, 6))
    if len(points) > max_points:
        points = points[np.linspace(0, len(points) - 1, max_points).round().astype(int)]
    return points


def held_out(n_frames: int) -> list[int]:
    """Every eighth keyframe is kept out of training to score the splat."""
    return list(range(HOLD_OUT_EVERY - 1, n_frames, HOLD_OUT_EVERY))
