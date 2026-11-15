"""Scene format, timing and small numeric helpers shared by the GPU jobs.

A prepared scene lives in /vol/scenes/<name>/:
  images/0000.jpg ...      RGB frames
  depth/0000.png ...       optional uint16 depth in millimetres (LiDAR or rendered)
  cameras.json             frames (file, K, c2w OpenCV, split), up vector, metric flag
  points.npy               (N, 6) initial points: xyz, rgb 0..1
  gt_boxes.json            optional annotated boxes (ARKitScenes)
Outputs go to /vol/out/<name>/.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

VOL = Path("/vol")


def scene_dir(name: str) -> Path:
    return VOL / "scenes" / name


def out_dir(name: str) -> Path:
    d = VOL / "out" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_scene(name: str, refined: bool = True) -> dict:
    """Scene cameras; by default with poses refined during splat training, if any."""
    ref = VOL / "out" / name / "cameras_refined.json"
    if refined and ref.exists():
        return json.loads(ref.read_text())
    return json.loads((scene_dir(name) / "cameras.json").read_text())


def save_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=float))


def load_json(path: Path, default: object = None) -> object:
    return json.loads(path.read_text()) if path.exists() else default


def read_rgb(path: Path) -> np.ndarray:
    import cv2

    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def write_rgb(path: Path, rgb: np.ndarray, quality: int = 90) -> None:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    bgr = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2BGR)
    if path.suffix.lower() in (".jpg", ".jpeg"):
        cv2.imwrite(str(path), bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    else:
        cv2.imwrite(str(path), bgr)


def read_depth_m(path: Path) -> np.ndarray:
    import cv2

    d = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    return d.astype(np.float32) / 1000.0


def up_vector(scene: dict) -> np.ndarray:
    return np.asarray(scene["up"], dtype=np.float64)


def up_axis(scene: dict) -> int:
    return int(np.argmax(np.abs(up_vector(scene))))


def unproject(depth: np.ndarray, k: np.ndarray, c2w: np.ndarray, ys: np.ndarray, xs: np.ndarray):
    z = depth[ys, xs]
    x = (xs + 0.5 - k[0, 2]) / k[0, 0] * z
    y = (ys + 0.5 - k[1, 2]) / k[1, 1] * z
    cam = np.stack([x, y, z], axis=1)
    return cam @ c2w[:3, :3].T + c2w[:3, 3]


def voxel_stats(points: np.ndarray, voxel: float) -> dict:
    """Same structure as twin_risk.fusion.voxelize, computed with numpy."""
    if len(points) == 0:
        return {}
    keys = np.floor(points / voxel).astype(np.int64)
    uniq, inv, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    inv = inv.reshape(-1)
    sums = np.zeros((len(uniq), 3))
    np.add.at(sums, inv, points)
    return {
        (int(k[0]), int(k[1]), int(k[2])): (int(c), float(s[0]), float(s[1]), float(s[2]))
        for k, c, s in zip(uniq, counts, sums, strict=True)
    }


def gpu_name() -> str:
    try:
        import torch

        return torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


@contextmanager
def timed(scene: str, stage: str, gpu: str):
    """Record wall time of a stage in /vol/out/<scene>/timings.json."""
    t0 = time.time()
    yield
    dt = time.time() - t0
    path = out_dir(scene) / "timings.json"
    data = load_json(path, {}) or {}
    data[stage] = {"seconds": round(dt, 2), "gpu": gpu, "device": gpu_name()}
    save_json(path, data)
    print(f"[{scene}] {stage}: {dt:.1f}s on {gpu}", flush=True)


def env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))
