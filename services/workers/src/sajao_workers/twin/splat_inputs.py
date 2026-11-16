"""Inputs for splat training: initial points from depth, and held-out views."""

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

# One frame: RGB (H, W, 3) uint8, depth in metres (0 where unknown), 3x3 intrinsics,
# 4x4 camera-to-world (OpenCV camera).
Frame = tuple[np.ndarray, np.ndarray, Sequence[Sequence[float]], Sequence[Sequence[float]]]
HOLD_OUT_EVERY = 10
# A view counts as near the capture path when a training camera stood within this
# distance of it. The same radius bounds the twin's safe viewing region.
NEAR_PATH_M = 0.3


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
    """Every tenth keyframe is kept out of training to score the splat."""
    return list(range(HOLD_OUT_EVERY - 1, n_frames, HOLD_OUT_EVERY))


def nearest_training_camera(
    c2w: np.ndarray, test: Sequence[int], train: Sequence[int]
) -> list[tuple[float, float]]:
    """For each test view: metres to the nearest training camera, and the angle
    in degrees between the two viewing directions."""
    positions, forwards = c2w[:, :3, 3], c2w[:, :3, 2]
    out = []
    for i in test:
        d = np.linalg.norm(positions[list(train)] - positions[i], axis=1)
        j = int(np.argmin(d))
        cos = float(np.clip(forwards[train[j]] @ forwards[i], -1.0, 1.0))
        out.append((float(d[j]), float(np.degrees(np.arccos(cos)))))
    return out


def held_out_split(c2w: np.ndarray) -> list[int]:
    """About a tenth of the keyframes, chosen to score the splat both near the
    capture path and away from it (golden rooms only).

    Half are spread evenly, so training cameras stand right beside them. The
    other half are one run of consecutive keyframes: with the whole run out of
    training, its middle views are as far from any training camera as the
    capture allows. The run is placed where it leaves the most views more than
    NEAR_PATH_M from every remaining camera.
    """
    n = len(c2w)
    budget = round(n / HOLD_OUT_EVERY)
    if budget < 2:
        return held_out(n)
    run = budget // 2
    best = (-1, 0.0, 1)
    for start in range(1, n - run):
        block = list(range(start, start + run))
        rest = [i for i in range(n) if i < start or i >= start + run]
        metres = [m for m, _ in nearest_training_camera(c2w, block, rest)]
        score = (sum(m > NEAR_PATH_M for m in metres), round(sum(metres), 6))
        if score > best[:2]:
            best = (*score, start)
    block = list(range(best[2], best[2] + run))
    # The spread views keep both neighbours in training, so they stay near the path.
    free = [i for i in range(1, n - 1) if not (block[0] - 1 <= i <= block[-1] + 1)]
    spread: list[int] = []
    for j in range(budget - run):
        pick = free[int((j + 0.5) * len(free) / (budget - run))]
        if not spread or pick > spread[-1] + 1:
            spread.append(pick)
    return sorted({*block, *spread})


def split_views(c2w: np.ndarray, test: Sequence[int], train: Sequence[int]) -> list[dict[str, Any]]:
    """Each held-out view with its distance to the training cameras and its side
    of the split: near the capture path, or far from it."""
    return [
        {
            "index": int(i),
            "nearest_m": round(metres, 3),
            "nearest_deg": round(degrees, 1),
            "split": "near" if round(metres, 3) <= NEAR_PATH_M else "far",
        }
        for i, (metres, degrees) in zip(
            test, nearest_training_camera(c2w, test, train), strict=True
        )
    ]


def summarise(views: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Mean PSNR, SSIM and LPIPS of scored views: near the path, far from it, and all."""
    out: dict[str, dict[str, Any]] = {}
    for name in ("near", "far", "all"):
        rows = [v for v in views if name == "all" or v["split"] == name]
        entry: dict[str, Any] = {"views": len(rows)}
        for metric, digits in (("psnr", 2), ("ssim", 3), ("lpips", 3)):
            if rows:
                entry[metric] = round(float(np.mean([v[metric] for v in rows])), digits)
        out[name] = entry
    return out
