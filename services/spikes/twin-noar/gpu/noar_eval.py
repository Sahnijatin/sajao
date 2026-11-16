"""Twin without AR poses: feed-forward camera poses, MoGe-3 depth, scale from each source.

AR scan review, Step 2. On the five SJ-116 ARKitScenes rooms, 120 evenly spaced
frames each (a capture package's maximum), the AR poses are withheld:

1. poses come from a feed-forward model given only the images and intrinsics;
2. metric scale comes from each source in turn: the model's own, MoGe-3 depth,
   AR translation (AR present but unhealthy), or one tape value (simulated as
   the true length of the room's largest annotated object);
3. objects are lifted with MoGe-3 depth on those poses through the spike's
   fusion and scored against the ARKitScenes boxes, beside the AR-pose path
   in the same harness;
4. splats are trained on both pose sets and scored on held-out views.

Predicted poses are placed in the AR world by a rigid transform (rotation from
the camera orientations, then translation): a choice of frame only. Scale is
never fitted to the AR path except for the "ar_translation" source.
"""

from __future__ import annotations

import json
import math
import os
import time

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # an open xet log blocks volume commits

import numpy as np
from twin_gpu.common import (
    load_scene,
    out_dir,
    read_rgb,
    save_json,
    scene_dir,
    unproject,
    voxel_stats,
)

ROOMS = [
    "arkit_living_47331265",
    "arkit_living_41159541",
    "arkit_living_41159566",
    "arkit_bedroom_47430034",
    "arkit_bedroom_47895350",
]
N_VIEWS = 120
MAPANYTHING_APACHE = "facebook/map-anything-apache"
MAPANYTHING_APACHE_REVISION = "00f9c245bbcb60522d1ed7f9e9d88462c6e3f38a"
SCALE_SOURCES = ["model", "moge3", "ar_translation", "tape"]


def noar_dir(name: str):
    d = out_dir(name) / "noar"
    d.mkdir(parents=True, exist_ok=True)
    return d


def views_for(name: str) -> list[int]:
    """120 evenly spaced frames from those the depth benchmark scored."""
    from depth_eval import frames_for

    frames = frames_for(name)
    picks = np.linspace(0, len(frames) - 1, min(N_VIEWS, len(frames))).round().astype(int)
    return [frames[i] for i in picks]


# --- poses -------------------------------------------------------------------


def predict_mapanything(name: str) -> dict:
    """Camera poses and depth from images and intrinsics only (no AR poses)."""
    import cv2
    import torch
    from mapanything.models import MapAnything
    from mapanything.utils.image import preprocess_inputs

    path = noar_dir(name) / "poses_mapanything_apache.npz"
    if path.exists():
        return json.loads((noar_dir(name) / "poses_mapanything_apache.json").read_text())
    scene = load_scene(name, refined=False)
    sd = scene_dir(name)
    frames = views_for(name)
    model = MapAnything.from_pretrained(MAPANYTHING_APACHE, revision=MAPANYTHING_APACHE_REVISION)
    model = model.cuda().eval()
    tw, th = 518, 392
    views = []
    for fi in frames:
        f = scene["frames"][fi]
        rgb = read_rgb(sd / f["file"])
        h, w = rgb.shape[:2]
        k = np.asarray(f["K"], dtype=np.float32).copy()
        k[0] *= tw / w
        k[1] *= th / h
        img = cv2.resize(rgb, (tw, th), interpolation=cv2.INTER_AREA)
        views.append({"img": torch.from_numpy(img), "intrinsics": torch.from_numpy(k)})
    started = time.time()
    proc = preprocess_inputs(views, resize_mode="fixed_size", size=(tw, th))
    with torch.no_grad():
        preds = model.infer(
            proc,
            memory_efficient_inference=True,
            use_amp=True,
            amp_dtype="bf16",
            apply_mask=True,
            mask_edges=True,
            apply_confidence_mask=True,
            confidence_percentile=10,
        )
    seconds = time.time() - started
    c2w, depth = [], []
    for fi, p in zip(frames, preds, strict=True):
        f = scene["frames"][fi]
        d = p["depth_z"][0, ..., 0].float().cpu().numpy()
        m = p["mask"][0, ..., 0].cpu().numpy().astype(bool)
        depth.append(
            cv2.resize(np.where(m, d, 0.0), (f["w"], f["h"]), interpolation=cv2.INTER_NEAREST)
        )
        c2w.append(p["camera_poses"][0].float().cpu().numpy())
    np.savez_compressed(
        path, frames=np.array(frames), c2w=np.stack(c2w), depth=np.stack(depth).astype(np.float16)
    )
    info = {"model": "mapanything_apache", "views": len(frames), "seconds": round(seconds, 1)}
    save_json(noar_dir(name) / "poses_mapanything_apache.json", info)
    return info


# --- alignment and scale -------------------------------------------------------


def _rotation_mean(rs: np.ndarray) -> np.ndarray:
    u, _, vt = np.linalg.svd(rs.sum(axis=0))
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    return r


def align(pred: np.ndarray, ar: np.ndarray, scale: float) -> tuple[np.ndarray, dict]:
    """Rigidly place scaled predicted cameras in the AR world; report pose errors."""
    scaled = pred.copy()
    scaled[:, :3, 3] *= scale
    r = _rotation_mean(ar[:, :3, :3] @ np.transpose(scaled[:, :3, :3], (0, 2, 1)))
    centres = scaled[:, :3, 3] @ r.T
    t = (ar[:, :3, 3] - centres).mean(axis=0)
    out = scaled.copy()
    out[:, :3, :3] = r @ scaled[:, :3, :3]
    out[:, :3, 3] = centres + t
    err = np.linalg.norm(out[:, :3, 3] - ar[:, :3, 3], axis=1)
    rel = np.einsum("nij,nkj->nik", out[:, :3, :3], ar[:, :3, :3])
    ang = np.degrees(np.arccos(np.clip((np.trace(rel, axis1=1, axis2=2) - 1) / 2, -1, 1)))
    return out, {
        "centre_rmse_cm": round(float(np.sqrt((err**2).mean()) * 100), 1),
        "rotation_median_deg": round(float(np.median(ang)), 2),
    }


def ar_translation_scale(pred: np.ndarray, ar: np.ndarray) -> float:
    """The scale that best fits the AR camera path (AR present but unhealthy)."""
    r = _rotation_mean(ar[:, :3, :3] @ np.transpose(pred[:, :3, :3], (0, 2, 1)))
    p = pred[:, :3, 3] @ r.T
    a = ar[:, :3, 3]
    p0, a0 = p - p.mean(0), a - a.mean(0)
    return float((p0 * a0).sum() / (p0 * p0).sum())


def moge_scale(name: str, frames: list[int], pred_depth: np.ndarray) -> float:
    """Median ratio of MoGe-3 metric depth to the pose model's depth."""
    from depth_eval import load_depths

    moge = load_depths(name, "moge3")
    ratios = []
    for fi, d in zip(frames, pred_depth, strict=True):
        m = moge.get(fi)
        if m is None:
            continue
        ok = (m > 0.1) & (d > 0.1)
        if ok.sum() > 100:
            ratios.append(float(np.median(m[ok] / d[ok])))
    return float(np.median(ratios))


# --- objects -----------------------------------------------------------------


def lift(name: str, frames: list[int], c2w: dict[int, np.ndarray], depth_for) -> list:
    """The spike's lifting, with the given poses instead of the scene's."""
    import cv2
    from twin_gpu.objects import VOXEL, load_masks

    from twin_risk.fusion import Observation

    scene = load_scene(name, refined=False)
    obs = []
    kernel = np.ones((5, 5), np.uint8)
    rng = np.random.default_rng(0)
    for fi in frames:
        depth = depth_for(fi)
        if depth is None:
            continue
        masks, labels, scores, _ = load_masks(name, fi)
        k = np.asarray(scene["frames"][fi]["K"])
        for mi in range(len(labels)):
            m = cv2.erode(masks[mi].astype(np.uint8), kernel) > 0
            ys, xs = np.nonzero(m & (depth > 0.05))
            if len(ys) < 50:
                continue
            if len(ys) > 4000:
                sel = rng.choice(len(ys), 4000, replace=False)
                ys, xs = ys[sel], xs[sel]
            z = depth[ys, xs]
            med = np.median(z)
            mad = np.median(np.abs(z - med)) * 1.4826
            ok = np.abs(z - med) <= 3 * mad + 0.05 * med
            pts = unproject(depth, k, c2w[fi], ys[ok], xs[ok])
            obs.append(
                Observation(
                    fi, labels[mi], float(scores[mi]), voxel_stats(pts, VOXEL), key=fi * 1000 + mi
                )
            )
    return obs


def objects_score(name: str, label: str, frames: list[int], c2w: dict[int, np.ndarray]) -> dict:
    from depth_eval import load_depths
    from twin_gpu import objects

    objects.set_detector("yoloe")
    objects.set_poses("raw")
    moge = load_depths(name, "moge3")
    obs = lift(name, frames, c2w, moge.get)
    result = objects.fuse_and_score(name, obs, f"noar_{label}")
    return {"metrics_seen": result["metrics_seen"], "boxes": result["boxes"], "gt": result["gt"]}


def _tape_scale(
    name: str, frames: list[int], pred: np.ndarray, ar: np.ndarray, s_moge: float
) -> float:
    """One tape value: the true length of the largest annotated object the twin found."""
    from twin_risk.metrics import canonical_class

    aligned, _ = align(pred, ar, s_moge)
    found = objects_score(name, "tape_probe", frames, dict(zip(frames, aligned, strict=True)))
    best = None
    for gt in found["gt"]:
        cls = canonical_class(gt["label"]) or gt["label"]
        for box in found["boxes"]:
            if (canonical_class(box["label"]) or box["label"]) != cls:
                continue
            d = math.dist(box["center"], gt["center"])
            if d < 0.5 * gt["length"] and (best is None or gt["length"] > best[0]):
                best = (gt["length"], box["length"])
    if best is None:
        return s_moge
    return s_moge * best[0] / best[1]


def score_room(name: str, method: str = "mapanything_apache") -> dict:
    """AR-pose baseline and every scale source, in the same harness."""
    scene = load_scene(name, refined=False)
    z = np.load(noar_dir(name) / f"poses_{method}.npz")
    frames = [int(f) for f in z["frames"]]
    pred = z["c2w"].astype(np.float64)
    pred_depth = z["depth"].astype(np.float32)
    ar = np.stack([np.asarray(scene["frames"][fi]["c2w"], dtype=np.float64) for fi in frames])

    out = {"scene": name, "method": method, "views": len(frames)}
    out["ar_poses"] = objects_score(name, "ar", frames, dict(zip(frames, ar, strict=True)))[
        "metrics_seen"
    ]
    s_moge = moge_scale(name, frames, pred_depth)
    scales = {
        "model": 1.0,
        "moge3": s_moge,
        "ar_translation": ar_translation_scale(pred, ar),
    }
    scales["tape"] = _tape_scale(name, frames, pred, ar, s_moge)
    out["true_scale"] = round(scales["ar_translation"], 4)
    for source, s in scales.items():
        aligned, pose = align(pred, ar, s)
        metrics = objects_score(
            name, f"{method}_{source}", frames, dict(zip(frames, aligned, strict=True))
        )
        out[source] = {
            "scale": round(s, 4),
            "scale_error_pct": round(100 * (s / scales["ar_translation"] - 1), 1),
            "pose": pose,
            "metrics_seen": metrics["metrics_seen"],
        }
    save_json(noar_dir(name) / f"score_{method}.json", out)
    return out


# --- splats ------------------------------------------------------------------


def splat_room(
    name: str, poses: str, source: str = "moge3", method: str = "mapanything_apache"
) -> dict:
    """Held-out PSNR of a splat trained on AR poses (LiDAR depth) or on predicted poses
    (MoGe-3 depth), with the twin worker's trainer and its pose refinement."""
    import io

    import splat_gpu
    from PIL import Image

    from sajao_workers.steps import LocalArtifactStore

    store = LocalArtifactStore(out_dir(name).parent.parent / "noar-store")
    scene = load_scene(name, refined=False)
    sd = scene_dir(name)
    frames = views_for(name)
    ar = {fi: np.asarray(scene["frames"][fi]["c2w"], dtype=np.float64) for fi in frames}
    if poses == "ar":
        c2w, depth_for = ar, None
    else:
        z = np.load(noar_dir(name) / f"poses_{method}.npz")
        pred = z["c2w"].astype(np.float64)
        arr = np.stack([ar[int(f)] for f in z["frames"]])
        s = json.loads((noar_dir(name) / f"score_{method}.json").read_text())[source]["scale"]
        aligned, _ = align(pred, arr, s)
        c2w = {int(f): a for f, a in zip(z["frames"], aligned, strict=True)}
        from depth_eval import load_depths

        moge = load_depths(name, "moge3")
        depth_for = moge.get

    def depth_png(fi: int) -> bytes:
        if depth_for is None:
            return (sd / scene["frames"][fi]["depth"]).read_bytes()
        mm = np.clip(np.round(depth_for(fi) * 1000), 0, 65535).astype(np.uint16)
        buf = io.BytesIO()
        Image.fromarray(mm).save(buf, format="PNG")
        return buf.getvalue()

    manifest = {
        "up_axis": 2,
        "depth_source": "lidar" if poses == "ar" else "image",
        "frames": [
            {
                "keyframe_id": f"kf{fi:04d}",
                "image": store.put_blob((sd / scene["frames"][fi]["file"]).read_bytes()),
                "width": scene["frames"][fi]["w"],
                "height": scene["frames"][fi]["h"],
                "intrinsics": scene["frames"][fi]["K"],
                "c2w": c2w[fi].tolist(),
                "depth": store.put_blob(depth_png(fi)),
            }
            for fi in frames
        ],
    }
    payload = {
        "frames": store.put_blob(json.dumps(manifest).encode()),
        "objects": store.put_blob(b"[]"),
    }
    label = "ar" if poses == "ar" else f"{method}_{source}"
    cached = noar_dir(name) / f"splat_{label}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    result = splat_gpu.train(payload, store)
    out = {
        k: result[k]
        for k in ("psnr_heldout", "psnr_heldout_raw", "gaussians", "train_seconds", "gpu")
    }
    out.update(scene=name, poses=label)
    save_json(cached, out)
    return out
