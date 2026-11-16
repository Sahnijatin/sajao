"""LaMa (big-lama, Apache 2.0) inpainting as a local GPU job.

Uses the TorchScript export published with simple-lama-inpainting v0.1.0. The
wrapper is reimplemented here to avoid that package's pillow and OpenCV pins.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

URL = "https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt"
CACHE = Path("/vol/models/big-lama.pt")

_model = None


def _load():
    global _model
    if _model is None:
        import torch

        if not CACHE.exists():
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["curl", "-sSfL", "-o", str(CACHE), URL], check=True)
        _model = torch.jit.load(str(CACHE), map_location="cuda").eval()
    return _model


def inpaint(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Fill `mask` (H, W bool) in `rgb` (H, W, 3 uint8). Returns uint8."""
    import torch
    import torch.nn.functional as F

    if not mask.any():
        return rgb.copy()
    model = _load()
    h, w = mask.shape
    img = torch.from_numpy(rgb).float().permute(2, 0, 1)[None].cuda() / 255.0
    m = torch.from_numpy(mask.astype(np.float32))[None, None].cuda()
    ph, pw = (8 - h % 8) % 8, (8 - w % 8) % 8
    img = F.pad(img, (0, pw, 0, ph), mode="reflect")
    m = F.pad(m, (0, pw, 0, ph), mode="reflect")
    with torch.no_grad():
        out = model(img, (m > 0).float())
    out = (out[0, :, :h, :w].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
    keep = ~mask
    out[keep] = rgb[keep]
    return out
