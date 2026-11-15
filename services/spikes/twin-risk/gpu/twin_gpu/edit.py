"""Split a trained splat by object masks, hide one object, and fill the hole two ways.

A: plane fill. Fit the shell planes around the object (support plane, nearby
   walls), render each as an orthographic texture without the object, inpaint
   the hole in texture space with LaMa, and add flat Gaussians on the plane.
B: per-frame fill. Inpaint the object out of every training frame with LaMa and
   fine-tune the object-free splat on the inpainted frames.
"""

from __future__ import annotations

import math
import time

import numpy as np
from twin_gpu import lama
from twin_gpu.common import (
    load_scene,
    out_dir,
    read_rgb,
    save_json,
    scene_dir,
    up_vector,
    write_rgb,
)
from twin_gpu.objects import box_json, load_masks, object_frames
from twin_gpu.splat import (
    C0,
    load_frames,
    load_params,
    optimise,
    render,
    save_params,
    scene_scale,
)

from twin_risk.fusion import fuse
from twin_risk.geometry import UprightBox, fit_upright_box
from twin_risk.metrics import canonical_class
from twin_risk.split import BACKGROUND, decide_label

PREFERRED = ["sofa", "chair", "table", "stool", "bed", "tv_monitor", "shelf", "cabinet"]
PREFERRED_NAMES = ["potted plant", "lamp", "toy", "vase", "bowl", "ottoman"]


def _torch_frames(scene, name, frames):
    import torch

    ks = torch.tensor([scene["frames"][i]["K"] for i in frames], dtype=torch.float32, device="cuda")
    c2w = torch.tensor(
        [scene["frames"][i]["c2w"] for i in frames], dtype=torch.float32, device="cuda"
    )
    return ks, torch.linalg.inv(c2w)


def splat_depth(params, scene, name, frames) -> dict[int, np.ndarray]:
    import torch

    ks, vms = _torch_frames(scene, name, frames)
    out = {}
    with torch.no_grad():
        for j, fi in enumerate(frames):
            f = scene["frames"][fi]
            rc, ra, _ = render(params, vms[j : j + 1], ks[j : j + 1], f["w"], f["h"], mode="RGB+ED")
            d = rc[0, ..., 3].cpu().numpy()
            a = ra[0, ..., 0].cpu().numpy()
            out[fi] = np.where(a > 0.5, d, 0.0).astype(np.float32)
    return out


def instances_from_splat(params, name):
    """Lift masks with splat depth and fuse into 3D instances (works without LiDAR)."""
    from twin_gpu.objects import lift

    scene = load_scene(name)
    frames = object_frames(scene)
    depths = splat_depth(params, scene, name, frames)
    obs, _ = lift(name, frames, depths.get)
    inst = fuse(obs)
    return inst, frames, depths


def vote_labels(params, scene, name, frames, depths, inst_ids):
    """Per-Gaussian label from mask votes in views where its centre is visible."""
    import torch

    n = len(params["means"])
    n_obj = max(inst_ids.values(), default=0) + 1
    votes = torch.zeros((n, n_obj), dtype=torch.int32, device="cuda")
    visible = torch.zeros(n, dtype=torch.int32, device="cuda")
    ks, vms = _torch_frames(scene, name, frames)
    means = params["means"].detach()
    homo = torch.cat([means, torch.ones(n, 1, device="cuda")], 1)
    metric = scene.get("metric", True)
    for j, fi in enumerate(frames):
        if scene["frames"][fi]["split"] != "train":
            continue
        f = scene["frames"][fi]
        masks, labels, _, _ = load_masks(name, fi)
        idmap = np.zeros((f["h"], f["w"]), np.int32)
        order = np.argsort([-m.sum() for m in masks])  # small masks drawn last win overlaps
        for mi in order:
            oid = inst_ids.get(fi * 1000 + int(mi))
            if oid:
                idmap[masks[mi]] = oid
        cam = homo @ vms[j].T
        z = cam[:, 2]
        u = (ks[j, 0, 0] * cam[:, 0] / z + ks[j, 0, 2]).long()
        v = (ks[j, 1, 1] * cam[:, 1] / z + ks[j, 1, 2]).long()
        ok = (z > 0.05) & (u >= 0) & (u < f["w"]) & (v >= 0) & (v < f["h"])
        d = torch.from_numpy(depths[fi]).cuda()
        uu, vv = u.clamp(0, f["w"] - 1), v.clamp(0, f["h"] - 1)
        dr = d[vv, uu]
        tol = 0.05 * z + (0.03 if metric else 0.0)
        vis = ok & (dr > 0) & ((z - dr).abs() < tol)
        visible += vis.int()
        obj = torch.from_numpy(idmap).cuda()[vv, uu].long()
        hit = vis & (obj > 0)
        votes[hit.nonzero().flatten(), obj[hit]] += 1
    vis_np = visible.cpu().numpy()
    votes_np = votes.cpu().numpy()
    labels = np.zeros(n, np.int32)
    nz = np.nonzero(votes_np[:, 1:].sum(1))[0]
    for g in nz:
        row = votes_np[g]
        labels[g] = decide_label({k: int(row[k]) for k in np.nonzero(row)[0]}, int(vis_np[g]))
    return labels, vis_np


def _inside_box(points: np.ndarray, b: UprightBox, up: np.ndarray, pad: float) -> np.ndarray:
    a_, b_ = (i for i in range(3) if i != b.up_axis)
    rel = points - np.asarray(b.center)
    c, s = math.cos(b.yaw), math.sin(b.yaw)
    u = rel[:, a_] * c + rel[:, b_] * s
    v = -rel[:, a_] * s + rel[:, b_] * c
    h = rel[:, b.up_axis]
    return (
        (np.abs(u) <= b.length / 2 + pad)
        & (np.abs(v) <= b.width / 2 + pad)
        & (np.abs(h) <= b.height / 2 + pad)
    )


def choose_object(boxes, inst_gauss_counts, metric: bool):
    best, best_key = None, None
    for oid, (label, b, nframes) in boxes.items():
        if inst_gauss_counts.get(oid, 0) < 1500 or nframes < 4:
            continue
        if metric and not (0.25 < b.length < 2.6):
            continue
        cls = canonical_class(label)
        if cls in PREFERRED:
            rank = PREFERRED.index(cls)
        elif label in PREFERRED_NAMES:
            rank = len(PREFERRED) + PREFERRED_NAMES.index(label)
        else:
            continue
        key = (rank, -nframes)
        if best_key is None or key < best_key:
            best, best_key = oid, key
    return best


def ransac_planes(
    points: np.ndarray, thr: float, max_planes: int = 4, iters: int = 400, min_frac: float = 0.03
):
    rng = np.random.default_rng(0)
    planes = []
    rest = points
    for _ in range(max_planes):
        if len(rest) < 100:
            break
        best_in = None
        for _ in range(iters):
            p = rest[rng.choice(len(rest), 3, replace=False)]
            n = np.cross(p[1] - p[0], p[2] - p[0])
            if np.linalg.norm(n) < 1e-9:
                continue
            n /= np.linalg.norm(n)
            dist = np.abs((rest - p[0]) @ n)
            inl = dist < thr
            if best_in is None or inl.sum() > best_in.sum():
                best_in = inl
        if best_in is None or best_in.sum() < max(100, min_frac * len(points)):
            break
        q = rest[best_in]
        c = q.mean(0)
        _, _, vt = np.linalg.svd(q - c, full_matrices=False)
        planes.append((vt[2], c, int(best_in.sum())))
        rest = rest[~best_in]
    return planes


def _quat_from_matrix(r: np.ndarray) -> np.ndarray:
    """wxyz quaternion from a rotation matrix."""
    t = np.trace(r)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        return np.array(
            [0.25 * s, (r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s]
        )
    i = int(np.argmax(np.diag(r)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(1.0 + r[i, i] - r[j, j] - r[k, k]) * 2
    q = np.zeros(4)
    q[0] = (r[k, j] - r[j, k]) / s
    q[1 + i] = 0.25 * s
    q[1 + j] = (r[j, i] + r[i, j]) / s
    q[1 + k] = (r[k, i] + r[i, k]) / s
    return q


def plane_fill(
    params, keep: np.ndarray, box: UprightBox, up: np.ndarray, cam_center: np.ndarray, metric: bool
):
    """Approach A. Returns new Gaussian tensors and per-plane diagnostics."""
    import cv2
    import torch

    means = params["means"].detach().cpu().numpy()
    opac = torch.sigmoid(params["opacities"]).detach().cpu().numpy()
    diag = math.sqrt(box.length**2 + box.width**2 + box.height**2)
    region = (
        _inside_box(means, box, up, pad=0.6 * max(box.length, box.height)) & keep & (opac > 0.3)
    )
    thr = max(0.012 * diag, 0.01) if metric else 0.012 * diag
    planes = ransac_planes(means[region], thr)
    center = np.asarray(box.center)
    bottom = center @ up - box.height / 2
    corners = []
    a_, b_ = (i for i in range(3) if i != box.up_axis)
    for su in (-1, 1):
        for sv in (-1, 1):
            for sh in (-1, 1):
                c, s = math.cos(box.yaw), math.sin(box.yaw)
                p = center.copy()
                p[a_] += su * box.length / 2 * c - sv * box.width / 2 * s
                p[b_] += su * box.length / 2 * s + sv * box.width / 2 * c
                p[box.up_axis] += sh * box.height / 2
                corners.append(p)
    corners = np.array(corners)
    new = {k: [] for k in ("means", "scales", "quats", "opacities", "sh0")}
    diags = []
    for n, origin, n_in in planes:
        if np.dot(n, cam_center - origin) < 0:
            n = -n
        ndotup = abs(float(np.dot(n, up)))
        height = float(origin @ up)
        if ndotup > 0.9:
            if height > bottom + 0.15 * box.height:
                continue  # a horizontal surface above the object's base is not its support
            kind = "support"
        elif ndotup < 0.2:
            dist = abs(float((center - origin) @ n))
            if dist > 0.5 * diag + max(box.length, box.width) / 2:
                continue
            kind = "wall"
        else:
            continue
        o = origin + n * float((center - origin) @ n)  # object centre projected on the plane
        if ndotup < 0.9:
            ref = up
        else:
            ref = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 0, 1.0])
        e1 = np.cross(n, ref)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(e1, n)
        proj = np.stack([(corners - o) @ e1, (corners - o) @ e2], 1)
        margin = 0.25 * diag
        lo, hi = proj.min(0) - margin, proj.max(0) + margin
        texel = float((hi - lo).max() / 512)
        wpx, hpx = math.ceil((hi[0] - lo[0]) / texel), math.ceil((hi[1] - lo[1]) / texel)
        mid = o + (lo[0] + hi[0]) / 2 * e1 + (lo[1] + hi[1]) / 2 * e2
        dist_back = 2 * diag
        c2w = np.eye(4)
        c2w[:3, 0], c2w[:3, 1], c2w[:3, 2], c2w[:3, 3] = e1, e2, -n, mid + n * dist_back
        vm = torch.tensor(np.linalg.inv(c2w), dtype=torch.float32, device="cuda")[None]
        k = torch.tensor(
            [[1 / texel, 0, wpx / 2], [0, 1 / texel, hpx / 2], [0, 0, 1]],
            dtype=torch.float32,
            device="cuda",
        )[None]
        sd = (means - origin) @ n
        on_plane = torch.from_numpy(keep & (np.abs(sd) < 2 * thr)).cuda()
        with torch.no_grad():
            rc, ra, _ = render(
                params, vm, k, wpx, hpx, mask=on_plane, sh_degree=0, camera_model="ortho"
            )
        tex = (rc[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
        alpha = ra[0, ..., 0].cpu().numpy()
        px = ((proj - lo) / texel).astype(np.float32)
        hull = cv2.convexHull(px)
        region_m = np.zeros((hpx, wpx), np.uint8)
        cv2.fillConvexPoly(region_m, hull.astype(np.int32), 1)
        region_m = cv2.dilate(region_m, np.ones((9, 9), np.uint8)) > 0
        hole = region_m & (alpha < 0.7)
        if hole.sum() < 20:
            diags.append(
                {"kind": kind, "inliers": n_in, "hole_px": int(hole.sum()), "skipped": True}
            )
            continue
        filled = lama.inpaint(tex, hole)
        ys, xs = np.nonzero(hole)
        stride = 1 if len(ys) < 80_000 else 2
        ys, xs = ys[::stride], xs[::stride]
        pos = (
            mid[None]
            + ((xs + 0.5 - wpx / 2) * texel)[:, None] * e1
            + ((ys + 0.5 - hpx / 2) * texel)[:, None] * e2
        )
        pos = pos + n * 0.002 * diag
        rot = np.stack([e1, -e2, n], 1)
        q = _quat_from_matrix(rot)
        cols = filled[ys, xs] / 255.0
        m = len(pos)
        sc = texel * stride * 0.8
        new["means"].append(pos)
        new["scales"].append(np.log(np.tile([sc, sc, sc * 0.1], (m, 1))))
        new["quats"].append(np.tile(q, (m, 1)))
        new["opacities"].append(np.full(m, math.log(0.95 / 0.05)))
        new["sh0"].append(((cols - 0.5) / C0)[:, None, :])
        diags.append(
            {
                "kind": kind,
                "inliers": n_in,
                "texture_px": [wpx, hpx],
                "texel": texel,
                "hole_px": int(hole.sum()),
                "new_gaussians": m,
            }
        )
        plane_fill.textures.append((kind, tex, hole, filled))
    return new, diags


plane_fill.textures = []


def merge(params, keep: np.ndarray, new: dict):
    import torch

    keep_t = torch.from_numpy(keep).cuda()
    out = {}
    for key in ("means", "scales", "quats", "opacities", "sh0", "shN"):
        base = params[key].detach()[keep_t]
        if new.get("means") and key != "shN":
            add = torch.tensor(np.concatenate(new[key]), dtype=torch.float32, device="cuda")
            base = torch.cat([base, add], 0)
        elif new.get("means"):
            m = sum(len(x) for x in new["means"])
            base = torch.cat([base, torch.zeros((m, *base.shape[1:]), device="cuda")], 0)
        out[key] = torch.nn.Parameter(base.contiguous())
    return torch.nn.ParameterDict(out)


def to_img(rc) -> np.ndarray:
    return (rc[0, ..., :3].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)


def detector_score(rgb: np.ndarray, label: str, box_xyxy) -> float:
    """Highest detector score for `label` overlapping the object's image box."""
    import torch
    from PIL import Image
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    from twin_gpu.objects import GDINO

    if not hasattr(detector_score, "m"):
        detector_score.p = AutoProcessor.from_pretrained(GDINO)
        detector_score.m = AutoModelForZeroShotObjectDetection.from_pretrained(GDINO).cuda().eval()
    p, m = detector_score.p, detector_score.m
    h, w = rgb.shape[:2]
    inp = p(images=Image.fromarray(rgb), text=label + ".", return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = m(**inp)
    res = p.post_process_grounded_object_detection(
        out, inp.input_ids, threshold=0.05, text_threshold=0.05, target_sizes=[(h, w)]
    )[0]
    x0, y0, x1, y1 = box_xyxy
    best = 0.0
    for b, s in zip(res["boxes"].tolist(), res["scores"].tolist(), strict=True):
        ix = max(0, min(x1, b[2]) - max(x0, b[0]))
        iy = max(0, min(y1, b[3]) - max(y0, b[1]))
        if ix * iy > 0.3 * (b[2] - b[0]) * (b[3] - b[1]):
            best = max(best, float(s))
    return best


def run_edit(name: str, finetune_steps: int = 5000) -> dict:
    import cv2
    import torch

    scene = load_scene(name)
    od = out_dir(name)
    params = load_params(od / "splat.pt")
    up = up_vector(scene)
    upi = int(np.argmax(np.abs(up)))
    timings = {}

    t0 = time.time()
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
    labels, _visible = vote_labels(params, scene, name, frames, depths, inst_ids)
    timings["split_seconds"] = round(time.time() - t0, 1)
    counts = {
        int(k): int(v)
        for k, v in zip(*np.unique(labels, return_counts=True), strict=True)
        if k != BACKGROUND
    }

    # Split quality: object-only render versus the 2D mask on held-out views.
    ious = {}
    test_frames = [fi for fi in frames if scene["frames"][fi]["split"] == "test"]
    ks, vms = _torch_frames(scene, name, test_frames)
    labels_t = torch.from_numpy(labels).cuda()
    per_view = []
    for j, fi in enumerate(test_frames):
        f = scene["frames"][fi]
        masks, mlabels, _, mboxes = load_masks(name, fi)
        for mi in range(len(mlabels)):
            o = inst_ids.get(fi * 1000 + mi)
            if not o or counts.get(o, 0) < 300:
                continue
            with torch.no_grad():
                _, ra, _ = render(
                    params, vms[j : j + 1], ks[j : j + 1], f["w"], f["h"], mask=labels_t == o
                )
            pred = ra[0, ..., 0].cpu().numpy() > 0.5
            gt = masks[mi]
            iou = float((pred & gt).sum() / max(1, (pred | gt).sum()))
            ious.setdefault(o, []).append(iou)
            per_view.append((fi, mi, o, int(gt.sum())))

    target = choose_object(boxes, counts, scene.get("metric", True))
    if target is None:
        raise RuntimeError("no suitable object to hide")
    label, box, nframes = boxes[target]
    means_np = params["means"].detach().cpu().numpy()
    voted = labels == target
    support_h = float(np.asarray(box.center) @ up - box.height / 2)
    above = (means_np @ up) > support_h + 0.04 * box.height
    in_box = _inside_box(means_np, box, up, pad=0.03 * max(box.length, 1e-3)) & above
    remove = voted | in_box
    keep = ~remove
    cams = np.array([np.asarray(f["c2w"])[:3, 3] for f in scene["frames"]])
    cam_center = cams.mean(0)

    removed = merge(params, keep, {})
    t0 = time.time()
    plane_fill.textures = []
    new, plane_diag = plane_fill(params, keep, box, up, cam_center, scene.get("metric", True))
    filled_a = merge(params, keep, new)
    torch.cuda.synchronize()
    timings["fill_a_seconds"] = round(time.time() - t0, 1)
    for t_i, (kind, tex, hole, filled) in enumerate(plane_fill.textures):
        vis = tex.copy()
        vis[hole] = (vis[hole] * 0.4 + np.array([255, 0, 0]) * 0.6).astype(np.uint8)
        write_rgb(od / "edit" / f"plane_{t_i}_{kind}.jpg", np.concatenate([vis, filled], axis=1))

    # Approach B: inpaint each training frame, then fine-tune the object-free splat.
    t0 = time.time()
    tidx, timgs, tks, tvms = load_frames(scene, name, "train")
    obj_mask_t = torch.from_numpy(remove).cuda()
    inpainted = []
    t_inp = time.time()
    for j in range(len(tidx)):
        f = scene["frames"][tidx[j]]
        with torch.no_grad():
            _, ra, _ = render(
                params, tvms[j : j + 1], tks[j : j + 1], f["w"], f["h"], mask=obj_mask_t
            )
        m = ra[0, ..., 0].cpu().numpy() > 0.15
        m = cv2.dilate(m.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        inpainted.append(lama.inpaint(timgs[j].cpu().numpy(), m))
    inpaint_s = time.time() - t_inp
    imgs_b = torch.from_numpy(np.stack(inpainted)).cuda()
    filled_b = merge(params, keep, {})
    scale = scene_scale(tvms)
    filled_b = optimise(
        filled_b,
        imgs_b,
        tvms,
        tks,
        finetune_steps,
        scale * 0.1,  # late-training learning rate for positions
        refine_stop=int(finetune_steps * 0.6),
        refine_start=100,
        reset_every=10**9,
        log=f"{name} fill-B",
    )
    torch.cuda.synchronize()
    timings["fill_b_seconds"] = round(time.time() - t0, 1)
    timings["fill_b_inpaint_seconds"] = round(inpaint_s, 1)
    save_params(filled_b, od / "splat_fill_b.pt")
    save_params(filled_a, od / "splat_fill_a.pt")
    np.save(od / "labels.npy", labels)

    # Before and after images on the two held-out views where the object is largest.
    views = sorted([v for v in per_view if v[2] == target], key=lambda v: -v[3])[:2]
    if not views:
        views = [(test_frames[0], -1, target, 0)]
    report_views = []
    for k_i, (fi, mi, _, _) in enumerate(views):
        f = scene["frames"][fi]
        kk, vv = _torch_frames(scene, name, [fi])
        photo = read_rgb(scene_dir(name) / f["file"])
        with torch.no_grad():
            full = to_img(render(params, vv, kk, f["w"], f["h"])[0])
            rem_rc, rem_a, _ = render(removed, vv, kk, f["w"], f["h"])
            a_img = to_img(render(filled_a, vv, kk, f["w"], f["h"])[0])
            b_rc, b_a, _ = render(filled_b, vv, kk, f["w"], f["h"])
            a_a = render(filled_a, vv, kk, f["w"], f["h"])[1]
        rem = to_img(rem_rc)
        b_img = to_img(b_rc)
        if mi >= 0:
            _, _, _, mboxes = load_masks(name, fi)
            masks, _, _, _ = load_masks(name, fi)
            region = cv2.dilate(masks[mi].astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
            bx = mboxes[mi].tolist()
        else:
            region = np.ones((f["h"], f["w"]), bool)
            bx = [0, 0, f["w"], f["h"]]

        def cov(a, region=region) -> float:
            return float(a[0, ..., 0].cpu().numpy()[region].mean())

        name_for_det = label if label in VOCAB_SAFE else (canonical_class(label) or label)
        report_views.append(
            {
                "frame": fi,
                "alpha_in_hole": {"removed": cov(rem_a), "fill_a": cov(a_a), "fill_b": cov(b_a)},
                "detector_score_for_object": {
                    "photo": detector_score(photo, name_for_det, bx),
                    "removed": detector_score(rem, name_for_det, bx),
                    "fill_a": detector_score(a_img, name_for_det, bx),
                    "fill_b": detector_score(b_img, name_for_det, bx),
                },
            }
        )
        tiles = [photo, full, rem, a_img, b_img]
        names = ["photo", "splat", "object hidden", "A: plane inpaint", "B: per-frame inpaint"]
        strip = []
        for t, nm in zip(tiles, names, strict=True):
            t = t.copy()
            cv2.rectangle(t, (0, 0), (t.shape[1], 28), (0, 0, 0), -1)
            cv2.putText(
                t, nm, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA
            )
            strip.append(t)
            write_rgb(od / "edit" / f"view{k_i}_{nm.split(':')[0].replace(' ', '_')}.jpg", t)
        write_rgb(od / "edit" / f"view{k_i}_strip.jpg", np.concatenate(strip, axis=1))

    from twin_gpu.objects import DET

    result = {
        "scene": name,
        "detector": DET,
        "instances": len(boxes),
        "instance_labels": {str(k): v[0] for k, v in boxes.items()},
        "gaussians": len(labels),
        "gaussians_assigned_to_objects": int((labels != BACKGROUND).sum()),
        "split_mask_iou_mean": float(np.mean([np.mean(v) for v in ious.values()]))
        if ious
        else None,
        "split_mask_iou_by_object": {
            boxes[o][0] + f"#{o}": float(np.mean(v)) for o, v in ious.items()
        },
        "hidden_object": {
            "id": target,
            "label": label,
            "box": box_json(label, box, nframes),
            "gaussians_voted": int(voted.sum()),
            "gaussians_in_box_extra": int((in_box & ~voted).sum()),
            "split_mask_iou": float(np.mean(ious[target])) if target in ious else None,
        },
        "fill_a": {"planes": plane_diag, "new_gaussians": int(sum(len(x) for x in new["means"]))},
        "fill_b": {
            "frames_inpainted": len(tidx),
            "finetune_steps": finetune_steps,
            "gaussians": len(filled_b["means"]),
        },
        "views": report_views,
        "timings": timings,
    }
    save_json(od / "edit.json", result)
    return result


VOCAB_SAFE = {"potted plant", "lamp", "toy", "vase", "bowl", "ottoman", "pillow"}
