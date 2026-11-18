"""Gate one product: its listing photos (cut out), its 3D asset and its listing size in,
a pass, fail or unverifiable report out.

Models are injected so the scoring runs anywhere: `embed` turns images (uint8 RGB on
white) into unit vectors. Photo cut-outs and the asset are made before this step.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from sajao_catalog.gate.gate import (
    Thresholds,
    ViewScore,
    fit_to_listing,
    paint_from_photo,
    report,
    thresholds_for,
)
from sajao_catalog.gate.metrics import to_square
from sajao_catalog.gate.raster import Cloud, sample_surface
from sajao_catalog.gate.search import search
from sajao_catalog.gate.views import classify

Embed = Callable[[list[NDArray[np.uint8]]], NDArray[np.float64]]
EMBED_SIZE = 448
POINTS = 300_000
# A held-out photo that looks less like the main photo than this shows part of the
# product or a room around it, not the product as sold (see the README for the data).
SAME_PRODUCT = 0.45


@dataclass(frozen=True)
class Mesh:
    vertices: NDArray[np.float64]
    faces: NDArray[np.int64]
    colors: NDArray[np.float64] | None  # per vertex, 0..1; None when untextured


def on_white(rgb: NDArray[np.float64], mask: NDArray[np.bool_]) -> NDArray[np.uint8]:
    img, m = to_square(rgb, mask, EMBED_SIZE)
    img = img.copy()
    img[~m] = 1.0
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def split(rgba: NDArray[np.uint8]) -> tuple[NDArray[np.float64], NDArray[np.bool_]]:
    return rgba[..., :3].astype(np.float64) / 255, rgba[..., 3] > 127


def select_views(
    photos: dict[str, NDArray[np.uint8]], main: str, category: str, embed: Embed
) -> tuple[dict[str, dict[str, object]], list[str]]:
    """Classify every photo; keep held-out photos of the whole product."""
    info: dict[str, dict[str, object]] = {}
    cls = {n: classify(photos[n], category) for n in photos}
    if cls[main].use == "too_small":
        return {main: {"use": "too_small", "lit": False}}, []
    names = sorted(n for n in photos if cls[n].use != "too_small")
    embs = embed([on_white(*split(photos[n])) for n in names])
    sims = dict(zip(names, (float(e @ embs[names.index(main)]) for e in embs), strict=True))
    keep = []
    for n in sorted(photos):
        v = cls[n]
        use: str = v.use
        if n == main:
            use = "main"
        elif use == "check" and sims[n] < SAME_PRODUCT:
            use = "part_or_scene"
        info[n] = {"use": use, "lit": v.lit, "similar_to_main": round(sims.get(n, 0.0), 3)}
        if use == "check":
            keep.append(n)
    return info, keep


def build_cloud(mesh: Mesh, dims_cm: dict[str, float], main: NDArray[np.uint8]) -> Cloud:
    v = fit_to_listing(mesh.vertices, dims_cm)
    cols = mesh.colors if mesh.colors is not None else np.full((len(v), 3), 0.7)
    cloud = sample_surface(v, mesh.faces, cols, POINTS)
    if mesh.colors is None:
        cloud = paint_from_photo(cloud, *split(main))
    return cloud


def gate_product(
    photos: dict[str, NDArray[np.uint8]],
    main: str,
    category: str,
    dims_cm: dict[str, float],
    mesh: Mesh,
    embed: Embed,
    thresholds: Thresholds | None = None,
    views: tuple[dict[str, dict[str, object]], list[str]] | None = None,
) -> dict[str, object]:
    """`photos`: cut-outs (RGBA, alpha = product) by name; `main` is the one the asset
    was built from. Pass `views` to reuse a selection (wrong-product calibration)."""
    th = thresholds or thresholds_for(category)
    info, keep = views or select_views(photos, main, category, embed)
    cloud = build_cloud(mesh, dims_cm, photos[main])
    scores = []
    for n in keep:
        rgb, mask = split(photos[n])
        m = search(cloud, rgb, mask)
        e = embed([on_white(m.render, m.render_mask), on_white(rgb, mask)])
        scores.append(
            ViewScore(
                view=n,
                silhouette=round(m.silhouette, 4),
                colour=round(m.colour, 3),
                embedding=round(float(e[0] @ e[1]), 4),
                lit=bool(info[n]["lit"]),
                pose={"azimuth": m.pose.azimuth, "elevation": m.pose.elevation, "fov": m.pose.fov},
            )
        )
    return {**report(scores, th), "photos": info}
