"""A small point-splat rasterizer for the fidelity gate (numpy only, no GPU, no
third-party renderer).

The mesh surface is sampled once into points, area-weighted, with colours from the
vertices. Rendering projects the points through a pinhole camera, keeps the nearest
point per pixel (a z-buffer), and closes the small gaps between samples. That is enough
for what the gate compares: silhouettes, mean colour and an embedding of the view.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

F = NDArray[np.float64]


@dataclass(frozen=True)
class Cloud:
    points: F  # (n, 3)
    colors: F  # (n, 3) in 0..1
    normals: F  # (n, 3) unit


def sample_surface(
    vertices: F, faces: NDArray[np.int64], colors: F, n: int, seed: int = 0
) -> Cloud:
    """Area-weighted points on the triangles, colours interpolated from the vertices."""
    tri = vertices[faces]  # (f, 3, 3)
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = 0.5 * np.linalg.norm(cross, axis=1)
    keep = area > 0
    faces, tri, cross, area = faces[keep], tri[keep], cross[keep], area[keep]
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(faces), size=n, p=area / area.sum())
    u, v = rng.random(n), rng.random(n)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    w = np.stack([1 - u - v, u, v], 1)  # (n, 3) barycentric
    pts = np.einsum("nk,nkd->nd", w, tri[pick])
    col = np.einsum("nk,nkd->nd", w, colors[faces[pick]])
    nrm = cross[pick] / np.linalg.norm(cross[pick], axis=1, keepdims=True)
    return Cloud(pts, np.clip(col, 0, 1), nrm)


def look_at(eye: F, target: F, up: F | None = None) -> F:
    """World-to-camera 4x4 (camera looks down +z, y down in the image)."""
    up = np.array([0.0, 1.0, 0.0]) if up is None else up
    z = target - eye
    z = z / np.linalg.norm(z)
    x = np.cross(z, up)
    if np.linalg.norm(x) < 1e-6:
        x = np.cross(z, np.array([0.0, 0.0, 1.0]))
    x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    m = np.eye(4)
    m[:3, :3] = np.stack([x, y, z])
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def orbit(center: F, radius: float, azimuth_deg: float, elevation_deg: float) -> F:
    """World-to-camera matrix on a sphere around `center` (y is up)."""
    az, el = np.radians(azimuth_deg), np.radians(elevation_deg)
    eye = center + radius * np.array([np.sin(az) * np.cos(el), np.sin(el), np.cos(az) * np.cos(el)])
    return look_at(eye, center)


def render(
    cloud: Cloud, world_to_cam: F, fov_deg: float, size: int, light: F | None = None
) -> tuple[F, NDArray[np.bool_]]:
    """RGB (size, size, 3) on white and a bool mask. Soft Lambert shading from `light`
    (camera direction by default), so shape reads in the image as it does in a photo."""
    p = cloud.points @ world_to_cam[:3, :3].T + world_to_cam[:3, 3]
    z = p[:, 2]
    front = z > 1e-4
    f = 0.5 * size / np.tan(np.radians(fov_deg) / 2)
    px = (f * p[front, 0] / z[front] + size / 2).astype(np.int64)
    py = (f * p[front, 1] / z[front] + size / 2).astype(np.int64)
    inside = (px >= 0) & (px < size) & (py >= 0) & (py < size)
    idx = (py * size + px)[inside]
    depth = z[front][inside]
    order = np.lexsort((depth, idx))  # by pixel, nearest first
    idx, first = np.unique(idx[order], return_index=True)
    sel = np.flatnonzero(front)[inside][order][first]
    n_cam = cloud.normals[sel] @ world_to_cam[:3, :3].T
    d = np.array([0.0, 0.0, -1.0]) if light is None else light / np.linalg.norm(light)
    # Mostly ambient: studio photos are lit softly from all sides, so a top seen at a
    # grazing angle stays nearly its own colour.
    shade = 0.75 + 0.25 * np.abs(n_cam @ d)
    flat_rgb = np.ones((size * size, 3))
    flat_rgb[idx] = cloud.colors[sel] * shade[:, None]
    flat_z = np.full(size * size, np.inf)
    flat_z[idx] = depth[order][first]
    rgb, zbuf = flat_rgb.reshape(size, size, 3), flat_z.reshape(size, size)
    # Points of a far surface seen through gaps between near samples: drop a pixel that
    # lies well behind its neighbourhood's nearest surface, then refill from neighbours.
    span = float(np.ptp(depth)) if depth.size else 0.0
    behind = zbuf > _min_filter(zbuf, 2) + max(0.03 * span, 1e-6)
    zbuf[behind] = np.inf
    rgb[behind] = 1.0
    return close_gaps(rgb, np.isfinite(zbuf), passes=3)


def _min_filter(img: F, r: int) -> F:
    out = img.copy()
    p = np.pad(img, r, constant_values=np.inf)
    h, w = img.shape
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out = np.minimum(out, p[r + dy : r + dy + h, r + dx : r + dx + w])
    return out


def close_gaps(rgb: F, mask: NDArray[np.bool_], passes: int = 2) -> tuple[F, NDArray[np.bool_]]:
    """Fill pixels that sit between samples: a pixel is filled when at least 5 of its 8
    neighbours are, with their mean colour. Edges stay where the surface ends."""
    for _ in range(passes):
        m = np.pad(mask, 1)
        c = np.pad(rgb, ((1, 1), (1, 1), (0, 0)))
        h, w = mask.shape
        count = np.zeros((h, w))
        acc = np.zeros((h, w, 3))
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                mm = m[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
                count += mm
                acc += c[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w] * mm[..., None]
        fill = ~mask & (count >= 5)
        rgb = rgb.copy()
        rgb[fill] = acc[fill] / count[fill][:, None]
        mask = mask | fill
    return rgb, mask
