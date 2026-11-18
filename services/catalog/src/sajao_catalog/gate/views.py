"""Which listing photos can check a product.

A check photo shows one whole product, as sold. Dimension drawings, detail close-ups,
photos with other furniture in them and (for colour) photos of a lamp switched on do not:
judging an asset against them fails good assets or passes bad ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

Use = Literal["check", "drawing", "crop", "several_objects", "too_small"]


@dataclass(frozen=True)
class ViewInfo:
    use: Use
    lit: bool  # a lamp photographed switched on: shape and look count, colour does not


F = NDArray[np.float64]


def _hsv(rgb: NDArray[np.uint8]) -> tuple[F, F, F]:
    x = rgb.astype(np.float64) / 255
    mx, mn = x.max(-1), x.min(-1)
    v = mx
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0)
    d = np.maximum(mx - mn, 1e-9)
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    return h, s, v


def _components(mask: NDArray[np.bool_]) -> list[int]:
    """Sizes of the 4-connected components, largest first (small masks only)."""
    h, w = mask.shape
    seen = np.zeros_like(mask)
    sizes = []
    for y, x in zip(*np.nonzero(mask), strict=True):
        if seen[y, x]:
            continue
        stack, n = [(y, x)], 0
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            n += 1
            for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        sizes.append(n)
    return sorted(sizes, reverse=True)


def classify(rgba: NDArray[np.uint8], category: str) -> ViewInfo:
    """`rgba`: the listing photo with the product cut out (alpha = product)."""
    mask = rgba[..., 3] > 127
    h, w = mask.shape
    if mask.sum() < 0.01 * h * w:
        return ViewInfo("too_small", False)
    hue, sat, val = _hsv(rgba[..., :3])
    s, v = sat[mask], val[mask]
    coloured = float((s > 40 / 255).mean())
    mid = float(((v > 110 / 255) & (v < 235 / 255)).mean())
    white = float(((v >= 235 / 255) & (s <= 20 / 255)).mean())
    dark = float((v < 0.35).mean())
    # Line art: dark lines, almost no colour and almost no mid-tones; or a white drawing
    # with a few labels. A photo of a white product has shading but no dark lines.
    # Dimension drawings carry blue labels: saturated blue on line art with few mid-tones.
    blue = float(((hue[mask] >= 190) & (hue[mask] <= 250) & (s >= 0.3)).mean())
    if (
        (dark >= 0.04 and coloured <= 0.08 and mid <= 0.16)
        or (dark >= 0.04 and coloured <= 0.15 and white >= 0.6 and mid <= 0.12)
        or (blue >= 0.02 and mid <= 0.3)
    ):
        return ViewInfo("drawing", False)
    ys, xs = np.nonzero(mask)
    m = 2
    edges = (ys.min() <= m, xs.min() <= m, ys.max() >= h - 1 - m, xs.max() >= w - 1 - m)
    touches = sum(map(int, edges))
    if touches >= 2:
        return ViewInfo("crop", False)
    small = mask[:: max(1, h // 128), :: max(1, w // 128)]
    comps = _components(small)
    if len(comps) > 1 and comps[1] >= 0.2 * comps[0]:
        return ViewInfo("several_objects", False)
    lit = False
    if category in {"floor_lamp", "table_lamp", "lamp"}:
        bright = mask & (val >= 0.93)
        if bright.sum() >= 0.08 * mask.sum():
            hb, sb = hue[bright], sat[bright]
            warm = (hb >= 15) & (hb <= 55) & (sb >= 0.12)
            lit = bool(warm.mean() >= 0.5) or bool((val[mask] >= 0.995).mean() >= 0.25)
    return ViewInfo("check", lit)
