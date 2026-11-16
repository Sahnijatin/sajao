"""Automatic render checks (the review's table), comparing a final image with the
composite that code produced for the same Design and camera.

  present          item visible in the composite above a minimum area
  position/size    SAM 2.1 mask in the final at the item's box vs the composite mask
  recognisable     DINOv2 similarity and colour difference, final crop vs composite crop
  room geometry    edge F1 outside product and cleared regions; MoGe-3 depth vs composite depth
  invented objects YOLOE detections in the final not explained by the composite or a product
  looks good       Qwen3-VL score, 1 to 10
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import numpy as np

from bakeoff.metrics import edge_f1, mask_iou, max_edge_shift, mean_color_delta_e, scale_invariant_depth_error

SAM = ("facebook/sam2.1-hiera-large", "665f8e2a")
DINO = ("facebook/dinov2-base", "f9e44c81")
VLM = ("Qwen/Qwen3-VL-8B-Instruct", "0c351dd0")
MOGE = ("Ruicheng/moge-3-vitl", "184008f877d7ad1ad4c2cd2182a9bd1f63d0e5be")


@dataclass
class Th:
    min_area: float = 0.002  # share of the image
    iou: float = 0.90
    edge_px: float = 8.0
    emb: float = 0.80
    de: float = 8.0
    edge_f1: float = 0.70
    depth_rel: float = 0.08
    invented_conf: float = 0.35
    aesthetic: float = 6.0


_m: dict = {}


def sam():
    if "sam" not in _m:
        from transformers import Sam2Model, Sam2Processor

        _m["sam"] = (Sam2Processor.from_pretrained(SAM[0], revision=SAM[1]),
                     Sam2Model.from_pretrained(SAM[0], revision=SAM[1]).cuda().eval())
    return _m["sam"]


def dino():
    if "dino" not in _m:
        from transformers import AutoImageProcessor, AutoModel

        _m["dino"] = (AutoImageProcessor.from_pretrained(DINO[0], revision=DINO[1]),
                      AutoModel.from_pretrained(DINO[0], revision=DINO[1]).cuda().eval())
    return _m["dino"]


def sam_box(img: np.ndarray, box: list[float]) -> np.ndarray:
    import torch

    proc, model = sam()
    inp = proc(images=img, input_boxes=[[box]], return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model(**inp, multimask_output=False)
    m = proc.post_process_masks(out.pred_masks.cpu(), inp["original_sizes"].cpu())[0]
    return m[0, 0].numpy() > 0.5


def embed(crops: list[np.ndarray]) -> np.ndarray:
    import torch

    proc, model = dino()
    with torch.no_grad():
        f = model(**proc(images=crops, return_tensors="pt").to("cuda")).pooler_output
    return torch.nn.functional.normalize(f, dim=-1).cpu().numpy()


def _crop(img, mask, pad=0.08):
    ys, xs = np.nonzero(mask)
    h, w = mask.shape
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    px, py = int((x1 - x0) * pad), int((y1 - y0) * pad)
    return img[max(0, y0 - py): min(h, y1 + py), max(0, x0 - px): min(w, x1 + px)]


def item_check(final: np.ndarray, ref: np.ndarray, vis: np.ndarray, th: Th) -> dict:
    """One item. `vis` is its visible mask in the composite (the truth)."""
    area = vis.mean()
    if area < th.min_area:
        return {"present": False, "passed": False, "reason": "not visible in composite", "area": float(area)}
    ys, xs = np.nonzero(vis)
    box = [float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)]
    seg = sam_box(final, box)
    seg_ref = sam_box(ref, box)
    iou = mask_iou(seg, seg_ref)
    shift = max_edge_shift(seg, seg_ref)
    e = embed([_crop(final, vis), _crop(ref, vis)])
    emb = float(e[0] @ e[1])
    de = mean_color_delta_e(final, vis, ref, vis)
    pos_ok = iou >= th.iou and shift <= th.edge_px
    rec_ok = emb >= th.emb and de <= th.de
    return {"present": True, "area": float(area), "iou": iou, "edge_shift_px": shift, "emb": emb, "de": de,
            "position_ok": bool(pos_ok), "recognisable_ok": bool(rec_ok), "passed": bool(pos_ok and rec_ok)}


def edges(img: np.ndarray) -> np.ndarray:
    import cv2

    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), (0, 0), 1.5)
    return cv2.Canny(g, 40, 110) > 0


def moge_depth(img: np.ndarray) -> np.ndarray:
    import torch

    if "moge" not in _m:
        from huggingface_hub import hf_hub_download
        from moge.model.v3 import MoGeModel

        _m["moge"] = MoGeModel.from_pretrained(hf_hub_download(MOGE[0], "model.pt", revision=MOGE[1])).cuda().eval()
    x = torch.from_numpy(img).float().cuda().permute(2, 0, 1) / 255
    with torch.no_grad():
        out = _m["moge"].infer(x)
    return out["depth"].float().cpu().numpy()


def room_check(final: np.ndarray, ref: np.ndarray, ref_depth: np.ndarray, protect: np.ndarray, th: Th) -> dict:
    import cv2

    valid = ~cv2.dilate(protect.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    f1 = edge_f1(edges(final), edges(ref), tol=3, valid=valid)
    d = moge_depth(final)
    dref = ref_depth.astype(np.float32)
    rel = scale_invariant_depth_error(d, dref, np.isfinite(dref) & (dref > 0.2) & (dref < 15))
    ok = f1 >= th.edge_f1 and (np.isnan(rel) or rel <= th.depth_rel)
    return {"edge_f1": f1, "depth_rel": rel, "passed": bool(ok)}


def detect(img: np.ndarray) -> list[dict]:
    if "yoloe" not in _m:
        from ultralytics import YOLOE

        m = YOLOE("/vol/models/yoloe-26x-seg.pt")
        names = ["sofa", "chair", "armchair", "table", "coffee table", "bed", "lamp", "potted plant", "rug",
                 "wardrobe", "shelf", "cabinet", "tv", "picture frame", "vase", "pillow", "curtain", "stool",
                 "ottoman", "desk", "bench", "mirror", "clock", "basket", "bottle", "book", "person", "dog", "cat"]
        m.set_classes(names, m.get_text_pe(names))
        _m["yoloe"] = m
    r = _m["yoloe"].predict(img[..., ::-1].copy(), conf=0.2, verbose=False)[0]
    out = []
    for b, c, k in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(), r.boxes.cls.cpu().numpy(),
                       strict=True):
        out.append({"box": b.tolist(), "conf": float(c), "label": r.names[int(k)]})
    return out


def _box_iou(a, b):
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def invented_check(final: np.ndarray, ref: np.ndarray, product_union: np.ndarray, th: Th) -> dict:
    df, dr = detect(final), detect(ref)
    inv = []
    for d in df:
        if d["conf"] < th.invented_conf:
            continue
        if any(_box_iou(d["box"], r["box"]) > 0.3 for r in dr):
            continue
        x0, y0, x1, y1 = (int(v) for v in d["box"])
        sub = product_union[max(0, y0):y1, max(0, x0):x1]
        if sub.size and sub.mean() > 0.5:
            continue
        inv.append(d)
    return {"invented": inv, "passed": not inv}


AESTHETIC_Q = (
    "You are judging a photo of a redesigned room for a home-decor app. Rate from 1 to 10 how much a typical "
    "homeowner would want to live in this room as shown, considering how real and well lit it looks and how good "
    "the furniture and styling are. A room that looks fake, pasted-in or broken scores low. Reply with only the "
    "number."
)


def aesthetic(img: np.ndarray) -> float:
    import re

    import torch
    from PIL import Image

    if "vlm" not in _m:
        from transformers import AutoModelForImageTextToText, AutoProcessor

        _m["vlm"] = (AutoProcessor.from_pretrained(VLM[0], revision=VLM[1]),
                     AutoModelForImageTextToText.from_pretrained(VLM[0], revision=VLM[1], torch_dtype=torch.bfloat16)
                     .cuda().eval())
    proc, model = _m["vlm"]
    msgs = [{"role": "user", "content": [{"type": "image", "image": Image.fromarray(img)},
                                         {"type": "text", "text": AESTHETIC_Q}]}]
    inp = proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_dict=True,
                                   return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model.generate(**inp, max_new_tokens=6, do_sample=False)
    txt = proc.batch_decode(out[:, inp["input_ids"].shape[1]:], skip_special_tokens=True)[0]
    m = re.search(r"\d+(\.\d+)?", txt)
    return float(m.group()) if m else float("nan")


def check_render(final: np.ndarray, ref: np.ndarray, vis_masks: np.ndarray, ref_depth: np.ndarray,
                 cleared: np.ndarray, th: Th | None = None, with_aesthetic: bool = True) -> dict:
    th = th or Th()
    items = [item_check(final, ref, m, th) for m in vis_masks]
    union = vis_masks.any(0) if len(vis_masks) else np.zeros(final.shape[:2], bool)
    room = room_check(final, ref, ref_depth, union | cleared, th)
    inv = invented_check(final, ref, union, th)
    score = aesthetic(final) if with_aesthetic else float("nan")
    present = [i for i in items if i["present"]]
    passed = all(i["passed"] for i in present) and room["passed"] and inv["passed"] and \
        (np.isnan(score) or score >= th.aesthetic)
    return {"items": items, "room": room, "invented": inv, "aesthetic": score, "passed": bool(passed),
            "thresholds": asdict(th)}


def dumps(x) -> str:
    return json.dumps(x, indent=1, default=float)
