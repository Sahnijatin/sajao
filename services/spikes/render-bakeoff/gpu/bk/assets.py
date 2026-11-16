"""Listing cutouts (BiRefNet), image-to-3D (TripoSG, TRELLIS.2, SAM 3D Objects) and mesh helpers.

Layout on the bake-off volume (/bk):
  listings/listings.json, listings/<id>/<i>.jpg     fetched listing photos (private)
  cutouts/<id>/<i>.png, cutouts/<id>/views.json     RGBA cutouts and clean-view flags
  assets/<model>/<id>/raw.glb, meta.json            model output, untouched
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

BK = Path("/bk")
BIREFNET = ("ZhengPeng7/BiRefNet", "e2bf8e44")
TRIPOSG = ("VAST-AI/TripoSG", "2c1c516d")
TRELLIS2 = ("microsoft/TRELLIS.2-4B", "af44b45f")


def listings() -> list[dict]:
    return json.loads((BK / "listings" / "listings.json").read_text())


def listing(lid: str) -> dict:
    return next(x for x in listings() if x["id"] == lid)


# ---------- cutouts ----------

_birefnet = None


def birefnet():
    global _birefnet
    if _birefnet is None:
        import torch
        from transformers import AutoModelForImageSegmentation

        m = AutoModelForImageSegmentation.from_pretrained(
            BIREFNET[0], revision=BIREFNET[1], trust_remote_code=True
        )
        _birefnet = m.to("cuda").eval().half()
        torch.set_float32_matmul_precision("high")
    return _birefnet


def cut(rgb: np.ndarray) -> np.ndarray:
    """Alpha (float 0..1) for an RGB uint8 image."""
    import torch
    import torch.nn.functional as F

    h, w = rgb.shape[:2]
    x = torch.from_numpy(rgb).cuda().permute(2, 0, 1)[None].float() / 255
    x = F.interpolate(x, (1024, 1024), mode="bilinear", align_corners=False)
    mean = torch.tensor([0.485, 0.456, 0.406], device="cuda")[:, None, None]
    std = torch.tensor([0.229, 0.224, 0.225], device="cuda")[:, None, None]
    with torch.no_grad():
        pred = birefnet()(((x - mean) / std).half())[-1].sigmoid().float()
    pred = F.interpolate(pred, (h, w), mode="bilinear", align_corners=False)
    return pred[0, 0].cpu().numpy()


def view_quality(rgb: np.ndarray, alpha: np.ndarray) -> dict:
    """Is this a clean whole-product studio view? (not a detail crop or a room scene)"""
    import cv2

    m = alpha > 0.5
    h, w = m.shape
    area = float(m.mean())
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return {"clean": False, "reason": "empty", "area": 0.0}
    margin = min(xs.min() / w, ys.min() / h, 1 - (xs.max() + 1) / w, 1 - (ys.max() + 1) / h)
    n, _lab, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8))
    biggest = float(stats[1:, cv2.CC_STAT_AREA].max() / m.sum()) if n > 1 else 0.0
    bg = rgb[~m].astype(np.float64) / 255
    bg_bright = float(bg.mean()) if len(bg) else 0.0
    bg_std = float(bg.std()) if len(bg) else 0.0
    reasons = []
    if margin < 0.01:
        reasons.append("touches_border")
    if area < 0.06:
        reasons.append("too_small")
    if area > 0.92:
        reasons.append("fills_frame")
    if biggest < 0.85:
        reasons.append("several_parts")
    if bg_bright < 0.75 or bg_std > 0.18:
        reasons.append("busy_background")
    return {
        "clean": not reasons,
        "reason": ",".join(reasons),
        "area": round(area, 3),
        "margin": round(float(margin), 3),
        "largest_part": round(biggest, 3),
        "bg_bright": round(bg_bright, 3),
        "bg_std": round(bg_std, 3),
    }


def make_cutouts(lid: str) -> dict:
    """BiRefNet cutouts for every listing photo not yet cut. The input photo (the one
    assets are built from) never changes once chosen."""
    import cv2

    src = BK / "listings" / lid
    dst = BK / "cutouts" / lid
    dst.mkdir(parents=True, exist_ok=True)
    prev = json.loads((dst / "views.json").read_text()) if (dst / "views.json").exists() else None
    done = {v["index"]: v for v in (prev or {}).get("views", [])}
    views = []
    for f in sorted(src.glob("*.jpg"), key=lambda p: int(p.stem)):
        if int(f.stem) in done:
            views.append(done[int(f.stem)])
            continue
        bgr = cv2.imread(str(f), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        s = 1400 / max(bgr.shape[:2])
        if s < 1:
            bgr = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        a = cut(rgb)
        q = view_quality(rgb, a)
        rgba = np.dstack([rgb, (a * 255).astype(np.uint8)])
        cv2.imwrite(str(dst / f"{f.stem}.png"), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        views.append({"index": int(f.stem), "method": "birefnet", **q})
    clean = [v["index"] for v in views if v["clean"]]
    inp = prev["input"] if prev and prev.get("input") is not None else (clean[0] if clean else None)
    out = {"id": lid, "views": views, "clean": clean, "input": inp}
    (dst / "views.json").write_text(json.dumps(out, indent=1))
    return out


CATEGORY_PROMPT = {
    "sofa": "a sofa.",
    "bed": "a bed.",
    "almirah": "a wardrobe.",
    "table": "a table.",
    "chair": "a chair.",
    "lamp": "a lamp.",
    "tv_unit": "a tv cabinet.",
    "shelf": "a bookshelf.",
}
GDINO = ("IDEA-Research/grounding-dino-base", "12bdfa31")
SAM21 = ("facebook/sam2.1-hiera-large", "665f8e2a")
_det: dict = {}


def product_mask(rgb: np.ndarray, category: str) -> tuple[np.ndarray | None, float]:
    """Room shot: find the product by its category name (Grounding DINO), mask it (SAM 2.1)."""
    import torch
    from PIL import Image

    if "gd" not in _det:
        from transformers import (
            AutoModelForZeroShotObjectDetection,
            AutoProcessor,
            Sam2Model,
            Sam2Processor,
        )

        _det["gd"] = (
            AutoProcessor.from_pretrained(GDINO[0], revision=GDINO[1]),
            AutoModelForZeroShotObjectDetection.from_pretrained(GDINO[0], revision=GDINO[1])
            .cuda()
            .eval(),
        )
        _det["sam"] = (
            Sam2Processor.from_pretrained(SAM21[0], revision=SAM21[1]),
            Sam2Model.from_pretrained(SAM21[0], revision=SAM21[1]).cuda().eval(),
        )
    proc, model = _det["gd"]
    img = Image.fromarray(rgb)
    inp = proc(
        images=img, text=CATEGORY_PROMPT.get(category, "furniture."), return_tensors="pt"
    ).to("cuda")
    with torch.no_grad():
        out = model(**inp)
    res = proc.post_process_grounded_object_detection(
        out, inp.input_ids, threshold=0.35, text_threshold=0.3, target_sizes=[rgb.shape[:2]]
    )[0]
    if len(res["scores"]) == 0:
        return None, 0.0
    i = int(res["scores"].argmax())
    box = res["boxes"][i].tolist()
    sp, sm = _det["sam"]
    si = sp(images=img, input_boxes=[[box]], return_tensors="pt").to("cuda")
    with torch.no_grad():
        so = sm(**si, multimask_output=False)
    m = (
        sp.post_process_masks(so.pred_masks.cpu(), si["original_sizes"].cpu())[0][0, 0].numpy()
        > 0.5
    )
    return m, float(res["scores"][i])


def recut_with_detector(lid: str, category: str) -> dict:
    """Second pass for photos BiRefNet could not isolate (room shots, props): detector
    plus SAM 2.1. A photo becomes a held-out view only if the product mask is whole,
    single and away from the frame edge."""
    import cv2

    dst = BK / "cutouts" / lid
    vj = json.loads((dst / "views.json").read_text())
    changed = 0
    for v in vj["views"]:
        if v["clean"] or v.get("method") == "detector_sam":
            continue
        f = BK / "listings" / lid / f"{v['index']}.jpg"
        bgr = cv2.imread(str(f), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        s = 1400 / max(bgr.shape[:2])
        if s < 1:
            bgr = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        m, score = product_mask(rgb, category)
        v["detector_score"] = round(score, 3)
        if m is None:
            continue
        q = view_quality(rgb, m.astype(np.float32))
        reasons = [r for r in q["reason"].split(",") if r and r != "busy_background"]
        if reasons:
            v["detector_reason"] = ",".join(reasons)
            continue
        rgba = np.dstack([rgb, m.astype(np.uint8) * 255])
        cv2.imwrite(str(dst / f"{v['index']}.png"), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        v.update({**q, "clean": True, "reason": "", "method": "detector_sam", "room_shot": True})
        changed += 1
    vj["clean"] = [v["index"] for v in vj["views"] if v["clean"]]
    (dst / "views.json").write_text(json.dumps(vj, indent=1))
    return {"id": lid, "recovered": changed, "clean": len(vj["clean"])}


def load_rgba(lid: str, idx: int) -> np.ndarray:
    import cv2

    bgra = cv2.imread(str(BK / "cutouts" / lid / f"{idx}.png"), cv2.IMREAD_UNCHANGED)
    return cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA)


# ---------- image to 3D ----------

_triposg = None


def triposg_pipe():
    global _triposg
    if _triposg is None:
        import sys

        import torch
        from huggingface_hub import snapshot_download

        sys.path.insert(0, "/opt/triposg")
        from triposg.pipelines.pipeline_triposg import TripoSGPipeline

        d = snapshot_download(TRIPOSG[0], revision=TRIPOSG[1])
        _triposg = TripoSGPipeline.from_pretrained(d).to("cuda", torch.float16)
    return _triposg


def run_triposg(lid: str, seed: int = 42) -> dict:
    import sys

    import cv2
    import torch
    import trimesh

    sys.path.insert(0, "/opt/triposg/scripts")
    from image_process import prepare_image

    views = json.loads((BK / "cutouts" / lid / "views.json").read_text())
    if views["input"] is None:
        return {"id": lid, "skipped": "no clean view"}
    out = BK / "assets" / "triposg" / lid
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(f"/tmp/{lid}.png")
    cv2.imwrite(tmp.as_posix(), cv2.cvtColor(load_rgba(lid, views["input"]), cv2.COLOR_RGBA2BGRA))
    pipe = triposg_pipe()
    t0 = time.time()
    img = prepare_image(tmp.as_posix(), bg_color=np.array([1.0, 1.0, 1.0]), rmbg_net=None)
    with torch.no_grad():
        o = pipe(
            image=img,
            generator=torch.Generator(device="cuda").manual_seed(seed),
            num_inference_steps=50,
            guidance_scale=7.0,
        ).samples[0]
    mesh = trimesh.Trimesh(o[0].astype(np.float32), np.ascontiguousarray(o[1]), process=False)
    if len(mesh.faces) > 300_000:
        import pymeshlab

        ms = pymeshlab.MeshSet()
        ms.add_mesh(pymeshlab.Mesh(vertex_matrix=mesh.vertices, face_matrix=mesh.faces))
        ms.meshing_merge_close_vertices()
        ms.meshing_decimation_quadric_edge_collapse(targetfacenum=300_000)
        cm = ms.current_mesh()
        mesh = trimesh.Trimesh(cm.vertex_matrix(), cm.face_matrix(), process=False)
    dt = time.time() - t0
    mesh.export(out / "raw.glb")
    meta = {
        "id": lid,
        "model": "triposg",
        "input_view": views["input"],
        "seconds": round(dt, 1),
        "faces": len(mesh.faces),
        "textured": False,
    }
    (out / "meta.json").write_text(json.dumps(meta))
    return meta


_trellis = None


def run_trellis2(lid: str, seed: int = 42) -> dict:
    """TRELLIS.2 (MIT). Needs the gated DINOv3 image encoder (HF_TOKEN)."""
    global _trellis
    import os
    import sys

    import torch
    from PIL import Image

    sys.path.insert(0, "/opt/trellis2")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    views = json.loads((BK / "cutouts" / lid / "views.json").read_text())
    if views["input"] is None:
        return {"id": lid, "skipped": "no clean view"}
    out = BK / "assets" / "trellis2" / lid
    out.mkdir(parents=True, exist_ok=True)
    if _trellis is None:
        from huggingface_hub import snapshot_download
        from trellis2.pipelines import Trellis2ImageTo3DPipeline

        # The loader takes no revision; pin by loading a snapshot at the pinned commit.
        local = snapshot_download(TRELLIS2[0], revision=TRELLIS2[1])
        _trellis = Trellis2ImageTo3DPipeline.from_pretrained(local)
        _trellis.cuda()
    import o_voxel

    img = Image.fromarray(load_rgba(lid, views["input"]))
    t0 = time.time()
    torch.manual_seed(seed)
    mesh = _trellis.run(img, seed=seed)[0]
    mesh.simplify(16777216)
    glb = o_voxel.postprocess.to_glb(
        vertices=mesh.vertices,
        faces=mesh.faces,
        attr_volume=mesh.attrs,
        coords=mesh.coords,
        attr_layout=mesh.layout,
        voxel_size=mesh.voxel_size,
        aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
        decimation_target=300_000,
        texture_size=2048,
        remesh=True,
        remesh_band=1,
        remesh_project=0,
    )
    dt = time.time() - t0
    glb.export(out / "raw.glb")
    meta = {
        "id": lid,
        "model": "trellis2",
        "input_view": views["input"],
        "seconds": round(dt, 1),
        "textured": True,
    }
    (out / "meta.json").write_text(json.dumps(meta))
    return meta


SAM3D = ("facebook/sam-3d-objects", None)
_sam3d = None


def run_sam3d(lid: str, seed: int = 42) -> dict:
    """SAM 3D Objects (SAM License, gated). Mesh with vertex colours from the 'glb' output."""
    global _sam3d
    import sys

    import numpy as np

    sys.path.insert(0, "/opt/sam3d/notebook")
    sys.path.insert(0, "/opt/sam3d")
    views = json.loads((BK / "cutouts" / lid / "views.json").read_text())
    if views["input"] is None:
        return {"id": lid, "skipped": "no clean view"}
    out = BK / "assets" / "sam3d" / lid
    out.mkdir(parents=True, exist_ok=True)
    if _sam3d is None:
        from huggingface_hub import snapshot_download
        from inference import Inference

        root = Path(snapshot_download(SAM3D[0]))
        _sam3d = Inference(str(root / "checkpoints" / "pipeline.yaml"), compile=False)
    rgba = load_rgba(lid, views["input"])
    t0 = time.time()
    res = _sam3d(rgba[..., :3], (rgba[..., 3] > 127).astype(np.uint8), seed=seed)
    dt = time.time() - t0
    glb = res.get("glb")
    if glb is None:
        return {"id": lid, "error": "no mesh output"}
    glb.export(out / "raw.glb")
    meta = {
        "id": lid,
        "model": "sam3d",
        "input_view": views["input"],
        "seconds": round(dt, 1),
        "textured": True,
    }
    (out / "meta.json").write_text(json.dumps(meta))
    return meta


# ---------- mesh helpers ----------


def load_mesh(path: Path):
    """(vertices (N,3) float32, faces (F,3) int32, vertex colours (N,3) 0..1 or None).

    Textures are baked to vertex colours by sampling the base colour at each vertex UV.
    """
    import trimesh

    scene = trimesh.load(path, force="scene", process=False)
    vs, fs, cs, off, any_col = [], [], [], 0, False
    for g in scene.dump():
        v = np.asarray(g.vertices, np.float32)
        f = np.asarray(g.faces, np.int32) + off
        col = None
        vis = g.visual
        try:
            if getattr(vis, "kind", None) == "texture" and vis.uv is not None:
                mat = vis.material
                tex = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
                if tex is not None:
                    t = np.asarray(tex.convert("RGB"), np.float32) / 255
                    uv = np.asarray(vis.uv, np.float32) % 1.0
                    px = np.clip(
                        (uv[:, 0] * (t.shape[1] - 1)).round().astype(int), 0, t.shape[1] - 1
                    )
                    py = np.clip(
                        ((1 - uv[:, 1]) * (t.shape[0] - 1)).round().astype(int), 0, t.shape[0] - 1
                    )
                    col = t[py, px]
                    fac = getattr(mat, "baseColorFactor", None)
                    if fac is not None:
                        col = col * (
                            np.asarray(fac[:3], np.float32) / 255
                            if max(fac) > 1
                            else np.asarray(fac[:3])
                        )
            elif getattr(vis, "kind", None) == "vertex":
                col = np.asarray(vis.vertex_colors[:, :3], np.float32) / 255
        except Exception:
            col = None
        if col is None:
            col = np.full((len(v), 3), 0.7, np.float32)
        else:
            any_col = True
        vs.append(v)
        fs.append(f)
        cs.append(col)
        off += len(v)
    v = np.concatenate(vs)
    return v, np.concatenate(fs), (np.concatenate(cs) if any_col else None)


def to_listing_size(v: np.ndarray, dims_cm: dict) -> tuple[np.ndarray, dict]:
    """Scale by code to the listing's dimensions (metres), y up, centred on the
    footprint, base at y=0. The larger horizontal extent maps to the larger
    listed horizontal size. Returns new vertices and the per-axis scale."""
    lo, hi = v.min(0), v.max(0)
    ext = np.maximum(hi - lo, 1e-6)
    hgt = dims_cm.get("height")
    horiz = sorted(
        [x for x in (dims_cm.get("width"), dims_cm.get("depth"), dims_cm.get("length")) if x],
        reverse=True,
    )
    if not horiz and dims_cm.get("diameter"):
        horiz = [dims_cm["diameter"], dims_cm["diameter"]]
    if not horiz and dims_cm.get("shade_diameter"):
        horiz = [dims_cm["shade_diameter"], dims_cm["shade_diameter"]]
    if len(horiz) == 1:
        horiz = [horiz[0], horiz[0] * ext[[0, 2]].min() / ext[[0, 2]].max()]
    big, small = (0, 2) if ext[0] >= ext[2] else (2, 0)
    target = np.empty(3)
    target[1] = hgt / 100 if hgt else ext[1]
    target[big] = horiz[0] / 100 if horiz else ext[big]
    target[small] = horiz[1] / 100 if len(horiz) > 1 else ext[small]
    s = target / ext
    centre = (lo + hi) / 2
    out = (v - centre) * s
    out[:, 1] -= out[:, 1].min()
    return out.astype(np.float32), {"scale": s.tolist(), "size_m": target.tolist()}
