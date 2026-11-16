"""Image and mask metrics shared by the fidelity gate and the render checks.

Pure numpy, no GPU, tested in CI.
"""

from __future__ import annotations

import numpy as np


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.astype(bool), b.astype(bool)
    union = (a | b).sum()
    return float((a & b).sum() / union) if union else 0.0


def bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """(x0, y0, x1, y1), exclusive ends, or None for an empty mask."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def max_edge_shift(a: np.ndarray, b: np.ndarray) -> float:
    """Largest move, in pixels, of any side of the two masks' bounding boxes."""
    ba, bb = bbox(a), bbox(b)
    if ba is None or bb is None:
        return float("inf")
    return float(max(abs(x - y) for x, y in zip(ba, bb, strict=True)))


def square_crop(mask: np.ndarray, margin: float = 0.05) -> tuple[int, int, int]:
    """Square around the mask's bounding box: (x0, y0, side). May extend past the image."""
    x0, y0, x1, y1 = bbox(mask) or (0, 0, mask.shape[1], mask.shape[0])
    side = round(max(x1 - x0, y1 - y0) * (1 + 2 * margin))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return round(cx - side / 2), round(cy - side / 2), max(side, 1)


def crop_pad(img: np.ndarray, x0: int, y0: int, side: int, fill: float | int = 0) -> np.ndarray:
    """Crop a square that may extend past the image, padding with `fill`."""
    h, w = img.shape[:2]
    out = np.full((side, side, *img.shape[2:]), fill, dtype=img.dtype)
    sx0, sy0 = max(x0, 0), max(y0, 0)
    sx1, sy1 = min(x0 + side, w), min(y0 + side, h)
    if sx1 > sx0 and sy1 > sy0:
        out[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = img[sy0:sy1, sx0:sx1]
    return out


# ---------- colour ----------


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB in 0..1 (any shape ending in 3) to CIE Lab (D65)."""
    c = np.asarray(rgb, dtype=np.float64)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ]
    )
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    e = 216 / 24389
    k = 24389 / 27
    f = np.where(xyz > e, np.cbrt(xyz), (k * xyz + 16) / 116)
    lab = np.stack(
        [116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1
    )
    return lab


def ciede2000(lab1: np.ndarray, lab2: np.ndarray, kl: float = 1.0) -> np.ndarray:
    """CIEDE2000 colour difference (Sharma et al. 2005). `kl` > 1 down-weights lightness."""
    l1, a1, b1 = np.moveaxis(np.asarray(lab1, dtype=np.float64), -1, 0)
    l2, a2, b2 = np.moveaxis(np.asarray(lab2, dtype=np.float64), -1, 0)
    c1, c2 = np.hypot(a1, b1), np.hypot(a2, b2)
    cbar = (c1 + c2) / 2
    g = 0.5 * (1 - np.sqrt(cbar**7 / (cbar**7 + 25.0**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dlp, dcp = l2 - l1, c2p - c1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(c1p * c2p == 0, 0, dh)
    dhp = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh / 2))
    lbp, cbp = (l1 + l2) / 2, (c1p + c2p) / 2
    hs = h1p + h2p
    hbp = np.where(
        c1p * c2p == 0,
        hs,
        np.where(
            np.abs(h1p - h2p) <= 180, hs / 2, np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)
        ),
    )
    t = (
        1
        - 0.17 * np.cos(np.radians(hbp - 30))
        + 0.24 * np.cos(np.radians(2 * hbp))
        + 0.32 * np.cos(np.radians(3 * hbp + 6))
        - 0.20 * np.cos(np.radians(4 * hbp - 63))
    )
    dtheta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    rc = 2 * np.sqrt(cbp**7 / (cbp**7 + 25.0**7))
    sl = 1 + 0.015 * (lbp - 50) ** 2 / np.sqrt(20 + (lbp - 50) ** 2)
    sc = 1 + 0.045 * cbp
    sh = 1 + 0.015 * cbp * t
    rt = -np.sin(np.radians(2 * dtheta)) * rc
    return np.asarray(
        np.sqrt(
            (dlp / (kl * sl)) ** 2
            + (dcp / sc) ** 2
            + (dhp / sh) ** 2
            + rt * (dcp / sc) * (dhp / sh)
        ),
        dtype=np.float64,
    )


def mean_color_delta_e(
    img1: np.ndarray, m1: np.ndarray, img2: np.ndarray, m2: np.ndarray, kl: float = 2.0
) -> float:
    """CIEDE2000 between the mean Lab colours of two masked regions (uint8 RGB).

    Lightness is down-weighted (kl=2) because renders and photos are lit differently.
    """
    if m1.sum() == 0 or m2.sum() == 0:
        return float("inf")
    lab1 = srgb_to_lab(img1[m1.astype(bool)].astype(np.float64) / 255).mean(0)
    lab2 = srgb_to_lab(img2[m2.astype(bool)].astype(np.float64) / 255).mean(0)
    return float(ciede2000(lab1, lab2, kl=kl))


# ---------- structure ----------


def edge_f1(e1: np.ndarray, e2: np.ndarray, tol: int = 2, valid: np.ndarray | None = None) -> float:
    """F1 of two binary edge maps with a pixel tolerance, inside `valid`."""
    from scipy.ndimage import binary_dilation

    e1, e2 = e1.astype(bool), e2.astype(bool)
    if valid is not None:
        e1, e2 = e1 & valid, e2 & valid
    if e1.sum() == 0 and e2.sum() == 0:
        return 1.0
    st = np.ones((2 * tol + 1, 2 * tol + 1), bool)
    p = (e2 & binary_dilation(e1, st)).sum() / max(e2.sum(), 1)
    r = (e1 & binary_dilation(e2, st)).sum() / max(e1.sum(), 1)
    return float(2 * p * r / (p + r)) if p + r else 0.0


def scale_invariant_depth_error(pred: np.ndarray, ref: np.ndarray, valid: np.ndarray) -> float:
    """Median relative error after fitting the scale of `pred` to `ref` (median ratio)."""
    v = valid & (ref > 1e-3) & (pred > 1e-6) & np.isfinite(pred) & np.isfinite(ref)
    if v.sum() < 100:
        return float("nan")
    s = np.median(ref[v] / pred[v])
    return float(np.median(np.abs(pred[v] * s - ref[v]) / ref[v]))
