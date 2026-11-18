"""The per-product fidelity gate.

A 3D asset is built from one listing photo (the main photo). It passes when, from the
best-matching camera, it agrees with every other photo of the whole product (held out):

- silhouette agreement at least `Thresholds.silhouette` (calibrated, see `calibrate`),
- mean colour difference at most `Thresholds.colour` (CIEDE2000, lightness weight 1/2),
  except against photos of a lamp switched on,
- DINOv3 embedding similarity at least `Thresholds.embedding`.

A product with no held-out photo of the whole product is unverifiable, never a pass.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from sajao_catalog.gate.raster import Cloud, render
from sajao_catalog.gate.search import camera, search

F = NDArray[np.float64]

Result = Literal["pass", "fail", "unverifiable"]


@dataclass(frozen=True)
class Thresholds:
    silhouette: float = 0.70
    colour: float = 10.0
    embedding: float = 0.475


# Calibrated per category so that another product's asset passes at most 5% of the time
# (see `calibrate` and the README). Beds: the listing's other photos are styled with
# bedding the asset does not have, so look scores sit lower for the right product too;
# no wrong bed passed at 0.35 (0 of 51 pairs). Proposed in Decisions; until approved,
# `thresholds_for(..., approved_only=True)` keeps the defaults.
CATEGORY: dict[str, Thresholds] = {"bed": Thresholds(embedding=0.35)}


def thresholds_for(category: str, approved_only: bool = False) -> Thresholds:
    return Thresholds() if approved_only else CATEGORY.get(category, Thresholds())


@dataclass
class ViewScore:
    view: str
    silhouette: float
    colour: float
    embedding: float
    lit: bool
    pose: dict[str, float] = field(default_factory=dict)

    def passes(self, th: Thresholds) -> bool:
        return (
            self.silhouette >= th.silhouette
            and self.embedding >= th.embedding
            and (self.lit or self.colour <= th.colour)
        )

    def misses(self, th: Thresholds) -> list[str]:
        out = []
        if self.silhouette < th.silhouette:
            out.append("shape")
        if not self.lit and self.colour > th.colour:
            out.append("colour")
        if self.embedding < th.embedding:
            out.append("look")
        return out


def decide(views: list[ViewScore], th: Thresholds) -> Result:
    if not views:
        return "unverifiable"
    return "pass" if all(v.passes(th) for v in views) else "fail"


def report(views: list[ViewScore], th: Thresholds) -> dict[str, object]:
    return {
        "result": decide(views, th),
        "thresholds": asdict(th),
        "views": [{**asdict(v), "misses": v.misses(th)} for v in views],
    }


def fit_to_listing(vertices: F, dims_cm: dict[str, float]) -> F:
    """Scale an asset (y up) to the listing's size, by code, never by the model. The
    larger horizontal extent takes the larger listed horizontal size, so a model that
    came out turned 90 degrees is not squashed. Sizes the listing does not give keep the
    model's proportions. Centred, base at y = 0."""
    lo, hi = vertices.min(0), vertices.max(0)
    ext = np.maximum(hi - lo, 1e-9)
    horiz = sorted(
        (dims_cm[k] for k in ("width", "depth", "length") if dims_cm.get(k)), reverse=True
    )
    for k in ("diameter", "shade_diameter"):
        if not horiz and dims_cm.get(k):
            horiz = [dims_cm[k], dims_cm[k]]
    big, small = (0, 2) if ext[0] >= ext[2] else (2, 0)
    target = ext.copy()
    if dims_cm.get("height"):
        target[1] = dims_cm["height"] / 100
    if horiz:
        target[big] = horiz[0] / 100
        target[small] = horiz[1] / 100 if len(horiz) > 1 else ext[small] * target[big] / ext[big]
    elif dims_cm.get("height"):
        target[[0, 2]] = ext[[0, 2]] * target[1] / ext[1]
    out: F = (vertices - (lo + hi) / 2) * (target / ext)
    out[:, 1] -= out[:, 1].min()
    return out


def paint_from_photo(
    cloud: Cloud, photo: NDArray[np.float64], photo_mask: NDArray[np.bool_]
) -> Cloud:
    """Colour an untextured asset from its main photo: find the matching camera, give each
    visible point the photo's colour there, and the rest the colour of the nearest
    visible point (always the real photo, never a model's repaint)."""
    from sajao_catalog.gate.metrics import bounding_square

    m = search(cloud, photo, photo_mask)
    size = 512
    w2c = camera(cloud, m.pose)
    p = cloud.points @ w2c[:3, :3].T + w2c[:3, 3]
    f = 0.5 * size / np.tan(np.radians(m.pose.fov) / 2)
    z = np.maximum(p[:, 2], 1e-6)
    px, py = f * p[:, 0] / z + size / 2, f * p[:, 1] / z + size / 2
    _, rmask = render(cloud, w2c, m.pose.fov, size)
    ry, rx = np.nonzero(rmask)
    # render frame -> photo frame through both bounding squares
    r_y0, r_x0, r_side = ry.min(), rx.min(), max(ry.max() - ry.min(), rx.max() - rx.min()) + 1
    p_y0, p_x0, p_side = bounding_square(photo_mask)
    s = p_side / r_side
    qy = ((py - r_y0) * s + p_y0).astype(np.int64)
    qx = ((px - r_x0) * s + p_x0).astype(np.int64)
    h, w = photo_mask.shape
    inside = (qy >= 0) & (qy < h) & (qx >= 0) & (qx < w)
    # visibility: nearest point per photo pixel
    key = np.where(inside, qy * w + qx, -1)
    order = np.lexsort((p[:, 2], key))
    first = np.r_[True, key[order][1:] != key[order][:-1]]
    vis = np.zeros(len(key), bool)
    vis[order[first]] = True
    vis &= inside
    vis[vis] &= photo_mask[qy[vis], qx[vis]]
    colors = cloud.colors.copy()
    if vis.any():
        colors[vis] = photo[qy[vis], qx[vis]]
        from scipy.spatial import cKDTree

        _, nn = cKDTree(cloud.points[vis]).query(cloud.points[~vis], k=1)
        colors[~vis] = colors[vis][nn]
    return Cloud(cloud.points, colors, cloud.normals)


def calibrate(
    true_products: list[list[ViewScore]],
    wrong_pairs: list[list[ViewScore]],
    base: Thresholds,
    max_false_pass: float = 0.05,
) -> tuple[Thresholds, float, float]:
    """Lowest silhouette threshold at which wrong-product pairs pass at most
    `max_false_pass` of the time. Colour and embedding stay as set by the founder.
    Returns (thresholds, true pass rate, wrong pass rate)."""
    best = base
    for s in np.round(np.arange(0.60, 0.96, 0.01), 2):
        th = Thresholds(float(s), base.colour, base.embedding)
        wrong = np.mean([decide(v, th) == "pass" for v in wrong_pairs]) if wrong_pairs else 0.0
        if wrong <= max_false_pass:
            best = th
            break
    true = np.mean([decide(v, best) == "pass" for v in true_products]) if true_products else 0.0
    wrong = np.mean([decide(v, best) == "pass" for v in wrong_pairs]) if wrong_pairs else 0.0
    return best, float(true), float(wrong)
