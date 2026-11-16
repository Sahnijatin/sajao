"""Twin access for the bake-off: room frame, survey, clearing (fill B for many objects).

Reads the SJ-116 spike's twins from the `sajao-twin-risk` volume (/vol) and writes
to the bake-off volume (/bk/rooms/<room>/).

Space frame: origin on the floor below the camera centroid, z up, x along the
dominant wall direction. Design positions are in this frame, in metres.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

BK = Path("/bk")


def room_dir(room: str) -> Path:
    d = BK / "rooms" / room
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_twin(room: str):
    from twin_gpu.common import load_scene, out_dir
    from twin_gpu.splat import load_params

    scene = load_scene(room)
    params = load_params(out_dir(room) / "splat.pt")
    lp = out_dir(room) / "labels.npy"
    labels = np.load(lp) if lp.exists() else None
    edit = json.loads((out_dir(room) / "edit.json").read_text()) if (out_dir(room) / "edit.json").exists() else {}
    return scene, params, labels, edit


def space_frame(scene: dict, params) -> dict:
    """World -> space transform from the floor height and the dominant wall direction."""
    import cv2
    import torch

    up = np.asarray(scene["up"], np.float64)
    up /= np.linalg.norm(up)
    means = params["means"].detach().cpu().numpy().astype(np.float64)
    opac = torch.sigmoid(params["opacities"]).detach().cpu().numpy()
    solid = means[opac > 0.5]
    h = solid @ up
    # Floor: the densest height bin in the lowest 25 cm above the 1st percentile.
    lo = np.percentile(h, 1)
    hist, edges = np.histogram(h[(h > lo - 0.05) & (h < lo + 0.25)], bins=60)
    floor = float(edges[np.argmax(hist)] + (edges[1] - edges[0]) / 2)
    # Horizontal basis.
    a = np.cross(up, [1.0, 0, 0])
    if np.linalg.norm(a) < 0.1:
        a = np.cross(up, [0, 1.0, 0])
    a /= np.linalg.norm(a)
    b = np.cross(up, a)
    wall = solid[(h > floor + 1.0) & (h < floor + 2.0)]
    ang = 0.0
    if len(wall) > 100:
        pts = np.stack([wall @ a, wall @ b], 1).astype(np.float32)
        ang = math.radians(cv2.minAreaRect(pts)[2])
    ex = math.cos(ang) * a + math.sin(ang) * b
    ey = np.cross(up, ex)
    cams = np.array([np.asarray(f["c2w"])[:3, 3] for f in scene["frames"]])
    c = cams.mean(0)
    origin = c - (c @ up - floor) * up
    r = np.stack([ex, ey, up])  # rows: space axes in world
    return {"origin": origin.tolist(), "R": r.tolist(), "floor_world_height": floor}


def to_space(fr: dict, p: np.ndarray) -> np.ndarray:
    return (np.asarray(p) - np.asarray(fr["origin"])) @ np.asarray(fr["R"]).T


def to_world(fr: dict, p: np.ndarray) -> np.ndarray:
    return np.asarray(p) @ np.asarray(fr["R"]) + np.asarray(fr["origin"])


def instance_boxes(params, labels, fr: dict, names: dict) -> list[dict]:
    """Upright boxes of every labelled object, in the space frame (yaw in degrees)."""
    import cv2

    if labels is None:
        return []
    means = params["means"].detach().cpu().numpy()
    sp = to_space(fr, means)
    out = []
    for oid in np.unique(labels):
        if oid <= 0:
            continue
        sel = labels == oid
        if sel.sum() < 200:
            continue
        p = sp[sel]
        zlo, zhi = np.percentile(p[:, 2], [2, 98])
        core = p[(p[:, 2] >= zlo) & (p[:, 2] <= zhi)]
        (cx, cy), (w, d), ang = cv2.minAreaRect(core[:, :2].astype(np.float32))
        out.append({"id": int(oid), "label": names.get(str(int(oid)), "?"), "n": int(sel.sum()),
                    "center": [float(cx), float(cy)], "size": [float(w), float(d), float(zhi - max(zlo, 0))],
                    "z": [float(zlo), float(zhi)], "yaw_deg": float(ang)})
    return out


def survey(room: str) -> dict:
    """Top-down picture with a 0.5 m grid, objects and keyframes; frame and boxes as JSON."""
    import cv2
    import torch
    from twin_gpu.splat import render

    scene, params, labels, edit = load_twin(room)
    fr = space_frame(scene, params)
    boxes = instance_boxes(params, labels, fr, edit.get("instance_labels", {}))
    means = params["means"].detach()
    sp = torch.from_numpy(to_space(fr, means.cpu().numpy())).float().cuda()
    keep = (sp[:, 2] < 1.5) & (sp[:, 2] > -0.3)
    cams = np.array([np.asarray(f["c2w"]) for f in scene["frames"]])
    cpos = to_space(fr, cams[:, :3, 3])
    cdir = cams[:, :3, 2] @ np.asarray(fr["R"]).T
    xy = sp[keep][:, :2].cpu().numpy()
    lo = np.minimum(np.percentile(xy, 1, axis=0), cpos[:, :2].min(0)) - 0.5
    hi = np.maximum(np.percentile(xy, 99, axis=0), cpos[:, :2].max(0)) + 0.5
    ppm = 100.0  # pixels per metre
    w, h = int((hi[0] - lo[0]) * ppm), int((hi[1] - lo[1]) * ppm)
    # Orthographic camera above the room looking down -z (space), image x = +x, image y = -y.
    rr = np.asarray(fr["R"])
    c2w = np.eye(4)
    c2w[:3, 0] = rr[0]
    c2w[:3, 1] = -rr[1]
    c2w[:3, 2] = -rr[2]
    centre_sp = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, 3.0])
    c2w[:3, 3] = to_world(fr, centre_sp)
    vm = torch.linalg.inv(torch.from_numpy(c2w).float().cuda())[None]
    k = torch.tensor([[[ppm, 0, w / 2], [0, ppm, h / 2], [0, 0, 1]]], dtype=torch.float32, device="cuda")
    with torch.no_grad():
        rc, _, _ = render(params, vm, k, w, h, mask=keep, camera_model="ortho")
    img = (rc[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def px(p):
        return int((p[0] - lo[0]) * ppm), int((hi[1] - p[1]) * ppm)

    for gx in np.arange(math.floor(lo[0] * 2) / 2, hi[0], 0.5):
        cv2.line(img, px((gx, lo[1])), px((gx, hi[1])), (90, 90, 90) if gx % 1 else (0, 0, 0), 1)
    for gy in np.arange(math.floor(lo[1] * 2) / 2, hi[1], 0.5):
        cv2.line(img, px((lo[0], gy)), px((hi[0], gy)), (90, 90, 90) if gy % 1 else (0, 0, 0), 1)
    for b in boxes:
        if b["n"] < 1500 or b["label"] in ("pillow", "vase", "toy", "bowl"):
            continue
        rect = ((b["center"][0], b["center"][1]), (b["size"][0], b["size"][1]), b["yaw_deg"])
        pts = np.array([px(p) for p in cv2.boxPoints(rect)], np.int32)
        cv2.polylines(img, [pts], True, (0, 0, 255), 2)
        cv2.putText(img, f"{b['id']}:{b['label'][:10]}", px(b["center"]), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (0, 255, 255), 1)
    for i in range(0, len(cpos), 10):
        p0 = px(cpos[i])
        d = cdir[i][:2] / max(np.linalg.norm(cdir[i][:2]), 1e-6)
        cv2.arrowedLine(img, p0, px(cpos[i][:2] + 0.35 * d), (255, 128, 0), 2, tipLength=0.3)
        cv2.putText(img, str(i), p0, cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    d = room_dir(room)
    cv2.imwrite(str(d / "survey.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    out = {"room": room, "frame": fr, "extent": [lo.tolist(), hi.tolist()], "ppm": ppm, "boxes": boxes,
           "cameras": [{"i": i, "pos": cpos[i].tolist(), "dir": cdir[i].tolist(),
                        "split": scene["frames"][i]["split"]} for i in range(len(cpos))]}
    (d / "survey.json").write_text(json.dumps(out, indent=1))
    return {"room": room, "boxes": len(boxes), "size_px": [w, h]}


def clear_zone(room: str, remove_ids: list[int], tag: str, finetune_steps: int = 5000) -> dict:
    """Fill B for a set of objects at once: remove their Gaussians (plus the unseen
    margin around them, keeping shell planes), inpaint every training frame with
    LaMa, fine-tune the object-free splat. One pass for all objects of a design."""
    import cv2
    import torch
    from twin_gpu import lama
    from twin_gpu.common import out_dir
    from twin_gpu.edit import _inside_box, merge, shell_planes
    from twin_gpu.splat import load_frames, optimise, render, save_params, scene_scale

    from twin_risk.geometry import fit_upright_box

    t_all = time.time()
    scene, params, labels, _ = load_twin(room)
    up = np.asarray(scene["up"], np.float64)
    upi = int(np.argmax(np.abs(up)))
    means = params["means"].detach().cpu().numpy()
    remove = np.zeros(len(means), bool)
    cams = np.array([np.asarray(f["c2w"])[:3, 3] for f in scene["frames"]])
    for oid in remove_ids:
        voted = labels == oid
        if voted.sum() < 50:
            continue
        box = fit_upright_box(means[voted], upi)
        support_h = float(np.asarray(box.center) @ up - box.height / 2)
        above = (means @ up) > support_h + 0.04 * box.height
        in_box = _inside_box(means, box, up, pad=0.03 * max(box.length, 1e-3)) & above
        planes, thr = shell_planes(params, ~(voted | in_box), box, up, cams.mean(0), True)
        on_shell = np.zeros(len(means), bool)
        for n, origin, _, _ in planes:
            on_shell |= np.abs((means - origin) @ n) < 1.5 * thr
        margin = _inside_box(means, box, up, pad=0.15 * max(box.length, box.width)) & above
        remove |= voted | in_box | (margin & ~on_shell)
    keep = ~remove
    t0 = time.time()
    tidx, timgs, tks, tvms = load_frames(scene, room, "train")
    rm_t = torch.from_numpy(remove).cuda()
    inpainted = []
    for j in range(len(tidx)):
        f = scene["frames"][tidx[j]]
        with torch.no_grad():
            _, ra, _ = render(params, tvms[j : j + 1], tks[j : j + 1], f["w"], f["h"], mask=rm_t)
        m = ra[0, ..., 0].cpu().numpy() > 0.15
        m = cv2.dilate(m.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        inpainted.append(lama.inpaint(timgs[j].cpu().numpy(), m) if m.any() else timgs[j].cpu().numpy())
    inpaint_s = time.time() - t0
    filled = merge(params, keep, {})
    filled = optimise(
        filled, torch.from_numpy(np.stack(inpainted)).cuda(), tvms, tks, finetune_steps,
        scene_scale(tvms) * 0.1, refine_stop=int(finetune_steps * 0.6), refine_start=100,
        reset_every=10**9, log=f"{room} clear {tag}",
    )
    torch.cuda.synchronize()
    d = room_dir(room)
    save_params(filled, d / f"cleared_{tag}.pt")
    np.save(d / f"removed_{tag}.npy", remove)
    res = {"room": room, "tag": tag, "objects": remove_ids, "gaussians_removed": int(remove.sum()),
           "inpaint_seconds": round(inpaint_s, 1), "total_seconds": round(time.time() - t_all, 1),
           "gpu": torch.cuda.get_device_name(0)}
    (d / f"cleared_{tag}.json").write_text(json.dumps(res, indent=1))
    _ = out_dir
    return res
