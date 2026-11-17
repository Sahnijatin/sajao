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


def floor_hits(k, c2w, w, h, fr: dict) -> tuple[np.ndarray, np.ndarray]:
    """Optical-axis depth to the floor (inf if the ray misses it) and the hit's space xy."""
    from bk.twin import to_space

    ys, xs = np.mgrid[0:h, 0:w]
    rays = np.stack(
        [(xs + 0.5 - k[0, 2]) / k[0, 0], (ys + 0.5 - k[1, 2]) / k[1, 1], np.ones_like(xs, float)],
        -1,
    )
    rs = (rays @ c2w[:3, :3].T) @ np.asarray(fr["R"]).T
    o = to_space(fr, c2w[:3, 3])
    with np.errstate(divide="ignore", invalid="ignore"):
        t = -o[2] / rs[..., 2]
    t = np.where(t > 0, t, np.inf)
    xy = o[:2] + rs[..., :2] * np.where(np.isfinite(t), t, 0)[..., None]
    return t, xy


def in_box(xy: np.ndarray, b: dict, margin: float) -> np.ndarray:
    """Points inside an oriented floor box (space frame) grown by `margin` metres."""
    a = np.radians(b.get("yaw_deg", 0.0))
    d = xy - np.asarray(b["center"])
    u = d[..., 0] * np.cos(a) + d[..., 1] * np.sin(a)
    v = -d[..., 0] * np.sin(a) + d[..., 1] * np.cos(a)
    return (np.abs(u) <= b["size"][0] / 2 + margin) & (np.abs(v) <= b["size"][1] / 2 + margin)


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


# Removal is decided by object type only. The twin's type is the first filter; the photo
# detector then protects anything it sees as a fixture, built-in or window, because twin
# labels can be wrong (a radiator labelled "lamp").
REMOVE_TYPES = (
    "sofa",
    "armchair",
    "chair",
    "bed",
    "table",
    "stool",
    "ottoman",
    "bench",  # furniture
    "rug",
    "carpet",  # rugs
    "lamp",
    "pillow",
    "cushion",
    "vase",
    "bowl",
    "potted plant",
    "plant",
    "toy",
    "basket",
    "blanket",
    "book",
    "picture",
    "frame",  # decor
)
PROTECT_PROMPT = (
    "window. curtain. blind. radiator. door. cabinet. wardrobe. shelf. bookcase. fireplace. "
    "television. air conditioner. light switch. socket. ceiling light. built-in cupboard."
)


def removable(label: str) -> bool:
    return any(t == label or t in label.split() for t in REMOVE_TYPES)


def c3_prep(room: str, variant: str, fi_hero: int, items: list[dict], n: int = 4) -> dict:
    """Photos, removal masks and plane depth for the chosen keyframes (twin image)."""
    import cv2
    import torch
    from bk.compose import camera, render_splat, wall_planes
    from bk.twin import load_twin, room_dir
    from scipy.ndimage import binary_dilation, binary_fill_holes
    from twin_gpu.common import read_rgb, scene_dir

    scene, original, labels, _ = load_twin(room)
    sv = json.loads((room_dir(room) / "survey.json").read_text())
    fr = sv["frame"]
    removed = np.load(room_dir(room) / f"removed_{variant}.npy")
    dropped = []
    if labels is not None:
        boxes = {b["id"]: b for b in sv.get("instances", sv.get("boxes", []))}
        ids = [int(i) for i in np.unique(labels[removed]) if i > 0]
        keep_ids = [i for i in ids if i in boxes and removable(boxes[i]["label"])]
        dropped = [(i, boxes[i]["label"]) for i in ids if i not in keep_ids and i in boxes]
        removed = np.isin(labels, keep_ids)
    frames = choose_keyframes(room, scene, original, removed, fi_hero, n)
    walls = wall_planes(original, fr, items, max_walls=4)
    out = c3_dir(room, variant)
    rm = torch.from_numpy(removed).cuda()
    kept_boxes = [boxes[i] for i in keep_ids] if labels is not None else []
    for fi in frames:
        k, c2w, w, h = camera(scene, fi)
        _, rd, ra = render_splat(original, k, c2w, w, h, mask=rm)
        _, fd, _ = render_splat(original, k, c2w, w, h)
        # only where the removed furniture is the front surface (kept objects in front stay)
        mask = (ra > 0.2) & (rd <= fd + 0.05)
        # Instance map: which removed object each pixel belongs to (photo masks are snapped
        # to these with SAM on the diffusion side).
        inst = np.zeros((h, w), np.int16)
        for i in keep_ids if labels is not None else []:
            _, di, ai = render_splat(
                original, k, c2w, w, h, mask=torch.from_numpy(labels == i).cuda()
            )
            mi = (ai > 0.3) & (di <= fd + 0.05)
            inst[mi] = i
        # Contact shadows: floor around each removed footprint (0.3 m margin), where no kept
        # object stands in front of the floor.
        ft, fxy = floor_hits(k, c2w, w, h, fr)
        shadow = np.zeros((h, w), bool)
        for b in kept_boxes:
            shadow |= in_box(fxy, b, 0.3)
        shadow &= np.isfinite(ft) & ((fd >= ft - 0.1) | mask)
        # Close gaps inside the furniture silhouette so no fragments survive the inpaint.
        mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
        mask = binary_dilation(binary_fill_holes(mask), iterations=6)
        photo = read_rgb(scene_dir(room) / scene["frames"][fi]["file"])
        photo = cv2.resize(photo, (w, h), interpolation=cv2.INTER_LANCZOS4)
        pd = plane_depth(k, c2w, w, h, fr, walls).astype(np.float32)
        np.savez_compressed(
            out / f"{fi}.npz",
            photo=photo,
            mask=mask,
            inst=inst,
            shadow=shadow,
            plane_depth=pd,
            K=k,
            c2w=c2w,
        )
    meta = {
        "room": room,
        "variant": variant,
        "hero": fi_hero,
        "frames": frames,
        "walls": len(walls),
        "not_removed": dropped,
        "types": sorted({boxes[i]["label"].split()[-1] for i in keep_ids})
        if labels is not None
        else [],
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


def protect_mask(rgb: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Pixels the photo shows as fixtures, built-ins or windows (Grounding DINO + SAM 2.1)."""
    import torch
    from bk import assets
    from PIL import Image

    if "gd" not in assets._det:  # load once, same pinned models as the listing recut
        assets.product_mask(np.zeros((64, 64, 3), np.uint8), "sofa")
    proc, model = assets._det["gd"]
    sp, sm = assets._det["sam"]
    img = Image.fromarray(rgb)
    inp = proc(images=img, text=PROTECT_PROMPT, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model(**inp)
    res = proc.post_process_grounded_object_detection(
        out, inp.input_ids, threshold=0.3, text_threshold=0.25, target_sizes=[rgb.shape[:2]]
    )[0]
    names = [str(x) for x in res.get("text_labels", res.get("labels", []))]
    m = np.zeros(rgb.shape[:2], bool)
    if len(res["scores"]) == 0:
        return m, []
    boxes = [b.tolist() for b in res["boxes"]]
    si = sp(images=img, input_boxes=[boxes], return_tensors="pt").to("cuda")
    with torch.no_grad():
        so = sm(**si, multimask_output=False)
    ms = sp.post_process_masks(so.pred_masks.cpu(), si["original_sizes"].cpu())[0][:, 0].numpy()
    for mi in ms:
        m |= mi > 0.5
    return m, names


def snap_mask(rgb: np.ndarray, v: dict) -> tuple[np.ndarray, dict]:
    """Photo-accurate removal mask: each removed object's splat silhouette is snapped to the
    photo with a SAM 2.1 box prompt, then contact shadows are added."""
    import cv2
    import torch
    from bk import assets
    from PIL import Image
    from scipy.ndimage import binary_dilation, binary_fill_holes

    if "sam" not in assets._det:
        assets.product_mask(np.zeros((64, 64, 3), np.uint8), "sofa")
    sp, sm = assets._det["sam"]
    inst = v.get("inst")
    h, w = rgb.shape[:2]
    m = v["mask"].copy()
    stats = {"snapped": 0, "kept_splat": 0}
    if inst is not None:
        img = Image.fromarray(rgb)
        for i in [int(x) for x in np.unique(inst) if x > 0]:
            mi = inst == i
            if mi.sum() < 1500:
                continue
            ys, xs = np.nonzero(mi)
            px, py = 0.04 * (xs.max() - xs.min()), 0.04 * (ys.max() - ys.min())
            box = [
                max(0, xs.min() - px),
                max(0, ys.min() - py),
                min(w - 1, xs.max() + px),
                min(h - 1, ys.max() + py),
            ]
            si = sp(images=img, input_boxes=[[box]], return_tensors="pt").to("cuda")
            with torch.no_grad():
                so = sm(**si, multimask_output=False)
            ms = (
                sp.post_process_masks(so.pred_masks.cpu(), si["original_sizes"].cpu())[0][
                    0, 0
                ].numpy()
                > 0.5
            )
            iou = (ms & mi).sum() / max((ms | mi).sum(), 1)
            if iou > 0.4:
                m |= ms
                stats["snapped"] += 1
            else:
                stats["kept_splat"] += 1
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8)).astype(
        bool
    )
    m = binary_fill_holes(m)
    if "shadow" in v:
        m |= v["shadow"]
    return binary_dilation(m, iterations=6), stats


def remove_prompt(types: list[str]) -> str:
    names = ", ".join(sorted(set(types))) or "furniture"
    return (
        f"Remove the {names} from this room photo. Show the empty floor and walls that were "
        "behind them, continuing the same floor material, wall colour and lighting, with soft "
        "natural shading. Do not add any furniture or objects. Keep everything else exactly "
        "the same, including windows, curtains, radiators, doors and built-in units."
    )


def remove_edit(model, img, twin_mask, protect, prompt, refs, seed, band_src=None):
    """Instruction removal on the real photo (no grey area: grey regions invite the model to
    paint new furniture). Accept only the model's changes that touch the twin's removal
    mask, never protected fixtures. Returns (image, accepted mask, seconds)."""
    import cv2
    from bk import passes

    x0, y0, x1, y1 = passes.crop_box(twin_mask, ctx=1.3)
    crop = img[y0:y1, x0:x1]
    out, dt = passes.edit(model, [crop, *refs], prompt, seed)
    la = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB).astype(np.float32)
    lb = cv2.cvtColor(out, cv2.COLOR_RGB2LAB).astype(np.float32)
    diff = cv2.GaussianBlur(np.linalg.norm(la - lb, axis=-1), (0, 0), 3) > 12
    diff = cv2.morphologyEx(diff.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    tm = twin_mask[y0:y1, x0:x1]
    # Accept the twin's mask plus the model's changes within a 60 px band around it
    # (contact shadows, silhouette edges the splat missed); nothing further away.
    band = cv2.dilate(
        (band_src if band_src is not None else twin_mask)[y0:y1, x0:x1].astype(np.uint8),
        np.ones((121, 121), np.uint8),
    ).astype(bool)
    acc = tm | (diff.astype(bool) & band)
    # A changed blob that lies mostly in the band is taken whole (thin legs, lamp stems
    # the splat mask missed); blobs mostly outside it are the model's own inventions.
    n, cc = cv2.connectedComponents(diff)
    for c in range(1, n):
        comp = cc == c
        if (comp & band).sum() >= 0.6 * comp.sum():
            acc |= comp
    acc &= ~protect[y0:y1, x0:x1]
    acc = cv2.dilate(acc.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    soft = cv2.GaussianBlur(acc.astype(np.float32), (0, 0), 2.0)[..., None]
    soft = np.maximum(soft, cv2.erode(acc.astype(np.uint8), np.ones((3, 3), np.uint8))[..., None])
    res = img.astype(np.float32).copy()
    res[y0:y1, x0:x1] = res[y0:y1, x0:x1] * (1 - soft) + out.astype(np.float32) * soft
    full = np.zeros(twin_mask.shape, bool)
    full[y0:y1, x0:x1] = acc
    return np.clip(res, 0, 255).astype(np.uint8), full, dt


def c3_inpaint(room: str, variant: str, model: str = "qwen", baseline: bool = False) -> dict:
    """Remove furniture from the hero keyframe, carry the result to the other keyframes,
    let the model remove only what the hero never saw, and measure consistency against
    independent per-view removal (gen image)."""
    import cv2

    d = c3_dir(room, variant)
    prep = json.loads((d / "prep.json").read_text())
    views = {fi: dict(np.load(d / f"{fi}.npz")) for fi in prep["frames"]}
    hero = prep["hero"]
    prompt = remove_prompt(prep.get("types", []))
    protected, snapped, prot = {}, {}, {}
    for fi, v in views.items():
        v["mask"], snapped[fi] = snap_mask(v["photo"], v)
        pm, names = protect_mask(v["photo"])
        prot[fi] = cv2.dilate(pm.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
        protected[fi] = {"px": int((v["mask"] & prot[fi]).sum()), "types": sorted(set(names))}
        v["mask"] = v["mask"] & ~prot[fi]
    seconds = 0.0
    fills, independent, coverage = {}, {}, {}
    fills[hero], views[hero]["mask"], dt = remove_edit(
        model, views[hero]["photo"], views[hero]["mask"], prot[hero], prompt, [], 21
    )
    seconds += dt
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
        coverage[fi] = {
            "mask_px": int(v["mask"].sum()),
            "reprojected_px": int(valid.sum()),
            "model_filled_px": int(holes.sum()),
        }
        # Always one clean-up edit: repaint uncovered areas and the border ring (seams and
        # fragments the hero never saw); the reprojected core stays locked.
        core = cv2.erode(valid.astype(np.uint8), np.ones((31, 31), np.uint8)).astype(bool)
        work = holes | (v["mask"] & ~core)
        if work.sum() > 200:
            p2 = (
                prompt
                + " Image 2 shows the same room from another angle, already emptied; match it."
            )
            fills[fi], acc, dt = remove_edit(
                model,
                seeded,
                work,
                prot[fi] | core,
                p2,
                [fills[hero]],
                21 + fi,
                band_src=v["mask"],
            )
            v["mask"] = valid | acc
            seconds += dt
        else:
            fills[fi] = seeded
            v["mask"] = valid
        if baseline:
            independent[fi], _, dt = remove_edit(
                model, v["photo"], views[fi]["mask"], prot[fi], prompt, [], 21 + fi
            )
            seconds += dt
    # Consistency: reproject each non-primary fill into the primary and compare there.
    pairs = []
    for fi in views:
        if fi == hero:
            continue
        modes = [("propagated", fills[fi])]
        if fi in independent:
            modes.append(("independent", independent[fi]))
        for name, src in modes:
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
        np.save(d / f"{fi}_mask.npy", views[fi]["mask"])  # final mask, fixtures excluded
    for fi, img in independent.items():
        cv2.imwrite(str(d / f"{fi}_independent.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    # Note: propagated overlap matches the primary by construction (same pixels, resampled);
    # the independent baseline shows how far apart per-view inpaints drift without it.
    res = {
        "coverage": coverage,
        "protected": protected,
        "snapped": snapped,
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
