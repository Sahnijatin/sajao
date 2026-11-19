"""Products composited into the room photo by code: the C3 base of the render (docs/16).

Every product is its gate-checked 3D asset, scaled to its listed size by code
(`fit_to_listing`), placed where the solver put it and seen through the photo's own
camera. No model draws a product, sets its size or moves it. Numpy only: the asset
surface is sampled into points (the assets are dense, so a point is smaller than a
pixel at room distance), projected with a depth buffer, and gaps closed.

Each product gets a soft contact shadow on the floor, and a mask, so the checks can
tell where it is and the light pass can lock its colour.

Frames: the space frame of the twin (metres, z up, floor at 0). Asset files are y up
with the front toward +z; a design item at rotation 0 has its width along +x and its
front toward +y (`sajao_engine.geometry.Rect`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from sajao_catalog.gate.gate import fit_to_listing
from sajao_catalog.gate.raster import Cloud, close_gaps, sample_surface

F = NDArray[np.float64]
B = NDArray[np.bool_]

# Surface points per square metre of asset surface, and the most per product.
POINTS_PER_M2 = 400_000
MAX_POINTS = 2_000_000
# Lighting on the products before the light pass: mostly ambient, a soft key from above.
AMBIENT, KEY = 0.72, 0.30
# Contact shadow: how dark directly under the product, and how far it spreads.
SHADOW_STRENGTH = 0.45
SHADOW_SPREAD_M = 0.12


@dataclass(frozen=True)
class PhotoCamera:
    """The photo's pinhole camera in the space frame (OpenCV axes: x right, y down)."""

    k: F  # 3x3 intrinsics at the photo's size
    rotation: F  # 3x3, camera to space
    position: F  # 3
    width: int
    height: int

    @classmethod
    def from_keyframe(cls, keyframe: Mapping[str, Any]) -> PhotoCamera:
        pose = keyframe["pose"]
        intr = keyframe["intrinsics"]
        x, y, z, w = (float(v) for v in pose["rotation"])
        r = np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )
        p = pose["position"]
        k = np.array(
            [[intr["fx"], 0.0, intr["cx"]], [0.0, intr["fy"], intr["cy"]], [0.0, 0.0, 1.0]]
        )
        return cls(
            k,
            r,
            np.array([p["x_m"], p["y_m"], p["z_m"]], dtype=np.float64),
            int(intr["width_px"]),
            int(intr["height_px"]),
        )

    def scaled(self, width: int, height: int) -> PhotoCamera:
        """The same camera for the photo resized to `width` by `height`."""
        s = np.diag([width / self.width, height / self.height, 1.0])
        return PhotoCamera(s @ self.k, self.rotation, self.position, width, height)

    def project(self, points: F) -> tuple[F, F]:
        """Pixel coordinates (n, 2) and depth along the view (n,) of space points."""
        cam = (points - self.position) @ self.rotation
        z = cam[:, 2]
        safe = np.where(z > 1e-6, z, np.nan)
        uv = np.stack(
            [
                self.k[0, 0] * cam[:, 0] / safe + self.k[0, 2],
                self.k[1, 1] * cam[:, 1] / safe + self.k[1, 2],
            ],
            axis=1,
        )
        return uv, z


@dataclass(frozen=True)
class Placed:
    """One product of a design, ready to draw."""

    key: str  # the design item's id
    cloud: Cloud  # in the space frame
    footprint: F  # (4, 2) corners on the floor


def place_asset(
    vertices: F,
    faces: NDArray[np.int64],
    colors: F,
    size_m: tuple[float, float, float],
    position: tuple[float, float],
    rotation_deg: float,
    key: str,
) -> Placed:
    """The asset fitted to the product's width, depth and height (metres) by code, turned
    and moved to where the design put it."""
    width, depth, height = size_m
    fitted = fit_to_listing(
        np.asarray(vertices, dtype=np.float64),
        {"width": width * 100, "depth": depth * 100, "height": height * 100},
    )
    tri = fitted[faces]
    area = float(
        0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1).sum()
    )
    n = int(min(MAX_POINTS, max(20_000, POINTS_PER_M2 * area)))
    cloud = sample_surface(fitted, faces, colors, n)
    # Asset (x, y up, z front) to the item's own frame (x width, y front, z up).
    to_local = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
    a = math.radians(rotation_deg)
    turn = np.array([[math.cos(a), -math.sin(a), 0.0], [math.sin(a), math.cos(a), 0.0], [0, 0, 1]])
    m = turn @ to_local
    shift = np.array([position[0], position[1], 0.0])
    placed = Cloud(cloud.points @ m.T + shift, cloud.colors, cloud.normals @ m.T)
    hw, hd = width / 2, depth / 2
    corners = np.array([[-hw, -hd], [hw, -hd], [hw, hd], [-hw, hd]]) @ turn[:2, :2].T
    return Placed(key, placed, corners + np.asarray(position))


def _min_filter(img: F, r: int) -> F:
    out = img.copy()
    p = np.pad(img, r, constant_values=np.inf)
    h, w = img.shape
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out = np.minimum(out, p[r + dy : r + dy + h, r + dx : r + dx + w])
    return out


def _blur(img: F, radius: int) -> F:
    """Box blur, repeated three times (close to a Gaussian), edge values extended."""
    out = img.astype(np.float64)
    if radius < 1:
        return out
    for _ in range(3):
        for axis in (0, 1):
            pad = [(0, 0)] * out.ndim
            pad[axis] = (radius + 1, radius)
            c = np.cumsum(np.pad(out, pad, mode="edge"), axis=axis)
            hi = np.take(c, np.arange(2 * radius + 1, c.shape[axis]), axis=axis)
            lo = np.take(c, np.arange(0, c.shape[axis] - 2 * radius - 1), axis=axis)
            out = (hi - lo) / (2 * radius + 1)
    return out


def _fill_polygon(poly: F, shape: tuple[int, int]) -> B:
    """Pixels inside a convex polygon given in pixel coordinates."""
    h, w = shape
    ys, xs = np.mgrid[0:h, 0:w]
    inside = np.ones(shape, dtype=bool)
    n = len(poly)
    area = sum(
        poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n)
    )
    sign = 1.0 if area > 0 else -1.0
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        inside &= sign * ((x1 - x0) * (ys + 0.5 - y0) - (y1 - y0) * (xs + 0.5 - x0)) >= 0
    return inside


@dataclass(frozen=True)
class Composite:
    image: F  # (h, w, 3) in 0..1
    masks: dict[str, B]  # every product's visible pixels, by design item id
    depth: F  # (h, w) metres along the view where a product is drawn, inf elsewhere


def contact_shadow(camera: PhotoCamera, footprint: F) -> F:
    """How much to darken each pixel (0..SHADOW_STRENGTH) for a product standing on
    `footprint`: its floor outline, grown and softened, seen from the camera."""
    centre = footprint.mean(axis=0)
    grown = centre + (footprint - centre) * 1.0
    edge = []
    for i in range(len(grown)):
        a, b = grown[i], grown[(i + 1) % len(grown)]
        for t in np.linspace(0, 1, 8, endpoint=False):
            edge.append(a + t * (b - a))
    floor = np.array([[x, y, 0.0] for x, y in edge])
    uv, z = camera.project(floor)
    if np.any(~np.isfinite(uv)) or np.any(z <= 0):
        return np.zeros((camera.height, camera.width))
    hull = _hull(uv)
    core = _fill_polygon(hull, (camera.height, camera.width)).astype(np.float64)
    # The spread in pixels at the footprint's distance.
    dist = float(np.median(z))
    radius = max(1, int(SHADOW_SPREAD_M * camera.k[0, 0] / max(dist, 0.3) / 2))
    return np.clip(_blur(core, radius) * SHADOW_STRENGTH, 0.0, SHADOW_STRENGTH)


def _hull(points: F) -> F:
    pts = sorted({(float(x), float(y)) for x, y in points})
    if len(pts) < 3:
        return np.array(pts)

    def half(seq: list[tuple[float, float]]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for p in seq:
            while (
                len(out) >= 2
                and (
                    (out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                    - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])
                )
                <= 0
            ):
                out.pop()
            out.append(p)
        return out

    return np.array(half(pts)[:-1] + half(pts[::-1])[:-1])


def composite(
    photo: F,
    camera: PhotoCamera,
    products: Sequence[Placed],
    occluders: B | None = None,
) -> Composite:
    """The products drawn into `photo` (h, w, 3 in 0..1), nearest first, with contact
    shadows under them. `occluders`: pixels of kept things in front of everything new
    (from the twin's hero masks), never drawn over."""
    h, w = photo.shape[:2]
    cam = camera if (camera.width, camera.height) == (w, h) else camera.scaled(w, h)
    shade = np.zeros((h, w))
    for p in products:
        shade = np.maximum(shade, contact_shadow(cam, p.footprint))
    image = photo * (1.0 - shade[..., None])
    zbuf = np.full(h * w, np.inf)
    colour = np.zeros((h * w, 3))
    owner = np.full(h * w, -1)
    key_light = np.array([0.3, -0.4, 0.86])
    key_light /= np.linalg.norm(key_light)
    for index, p in enumerate(products):
        uv, z = cam.project(p.cloud.points)
        ok = np.isfinite(uv).all(axis=1) & (z > 0.05)
        px = np.floor(uv[ok, 0]).astype(np.int64)
        py = np.floor(uv[ok, 1]).astype(np.int64)
        inside = (px >= 0) & (px < w) & (py >= 0) & (py < h)
        idx = (py * w + px)[inside]
        depth = z[ok][inside]
        normals = p.cloud.normals[ok][inside]
        colours = p.cloud.colors[ok][inside]
        order = np.lexsort((depth, idx))
        idx, first = np.unique(idx[order], return_index=True)
        depth, normals, colours = depth[order][first], normals[order][first], colours[order][first]
        nearer = depth < zbuf[idx]
        idx, depth = idx[nearer], depth[nearer]
        lit = AMBIENT + KEY * np.abs(normals[nearer] @ key_light)
        zbuf[idx] = depth
        colour[idx] = np.clip(colours[nearer] * lit[:, None], 0.0, 1.0)
        owner[idx] = index
    zimg = zbuf.reshape(h, w)
    # Far samples seen through gaps between near ones: drop, then fill from neighbours.
    finite = np.isfinite(zimg)
    behind = finite & (zimg > _min_filter(zimg, 2) + 0.05)
    zimg[behind] = np.inf
    rgb, drawn = close_gaps(colour.reshape(h, w, 3), np.isfinite(zimg), passes=3)
    own = owner.reshape(h, w).copy()
    own[behind] = -1
    # Filled gap pixels take the owner most of their neighbours have.
    for _ in range(3):
        missing = drawn & (own < 0)
        if not missing.any():
            break
        padded = np.pad(own, 1, constant_values=-1)
        best = np.full((h, w), -1)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                n = padded[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
                best = np.where((best < 0) & (n >= 0), n, best)
        own = np.where(missing, best, own)
    if occluders is not None:
        drawn &= ~occluders
    masks = {p.key: drawn & (own == i) for i, p in enumerate(products)}
    image = np.where(drawn[..., None], rgb, image)
    return Composite(image, masks, np.where(drawn, zimg, np.inf))
