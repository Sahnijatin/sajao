"""The lock: keep product pixels from the composite, take only light from the pass.

Inside product masks:   final = composite * blur(pass) / blur(composite)
Outside product masks:  final = pass
With `brightness_only`, pixels in that mask take one luminance ratio for all three
channels, so the pass can brighten or darken a product but never shift its hue.
The ratio is blurred so it carries smooth shading and colour cast only; edges,
texture and proportions inside the masks come from the composite by construction.
"""

from __future__ import annotations

import numpy as np


def _blur(img: np.ndarray, sigma: float) -> np.ndarray:
    from scipy.ndimage import gaussian_filter

    if img.ndim == 3:
        return np.stack([gaussian_filter(img[..., c], sigma) for c in range(img.shape[2])], -1)
    return np.asarray(gaussian_filter(img, sigma))


def masked_blur(img: np.ndarray, mask: np.ndarray, sigma: float) -> np.ndarray:
    """Normalised blur that only averages pixels inside `mask` (no bleed from outside)."""
    m = mask.astype(np.float64)
    num = _blur(img * m[..., None], sigma)
    den = _blur(m, sigma)[..., None]
    return np.where(den > 1e-6, num / np.maximum(den, 1e-6), img)


def lock(
    composite: np.ndarray,
    passed: np.ndarray,
    product_mask: np.ndarray,
    sigma: float = 8.0,
    ratio_range: tuple[float, float] = (0.5, 2.0),
    feather: float = 1.5,
    brightness_only: np.ndarray | None = None,
) -> np.ndarray:
    """Return the locked image (uint8). `composite` and `passed` are uint8 RGB of the
    same size; `product_mask` is bool (union of all product masks)."""
    c = composite.astype(np.float64) / 255.0
    p = passed.astype(np.float64) / 255.0
    m = product_mask.astype(bool)
    eps = 1e-3
    ratio = (masked_blur(p, m, sigma) + eps) / (masked_blur(c, m, sigma) + eps)
    ratio = np.clip(ratio, *ratio_range)
    if brightness_only is not None:
        lum = np.array([0.2126, 0.7152, 0.0722])
        b = brightness_only.astype(bool) & m
        ratio_y = (masked_blur((p @ lum)[..., None], b, sigma) + eps) / (
            masked_blur((c @ lum)[..., None], b, sigma) + eps
        )
        ratio_y = np.clip(ratio_y, *ratio_range)
        ratio = np.where(b[..., None], np.repeat(ratio_y, 3, -1), ratio)
    inside = np.clip(c * ratio, 0, 1)
    w = (
        _blur(m.astype(np.float64), feather)[..., None]
        if feather > 0
        else m[..., None].astype(np.float64)
    )
    # Keep the mask fully locked: feather only outward.
    w = np.maximum(w, m[..., None])
    out = w * inside + (1 - w) * p
    return np.asarray(np.clip(out, 0, 1) * 255 + 0.5, dtype=np.uint8)
