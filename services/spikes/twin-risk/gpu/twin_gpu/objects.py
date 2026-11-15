"""Segment every object across frames, lift to 3D boxes, name them, score them.

Detection and naming: Grounding DINO with a household vocabulary (open set).
Masks: SAM 2.1 prompted with the detector boxes. Lifting: per-pixel depth from
LiDAR, from MapAnything (images, intrinsics and AR poses, no depth), or from the
trained splat. Boxes are fitted by code to fused 3D points, never by a model.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from twin_gpu.common import (
    load_scene,
    out_dir,
    read_depth_m,
    read_rgb,
    save_json,
    scene_dir,
    unproject,
    up_axis,
    voxel_stats,
)

from twin_risk.fusion import Observation, fuse, instance_boxes, merge_instances
from twin_risk.geometry import UprightBox, box_from_obb
from twin_risk.metrics import LabelledBox, canonical_class, summarise

VOCAB = [
    "bed",
    "sofa",
    "chair",
    "armchair",
    "table",
    "desk",
    "cabinet",
    "wardrobe",
    "nightstand",
    "shelf",
    "television",
    "refrigerator",
    "stove",
    "oven",
    "sink",
    "toilet",
    "washing machine",
    "stool",
    "bathtub",
    "dishwasher",
    "fireplace",
    "lamp",
    "potted plant",
    "rug",
    "curtain",
    "pillow",
    "ottoman",
    "toy",
    "vase",
    "bowl",
]
GDINO = "IDEA-Research/grounding-dino-base"
SAM2 = "facebook/sam2.1-hiera-large"
MAPANYTHING = "facebook/map-anything"
YOLOE = "yoloe-26x-seg.pt"
DETECTORS = ("gdino", "yoloe")
DET = "gdino"  # set by set_detector(); selects mask folder and result file names


def set_detector(det: str) -> None:
    global DET
    if det not in DETECTORS:
        raise ValueError(det)
    DET = det


def _yoloe():
    import os

    from ultralytics import YOLOE as Yoloe

    models = Path("/vol/models")
    models.mkdir(parents=True, exist_ok=True)
    cwd = os.getcwd()
    os.chdir(models)  # the text encoder downloads into the working directory
    try:
        m = Yoloe(YOLOE)
        m.set_classes(VOCAB)
    finally:
        os.chdir(cwd)  # a working directory inside the volume blocks volume commits
    return m


VOXEL = 0.05


def object_frames(scene: dict, max_frames: int = 160) -> list[int]:
    """All test frames plus evenly spaced training frames."""
    test = [i for i, f in enumerate(scene["frames"]) if f["split"] == "test"]
    train = [i for i, f in enumerate(scene["frames"]) if f["split"] == "train"]
    step = max(1, len(train) // max(1, max_frames - len(test)))
    return sorted(set(test) | set(train[::step]))


def segment(name: str, max_frames: int = 160) -> dict:
    """Detector boxes and SAM masks for the object frames, cached on the volume."""
    import torch
    import torchvision
    from PIL import Image
    from transformers import (
        AutoModelForZeroShotObjectDetection,
        AutoProcessor,
        Sam2Model,
        Sam2Processor,
    )

    cached = out_dir(name) / f"segment_{DET}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    scene = load_scene(name)
    sd = scene_dir(name)
    od = out_dir(name) / f"masks_{DET}"
    od.mkdir(parents=True, exist_ok=True)
    frames = object_frames(scene, max_frames)
    if DET == "gdino":
        dproc = AutoProcessor.from_pretrained(GDINO)
        dmodel = AutoModelForZeroShotObjectDetection.from_pretrained(GDINO).cuda().eval()
    else:
        ymodel = _yoloe()
    sproc = Sam2Processor.from_pretrained(SAM2)
    smodel = Sam2Model.from_pretrained(SAM2).cuda().eval()
    text = ". ".join(VOCAB) + "."
    t_det = t_seg = 0.0
    n_masks = 0
    for fi in frames:
        rgb = read_rgb(sd / scene["frames"][fi]["file"])
        h, w = rgb.shape[:2]
        pil = Image.fromarray(rgb)
        t0 = time.time()
        if DET == "gdino":
            inputs = dproc(images=pil, text=text, return_tensors="pt").to("cuda")
            with torch.no_grad():
                out = dmodel(**inputs)
            res = dproc.post_process_grounded_object_detection(
                out, inputs.input_ids, threshold=0.30, text_threshold=0.25, target_sizes=[(h, w)]
            )[0]
            boxes = res["boxes"].float()
            scores = res["scores"].float()
            labels = [str(x).strip() for x in res.get("text_labels", res.get("labels"))]
        else:
            yr = ymodel.predict(pil, conf=0.25, verbose=False)[0]
            boxes = yr.boxes.xyxy.float()
            scores = yr.boxes.conf.float()
            labels = [VOCAB[int(c)] for c in yr.boxes.cls.tolist()]
        keep_lab = [i for i, lab in enumerate(labels) if lab]
        boxes, scores = boxes[keep_lab], scores[keep_lab]
        labels = [labels[i] for i in keep_lab]
        area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1]) / (w * h)
        ok = (area < 0.8).nonzero().flatten().tolist()
        boxes, scores, labels = boxes[ok], scores[ok], [labels[i] for i in ok]
        if len(labels):
            lab_ids = torch.tensor([VOCAB.index(x) if x in VOCAB else len(VOCAB) for x in labels])
            k = torchvision.ops.batched_nms(boxes, scores, lab_ids.to(boxes.device), 0.5).tolist()
            boxes, scores, labels = boxes[k], scores[k], [labels[i] for i in k]
        t_det += time.time() - t0
        masks = np.zeros((0, h, w), bool)
        t0 = time.time()
        if len(labels):
            sin = sproc(images=pil, input_boxes=[boxes.cpu().tolist()], return_tensors="pt").to(
                "cuda"
            )
            with torch.no_grad():
                sout = smodel(**sin, multimask_output=False)
            m = sproc.post_process_masks(sout.pred_masks.cpu(), sin["original_sizes"].cpu())[0]
            masks = (m[:, 0] > 0.5).numpy() if m.ndim == 4 else (m > 0.5).numpy()
        t_seg += time.time() - t0
        n_masks += len(labels)
        np.savez_compressed(
            od / f"{fi:04d}.npz",
            masks=np.packbits(masks, axis=-1),
            shape=np.array([len(labels), h, w]),
            boxes=boxes.cpu().numpy(),
            scores=scores.cpu().numpy(),
            labels=np.array(labels),
        )
    summary = {
        "frames": len(frames),
        "masks": n_masks,
        "detector_seconds": round(t_det, 1),
        "sam_seconds": round(t_seg, 1),
        "seconds_per_frame": round((t_det + t_seg) / max(1, len(frames)), 3),
    }
    summary["detector"] = DET
    save_json(out_dir(name) / f"segment_{DET}.json", summary)
    return summary


def load_masks(name: str, fi: int):
    z = np.load(out_dir(name) / f"masks_{DET}" / f"{fi:04d}.npz")
    n, h, w = (int(v) for v in z["shape"])
    masks = (
        np.unpackbits(z["masks"], axis=-1, count=w).astype(bool) if n else np.zeros((0, h, w), bool)
    )
    return masks, [str(x) for x in z["labels"]], z["scores"].astype(float), z["boxes"]


def mapanything_depth(name: str, frames: list[int]) -> dict[int, np.ndarray]:
    """Metric depth per frame from MapAnything given images, intrinsics and AR poses."""
    import cv2
    import torch
    from mapanything.models import MapAnything
    from mapanything.utils.image import preprocess_inputs

    scene = load_scene(name)
    sd = scene_dir(name)
    model = MapAnything.from_pretrained(MAPANYTHING).cuda().eval()
    out: dict[int, np.ndarray] = {}
    tw, th = 518, 392
    pose_err = []
    for start in range(0, len(frames), 48):
        chunk = frames[start : start + 48]
        views = []
        for fi in chunk:
            f = scene["frames"][fi]
            rgb = read_rgb(sd / f["file"])
            h, w = rgb.shape[:2]
            k = np.asarray(f["K"], dtype=np.float32).copy()
            k[0] *= tw / w
            k[1] *= th / h
            views.append(
                {
                    "img": torch.from_numpy(
                        cv2.resize(rgb, (tw, th), interpolation=cv2.INTER_AREA)
                    ),
                    "intrinsics": torch.from_numpy(k),
                    "camera_poses": torch.from_numpy(np.asarray(f["c2w"], dtype=np.float32)),
                    "is_metric_scale": torch.tensor([True]),
                }
            )
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
        for fi, p in zip(chunk, preds, strict=True):
            f = scene["frames"][fi]
            d = p["depth_z"][0, ..., 0].float().cpu().numpy()
            m = p["mask"][0, ..., 0].cpu().numpy().astype(bool)
            d = np.where(m, d, 0.0)
            out[fi] = cv2.resize(d, (f["w"], f["h"]), interpolation=cv2.INTER_NEAREST)
            pose = p["camera_poses"][0].float().cpu().numpy()
            pose_err.append(float(np.linalg.norm(pose[:3, 3] - np.asarray(f["c2w"])[:3, 3])))
    print(
        f"MapAnything output vs input pose translation, median {np.median(pose_err):.3f} m",
        flush=True,
    )
    return out


def lift(name: str, frames: list[int], depth_for) -> tuple[list[Observation], dict]:
    """Lift every mask to world voxels. Returns observations and (frame, mask) -> key."""
    import cv2

    scene = load_scene(name)
    obs = []
    kernel = np.ones((5, 5), np.uint8)
    rng = np.random.default_rng(0)
    for fi in frames:
        f = scene["frames"][fi]
        depth = depth_for(fi)
        if depth is None:
            continue
        masks, labels, scores, _ = load_masks(name, fi)
        k, c2w = np.asarray(f["K"]), np.asarray(f["c2w"])
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
            pts = unproject(depth, k, c2w, ys[ok], xs[ok])
            vox = voxel_stats(pts, VOXEL)
            obs.append(Observation(fi, labels[mi], float(scores[mi]), vox, key=fi * 1000 + mi))
    return obs, {}


def gt_boxes(name: str, upi: int) -> list[LabelledBox]:
    path = scene_dir(name) / "gt_boxes.json"
    if not path.exists():
        return []
    out = []
    for g in json.loads(path.read_text()):
        out.append(
            LabelledBox(g["label"], box_from_obb(g["center"], g["axes_columns"], g["lengths"], upi))
        )
    return out


def box_json(label: str, b: UprightBox, frames: int) -> dict:
    return {
        "label": label,
        "class": canonical_class(label),
        "center": list(b.center),
        "length": b.length,
        "width": b.width,
        "height": b.height,
        "yaw": b.yaw,
        "frames": frames,
    }


def fuse_and_score(name: str, obs: list[Observation], mode: str) -> dict:
    scene = load_scene(name)
    upi = up_axis(scene)
    t0 = time.time()
    raw = fuse(obs)
    inst = merge_instances(raw)
    boxes = instance_boxes(inst, upi)
    fuse_s = time.time() - t0
    preds = [LabelledBox(lab, b) for lab, b, _ in boxes]
    gts = gt_boxes(name, upi)
    result = {
        "scene": name,
        "mode": mode,
        "detector": DET,
        "observations": len(obs),
        "instances_before_merge": len(raw),
        "instances": len(boxes),
        "fuse_seconds": round(fuse_s, 2),
        "metrics": summarise(preds, gts) if gts else None,
        "named_objects": sorted({lab for lab, _, _ in boxes}),
        "boxes": [box_json(lab, b, n) for lab, b, n in boxes],
        "gt": [box_json(g.label, g.box, 0) for g in gts],
    }
    save_json(out_dir(name) / f"objects_{DET}_{mode}.json", result)
    draw_topdown(name, result, mode)
    return result


def draw_topdown(name: str, result: dict, mode: str) -> None:
    """Top-down plan: ground truth in grey, predictions in colour."""
    from PIL import Image, ImageDraw

    scene = load_scene(name)
    upi = up_axis(scene)
    allb = [
        UprightBox(tuple(x["center"]), x["length"], x["width"], x["height"], x["yaw"], upi)
        for x in result["gt"]
    ]
    pb = [
        UprightBox(tuple(x["center"]), x["length"], x["width"], x["height"], x["yaw"], upi)
        for x in result["boxes"]
    ]
    pts = [p for bx in allb + pb for p in bx.footprint()]
    if not pts:
        return
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    u0, u1, v0, v1 = min(us) - 0.3, max(us) + 0.3, min(vs) - 0.3, max(vs) + 0.3
    s = 700 / max(u1 - u0, v1 - v0)
    img = Image.new("RGB", (int((u1 - u0) * s) + 1, int((v1 - v0) * s) + 1), "white")
    dr = ImageDraw.Draw(img)

    def poly(bx: UprightBox) -> list[tuple[float, float]]:
        return [((u - u0) * s, (v - v0) * s) for u, v in bx.footprint()]

    for bx, x in zip(allb, result["gt"], strict=True):
        dr.polygon(poly(bx), outline=(150, 150, 150), width=3)
        dr.text(poly(bx)[0], x["label"], fill=(120, 120, 120))
    for bx, x in zip(pb, result["boxes"], strict=True):
        col = (220, 60, 60) if x["class"] else (60, 120, 220)
        dr.polygon(poly(bx), outline=col, width=2)
        dr.text(poly(bx)[2], x["label"], fill=col)
    img.save(out_dir(name) / f"topdown_{DET}_{mode}.png")


def run_objects(name: str, modes: list[str]) -> dict:
    scene = load_scene(name)
    sd = scene_dir(name)
    frames = object_frames(scene)
    results = {}
    for mode in modes:
        t0 = time.time()
        if mode == "lidar":
            obs, _ = lift(name, frames, lambda fi: read_depth_m(sd / scene["frames"][fi]["depth"]))
        elif mode == "mapanything":
            cache = out_dir(name) / "mapanything_depth.npz"
            if cache.exists():
                z = np.load(cache)
                depths = {int(k): z[k] for k in z.files}
            else:
                t1 = time.time()
                depths = mapanything_depth(name, frames)
                np.savez_compressed(cache, **{str(k): v for k, v in depths.items()})
                save_json(
                    out_dir(name) / "mapanything.json",
                    {"seconds": round(time.time() - t1, 1), "frames": len(frames)},
                )
            obs, _ = lift(name, frames, depths.get)
        else:
            raise ValueError(mode)
        r = fuse_and_score(name, obs, mode)
        r["seconds"] = round(time.time() - t0, 1)
        save_json(out_dir(name) / f"objects_{DET}_{mode}.json", r)
        results[mode] = r["metrics"]
    return results


def masks_dir(name: str) -> Path:
    return out_dir(name) / f"masks_{DET}"
