"""Photos path for phones without AR: how far off are the walls?

For each ARKitScenes room: 15 photos spread around the room (picked by view
direction from the 120 frames the depth benchmark scored), with no AR poses and
no LiDAR. MapAnything gives each photo a camera; MoGe-3 depth gives metric scale;
the cameras' average up gives the vertical; the production `fit_space` fits the
walls; one tape value (the true length of the room's longest wall) corrects the
scale. Every other wall and the ceiling are compared with the room fitted from
LiDAR and AR poses: that is the reference here, not tape, until golden rooms exist.
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import numpy as np
from noar_eval import MAPANYTHING_APACHE, MAPANYTHING_APACHE_REVISION, noar_dir, views_for
from twin_gpu.common import load_scene, read_depth_m, read_rgb, save_json, scene_dir

N_PHOTOS = 15


def _spread(c2w: list, n: int) -> list[int]:
    """Farthest-point picks by view direction, with a small weight on position."""
    c = np.asarray(c2w, dtype=np.float64)
    fwd = c[:, :3, 2] / np.linalg.norm(c[:, :3, 2], axis=1, keepdims=True)
    pos = c[:, :3, 3]

    def dist(i: int) -> np.ndarray:
        d: np.ndarray = np.arccos(np.clip(fwd @ fwd[i], -1, 1)) + 0.25 * np.linalg.norm(
            pos - pos[i], axis=1
        )
        return d

    picked, near = [0], dist(0)
    while len(picked) < min(n, len(c)):
        nxt = int(np.argmax(near))
        picked.append(nxt)
        near = np.minimum(near, dist(nxt))
    return sorted(picked)


def photo_frames(name: str, n: int = N_PHOTOS) -> list[int]:
    """Frames a person might take as photos: spread by view direction (AR poses used only
    to choose, never given to the method)."""
    scene = load_scene(name, refined=False)
    frames = views_for(name)
    picks = _spread([scene["frames"][f]["c2w"] for f in frames], n)
    return [frames[i] for i in picks]


def predict(name: str, n: int = N_PHOTOS) -> dict:
    """MapAnything cameras and depth for the photos, from images and intrinsics only."""
    import cv2
    import torch
    from mapanything.models import MapAnything
    from mapanything.utils.image import preprocess_inputs

    path = noar_dir(name) / f"photos{n}_mapanything.npz"
    frames = photo_frames(name, n)
    if path.exists():
        return {"frames": frames, "cached": True}
    scene = load_scene(name, refined=False)
    sd = scene_dir(name)
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
        views.append({"img": torch.from_numpy(cv2.resize(rgb, (tw, th), interpolation=cv2.INTER_AREA)),
                      "intrinsics": torch.from_numpy(k)})  # fmt: skip
    started = time.time()
    proc = preprocess_inputs(views, resize_mode="fixed_size", size=(tw, th))
    with torch.no_grad():
        preds = model.infer(proc, memory_efficient_inference=True, use_amp=True, amp_dtype="bf16",
                            apply_mask=True, mask_edges=True, apply_confidence_mask=True,
                            confidence_percentile=10)  # fmt: skip
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
    np.savez_compressed(path, frames=np.array(frames), c2w=np.stack(c2w),
                        depth=np.stack(depth).astype(np.float16))  # fmt: skip
    return {"frames": frames, "seconds": round(seconds, 1)}


def _y_up(up: list[float]) -> np.ndarray:
    a = np.asarray(up, dtype=np.float64) / np.linalg.norm(up)
    b = np.array([0.0, 1.0, 0.0])
    v, c = np.cross(a, b), float(a @ b)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1.0 + c)


def _points(depths, ks, c2ws, stride: int = 8) -> np.ndarray:
    out = []
    for d, k, c in zip(depths, ks, c2ws, strict=True):
        ys, xs = np.mgrid[0 : d.shape[0] : stride, 0 : d.shape[1] : stride]
        z = d[ys, xs]
        ok = z > 0.1
        ys, xs, z = ys[ok], xs[ok], z[ok]
        cam = np.stack(
            [(xs + 0.5 - k[0, 2]) / k[0, 0] * z, (ys + 0.5 - k[1, 2]) / k[1, 1] * z, z], 1
        )
        out.append(cam @ c[:3, :3].T + c[:3, 3])
    return np.concatenate(out)


def _dense_extent(
    values: np.ndarray, bin_m: float = 0.04, share: float = 0.3
) -> tuple[float, float]:
    """Each side's wall: the outermost bin, from the outside in, holding at least `share`
    of the densest bin on that side. Sparse points seen through doors and windows sit
    beyond it and are ignored."""
    lo, hi = np.percentile(values, [0.5, 99.5])
    edges = np.arange(lo, hi + bin_m, bin_m)
    counts, edges = np.histogram(values, bins=edges)
    mid = len(counts) // 2
    low_peak, high_peak = counts[:mid].max(), counts[mid:].max()
    low = next(i for i in range(mid) if counts[i] >= share * low_peak)
    high = next(i for i in range(len(counts) - 1, mid - 1, -1) if counts[i] >= share * high_peak)
    return float(edges[low] + bin_m / 2), float(edges[high] + bin_m / 2)


def fit_dense(points: np.ndarray, depth_source: str):
    """The production fit_space with the walls placed at dense layers, not percentiles."""
    from sajao_workers.twin import space as sp

    original = np.percentile

    def patched(a, q, *args, **kwargs):
        if isinstance(q, list) and q == [1.0, 99.0]:
            return np.array(_dense_extent(np.asarray(a)))
        return original(a, q, *args, **kwargs)

    sp.np.percentile = patched
    try:
        return sp.fit_space(points, depth_source=depth_source)
    finally:
        sp.np.percentile = original


def _pair(ref: list[float], test: list[float]) -> list[int] | None:
    """Test wall index for each reference wall, in the turn and direction that fit best."""
    n = len(ref)
    if len(test) != n:
        return None
    best = None
    for direction in (1, -1):
        for start in range(n):
            order = [(start + direction * i) % n for i in range(n)]
            cost = sum(abs(test[o] - r) for o, r in zip(order, ref, strict=True))
            if best is None or cost < best[0]:
                best = (cost, order)
    return best[1] if best else None


def walls_room(name: str, n: int = N_PHOTOS, poses: str = "pred", fit: str = "percentile") -> dict:
    from depth_eval import load_depths

    from sajao_workers.twin.photos import level_rotation, metric_scale, tape_factor
    from sajao_workers.twin.space import fit_space

    scene = load_scene(name, refined=False)
    sd = scene_dir(name)
    saved = np.load(noar_dir(name) / f"photos{n}_mapanything.npz")
    frames = [int(f) for f in saved["frames"]]
    pred_c2w, pred_depth = saved["c2w"].astype(np.float64), saved["depth"].astype(np.float32)
    moge = load_depths(name, "moge3")
    ks = [np.asarray(scene["frames"][f]["K"], dtype=np.float64) for f in frames]
    metric = [moge[f] for f in frames]

    # Photos path: scale from MoGe-3, vertical from the cameras, walls from MoGe-3 depth.
    s = metric_scale(list(pred_depth), metric)
    if poses == "ar":  # diagnosis: the true AR poses, turned y up, with MoGe-3 depth
        up_turn = _y_up(scene["up"])
        c2w = np.stack([np.asarray(scene["frames"][f]["c2w"], dtype=np.float64) for f in frames])
        c2w[:, :3, :3] = up_turn @ c2w[:, :3, :3]
        c2w[:, :3, 3] = c2w[:, :3, 3] @ up_turn.T
    else:
        c2w = pred_c2w.copy()
        c2w[:, :3, 3] *= s
        r = level_rotation(list(c2w))
        c2w[:, :3, :3] = r @ c2w[:, :3, :3]
        c2w[:, :3, 3] = c2w[:, :3, 3] @ r.T
    photo_points = _points(metric, ks, c2w)
    photos = (fit_dense if fit == "dense" else fit_space)(photo_points, depth_source="image")

    # Reference: every scored frame's LiDAR depth on its AR pose, turned y up.
    turn = _y_up(scene["up"])
    ref_frames = views_for(name)
    ref_c2w = []
    for f in ref_frames:
        c = np.asarray(scene["frames"][f]["c2w"], dtype=np.float64).copy()
        c[:3, :3] = turn @ c[:3, :3]
        c[:3, 3] = turn @ c[:3, 3]
        ref_c2w.append(c)
    lidar = [read_depth_m(sd / scene["frames"][f]["depth"]) for f in ref_frames]
    ref_k = []
    for f, d in zip(ref_frames, lidar, strict=True):
        k = np.asarray(scene["frames"][f]["K"], dtype=np.float64).copy()
        k[0] *= d.shape[1] / scene["frames"][f]["w"]
        k[1] *= d.shape[0] / scene["frames"][f]["h"]
        ref_k.append(k)
    ref = fit_space(_points(lidar, ref_k, ref_c2w, stride=4), depth_source="lidar")

    ref_walls = [w["length"]["value_m"] for w in ref.shell["walls"]]
    raw = [w["length"]["value_m"] for w in photos.shell["walls"]]
    tape_value = max(ref_walls)
    factor, tape_wall = tape_factor(
        photos.shell["walls"], [{"target": "wall_length", "value_m": tape_value}]
    )
    corrected = [v * factor for v in raw]
    out: dict = {
        "room": name,
        "photos": len(frames),
        "poses": poses,
        "fit": fit,
        "metric_scale": round(s, 4),
        "tape_m": round(tape_value, 3),
        "tape_factor": round(factor, 4),
        "ref_walls_m": [round(v, 3) for v in ref_walls],
        "photo_walls_raw_m": [round(v, 3) for v in raw],
        "ceiling_ref_m": ref.shell["ceiling_height"]["value_m"],
        "ceiling_raw_m": photos.shell["ceiling_height"]["value_m"],
        "ceiling_err_pct": round(
            100
            * (
                photos.shell["ceiling_height"]["value_m"]
                * factor
                / ref.shell["ceiling_height"]["value_m"]
                - 1
            ),
            1,
        ),
    }
    order = _pair(ref_walls, corrected)
    if order is None:
        out["note"] = f"{len(raw)} photo walls against {len(ref_walls)} reference walls"
    else:
        tape_index = next(i for i, w in enumerate(photos.shell["walls"]) if w["id"] == tape_wall)
        errors = [round(100 * (corrected[o] / rv - 1), 1) for o, rv in zip(order, ref_walls, strict=True)
                  if o != tape_index]  # fmt: skip
        raw_errors = [
            round(100 * (raw[o] / rv - 1), 1) for o, rv in zip(order, ref_walls, strict=True)
        ]
        out.update(wall_err_pct=errors, wall_err_pct_no_tape=raw_errors,
                   median_abs_wall_err_pct=round(float(np.median(np.abs(errors))), 1) if errors else None)  # fmt: skip
    save_json(noar_dir(name) / f"photos{n}_{poses}_{fit}_walls.json", out)
    return out
