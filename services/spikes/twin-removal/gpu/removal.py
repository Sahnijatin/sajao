"""Fill B with two inpainting models: LaMa versus Qwen-Image (diffusion).

Runs on the SJ-116 spike's splats and YOLOE masks (volume `sajao-twin-risk`).
For each case (a large and a small object in two ARKit living rooms):

1. prepare: the Gaussians to remove (same rule as the spike), the hole in every
   training frame, the frames to inpaint (at most MAX_INPAINT, the same for both
   models), and known-truth holes: the same hole shape shifted onto background
   the camera saw, so the fill can be scored against real pixels.
2. inpaint (per model): fill the chosen frames and the known-truth holes.
3. refill: fine-tune the object-free splat on each model's frames (frames that
   see the hole but were not inpainted are left out), then score it.
"""

from __future__ import annotations

import math
import time

import numpy as np
from prep_io import _psnr, load_prep, removal_dir, train_rgb
from twin_gpu.common import (
    load_scene,
    out_dir,
    read_rgb,
    save_json,
    scene_dir,
    up_vector,
    write_rgb,
)
from twin_gpu.edit import (
    _inside_box,
    choose_object,
    detector_score,
    instances_from_splat,
    merge,
    shell_planes,
    to_img,
    vote_labels,
)
from twin_gpu.splat import load_frames, load_params, optimise, render, scene_scale

from twin_risk.geometry import fit_upright_box
from twin_risk.split import BACKGROUND

# The objects the spike's edit run hid (edit.json), picked again with its own rule.
CASES = {
    "arkit_living_47331265": {"large": "sofa", "small": "chair armchair"},
    "arkit_living_41159541": {"large": "sofa", "small": "chair armchair"},
}
MAX_INPAINT = 48
MAX_KNOWN = 24
MIN_HOLE = 0.002  # fraction of the frame; smaller holes are ignored
FINETUNE_STEPS = 5000


def _context(name: str) -> dict:
    """The spike's split, rebuilt with its settings: Grounding DINO masks, refined poses."""
    from twin_gpu import objects

    objects.set_detector("gdino")
    objects.set_poses("refined")
    scene = load_scene(name)
    params = load_params(out_dir(name) / "splat.pt")
    up = up_vector(scene)
    upi = int(np.argmax(np.abs(up)))
    inst, frames, depths = instances_from_splat(params, name)
    inst_ids, boxes = {}, {}
    oid = 0
    for i in inst:
        n = len(i.frames)
        if n < 3:
            continue
        pts = i.core_points(max(2, math.ceil(0.15 * n)))
        if len(pts) < 8:
            continue
        oid += 1
        boxes[oid] = (i.label, fit_upright_box(pts, upi), n)
        for _fi, key in i.members:
            inst_ids[key] = oid
    labels, _ = vote_labels(params, scene, name, frames, depths, inst_ids)
    counts = {
        int(k): int(v)
        for k, v in zip(*np.unique(labels, return_counts=True), strict=True)
        if k != BACKGROUND
    }
    return {
        "scene": scene,
        "params": params,
        "up": up,
        "labels": labels,
        "boxes": boxes,
        "counts": counts,
    }


def _removal_set(ctx: dict, target: int) -> np.ndarray:
    """Same rule as the spike's hide_and_fill: voted, inside the box, and a margin off the shell."""
    scene, params, up, labels = ctx["scene"], ctx["params"], ctx["up"], ctx["labels"]
    _, box, _ = ctx["boxes"][target]
    metric = scene.get("metric", True)
    means = params["means"].detach().cpu().numpy()
    voted = labels == target
    support = float(np.asarray(box.center) @ up - box.height / 2)
    above = (means @ up) > support + 0.04 * box.height
    in_box = _inside_box(means, box, up, pad=0.03 * max(box.length, 1e-3)) & above
    cams = np.array([np.asarray(f["c2w"])[:3, 3] for f in scene["frames"]])
    planes, thr = shell_planes(params, ~(voted | in_box), box, up, cams.mean(0), metric)
    on_shell = np.zeros(len(means), bool)
    for n, origin, _, _ in planes:
        on_shell |= np.abs((means - origin) @ n) < 1.5 * thr
    margin = _inside_box(means, box, up, pad=0.15 * max(box.length, box.width)) & above
    return voted | in_box | (margin & ~on_shell & ~(voted | in_box))


def _shift(mask: np.ndarray, dy: int, dx: int) -> np.ndarray:
    h, w = mask.shape
    out = np.zeros_like(mask)
    ys, xs = slice(max(0, dy), min(h, h + dy)), slice(max(0, dx), min(w, w + dx))
    src_y, src_x = slice(max(0, -dy), min(h, h - dy)), slice(max(0, -dx), min(w, w - dx))
    out[ys, xs] = mask[src_y, src_x]
    return out


def known_hole(hole: np.ndarray) -> np.ndarray | None:
    """The hole moved onto pixels the camera saw, clear of the object and its margin."""
    import cv2

    h, w = hole.shape
    keepout = cv2.dilate(hole.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0
    area = hole.sum()
    for fx, fy in [(0.5, 0), (-0.5, 0), (0.33, 0), (-0.33, 0), (0.5, 0.25), (-0.5, -0.25)]:
        moved = _shift(hole, int(fy * h), int(fx * w))
        if moved.sum() >= 0.9 * area and not (moved & keepout).any():
            return moved
    return None


def prepare(name: str, kind: str) -> dict:
    import cv2
    import torch

    expected = CASES[name][kind]
    ctx = _context(name)
    target = choose_object(ctx["boxes"], ctx["counts"], ctx["scene"].get("metric", True), kind)
    label = ctx["boxes"][target][0] if target is not None else None
    if label != expected:
        raise RuntimeError(f"{name} {kind}: object {target} is {label}, expected {expected}")
    remove = _removal_set(ctx, target)
    scene, params = ctx["scene"], ctx["params"]
    tidx, _, tks, tvms = load_frames(scene, name, "train")
    mask_t = torch.from_numpy(remove).cuda()
    holes = []
    for j in range(len(tidx)):
        f = scene["frames"][tidx[j]]
        with torch.no_grad():
            _, alpha, _ = render(
                params, tvms[j : j + 1], tks[j : j + 1], f["w"], f["h"], mask=mask_t
            )
        m = alpha[0, ..., 0].cpu().numpy() > 0.15
        holes.append(cv2.dilate(m.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0)
    holes = np.stack(holes)
    seen = [j for j in range(len(tidx)) if holes[j].mean() >= MIN_HOLE]
    step = max(1, math.ceil(len(seen) / MAX_INPAINT))
    inpaint = seen[::step][:MAX_INPAINT]
    drop = sorted(set(seen) - set(inpaint))
    known = []
    for j in seen[:: max(1, len(seen) // MAX_KNOWN)]:
        moved = known_hole(holes[j])
        if moved is not None:
            known.append((j, moved))
        if len(known) == MAX_KNOWN:
            break
    d = removal_dir(name, kind)
    np.save(d / "remove.npy", remove)
    np.savez_compressed(
        d / "prep.npz",
        frames=np.array([tidx[j] for j in range(len(tidx))]),
        holes=np.packbits(holes, axis=-1),
        shape=np.array(holes.shape),
        inpaint=np.array(inpaint),
        drop=np.array(drop, dtype=int),
        known=np.array([j for j, _ in known], dtype=int),
        known_holes=np.packbits(np.stack([m for _, m in known]), axis=-1)
        if known
        else np.zeros((0,), np.uint8),
    )
    summary = {
        "object": int(target),
        "label": label,
        "gaussians_removed": int(remove.sum()),
        "train_frames": len(tidx),
        "frames_seeing_hole": len(seen),
        "frames_inpainted": len(inpaint),
        "frames_dropped": len(drop),
        "known_truth_holes": len(known),
        "mean_hole_fraction": round(float(holes[seen].mean()), 4) if seen else 0.0,
    }
    save_json(d / "prep.json", summary)
    return summary


def inpaint_lama(name: str, kind: str) -> dict:
    """LaMa on the chosen frames and the known-truth holes, same inputs as Qwen-Image."""
    from twin_gpu import lama

    prep = load_prep(name, kind)
    started = time.time()
    frames = [
        lama.inpaint(train_rgb(name, prep["frames"][j]), prep["holes"][j]) for j in prep["inpaint"]
    ]
    seconds = time.time() - started
    known = [
        lama.inpaint(train_rgb(name, prep["frames"][j]), m)
        for j, m in zip(prep["known"], prep["known_holes"], strict=True)
    ]
    d = removal_dir(name, kind)
    np.savez_compressed(
        d / "inpaint_lama.npz",
        frames=np.stack(frames),
        known=np.stack(known) if known else np.zeros((0,)),
    )
    out = {"model": "lama", "frames": len(frames), "inpaint_seconds": round(seconds, 1)}
    save_json(d / "inpaint_lama.json", out)
    return out


def _grow(box: tuple[int, int, int, int], shape: tuple[int, ...], minimum: int = 64):
    """Expand a box to at least `minimum` pixels per side, inside the image (LPIPS needs room)."""
    x0, y0, x1, y1 = box
    h, w = shape[:2]
    for lo, hi, size in ((0, 2, w), (1, 3, h)):
        need = minimum - (box[hi] - box[lo])
        if need > 0:
            a = max(0, (x0, y0)[lo] - need // 2)
            b = min(size, a + max(minimum, (x1, y1)[lo] - (x0, y0)[lo]))
            a = max(0, b - minimum)
            if lo == 0:
                x0, x1 = a, b
            else:
                y0, y1 = a, b
    return x0, y0, x1, y1


def _bbox(mask: np.ndarray, pad: int = 8) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    h, w = mask.shape
    return (
        max(0, xs.min() - pad),
        max(0, ys.min() - pad),
        min(w, xs.max() + pad + 1),
        min(h, ys.max() + pad + 1),
    )


def known_truth_scores(name: str, kind: str, model: str) -> dict:
    """PSNR inside the hole and LPIPS on the hole's box, against the real pixels."""
    import lpips
    import torch

    prep = load_prep(name, kind)
    z = np.load(removal_dir(name, kind) / f"inpaint_{model}.npz")
    if not len(prep["known"]):
        return {"holes": 0}
    net = lpips.LPIPS(net="alex", verbose=False).cuda()
    psnrs, lps = [], []
    for out, j, m in zip(z["known"], prep["known"], prep["known_holes"], strict=True):
        truth = train_rgb(name, prep["frames"][j])
        psnrs.append(_psnr(out[m], truth[m]))
        x0, y0, x1, y1 = _grow(_bbox(m), m.shape)

        def t(img: np.ndarray, x0=x0, y0=y0, x1=x1, y1=y1) -> torch.Tensor:
            crop = torch.from_numpy(img[y0:y1, x0:x1]).float().permute(2, 0, 1)[None] / 127.5 - 1
            return crop.cuda()

        with torch.no_grad():
            lps.append(float(net(t(out), t(truth)).item()))
    return {
        "holes": len(psnrs),
        "psnr_in_hole": round(float(np.mean(psnrs)), 2),
        "lpips_on_hole_box": round(float(np.mean(lps)), 4),
    }


def refill(name: str, kind: str, models: list[str]) -> dict:
    """Fine-tune the object-free splat on each model's frames and score it."""
    import cv2
    import torch
    from twin_gpu import lama

    scene = load_scene(name)
    params = load_params(out_dir(name) / "splat.pt")
    d = removal_dir(name, kind)
    remove = np.load(d / "remove.npy")
    keep = ~remove
    prep = load_prep(name, kind)
    tidx, timgs, tks, tvms = load_frames(scene, name, "train")
    label = CASES[name][kind].split()[-1]

    # Held-out views where the hole is largest, for images and the ghost check.
    test_idx, _, sks, svms = load_frames(scene, name, "test")
    mask_t = torch.from_numpy(remove).cuda()
    areas = []
    for j, fi in enumerate(test_idx):
        f = scene["frames"][fi]
        with torch.no_grad():
            _, a, _ = render(params, svms[j : j + 1], sks[j : j + 1], f["w"], f["h"], mask=mask_t)
        areas.append((float((a[0, ..., 0] > 0.15).float().mean()), j))
    views = [j for _, j in sorted(areas, reverse=True)[:2]]
    removed = merge(params, keep, {})

    results, tiles = {}, {}
    known = {m: known_truth_scores(name, kind, m) for m in models if m != "lama_all"}
    for model in models:
        started = time.time()
        imgs = timgs.clone()
        use = np.ones(len(tidx), bool)
        if model == "lama_all":  # the spike's setting: LaMa on every frame that sees the hole
            for j in range(len(tidx)):
                if prep["holes"][j].any():
                    out = lama.inpaint(timgs[j].cpu().numpy(), prep["holes"][j])
                    imgs[j] = torch.from_numpy(out).cuda()
        else:
            z = np.load(d / f"inpaint_{model}.npz")
            for out, j in zip(z["frames"], prep["inpaint"], strict=True):
                imgs[j] = torch.from_numpy(out).cuda()
            use[prep["drop"]] = False
        sel = torch.from_numpy(np.nonzero(use)[0]).cuda()
        filled = optimise(
            merge(params, keep, {}),
            imgs[sel],
            tvms[sel],
            tks[sel],
            FINETUNE_STEPS,
            scene_scale(tvms) * 0.1,
            refine_stop=int(FINETUNE_STEPS * 0.6),
            refine_start=100,
            reset_every=10**9,
            log=f"{name} {kind} {model}",
        )
        torch.cuda.synchronize()
        seconds = time.time() - started

        # Consistency: does the splat agree with the model's own fills across views?
        agree = []
        for j in prep["inpaint"][:: max(1, len(prep["inpaint"]) // 12)]:
            f = scene["frames"][tidx[j]]
            with torch.no_grad():
                img = to_img(render(filled, tvms[j : j + 1], tks[j : j + 1], f["w"], f["h"])[0])
            m = prep["holes"][j]
            agree.append(_psnr(img[m], imgs[j].cpu().numpy()[m]))

        ghost, rendered = [], []
        for j in views:
            f = scene["frames"][test_idx[j]]
            with torch.no_grad():
                img = to_img(render(filled, svms[j : j + 1], sks[j : j + 1], f["w"], f["h"])[0])
                _, a, _ = render(
                    params, svms[j : j + 1], sks[j : j + 1], f["w"], f["h"], mask=mask_t
                )
            hole = a[0, ..., 0].cpu().numpy() > 0.15
            if hole.any():
                ghost.append(detector_score(img, label, list(_bbox(hole, 0))))
            rendered.append(img)
        tiles[model] = rendered
        results[model] = {
            "train_frames_used": int(use.sum()),
            "refill_seconds": round(seconds, 1),
            "fill_agreement_psnr": round(float(np.mean(agree)), 2) if agree else None,
            "ghost_detector_score": round(float(np.mean(ghost)), 3) if ghost else None,
        }
        if model in known:
            results[model]["known_truth"] = known[model]

    names = {"lama": "LaMa", "qwen": "Qwen-Image", "lama_all": "LaMa, all frames"}
    for k, j in enumerate(views):
        f = scene["frames"][test_idx[j]]
        photo = read_rgb(scene_dir(name) / f["file"])
        with torch.no_grad():
            hidden = to_img(render(removed, svms[j : j + 1], sks[j : j + 1], f["w"], f["h"])[0])
        strip = []
        for title, img in [("photo", photo), ("object hidden", hidden)] + [
            (names[m], tiles[m][k]) for m in models
        ]:
            img = img.copy()
            cv2.rectangle(img, (0, 0), (img.shape[1], 28), (0, 0, 0), -1)
            cv2.putText(
                img, title, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA
            )
            strip.append(img)
        write_rgb(d / f"view{k}_strip.jpg", np.concatenate(strip, axis=1))

    out = {"scene": name, "kind": kind, "object": CASES[name][kind], "models": results}
    save_json(d / "refill.json", out)
    return out
