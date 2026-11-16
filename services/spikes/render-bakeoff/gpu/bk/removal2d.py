"""Arm C3 removal: 2D diffusion inpainting on 3 to 5 hero keyframes, consistent across views.

The twin's object labels give an exact mask of the furniture a design removes in every
keyframe. The primary keyframe is inpainted with the edit model (paste back inside the
mask only). Its fill is lifted onto the room's floor and wall planes and reprojected
into the other keyframes; the model then fills only what the primary view never saw,
with the primary result as a reference. Consistency is measured against a baseline
that inpaints every view independently.

Twin-side prep runs on the twin image (gsplat); inpainting runs on the gen image.
Files: /bk/rooms/<room>/c3/<variant>/<frame>.npz and c3/<variant>/inpaint.json.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

BK = Path("/bk")
SCALE = 2


def c3_dir(room: str, variant: str) -> Path:
    d = BK / "rooms" / room / "c3" / variant
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- twin side ----------


def plane_depth(k, c2w, w, h, fr: dict, walls: list[dict]) -> np.ndarray:
    """Depth along the optical axis to the nearest floor or wall plane hit (inf if none)."""
    from bk.twin import to_space

    ys, xs = np.mgrid[0:h, 0:w]
    rays = np.stack(
        [(xs + 0.5 - k[0, 2]) / k[0, 0], (ys + 0.5 - k[1, 2]) / k[1, 1], np.ones_like(xs, float)],
        -1,
    )
    rs = (rays @ c2w[:3, :3].T) @ np.asarray(
        fr["R"]
    ).T  # space-frame directions, z component of the camera ray = 1
    o = to_space(fr, c2w[:3, 3])
    best = np.full((h, w), np.inf)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = -o[2] / rs[..., 2]
        best = np.where(t > 0, t, np.inf)
        for wl in walls:
            a, n = np.asarray(wl["point"]), np.asarray(wl["normal"])
            denom = rs[..., 0] * n[0] + rs[..., 1] * n[1]
            tw = ((a - o[:2]) @ n) / denom
            hit = o[:2] + rs[..., :2] * tw[..., None]
            (x0, y0), (x1, y1) = wl["ends"]
            seg = np.array([x1 - x0, y1 - y0])
            u = ((hit - [x0, y0]) @ seg) / max(seg @ seg, 1e-9)
            z = o[2] + rs[..., 2] * tw
            ok = (tw > 0) & (u >= -0.05) & (u <= 1.05) & (z >= -0.05) & (z <= 2.8)
            best = np.where(ok & (tw < best), tw, best)
    return best  # t along a ray with unit z in camera space is the optical-axis depth


def choose_keyframes(room: str, scene, original, removed, fi_hero: int, n: int = 4) -> list[int]:
    """The hero plus up to n-1 sharp keyframes that see the removal zone from other angles."""
    import cv2
    import torch
    from bk.compose import render_splat
    from twin_gpu.common import read_rgb, scene_dir

    rm = torch.from_numpy(removed).cuda()
    cand = []
    for fi, f in enumerate(scene["frames"]):
        if fi % 3:  # every third frame is plenty for the choice
            continue
        k = np.asarray(f["K"], float)
        c2w = np.asarray(f["c2w"], float)
        _, _, ra = render_splat(original, k, c2w, f["w"], f["h"], mask=rm)
        area = float((ra > 0.2).mean())
        if area < 0.03:
            continue
        g = cv2.cvtColor(read_rgb(scene_dir(room) / f["file"]), cv2.COLOR_RGB2GRAY)
        sharp = float(cv2.Laplacian(g, cv2.CV_64F).var())
        cand.append((area * math.log1p(sharp), fi, c2w))
    cand.sort(reverse=True)
    hero_c2w = np.asarray(scene["frames"][fi_hero]["c2w"], float)
    chosen = [(fi_hero, hero_c2w)]
    for _, fi, c2w in cand:
        if len(chosen) >= n:
            break
        ok = True
        for _, c in chosen:
            ang = math.degrees(math.acos(np.clip(c2w[:3, 2] @ c[:3, 2], -1, 1)))
            if ang < 20 and np.linalg.norm(c2w[:3, 3] - c[:3, 3]) < 0.5:
                ok = False
                break
        if ok:
            chosen.append((fi, c2w))
    return [fi for fi, _ in chosen]


def c3_prep(room: str, variant: str, fi_hero: int, items: list[dict], n: int = 4) -> dict:
    """Photos, removal masks and plane depth for the chosen keyframes (twin image)."""
    import cv2
    import torch
    from bk.compose import camera, render_splat, wall_planes
    from bk.twin import load_twin, room_dir
    from scipy.ndimage import binary_dilation
    from twin_gpu.common import read_rgb, scene_dir

    scene, original, _, _ = load_twin(room)
    fr = json.loads((room_dir(room) / "survey.json").read_text())["frame"]
    removed = np.load(room_dir(room) / f"removed_{variant}.npy")
    frames = choose_keyframes(room, scene, original, removed, fi_hero, n)
    walls = wall_planes(original, fr, items, max_walls=4)
    out = c3_dir(room, variant)
    rm = torch.from_numpy(removed).cuda()
    for fi in frames:
        k, c2w, w, h = camera(scene, fi)
        _, rd, ra = render_splat(original, k, c2w, w, h, mask=rm)
        _, fd, _ = render_splat(original, k, c2w, w, h)
        # only where the removed furniture is the front surface (kept objects in front stay)
        mask = binary_dilation((ra > 0.2) & (rd <= fd + 0.05), iterations=6)
        photo = read_rgb(scene_dir(room) / scene["frames"][fi]["file"])
        photo = cv2.resize(photo, (w, h), interpolation=cv2.INTER_LANCZOS4)
        pd = plane_depth(k, c2w, w, h, fr, walls).astype(np.float32)
        np.savez_compressed(out / f"{fi}.npz", photo=photo, mask=mask, plane_depth=pd, K=k, c2w=c2w)
    meta = {
        "room": room,
        "variant": variant,
        "hero": fi_hero,
        "frames": frames,
        "walls": len(walls),
    }
    (out / "prep.json").write_text(json.dumps(meta, indent=1))
    return meta


# ---------- diffusion side ----------


def _project(pts_world, k, c2w):
    w2c = np.linalg.inv(c2w)
    pc = pts_world @ w2c[:3, :3].T + w2c[:3, 3]
    z = pc[:, 2]
    uv = pc[:, :2] / np.maximum(z[:, None], 1e-6) * [k[0, 0], k[1, 1]] + [k[0, 2], k[1, 2]]
    return uv, z


def _lift(view: dict, ys, xs):
    k, c2w, d = view["K"], view["c2w"], view["plane_depth"][ys, xs]
    cam = np.stack([(xs + 0.5 - k[0, 2]) / k[0, 0] * d, (ys + 0.5 - k[1, 2]) / k[1, 1] * d, d], 1)
    return cam @ c2w[:3, :3].T + c2w[:3, 3], np.isfinite(d)


def reproject_fill(src: dict, src_img: np.ndarray, dst: dict) -> tuple[np.ndarray, np.ndarray]:
    """Colours for dst's masked pixels taken from src's filled image through the planes.
    Returns (colours HxWx3, valid mask)."""
    h, w = dst["mask"].shape
    ys, xs = np.nonzero(dst["mask"])
    pts, ok = _lift(dst, ys, xs)
    uv, z = _project(pts, src["K"], src["c2w"])
    sh, sw = src["mask"].shape
    inside = (
        ok
        & (z > 0.1)
        & (uv[:, 0] >= 0)
        & (uv[:, 0] < sw - 1)
        & (uv[:, 1] >= 0)
        & (uv[:, 1] < sh - 1)
    )
    ui, vi = uv[inside, 0].astype(int), uv[inside, 1].astype(int)
    # only reuse pixels the source actually filled (its mask) or saw unoccluded at the same plane
    keep = src["mask"][vi, ui]
    col = np.zeros((h, w, 3), np.uint8)
    valid = np.zeros((h, w), bool)
    yy, xx = ys[inside][keep], xs[inside][keep]
    col[yy, xx] = src_img[vi[keep], ui[keep]]
    valid[yy, xx] = True
    return col, valid


def _psnr(a, b, m) -> float:
    if m.sum() < 50:
        return float("nan")
    mse = float(np.mean((a[m].astype(float) - b[m].astype(float)) ** 2))
    return float(10 * np.log10(255.0**2 / max(mse, 1e-6)))


def c3_inpaint(room: str, variant: str, model: str = "qwen") -> dict:
    """Inpaint the primary keyframe, propagate to the others, and measure consistency
    against independent per-view inpainting (gen image)."""
    import cv2
    from bk import passes

    d = c3_dir(room, variant)
    prep = json.loads((d / "prep.json").read_text())
    views = {fi: dict(np.load(d / f"{fi}.npz")) for fi in prep["frames"]}
    hero = prep["hero"]
    prompt = passes.CLEAN_PROMPT
    seconds = 0.0
    fills, independent = {}, {}
    fills[hero], dt = passes.region_edit(
        model, views[hero]["photo"], views[hero]["mask"], prompt, [], 21
    )
    seconds += dt
    ref = fills[hero]
    for fi, v in views.items():
        if fi == hero:
            continue
        col, valid = reproject_fill(views[hero], fills[hero], v)
        seeded = v["photo"].copy()
        seeded[valid] = col[valid]
        holes = v["mask"] & ~valid
        holes = cv2.morphologyEx(
            holes.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)
        ).astype(bool)
        if holes.sum() > 200:
            p2 = (
                prompt
                + " Image 2 shows the same room from another angle with the same area already filled; match it."
            )
            fills[fi], dt = passes.region_edit(model, seeded, holes, p2, [ref], 21 + fi)
            seconds += dt
        else:
            fills[fi] = seeded
        independent[fi], dt = passes.region_edit(model, v["photo"], v["mask"], prompt, [], 21 + fi)
        seconds += dt
    # Consistency: reproject each non-primary fill into the primary and compare there.
    pairs = []
    for fi in views:
        if fi == hero:
            continue
        for name, src in (("propagated", fills[fi]), ("independent", independent[fi])):
            col, valid = reproject_fill(views[fi], src, views[hero])
            pairs.append(
                {
                    "frame": fi,
                    "mode": name,
                    "overlap_px": int(valid.sum()),
                    "psnr_vs_primary": _psnr(col, fills[hero], valid),
                }
            )
    for fi, img in fills.items():
        cv2.imwrite(str(d / f"{fi}_inpainted.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    for fi, img in independent.items():
        cv2.imwrite(str(d / f"{fi}_independent.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    res = {
        "room": room,
        "variant": variant,
        "model": model,
        "hero": hero,
        "frames": list(views),
        "model_seconds": round(seconds, 1),
        "consistency": pairs,
    }
    (d / "inpaint.json").write_text(json.dumps(res, indent=1, default=float))
    return res
