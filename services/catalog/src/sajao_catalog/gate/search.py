"""Find the camera from which an asset best matches a photo, then score that view.

Shape is compared in bounding squares, so the photo's framing does not matter. The
coarse search is a grid of azimuth, elevation and field of view on a light point
sample; the best few are re-rendered sharper and nudged locally.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from sajao_catalog.gate.metrics import mean_colour_difference, silhouette, to_square
from sajao_catalog.gate.raster import Cloud, orbit, render

AZIMUTHS = np.arange(0.0, 360.0, 15.0)
ELEVATIONS = np.array([0.0, 10.0, 20.0, 30.0, 45.0, 60.0])  # listing photos are never from below
FOVS = np.array([20.0, 45.0])
COARSE, FINE = 96, 256


@dataclass(frozen=True)
class Pose:
    azimuth: float
    elevation: float
    fov: float


@dataclass(frozen=True)
class Match:
    pose: Pose
    silhouette: float
    colour: float
    render: NDArray[np.float64]  # (FINE, FINE, 3), bounding square
    render_mask: NDArray[np.bool_]
    photo: NDArray[np.float64]  # (FINE, FINE, 3), bounding square
    photo_mask: NDArray[np.bool_]


def subsample(cloud: Cloud, n: int, seed: int = 1) -> Cloud:
    if len(cloud.points) <= n:
        return cloud
    i = np.random.default_rng(seed).choice(len(cloud.points), n, replace=False)
    return Cloud(cloud.points[i], cloud.colors[i], cloud.normals[i])


def camera(cloud: Cloud, pose: Pose) -> NDArray[np.float64]:
    lo, hi = cloud.points.min(0), cloud.points.max(0)
    center = (lo + hi) / 2
    radius = 1.1 * np.linalg.norm(hi - lo) / (2 * np.tan(np.radians(pose.fov) / 2))
    return orbit(center, radius, pose.azimuth, pose.elevation)


def view(cloud: Cloud, pose: Pose, size: int) -> tuple[NDArray[np.float64], NDArray[np.bool_]]:
    rgb, mask = render(cloud, camera(cloud, pose), pose.fov, size * 2)
    if not mask.any():
        return np.ones((size, size, 3)), np.zeros((size, size), bool)
    return to_square(rgb, mask, size)


def search(
    cloud: Cloud, photo: NDArray[np.float64], photo_mask: NDArray[np.bool_], keep: int = 5
) -> Match:
    """`photo`: RGB 0..1 with the product cut out by `photo_mask`."""
    p_small = to_square(photo_mask, photo_mask, COARSE)[1]
    light = subsample(cloud, 20_000)
    coarse = []
    for fov in FOVS:
        for el in ELEVATIONS:
            for az in AZIMUTHS:
                pose = Pose(float(az), float(el), float(fov))
                coarse.append((silhouette(view(light, pose, COARSE)[1], p_small), pose))
    coarse.sort(key=lambda t: -t[0])
    p_rgb, p_mask = to_square(photo, photo_mask, FINE)
    best: Match | None = None
    for _, pose in coarse[:keep]:
        for daz in (-7.5, 0.0, 7.5):
            for del_ in (-7.5, 0.0, 7.5):
                p = Pose(pose.azimuth + daz, max(-5.0, pose.elevation + del_), pose.fov)
                rgb, mask = view(cloud, p, FINE)
                s = silhouette(mask, p_mask)
                if best is None or s > best.silhouette:
                    both = mask & p_mask
                    colour = mean_colour_difference(rgb, both, p_rgb, both)
                    best = Match(p, s, colour, rgb, mask, p_rgb, p_mask)
    assert best is not None  # noqa: S101 (the grid is never empty)
    return best
