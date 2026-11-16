"""Reading and writing removal-eval files. Light imports only, for both GPU images."""

from __future__ import annotations

import math

import numpy as np
from twin_gpu.common import load_scene, out_dir, read_rgb, scene_dir


def removal_dir(name: str, kind: str):
    d = out_dir(name) / "removal" / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_prep(name: str, kind: str) -> dict:
    z = np.load(removal_dir(name, kind) / "prep.npz")
    n, h, w = (int(v) for v in z["shape"])
    holes = np.unpackbits(z["holes"], axis=-1, count=w).astype(bool).reshape(n, h, w)
    known = z["known"].astype(int)
    known_holes = (
        np.unpackbits(z["known_holes"], axis=-1, count=w).astype(bool).reshape(len(known), h, w)
        if len(known)
        else np.zeros((0, h, w), bool)
    )
    return {
        "frames": z["frames"].astype(int),
        "holes": holes,
        "inpaint": z["inpaint"].astype(int),
        "drop": z["drop"].astype(int),
        "known": known,
        "known_holes": known_holes,
    }


def train_rgb(name: str, frame: int) -> np.ndarray:
    scene = load_scene(name)
    return read_rgb(scene_dir(name) / scene["frames"][frame]["file"])


def _psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2))
    return 99.0 if mse == 0 else 10 * math.log10(255.0**2 / mse)
