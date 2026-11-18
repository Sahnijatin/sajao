"""Comparisons between a rendered asset and a listing photo."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

F = NDArray[np.float64]
B = NDArray[np.bool_]


def bounding_square(mask: B) -> tuple[int, int, int]:
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    side = max(y1 - y0, x1 - x0)
    return int((y0 + y1 - side) // 2), int((x0 + x1 - side) // 2), int(side)


def to_square(img: F | B, mask: B, size: int) -> tuple[F, B]:
    """Crop to the mask's bounding square (padding outside the image) and resample to
    `size` by nearest neighbour, so position and scale no longer matter."""
    y0, x0, side = bounding_square(mask)
    idx = (np.arange(size) + 0.5) * side / size
    rows = (y0 + idx).astype(np.int64)
    cols = (x0 + idx).astype(np.int64)
    h, w = mask.shape
    rin = (rows >= 0) & (rows < h)
    cin = (cols >= 0) & (cols < w)
    rr, cc = np.clip(rows, 0, h - 1), np.clip(cols, 0, w - 1)
    valid = rin[:, None] & cin[None, :]
    m = mask[rr][:, cc] & valid
    if img.ndim == 3:
        out = np.where(valid[..., None], img[rr][:, cc], 1.0).astype(np.float64)
    else:
        out = np.where(valid, img[rr][:, cc], False)
    return out, m


def dilate(mask: B, r: int) -> B:
    if r <= 0:
        return mask
    out = mask.copy()
    h, w = mask.shape
    p = np.pad(mask, r)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy * dy + dx * dx <= r * r:
                out |= p[r + dy : r + dy + h, r + dx : r + dx + w]
    return out


def silhouette(a: B, b: B, tolerance: float = 0.02) -> float:
    """Shape agreement of two masks already in bounding squares of the same size: the
    share of each mask's pixels that lie within `tolerance` (of the side) of the other.
    Equal to 1 for identical shapes; unlike IoU, a thin leg one pixel off still agrees."""
    r = max(1, round(tolerance * a.shape[0]))
    na, nb = a.sum(), b.sum()
    if na == 0 or nb == 0:
        return 0.0
    return float(((a & dilate(b, r)).sum() + (b & dilate(a, r)).sum()) / (na + nb))


def iou(a: B, b: B) -> float:
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def srgb_to_lab(rgb: F) -> F:
    """sRGB in 0..1 to CIE Lab (D65)."""
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    m = np.array(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ]
    )
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    x, y, z = f[..., 0], f[..., 1], f[..., 2]
    return np.stack([116 * y - 16, 500 * (x - y), 200 * (y - z)], -1)


def ciede2000(lab1: F, lab2: F, kl: float = 1.0) -> float:
    """CIEDE2000 between two Lab colours."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c1, c2 = np.hypot(a1, b1), np.hypot(a2, b2)
    cm = (c1 + c2) / 2
    g = 0.5 * (1 - np.sqrt(cm**7 / (cm**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dl, dc = l2 - l1, c2p - c1p
    dh = h2p - h1p
    if c1p * c2p == 0:
        dh = 0.0
    elif dh > 180:
        dh -= 360
    elif dh < -180:
        dh += 360
    dH = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh / 2))
    lm, cpm = (l1 + l2) / 2, (c1p + c2p) / 2
    hs = h1p + h2p
    if c1p * c2p == 0:
        hm = hs
    elif abs(h1p - h2p) <= 180:
        hm = hs / 2
    else:
        hm = (hs + 360) / 2 if hs < 360 else (hs - 360) / 2
    t = (
        1
        - 0.17 * np.cos(np.radians(hm - 30))
        + 0.24 * np.cos(np.radians(2 * hm))
        + 0.32 * np.cos(np.radians(3 * hm + 6))
        - 0.20 * np.cos(np.radians(4 * hm - 63))
    )
    sl = 1 + 0.015 * (lm - 50) ** 2 / np.sqrt(20 + (lm - 50) ** 2)
    sc, sh = 1 + 0.045 * cpm, 1 + 0.015 * cpm * t
    rt = (
        -2
        * np.sqrt(cpm**7 / (cpm**7 + 25**7))
        * np.sin(np.radians(60 * np.exp(-(((hm - 275) / 25) ** 2))))
    )
    return float(
        np.sqrt(
            (dl / (kl * sl)) ** 2 + (dc / sc) ** 2 + (dH / sh) ** 2 + rt * (dc / sc) * (dH / sh)
        )
    )


def mean_colour_difference(rgb1: F, m1: B, rgb2: F, m2: B) -> float:
    """CIEDE2000 between the mean Lab colours of two regions. Lightness counts half
    (kl=2): a studio photo and a render are lit differently."""
    if not m1.any() or not m2.any():
        return float("inf")
    return ciede2000(srgb_to_lab(rgb1[m1]).mean(0), srgb_to_lab(rgb2[m2]).mean(0), kl=2.0)
