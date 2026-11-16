"""Object removal for the twin worker, on the GPU: fill B with LaMa (Apache 2.0).

Ported from the removal comparison, where LaMa beat a diffusion model by 9 to
13 dB against real pixels. `remove` reads the splat, its labels and refined
cameras from the artifact store, takes out the named objects (the rule is in
sajao_workers.twin.removal), renders the hole in every keyframe, inpaints a
spread of those keyframes, fine-tunes the splat on them and writes it back.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import time
from pathlib import Path

import numpy as np
from splat_gpu import InputError, _decode_rgb, export_ply, optimise, render, scene_scale

# The TorchScript export published with simple-lama-inpainting v0.1.0, pinned by hash.
LAMA_URL = (
    "https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt"
)
LAMA_FILE = Path("/vol/models/big-lama.pt")
HOLE_ALPHA = 0.15  # rendered opacity of the removed Gaussians that counts as hole
HOLE_DILATE = 9  # pixels: covers the object's soft edge and shadow fringe

_lama = None


def _load_lama(sha256: str):
    global _lama
    if _lama is None:
        import torch

        if not LAMA_FILE.exists():
            LAMA_FILE.parent.mkdir(parents=True, exist_ok=True)
            part = LAMA_FILE.with_suffix(".part")
            subprocess.run(["curl", "-sSfL", "-o", str(part), LAMA_URL], check=True)  # noqa: S603, S607
            part.rename(LAMA_FILE)
        digest = hashlib.sha256(LAMA_FILE.read_bytes()).hexdigest()
        if digest != sha256:
            raise InputError(f"LaMa weights do not match the pinned hash ({digest[:12]})")
        _lama = torch.jit.load(str(LAMA_FILE), map_location="cuda").eval()
    return _lama


def inpaint(rgb: np.ndarray, mask: np.ndarray, sha256: str) -> np.ndarray:
    """Fill `mask` (H, W bool) in `rgb` (H, W, 3 uint8); pixels outside it are kept."""
    import torch
    import torch.nn.functional as F

    model = _load_lama(sha256)
    h, w = mask.shape
    img = torch.from_numpy(rgb).float().permute(2, 0, 1)[None].cuda() / 255.0
    m = torch.from_numpy(mask.astype(np.float32))[None, None].cuda()
    ph, pw = (8 - h % 8) % 8, (8 - w % 8) % 8
    img = F.pad(img, (0, pw, 0, ph), mode="reflect")
    m = F.pad(m, (0, pw, 0, ph), mode="reflect")
    with torch.no_grad():
        out = model(img, (m > 0).float())
    out = (out[0, :, :h, :w].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
    out[~mask] = rgb[~mask]
    return out


def load_ply(data: bytes):
    """Parameters from the standard 3DGS PLY that `export_ply` writes."""
    import torch

    end = data.index(b"end_header\n") + len(b"end_header\n")
    header = data[:end].decode().splitlines()
    count = next(int(line.split()[2]) for line in header if line.startswith("element vertex"))
    names = [line.split()[2] for line in header if line.startswith("property float")]
    table = np.frombuffer(data, np.float32, count * len(names), end).reshape(count, len(names))
    col = {n: i for i, n in enumerate(names)}

    def take(*keys: str) -> np.ndarray:
        return table[:, [col[k] for k in keys]]

    rest = sorted((n for n in names if n.startswith("f_rest_")), key=lambda n: int(n[7:]))
    k = len(rest) // 3
    shn = take(*rest).reshape(count, 3, k).transpose(0, 2, 1)
    values = {
        "means": take("x", "y", "z"),
        "scales": take("scale_0", "scale_1", "scale_2"),
        "quats": take("rot_0", "rot_1", "rot_2", "rot_3"),
        "opacities": table[:, col["opacity"]],
        "sh0": take("f_dc_0", "f_dc_1", "f_dc_2")[:, None, :],
        "shN": shn,
    }
    return torch.nn.ParameterDict(
        {
            key: torch.nn.Parameter(torch.from_numpy(np.ascontiguousarray(v)).float().cuda())
            for key, v in values.items()
        }
    )


def _psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return 99.0 if mse == 0 else 10 * np.log10(255.0**2 / mse)


def remove(payload: dict, store, lama_sha256: str, steps: int = 5000) -> dict:
    """Take the objects in `payload["remove"]` (1-based labels) out of the splat."""
    import cv2
    import torch

    from sajao_workers.twin.removal import box_of, choose_frames, removal_set

    for key in ("splat", "labels", "cameras", "frames", "objects"):
        if not store.has_blob(payload[key]):
            raise InputError(f"{key} is not in the store")
    params = load_ply(store.read_blob(payload["splat"]))
    labels = np.load(io.BytesIO(store.read_blob(payload["labels"])))
    if len(labels) != len(params["means"]):
        raise InputError("labels do not match the splat")
    cameras = {c["keyframe_id"]: c["c2w"] for c in json.loads(store.read_blob(payload["cameras"]))}
    frames = json.loads(store.read_blob(payload["frames"]))["frames"]
    objects = json.loads(store.read_blob(payload["objects"]))
    if any(f["keyframe_id"] not in cameras for f in frames):
        raise InputError("a keyframe has no refined camera")

    c2w = np.array([cameras[f["keyframe_id"]] for f in frames], dtype=np.float64)
    means = params["means"].detach().cpu().numpy()
    opacity = torch.sigmoid(params["opacities"]).detach().cpu().numpy()
    gone = np.zeros(len(means), bool)
    for index in payload["remove"]:
        if not 1 <= index <= len(objects):
            raise InputError(f"no object {index}")
        box = box_of(objects[index - 1])
        gone |= removal_set(means, opacity, labels, index, box, c2w[:, :3, 3].mean(0))

    rgbs = [_decode_rgb(store.read_blob(f["image"])) for f in frames]
    h, w = rgbs[0].shape[:2]
    ks = torch.tensor([f["intrinsics"] for f in frames], dtype=torch.float32, device="cuda")
    vms = torch.linalg.inv(torch.tensor(c2w, dtype=torch.float32, device="cuda"))
    gone_t = torch.from_numpy(gone).cuda()
    kernel = np.ones((HOLE_DILATE, HOLE_DILATE), np.uint8)
    holes = []
    for j in range(len(frames)):
        with torch.no_grad():
            _, alpha, _ = render(params, vms[j : j + 1], ks[j : j + 1], w, h, mask=gone_t)
        hit = (alpha[0, ..., 0] > HOLE_ALPHA).cpu().numpy().astype(np.uint8)
        holes.append(cv2.dilate(hit, kernel) > 0)
    inpaint_at, drop = choose_frames([float(m.mean()) for m in holes])

    started = time.time()
    imgs = torch.from_numpy(np.stack(rgbs)).cuda()
    for j in inpaint_at:
        imgs[j] = torch.from_numpy(inpaint(rgbs[j], holes[j], lama_sha256)).cuda()
    torch.cuda.synchronize()
    inpaint_seconds = time.time() - started

    keep = ~gone_t
    edited = torch.nn.ParameterDict(
        {k: torch.nn.Parameter(v.detach()[keep].clone()) for k, v in params.items()}
    )
    use = torch.tensor(sorted(set(range(len(frames))) - set(drop)), device="cuda")
    torch.manual_seed(0)
    started = time.time()
    edited = optimise(
        edited,
        imgs[use],
        vms[use],
        ks[use],
        steps,
        scene_scale(vms[use]) * 0.1,
        refine_stop=int(steps * 0.6),
        refine_start=100,
        reset_every=10**9,
        log="twin remove",
    )
    torch.cuda.synchronize()
    finetune_seconds = time.time() - started

    # Does the splat agree with the fills across views? Low agreement means a blotchy hole.
    agree = []
    for j in inpaint_at[:: max(1, len(inpaint_at) // 12)]:
        with torch.no_grad():
            rc, _, _ = render(edited, vms[j : j + 1], ks[j : j + 1], w, h)
        img = (rc[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
        agree.append(_psnr(img[holes[j]], imgs[j].cpu().numpy()[holes[j]]))

    preview = None
    if payload.get("preview"):
        # Before and after, side by side, where the hole is largest: for people to judge.
        views = sorted(inpaint_at, key=lambda j: -float(holes[j].mean()))[:2]
        rows = []
        for j in views:
            with torch.no_grad():
                rc, _, _ = render(edited, vms[j : j + 1], ks[j : j + 1], w, h)
            after = (rc[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
            rows.append(np.concatenate([rgbs[j], imgs[j].cpu().numpy(), after], axis=1))
        if rows:
            ok, jpg = cv2.imencode(".jpg", cv2.cvtColor(np.concatenate(rows), cv2.COLOR_RGB2BGR))
            preview = store.put_blob(jpg.tobytes()) if ok else None

    ply = Path("/tmp/twin_removed.ply")  # noqa: S108
    gaussians = export_ply(edited, ply)
    result = {
        "splat": store.put_blob(ply.read_bytes()),
        "gaussians": gaussians,
        "gaussians_removed": int(gone.sum()),
        "frames_inpainted": len(inpaint_at),
        "frames_dropped": len(drop),
        "fill_agreement_psnr": round(float(np.mean(agree)), 2) if agree else 0.0,
        "inpaint_seconds": round(inpaint_seconds, 1),
        "finetune_seconds": round(finetune_seconds, 1),
        "gpu": torch.cuda.get_device_name(),
    }
    if preview:
        result["preview"] = preview
    ply.unlink()
    return result
