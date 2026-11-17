"""Generative passes: the lighting pass (C1, C2, C3) and arm B (guided region edits).

Open models run here on Modal (Qwen-Image-Edit-2511 with the Lightning LoRA, or
FLUX.2 klein 4B; both Apache 2.0). Gemini on Vertex AI plugs into the same
`edit()` call for arm B once its key exists.
"""

from __future__ import annotations

import time

import numpy as np

QWEN = ("Qwen/Qwen-Image-Edit-2511", "6f3ccc0b")
QWEN_LIGHTNING = (
    "lightx2v/Qwen-Image-Edit-2511-Lightning",
    "107d238d",
    "Qwen-Image-Edit-2511-Lightning-8steps-V1.0-bf16.safetensors",
)
FLUX2K = ("black-forest-labs/FLUX.2-klein-4B", "e7b7dc27")

LIGHT_PROMPT = (
    "Turn this into a professional interior photograph of the same room. Keep every object exactly the same: "
    "same shape, size, position, colour, pattern and material. Keep the walls, floor, windows and the camera "
    "exactly the same. Only improve the light: soft natural daylight, realistic soft shadows under and behind "
    "furniture, contact shadows where furniture meets the floor, subtle reflections on smooth surfaces. "
    "Do not add, remove or move anything."
)
CLEAN_PROMPT = (
    "Fill the grey area with the empty floor and wall that continue naturally around it, matching their colour, "
    "texture and lighting. The floor keeps exactly the material visible elsewhere in the image (carpet stays "
    "carpet, tiles stay tiles). Do not add any furniture or objects. Keep everything outside the grey area unchanged."
)


def place_prompt(name: str, kind: str) -> str:
    where = {"rug": "lying flat on the floor", "art": "hanging on the wall"}.get(
        kind, "standing on the floor"
    )
    return (
        f"Image 1 is a photo of a room with a grey area. Fill the grey area with the {name} shown in image 2, "
        f"{where}, seen from this camera's angle, sized and shaped to fill the grey area exactly. Copy the "
        "product from image 2 faithfully: same shape, colours, fabric and details. Match the room's lighting and "
        "add natural shadows. Keep everything outside the grey area unchanged."
    )


_pipes: dict = {}


def pipe(model: str):
    import torch

    if model in _pipes:
        return _pipes[model]
    if model == "qwen":
        from diffusers import QwenImageEditPlusPipeline

        p = QwenImageEditPlusPipeline.from_pretrained(
            QWEN[0], revision=QWEN[1], torch_dtype=torch.bfloat16
        )
        p.load_lora_weights(
            QWEN_LIGHTNING[0], revision=QWEN_LIGHTNING[1], weight_name=QWEN_LIGHTNING[2]
        )
        p.fuse_lora()
        p.to("cuda")
    elif model == "flux2k":
        from diffusers import Flux2KleinPipeline

        p = Flux2KleinPipeline.from_pretrained(
            FLUX2K[0], revision=FLUX2K[1], torch_dtype=torch.bfloat16
        )
        p.to("cuda")
    else:
        raise ValueError(model)
    p.set_progress_bar_config(disable=True)
    _pipes[model] = p
    return p


def _fit(w: int, h: int, mp: float = 1.05) -> tuple[int, int]:
    s = (mp * 1e6 / (w * h)) ** 0.5
    return int(round(w * s / 16) * 16), int(round(h * s / 16) * 16)


def edit(model: str, images: list[np.ndarray], prompt: str, seed: int) -> tuple[np.ndarray, float]:
    """One image edit. images[0] is the image being edited; the rest are references.
    Returns (uint8 RGB at images[0]'s size, seconds)."""
    import torch
    from PIL import Image

    h, w = images[0].shape[:2]
    ow, oh = _fit(w, h)
    pils = [Image.fromarray(images[0]).resize((ow, oh), Image.LANCZOS)] + [
        Image.fromarray(i) for i in images[1:]
    ]
    g = torch.Generator("cuda").manual_seed(seed)
    t0 = time.time()
    if model == "qwen":
        out = pipe(model)(
            image=pils,
            prompt=prompt,
            negative_prompt=" ",
            num_inference_steps=8,
            true_cfg_scale=1.0,
            generator=g,
            width=ow,
            height=oh,
        ).images[0]
    elif model == "flux2k":
        out = pipe(model)(
            image=pils,
            prompt=prompt,
            num_inference_steps=4,
            guidance_scale=1.0,
            generator=g,
            width=ow,
            height=oh,
        ).images[0]
    elif model == "gemini":
        from bk.gemini import gemini_edit

        out = gemini_edit(pils, prompt, seed)
    else:
        raise ValueError(model)
    dt = time.time() - t0
    return np.asarray(out.convert("RGB").resize((w, h), Image.LANCZOS)), dt


# ---------- arm B: region-by-region guided edits ----------

GREY = np.array([128, 128, 128], np.uint8)


def crop_box(mask: np.ndarray, ctx: float = 1.6, min_side: int = 384) -> tuple[int, int, int, int]:
    """Box around the mask with context, at least `min_side` each way, inside the image."""
    ys, xs = np.nonzero(mask)
    h, w = mask.shape
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    bw = int(min(w, max(min_side, (xs.max() - xs.min()) * ctx)))
    bh = int(min(h, max(min_side, (ys.max() - ys.min()) * ctx)))
    x0 = int(np.clip(cx - bw / 2, 0, w - bw))
    y0 = int(np.clip(cy - bh / 2, 0, h - bh))
    return x0, y0, x0 + bw, y0 + bh


def region_edit(
    model: str,
    img: np.ndarray,
    region: np.ndarray,
    prompt: str,
    refs: list[np.ndarray],
    seed: int,
    grey: bool = True,
) -> tuple[np.ndarray, float]:
    """Grey out `region` (unless grey=False), edit a crop around it, paste the result back
    inside the region only."""
    import cv2

    x0, y0, x1, y1 = crop_box(region)
    crop = img[y0:y1, x0:x1].copy()
    rc = region[y0:y1, x0:x1]
    if grey:
        crop[rc] = GREY
    out, dt = edit(model, [crop, *refs], prompt, seed)
    soft = cv2.GaussianBlur(rc.astype(np.float32), (0, 0), 2.0)
    soft = np.maximum(
        soft, cv2.erode(rc.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(np.float32)
    )[..., None]
    res = img.copy().astype(np.float32)
    res[y0:y1, x0:x1] = res[y0:y1, x0:x1] * (1 - soft) + out.astype(np.float32) * soft
    return np.clip(res, 0, 255).astype(np.uint8), dt


def arm_b(
    model: str,
    photo: np.ndarray,
    clear_region: np.ndarray,
    items: list[dict],
    full_masks: np.ndarray,
    refs: dict,
    check_item,
    retries: int = 2,
    seed0: int = 1,
) -> dict:
    """photo: keyframe (uint8, render size). clear_region: removed furniture (bool).
    items: render items; full_masks[i]: item i's silhouette from the composite (the
    layout guide). refs[i]: listing cutout on white. check_item(img, i) -> (passed, score, detail)."""
    import cv2

    log = []
    img = photo.copy()
    t_total = 0.0
    union = full_masks.any(0) if len(full_masks) else np.zeros(photo.shape[:2], bool)
    leftover = clear_region & ~cv2.dilate(union.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(
        bool
    )
    if leftover.sum() > 200:
        img, dt = region_edit(model, img, leftover, CLEAN_PROMPT, [], seed0)
        t_total += dt
        log.append({"step": "clean", "seconds": round(dt, 2), "px": int(leftover.sum())})
    order = sorted(range(len(items)), key=lambda i: -int(full_masks[i].sum()))
    for i in order:
        m = full_masks[i]
        if m.sum() < 100:
            log.append({"step": "place", "item": items[i]["id"], "skipped": "not in view"})
            continue
        region = cv2.dilate(m.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        if items[i]["tier"] != "art":
            # include the old furniture under the new item, if any
            region |= clear_region & cv2.dilate(
                m.astype(np.uint8), np.ones((41, 41), np.uint8)
            ).astype(bool)
        attempts = []
        for a in range(retries + 1):
            cand, dt = region_edit(
                model,
                img,
                region,
                place_prompt(items[i]["name"], items[i]["tier"]),
                [refs[i]],
                seed0 + 100 * (a + 1) + i,
            )
            t_total += dt
            ok, score, detail = check_item(cand, i)
            attempts.append(
                {
                    "attempt": a,
                    "passed": bool(ok),
                    "score": float(score),
                    "seconds": round(dt, 2),
                    "detail": detail,
                    "_img": cand,
                }
            )
            if ok:
                break
        best = max(attempts, key=lambda x: (x["passed"], x["score"]))
        img = best["_img"]
        for x in attempts:
            x.pop("_img")
        log.append(
            {
                "step": "place",
                "item": items[i]["id"],
                "attempts": attempts,
                "passed": best["passed"],
            }
        )
    return {"image": img, "log": log, "model_seconds": round(t_total, 1)}
