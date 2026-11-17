"""Product fidelity per version: does each product, as it appears in a version's image,
still look like the catalog item?

Thresholds (DINOv3 gate): silhouette IoU >= 0.70, colour difference (CIEDE2000, mean) <= 10,
DINOv3 embedding similarity >= 0.475.

- Colour and embedding compare the product in the image with the listing's held-out
  photos: every clean listing photo except the one the asset (or arm B's reference) was
  made from. A listing with no held-out photo is "unverifiable", never a pass.
- Silhouette compares the product's mask in the image with its mask in the code-made
  layout (the catalog item's shape at listing dimensions, same camera), both segmented
  with the same box so segmentation errors cancel. A held-out studio
  photo is taken from another viewpoint, so it cannot judge shape at the room camera;
  the 3D shape itself is gated on held-out photos separately (see fidelity.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

BK = Path("/bk")
DINOV3 = "facebook/dinov3-vitl16-pretrain-lvd1689m"
TH = {"silhouette": 0.70, "colour": 10.0, "embedding": 0.475}
REFERENCE = {
    "A": "A",
    "C1": "A",
    "C2": "A",
    "C3base": "C3base",
    "C3": "C3base",
    "C3L": "C3base",
    "B": "C3base",
}

_m: dict = {}


def dinov3():
    if "d3" not in _m:
        from huggingface_hub import HfApi
        from transformers import AutoImageProcessor, AutoModel

        rev = HfApi().model_info(DINOV3).sha  # pinned per run, recorded in the output
        _m["d3"] = (
            AutoImageProcessor.from_pretrained(DINOV3, revision=rev),
            AutoModel.from_pretrained(DINOV3, revision=rev).cuda().eval(),
            rev,
        )
    return _m["d3"]


def embed(imgs: list[np.ndarray]) -> np.ndarray:
    import torch

    proc, model, _ = dinov3()
    with torch.no_grad():
        f = model(**proc(images=imgs, return_tensors="pt").to("cuda")).pooler_output
    return torch.nn.functional.normalize(f.float(), dim=-1).cpu().numpy()


def on_white(rgb: np.ndarray, mask: np.ndarray, size: int = 448) -> np.ndarray:
    """Product pixels on white, cropped to the mask's bounding square."""
    import cv2

    from bakeoff.metrics import crop_pad, square_crop

    im = rgb.copy()
    im[~mask] = 255
    x0, y0, side = square_crop(mask)
    return cv2.resize(crop_pad(im, x0, y0, side, 255), (size, size), interpolation=cv2.INTER_AREA)


def held_out(lid: str) -> list[tuple[np.ndarray, np.ndarray]]:
    """(rgb, mask) of each clean listing photo except the input one and drawings."""
    import cv2
    from bk.assets import is_drawing

    key = ("ho", lid)
    if key in _m:
        return _m[key]
    out = []
    for root in (BK / "cutouts", BK / "extras_cutouts"):
        vf = root / lid / "views.json"
        if not vf.exists():
            continue
        v = json.loads(vf.read_text())
        for i in v.get("clean", []):
            if i == v.get("input"):
                continue
            p = root / lid / f"{i}.png"
            if not p.exists():
                continue
            rgba = cv2.cvtColor(cv2.imread(str(p), cv2.IMREAD_UNCHANGED), cv2.COLOR_BGRA2RGBA)
            if is_drawing(rgba):  # dimension drawings and detail crops are not photos
                continue
            out.append((rgba[..., :3], rgba[..., 3] > 127))
        break
    _m[key] = out
    return out


def product_gate(room: str, design_id: str, arms: list[str]) -> dict:
    import cv2
    from bk.checks import sam_box
    from bk.design import load_render_design

    from bakeoff.metrics import mask_iou, mean_color_delta_e

    d = load_render_design(room, design_id, "")
    base = BK / "renders" / room / design_id
    out = {
        "room": room,
        "design": design_id,
        "dinov3_revision": dinov3()[2],
        "thresholds": TH,
        "arms": {},
    }
    ho_emb = {}
    for it in d["render_items"]:
        ho = held_out(it["listing"])
        if ho:
            ho_emb[it["listing"]] = embed([on_white(r, m) for r, m in ho])
    for arm in arms:
        kind = arm.split("_")[0]
        src = base / arm / "image.png"
        if not src.exists():
            out["arms"][arm] = {"missing": True}
            continue
        img = cv2.cvtColor(cv2.imread(str(src)), cv2.COLOR_BGR2RGB)
        z = np.load(base / REFERENCE[kind] / "masks.npz")
        ref_img = cv2.cvtColor(
            cv2.imread(str(base / REFERENCE[kind] / "image.png")), cv2.COLOR_BGR2RGB
        )
        rows = []
        for i, it in enumerate(d["render_items"]):
            vis = z["vis"][i]
            row = {
                "item": it["id"],
                "name": it.get("name"),
                "listing": it["listing"],
                "tier": it["tier"],
            }
            if vis.mean() < 0.002:
                rows.append({**row, "status": "not in view"})
                continue
            if kind in ("A", "C3base"):
                m, sil = vis, 1.0  # the code-made layouts themselves
            else:
                ys, xs = np.nonzero(vis)
                pw, ph = 0.05 * (xs.max() - xs.min()), 0.05 * (ys.max() - ys.min())
                h, w = vis.shape
                box = [
                    max(0, xs.min() - pw),
                    max(0, ys.min() - ph),
                    min(w - 1, xs.max() + pw),
                    min(h - 1, ys.max() + ph),
                ]
                m = sam_box(img, box)
                # Same box, same segmenter on the reference image: segmentation errors
                # (see-through frames, thin legs) cancel, real shape changes do not.
                m_ref = sam_box(ref_img, box)
                sil = float(mask_iou(m, m_ref))
            ho = held_out(it["listing"])
            if not ho:
                rows.append({**row, "silhouette": sil, "status": "unverifiable"})
                continue
            e = embed([on_white(img, m)])[0]
            sims = ho_emb[it["listing"]] @ e
            des = [mean_color_delta_e(img, m, r, mk) for r, mk in ho]
            emb, de = float(sims.max()), float(min(des))
            ok = {
                "silhouette": sil >= TH["silhouette"],
                "colour": de <= TH["colour"],
                "embedding": emb >= TH["embedding"],
            }
            rows.append(
                {
                    **row,
                    "silhouette": sil,
                    "colour_de": de,
                    "embedding": emb,
                    "held_out_photos": len(ho),
                    "ok": ok,
                    "status": "pass" if all(ok.values()) else "fail",
                    "drift": [k for k, v in ok.items() if not v],
                }
            )
        out["arms"][arm] = rows
    (base / "product_gate.json").write_text(json.dumps(out, indent=1, default=float))
    return json.loads(json.dumps(out, default=float))
