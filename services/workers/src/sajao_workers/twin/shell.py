"""The room shell's doors, windows and surface textures, from the keyframes.

Openings: a door or window mask in a keyframe is turned into rays from the
camera; each ray is intersected with the fitted wall planes, and the nearest
wall it hits names the wall. Rays, not depth, because depth through glass or
an open door lands outside the room. Per frame the hits give an interval along
the wall and a vertical interval; intervals of the same kind on the same wall
are fused across frames, and an opening seen in fewer than MIN_FRAMES frames is
dropped. Code measures every size; no model sets one.

Textures: each wall, the floor and the ceiling is sampled on a grid; each grid
point is projected into the keyframes, and the frame that sees it most squarely
and closely, with nothing in front (depth) and no object over it (object masks),
gives its colour.

All geometry is in the space frame (z up from the floor, see twin/space.py).
Keyframe poses are camera-to-world in the AR world with OpenCV camera axes.
"""

import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from PIL import Image

from sajao_workers.twin.space import DepthSource, Space

OpeningKind = Literal["door", "window"]
MIN_FRAMES = 2
MIN_HITS = 50  # rays on one wall for a frame to count
RAY_STRIDE = 4  # pixels between rays
# (floor in metres, fraction of the size): mask edges and the wall fit add to depth error.
OPENING_BANDS: dict[DepthSource, tuple[float, float]] = {
    "lidar": (0.05, 0.05),
    "image": (0.08, 0.08),
}
TEXELS_PER_M = 100
MIN_FACING = 0.35  # cosine of the view angle to the surface (about 70 degrees off square)
# Plausible openings (metres): smaller ones are frames, mirrors or mask fragments.
MIN_SIZE: dict[str, tuple[float, float]] = {"door": (0.5, 1.6), "window": (0.3, 0.3)}
JOIN_GAP_M = 0.15  # panes of one window this close along the wall are one window
MAX_TEXTURE_PX = 2048


@dataclass(frozen=True)
class Frame:
    """One keyframe's geometry: intrinsics (pixels), camera to world, image size."""

    k: np.ndarray
    c2w: np.ndarray
    width: int
    height: int


@dataclass(frozen=True)
class OpeningSighting:
    kind: OpeningKind
    wall_id: str
    along: tuple[float, float]  # metres from the wall's start
    vertical: tuple[float, float]  # metres above the floor


def _walls(shell: Mapping[str, Any]) -> list[tuple[str, np.ndarray, np.ndarray, float]]:
    out = []
    for w in shell["walls"]:
        if w.get("kind") == "open":
            continue  # nothing hangs on an edge with no wall
        s = np.array([w["start"]["x_m"], w["start"]["y_m"]])
        e = np.array([w["end"]["x_m"], w["end"]["y_m"]])
        length = float(np.linalg.norm(e - s))
        out.append((w["id"], s, (e - s) / length, length))
    return out


def _extent(values: np.ndarray, trim: float = 1.0) -> tuple[float, float]:
    """Ends of a spread of hits, robust to a few stray rays: the 1st to 99th percentile,
    widened back to the whole spread (rays are spread evenly over an opening)."""
    lo, hi = np.percentile(values, [trim, 100.0 - trim])
    centre, half = (lo + hi) / 2, (hi - lo) / 2 / (1.0 - 2 * trim / 100.0)
    return float(centre - half), float(centre + half)


def sight_opening(
    kind: OpeningKind, mask: np.ndarray, frame: Frame, space: Space
) -> OpeningSighting | None:
    """Where one mask of a door or window lies on the walls, or None if it hits none."""
    shell = space.shell
    ceiling = float(shell["ceiling_height"]["value_m"])
    ys, xs = np.nonzero(mask[::RAY_STRIDE, ::RAY_STRIDE])
    if len(xs) == 0:
        return None
    u, v = xs * RAY_STRIDE + 0.5, ys * RAY_STRIDE + 0.5
    rays = np.stack([(u - frame.k[0, 2]) / frame.k[0, 0], (v - frame.k[1, 2]) / frame.k[1, 1],
                     np.ones_like(u)], axis=1)  # fmt: skip
    origin = np.asarray(space.point(frame.c2w[:3, 3]))
    directions = (space.rotation @ frame.c2w[:3, :3] @ rays.T).T
    best_t = np.full(len(rays), np.inf)
    best_wall = np.full(len(rays), -1)
    best_along = np.zeros(len(rays))
    walls = _walls(shell)
    for i, (_, start, d, length) in enumerate(walls):
        normal = np.array([-d[1], d[0]])
        denominator = directions[:, :2] @ normal
        with np.errstate(divide="ignore", invalid="ignore"):
            t = ((start - origin[:2]) @ normal) / denominator
        hit = origin + t[:, None] * directions
        along = (hit[:, :2] - start) @ d
        ok = (
            np.isfinite(t)
            & (t > 0.1)
            & (along >= -0.2)
            & (along <= length + 0.2)
            & (hit[:, 2] >= -0.1)
            & (hit[:, 2] <= ceiling + 0.1)
            & (t < best_t)
        )
        best_t = np.where(ok, t, best_t)
        best_wall = np.where(ok, i, best_wall)
        best_along = np.where(ok, along, best_along)
    hits = best_wall >= 0
    if hits.sum() < MIN_HITS:
        return None
    wall = int(np.bincount(best_wall[hits]).argmax())
    on = best_wall == wall
    if on.sum() < MIN_HITS:
        return None
    z = origin[2] + best_t[on] * directions[on, 2]
    _, _, _, length = walls[wall]
    a0, a1 = _extent(best_along[on])
    z0, z1 = _extent(z)
    return OpeningSighting(
        kind,
        walls[wall][0],
        (max(0.0, float(a0)), min(length, float(a1))),
        (max(0.0, float(z0)), min(ceiling, float(z1))),
    )


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    inner = min(a[1], b[1]) - max(a[0], b[0])
    return max(0.0, inner) / max(1e-6, min(a[1] - a[0], b[1] - b[0]))


def _dimension(value: float, depth_source: DepthSource) -> dict[str, Any]:
    floor, fraction = OPENING_BANDS[depth_source]
    return {
        "value_m": round(value, 3),
        "source": "estimated",
        "error_band_m": round(max(floor, fraction * value), 3),
    }


def fuse_openings(
    sightings: Sequence[OpeningSighting], depth_source: DepthSource, min_frames: int = MIN_FRAMES
) -> list[dict[str, Any]]:
    """Openings seen in at least `min_frames` frames (1 for a single photo), as SpaceTwin
    openings."""
    groups: list[list[OpeningSighting]] = []
    for s in sightings:
        for group in groups:
            first = group[0]
            if (
                first.kind == s.kind
                and first.wall_id == s.wall_id
                and any(_overlap(g.along, s.along) >= 0.5 for g in group)
            ):
                group.append(s)
                break
        else:
            groups.append([s])
    fused: list[tuple[str, str, float, float, float, float]] = []
    for group in groups:
        if len(group) < min_frames:
            continue
        a0, a1, z0, z1 = np.median(
            [[g.along[0], g.along[1], g.vertical[0], g.vertical[1]] for g in group], axis=0
        )
        fused.append((group[0].kind, group[0].wall_id, float(a0), float(a1), float(z0), float(z1)))
    # Join panes: same kind and wall, touching along the wall, overlapping in height.
    fused.sort(key=lambda f: (f[0], f[1], f[2]))
    joined: list[tuple[str, str, float, float, float, float]] = []
    for f in fused:
        last = joined[-1] if joined else None
        if (
            last
            and last[:2] == f[:2]
            and f[2] - last[3] <= JOIN_GAP_M
            and _overlap((last[4], last[5]), (f[4], f[5])) > 0.5
        ):
            joined[-1] = (
                f[0],
                f[1],
                last[2],
                max(last[3], f[3]),
                min(last[4], f[4]),
                max(last[5], f[5]),
            )
        else:
            joined.append(f)
    openings = []
    for kind, wall_id, a0, a1, z0, z1 in joined:
        min_width, min_height = MIN_SIZE[kind]
        height = z1 if kind == "door" else z1 - z0
        if a1 - a0 < min_width or height < min_height:
            continue
        opening: dict[str, Any] = {
            "kind": kind,
            "wall_id": wall_id,
            "offset": _dimension(a0, depth_source),
            "width": _dimension(a1 - a0, depth_source),
        }
        if kind == "door":
            opening["height"] = _dimension(z1, depth_source)  # from the floor
        else:
            opening["height"] = _dimension(z1 - z0, depth_source)
            opening["sill_height"] = _dimension(z0, depth_source)
        openings.append(opening)
    openings.sort(key=lambda o: (o["wall_id"], o["offset"]["value_m"]))
    for kind in ("door", "window"):
        for n, o in enumerate((o for o in openings if o["kind"] == kind), start=1):
            o["id"] = f"{'d' if kind == 'door' else 'win'}{n}"
    return [{"id": o.pop("id"), **o} for o in openings]


def surface_rectangles(space: Space) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Each surface as (corner, first edge, second edge) in the space frame."""
    shell = space.shell
    height = float(shell["ceiling_height"]["value_m"])
    out = {}
    for wall_id, start, d, length in _walls(shell):
        corner = np.array([start[0], start[1], 0.0])
        out[wall_id] = (
            corner,
            np.array([d[0] * length, d[1] * length, 0.0]),
            np.array([0, 0, height]),
        )
    xs = [p["x_m"] for p in shell["floor_polygon"]]
    ys = [p["y_m"] for p in shell["floor_polygon"]]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    out["floor"] = (np.array([x0, y0, 0.0]), np.array([x1 - x0, 0, 0]), np.array([0, y1 - y0, 0]))
    out["ceiling"] = (
        np.array([x0, y0, height]),
        np.array([x1 - x0, 0, 0]),
        np.array([0, y1 - y0, 0]),
    )
    return out


def _rescale(index: np.ndarray, size: int, other: int) -> np.ndarray:
    """Pixel indices in an image of `size` mapped to one of `other` (same view)."""
    scaled: np.ndarray = np.minimum((index * other / size).astype(int), other - 1)
    return scaled


class TextureBuilder:
    """Builds one surface's texture a keyframe at a time (so frames need not all be in memory).

    For each grid point, the frame that sees it most squarely and closely wins, if
    nothing is in front of it (depth) and no object covers it (object masks).
    """

    def __init__(self, rectangle: tuple[np.ndarray, np.ndarray, np.ndarray], space: Space):
        corner, edge_u, edge_v = rectangle
        lu, lv = float(np.linalg.norm(edge_u)), float(np.linalg.norm(edge_v))
        scale = min(TEXELS_PER_M, MAX_TEXTURE_PX / max(lu, lv))
        self.nu, self.nv = max(2, int(lu * scale)), max(2, int(lv * scale))
        gu, gv = np.meshgrid(
            (np.arange(self.nu) + 0.5) / self.nu, (np.arange(self.nv) + 0.5) / self.nv
        )
        self.points = corner + gu.reshape(-1, 1) * edge_u + gv.reshape(-1, 1) * edge_v
        normal = np.cross(edge_u, edge_v)
        self.normal = normal / np.linalg.norm(normal)
        self.space = space
        self.world = (self.points + space.origin) @ space.rotation  # the inverse of Space.point
        self.best = np.zeros(len(self.points))
        self.colour = np.zeros((len(self.points), 3), np.uint8)

    def add(
        self, frame: Frame, image: np.ndarray, depth: np.ndarray | None, blocked: np.ndarray | None
    ) -> None:
        w2c = np.linalg.inv(frame.c2w)
        cam = self.world @ w2c[:3, :3].T + w2c[:3, 3]
        z = cam[:, 2]
        # Images may be stored smaller than the intrinsics' size: scale to the image.
        sx, sy = image.shape[1] / frame.width, image.shape[0] / frame.height
        with np.errstate(divide="ignore", invalid="ignore"):
            u = (frame.k[0, 0] * cam[:, 0] / z + frame.k[0, 2]) * sx
            v = (frame.k[1, 1] * cam[:, 1] / z + frame.k[1, 2]) * sy
        h, w = image.shape[:2]
        inside = (z > 0.2) & (u >= 0) & (u < w - 1) & (v >= 0) & (v < h - 1)
        ui = np.clip(np.nan_to_num(u), 0, w - 1).astype(int)
        vi = np.clip(np.nan_to_num(v), 0, h - 1).astype(int)
        if depth is not None:
            seen = depth[
                (vi * depth.shape[0] / h).astype(int), (ui * depth.shape[1] / w).astype(int)
            ]
            inside &= (seen <= 0) | (seen >= z - np.maximum(0.05, 0.05 * z))
        if blocked is not None:
            inside &= ~blocked[
                (vi * blocked.shape[0] / h).astype(int), (ui * blocked.shape[1] / w).astype(int)
            ]
        camera = self.space.rotation @ frame.c2w[:3, 3] - self.space.origin
        to_camera = camera[None, :] - self.points
        distance = np.linalg.norm(to_camera, axis=1)
        facing = np.abs(to_camera @ self.normal) / np.maximum(distance, 1e-6)
        inside &= facing >= MIN_FACING  # glancing views smear texels into streaks
        weight = np.where(inside, facing / np.maximum(distance, 0.3), 0.0)
        take = weight > self.best
        self.best = np.where(take, weight, self.best)
        self.colour[take] = image[vi[take], ui[take]]

    def result(self) -> tuple[np.ndarray, float]:
        """The texture (row 0 is the far edge of the second axis, the top of a wall) and the
        share of it seen; unseen texels take the median colour of the seen ones."""
        colour = self.colour.copy()
        seen = self.best > 0
        if seen.any():
            colour[~seen] = np.median(colour[seen], axis=0).astype(np.uint8)
        return colour.reshape(self.nv, self.nu, 3)[::-1], float(seen.mean())


def surface_texture(
    rectangle: tuple[np.ndarray, np.ndarray, np.ndarray],
    frames: Sequence[Frame],
    images: Sequence[np.ndarray],
    depths: Sequence[np.ndarray | None],
    blocked: Sequence[np.ndarray | None],
    space: Space,
) -> tuple[np.ndarray, float]:
    """RGB texture of one surface rectangle, and the share of it seen in some frame."""
    builder = TextureBuilder(rectangle, space)
    for frame, image, depth, mask in zip(frames, images, depths, blocked, strict=True):
        builder.add(frame, image, depth, mask)
    return builder.result()


def jpeg(rgb: np.ndarray, quality: int = 85) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def frame_of(record: Mapping[str, Any]) -> Frame:
    return Frame(
        np.asarray(record["intrinsics"], dtype=np.float64),
        np.asarray(record["c2w"], dtype=np.float64),
        int(record["width"]),
        int(record["height"]),
    )
