"""Qwen-Image inpainting (Apache 2.0) with the 8-step Lightning LoRA (Apache 2.0).

Each hole is filled in a square crop around it, resized to about one megapixel
(the model's working size), then pasted back only inside the hole with a soft
edge. Seeds are fixed per frame so reruns give the same pixels.
"""

from __future__ import annotations

import math

import numpy as np

MODEL = "Qwen/Qwen-Image"
MODEL_REVISION = "75e0b4be04f60ec59a75f475837eced720f823b6"
LORA = "lightx2v/Qwen-Image-Lightning"
LORA_REVISION = "d468c534b360e0754c6bf9e38ed49e1e09cd2e2a"
LORA_FILE = "Qwen-Image-Lightning-8steps-V2.0-bf16.safetensors"
STEPS = 8
PROMPT = (
    "The empty part of a lived-in room where furniture was removed: the floor, wall and "
    "skirting continue naturally with the same material, colour, lighting and perspective. "
    "Nothing stands there."
)
WORK_PIXELS = 1024 * 1024

# Scheduler settings published with the Lightning LoRA.
SCHEDULER = {
    "base_image_seq_len": 256,
    "base_shift": math.log(3),
    "invert_sigmas": False,
    "max_image_seq_len": 8192,
    "max_shift": math.log(3),
    "num_train_timesteps": 1000,
    "shift": 1.0,
    "shift_terminal": None,
    "stochastic_sampling": False,
    "time_shift_type": "exponential",
    "use_beta_sigmas": False,
    "use_dynamic_shifting": True,
    "use_exponential_sigmas": False,
    "use_karras_sigmas": False,
}

NEGATIVE = "furniture, chair, sofa, armchair, cushion, pillow, table, box, object, person"
FULL_STEPS = 40
FULL_CFG = 4.0

_pipe = None
_full = None


def full_pipeline():
    """Qwen-Image without the Lightning LoRA: default scheduler, real guidance and a negative prompt."""
    global _full
    if _full is None:
        import torch
        from diffusers import QwenImageInpaintPipeline

        _full = QwenImageInpaintPipeline.from_pretrained(
            MODEL, revision=MODEL_REVISION, torch_dtype=torch.bfloat16
        ).to("cuda")
        _full.set_progress_bar_config(disable=True)
    return _full


def pipeline():
    global _pipe
    if _pipe is None:
        import torch
        from diffusers import FlowMatchEulerDiscreteScheduler, QwenImageInpaintPipeline

        scheduler = FlowMatchEulerDiscreteScheduler.from_config(SCHEDULER)
        _pipe = QwenImageInpaintPipeline.from_pretrained(
            MODEL, revision=MODEL_REVISION, scheduler=scheduler, torch_dtype=torch.bfloat16
        ).to("cuda")
        _pipe.load_lora_weights(LORA, weight_name=LORA_FILE, revision=LORA_REVISION)
        _pipe.fuse_lora()
        _pipe.set_progress_bar_config(disable=True)
    return _pipe


def _crop(mask: np.ndarray) -> tuple[int, int, int, int]:
    """A square-ish window around the hole with as much context as the hole itself."""
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    side = max(xs.max() - xs.min(), ys.max() - ys.min()) * 2.0
    side = int(min(max(side, 192), max(h, w)))
    x0 = int(np.clip(cx - side / 2, 0, max(0, w - side)))
    y0 = int(np.clip(cy - side / 2, 0, max(0, h - side)))
    return x0, y0, min(w, x0 + side), min(h, y0 + side)


def inpaint(rgb: np.ndarray, mask: np.ndarray, seed: int, full: bool = False) -> np.ndarray:
    import cv2
    import torch
    from PIL import Image

    if not mask.any():
        return rgb.copy()
    x0, y0, x1, y1 = _crop(mask)
    crop, hole = rgb[y0:y1, x0:x1], mask[y0:y1, x0:x1]
    ch, cw = hole.shape
    scale = math.sqrt(WORK_PIXELS / (ch * cw))
    width, height = max(16, round(cw * scale / 16) * 16), max(16, round(ch * scale / 16) * 16)
    grown = cv2.dilate(hole.astype(np.uint8) * 255, np.ones((7, 7), np.uint8))
    settings = (
        {"negative_prompt": NEGATIVE, "num_inference_steps": FULL_STEPS, "true_cfg_scale": FULL_CFG}
        if full
        else {"num_inference_steps": STEPS, "true_cfg_scale": 1.0}
    )
    out = (full_pipeline() if full else pipeline())(
        prompt=PROMPT,
        image=Image.fromarray(crop).resize((width, height), Image.LANCZOS),
        mask_image=Image.fromarray(grown).resize((width, height), Image.NEAREST),
        height=height,
        width=width,
        strength=1.0,
        generator=torch.Generator("cuda").manual_seed(seed),
        **settings,
    ).images[0]
    filled = np.asarray(out.resize((cw, ch), Image.LANCZOS))
    # Soft edge just outside the hole; pixels outside it stay the photo's.
    alpha = cv2.GaussianBlur(grown.astype(np.float32) / 255, (0, 0), 2.0)
    alpha = np.maximum(alpha, hole)[..., None]
    result = rgb.copy()
    result[y0:y1, x0:x1] = (alpha * filled + (1 - alpha) * crop).round().astype(np.uint8)
    return result
