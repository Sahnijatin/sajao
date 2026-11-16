"""No-LiDAR depth: commercially licensed models versus MapAnything (CC BY-NC).

Runs on the SJ-116 spike's five ARKitScenes rooms (volume `sajao-twin-risk`),
on the same object frames the spike used. For each model:

1. predict metric depth per frame (each model in its own GPU image);
2. score it against LiDAR (high-confidence pixels only): AbsRel, delta < 1.25,
   and the median scale ratio;
3. lift the spike's YOLOE masks with that depth through the same fusion and box
   fitting, and score objects against the ARKitScenes boxes.

Depth from the models only places points; code fits the boxes.
"""

from __future__ import annotations

import os
import time

# Hugging Face's xet downloader keeps a log open on the volume, which blocks volume commits.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import numpy as np
from twin_gpu.common import load_scene, out_dir, read_depth_m, read_rgb, save_json, scene_dir

ROOMS = [
    "arkit_living_47331265",
    "arkit_living_41159541",
    "arkit_living_41159566",
    "arkit_bedroom_47430034",
    "arkit_bedroom_47895350",
]

MAPANYTHING_NC = "facebook/map-anything"
MAPANYTHING_APACHE = "facebook/map-anything-apache"
DA3 = "depth-anything/DA3METRIC-LARGE"
DA3_REVISION = "4010e39f3634a45bc60553321fb49fb760bd594e"
MOGE = "Ruicheng/moge-3-vitl"
MOGE_REVISION = "184008f877d7ad1ad4c2cd2182a9bd1f63d0e5be"
MODELS = ["lidar", "mapanything", "mapanything_apache", "da3_metric", "moge3"]


def frames_for(name: str) -> list[int]:
    from twin_gpu.objects import object_frames

    return object_frames(load_scene(name, refined=False))


def depth_path(name: str, model: str):
    return out_dir(name) / f"depth_{model}.npz"


def done(name: str, model: str) -> dict | None:
    """A finished prediction is reused, so a rerun only pays for what is missing."""
    import json

    info = out_dir(name) / f"depth_{model}.json"
    if info.exists() and depth_path(name, model).exists():
        return {**json.loads(info.read_text()), "reused": True}
    return None


def save_depths(name: str, model: str, depths: dict[int, np.ndarray], seconds: float) -> dict:
    np.savez_compressed(
        depth_path(name, model), **{str(k): v.astype(np.float16) for k, v in depths.items()}
    )
    info = {"model": model, "frames": len(depths), "seconds": round(seconds, 1)}
    save_json(out_dir(name) / f"depth_{model}.json", info)
    return info


def load_depths(name: str, model: str) -> dict[int, np.ndarray]:
    if model == "lidar":
        scene = load_scene(name, refined=False)
        sd = scene_dir(name)
        return {fi: read_depth_m(sd / scene["frames"][fi]["depth"]) for fi in frames_for(name)}
    z = np.load(depth_path(name, model))
    return {int(k): z[k].astype(np.float32) for k in z.files}


def predict_mapanything(name: str, model: str) -> dict:
    """Both checkpoints with the same code, frames and raw AR poses."""
    if (previous := done(name, model)) is not None:
        return previous
    from twin_gpu import objects

    objects.set_poses("raw")
    objects.MAPANYTHING = MAPANYTHING_APACHE if model == "mapanything_apache" else MAPANYTHING_NC
    frames = frames_for(name)
    started = time.time()
    depths = objects.mapanything_depth(name, frames)
    return save_depths(name, model, depths, time.time() - started)


def predict_da3(name: str) -> dict:
    """DA3 metric: depth in metres = focal (pixels, at the processed size) * output / 300."""
    if (previous := done(name, "da3_metric")) is not None:
        return previous
    import cv2
    import torch
    from depth_anything_3.api import DepthAnything3

    model = DepthAnything3.from_pretrained(DA3, revision=DA3_REVISION).to("cuda").eval()
    scene = load_scene(name, refined=False)
    sd = scene_dir(name)
    frames = frames_for(name)
    started = time.time()
    depths = {}
    for start in range(0, len(frames), 16):
        chunk = frames[start : start + 16]
        images = [read_rgb(sd / scene["frames"][fi]["file"]) for fi in chunk]
        with torch.no_grad():
            pred = model.inference(images)
        for fi, rgb, raw in zip(chunk, images, pred.depth, strict=True):
            h, w = rgb.shape[:2]
            ph, pw = raw.shape
            k = np.asarray(scene["frames"][fi]["K"])
            focal = (k[0, 0] * pw / w + k[1, 1] * ph / h) / 2
            metric = focal * raw / 300.0
            depths[fi] = cv2.resize(metric, (w, h), interpolation=cv2.INTER_LINEAR)
    return save_depths(name, "da3_metric", depths, time.time() - started)


def predict_moge(name: str) -> dict:
    """MoGe-3 given the known horizontal field of view from the AR intrinsics."""
    if (previous := done(name, "moge3")) is not None:
        return previous
    import math

    import torch
    from huggingface_hub import hf_hub_download
    from moge.model.v3 import MoGeModel

    weights = hf_hub_download(MOGE, "model.pt", revision=MOGE_REVISION)
    model = MoGeModel.from_pretrained(weights).to("cuda").eval()
    scene = load_scene(name, refined=False)
    sd = scene_dir(name)
    frames = frames_for(name)
    started = time.time()
    depths = {}
    for fi in frames:
        f = scene["frames"][fi]
        rgb = read_rgb(sd / f["file"])
        w = rgb.shape[1]
        fov_x = math.degrees(2 * math.atan(w / (2 * np.asarray(f["K"])[0, 0])))
        image = torch.tensor(rgb / 255, dtype=torch.float32, device="cuda").permute(2, 0, 1)
        with torch.no_grad():
            out = model.infer(image, fov_x=fov_x)
        depth = out["depth"].float().cpu().numpy()
        mask = out["mask"].cpu().numpy().astype(bool)
        depths[fi] = np.where(mask & np.isfinite(depth), depth, 0.0)
    return save_depths(name, "moge3", depths, time.time() - started)


def depth_scores(name: str, model: str) -> dict:
    """Against LiDAR on pixels where both have depth."""
    lidar = load_depths(name, "lidar")
    pred = load_depths(name, model)
    rel, d1, ratio, coverage = [], [], [], []
    for fi, g in lidar.items():
        d = pred.get(fi)
        if d is None:
            continue
        if d.shape != g.shape:
            import cv2

            d = cv2.resize(d, (g.shape[1], g.shape[0]), interpolation=cv2.INTER_NEAREST)
        lidar_ok = g > 0.1
        ok = lidar_ok & (d > 0.05) & np.isfinite(d)
        if ok.sum() < 100:
            continue
        coverage.append(ok.sum() / max(1, lidar_ok.sum()))
        r = d[ok] / g[ok]
        rel.append(float(np.mean(np.abs(d[ok] - g[ok]) / g[ok])))
        d1.append(float(np.mean(np.maximum(r, 1 / r) < 1.25)))
        ratio.append(float(np.median(r)))
    return {
        "frames": len(rel),
        "abs_rel": round(float(np.mean(rel)), 4),
        "delta_1_25": round(float(np.mean(d1)), 4),
        "median_scale_ratio": round(float(np.median(ratio)), 3),
        "coverage_of_lidar_pixels": round(float(np.mean(coverage)), 3),
    }


def object_scores(name: str, model: str) -> dict:
    from twin_gpu import objects

    objects.set_detector("yoloe")
    objects.set_poses("raw")
    depths = load_depths(name, model)
    obs, _ = objects.lift(name, frames_for(name), depths.get)
    result = objects.fuse_and_score(name, obs, f"bench_{model}")
    return result["metrics_seen"]


def score(name: str, model: str) -> dict:
    out = {"scene": name, "model": model, "objects_seen": object_scores(name, model)}
    if model != "lidar":
        out["depth"] = depth_scores(name, model)
        timing = out_dir(name) / f"depth_{model}.json"
        if timing.exists():
            import json

            out["predict"] = json.loads(timing.read_text())
    save_json(out_dir(name) / f"depth_bench_{model}.json", out)
    return out
