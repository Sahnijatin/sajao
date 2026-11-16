"""Per-SKU fidelity gate: render each asset from each listing photo's viewpoint and compare.

Viewpoint per photo is found by search: orbit cameras over azimuth, elevation and
field of view; silhouettes are compared after normalising both to their bounding
squares (so position and overall scale do not matter, but shape and proportion do).
The five best silhouettes are re-scored with colour and embedding; the best is kept.

Renders use nvdiffrast (evaluation only; NVIDIA source code license, see the register).
"""

from __future__ import annotations

import json
import math

import numpy as np
from bk.assets import BK, listing, load_mesh, load_rgba, to_listing_size

from bakeoff.metrics import crop_pad, mask_iou, mean_color_delta_e, square_crop

DINO = ("facebook/dinov2-base", "f9e44c81")
RES_SEARCH = 160
RES_FINAL = 384

_ctx = None
_dino = None


def ctx():
    global _ctx
    if _ctx is None:
        import nvdiffrast.torch as dr

        _ctx = dr.RasterizeCudaContext()
    return _ctx


def dino():
    global _dino
    if _dino is None:
        from transformers import AutoImageProcessor, AutoModel

        proc = AutoImageProcessor.from_pretrained(DINO[0], revision=DINO[1])
        model = AutoModel.from_pretrained(DINO[0], revision=DINO[1]).cuda().eval()
        _dino = (proc, model)
    return _dino


def embed(imgs: list[np.ndarray]) -> np.ndarray:
    import torch

    proc, model = dino()
    with torch.no_grad():
        x = proc(images=imgs, return_tensors="pt").to("cuda")
        f = model(**x).pooler_output
    f = torch.nn.functional.normalize(f, dim=-1)
    return f.cpu().numpy()


def look_at(eye: np.ndarray, target: np.ndarray, up=(0.0, 1.0, 0.0)) -> np.ndarray:
    """World-to-camera (OpenGL convention: camera looks down -z)."""
    f = target - eye
    f = f / np.linalg.norm(f)
    s = np.cross(f, up)
    s = s / max(np.linalg.norm(s), 1e-9)
    u = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def projection(fov_deg: float, near=0.05, far=50.0) -> np.ndarray:
    t = 1 / math.tan(math.radians(fov_deg) / 2)
    return np.array(
        [
            [t, 0, 0, 0],
            [0, t, 0, 0],
            [0, 0, -(far + near) / (far - near), -2 * far * near / (far - near)],
            [0, 0, -1, 0],
        ]
    )


def orbit(v: np.ndarray, az: float, el: float, fov: float) -> np.ndarray:
    """MVP for a camera on a sphere around the mesh, framing it fully."""
    lo, hi = v.min(0), v.max(0)
    c = (lo + hi) / 2
    r = np.linalg.norm(hi - lo) / 2
    dist = r / math.sin(math.radians(fov) / 2) * 1.05
    a, e = math.radians(az), math.radians(el)
    eye = c + dist * np.array([math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e)])
    return projection(fov) @ look_at(eye, c)


def render(v, f, col, mvps: np.ndarray, res: int, shade=True):
    """Batch render. Returns (rgb (B,res,res,3) float, mask (B,res,res) bool) as numpy."""
    import nvdiffrast.torch as dr
    import torch

    vt = torch.from_numpy(v).cuda().float()
    ft = torch.from_numpy(f).cuda().int()
    vh = torch.cat([vt, torch.ones_like(vt[:, :1])], 1)
    m = torch.from_numpy(mvps).cuda().float()
    clip = torch.einsum("bij,nj->bni", m, vh).contiguous()
    rast, _ = dr.rasterize(ctx(), clip, ft, (res, res))
    mask = rast[..., 3] > 0
    if col is None:
        col = np.full((len(v), 3), 0.7, np.float32)
    ct = torch.from_numpy(col).cuda().float()[None].expand(len(mvps), -1, -1).contiguous()
    rgb, _ = dr.interpolate(ct, rast, ft)
    if shade:
        # Face normals, lit from the camera plus ambient: close to a studio product shot.
        tri = vt[ft.long()]
        n = torch.nn.functional.normalize(
            torch.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0], dim=1), dim=1
        )
        fid = (rast[..., 3].long() - 1).clamp_min(0)
        nn = n[fid]
        inv = torch.linalg.inv(m)
        eye = inv[:, :3, 3] / inv[:, 3:, 3]
        cam_dir = torch.nn.functional.normalize(eye - vt.mean(0), dim=-1)[:, None, None, :]
        lam = (nn * cam_dir).sum(-1).abs()
        rgb = rgb * (0.55 + 0.45 * lam)[..., None]
    rgb = torch.where(mask[..., None], rgb, torch.ones_like(rgb))
    # nvdiffrast's image origin is the bottom row.
    return rgb.flip(1).clamp(0, 1).cpu().numpy(), mask.flip(1).cpu().numpy()


def norm_square(img: np.ndarray, mask: np.ndarray, res: int, fill=1.0):
    """Crop both to the mask's bounding square and resize to res."""
    import cv2

    x0, y0, side = square_crop(mask)
    im = crop_pad(img, x0, y0, side, fill)
    mk = crop_pad(mask.astype(np.uint8), x0, y0, side, 0)
    im = cv2.resize(im, (res, res), interpolation=cv2.INTER_AREA)
    mk = cv2.resize(mk, (res, res), interpolation=cv2.INTER_NEAREST) > 0
    return im, mk


GRID_AZ = np.arange(0, 360, 15.0)
GRID_EL = np.array([0.0, 10, 20, 30, 45])
GRID_FOV = np.array([20.0, 45.0])


def search_pose(v, f, photo_mask_sq: np.ndarray) -> list[tuple[float, float, float, float]]:
    """Top silhouette matches: [(iou, az, el, fov)], best first."""
    cands = [(a, e, fv) for a in GRID_AZ for e in GRID_EL for fv in GRID_FOV]
    res = []
    for s in range(0, len(cands), 120):
        chunk = cands[s : s + 120]
        _, masks = render(
            v, f, None, np.stack([orbit(v, *c) for c in chunk]), RES_SEARCH * 2, shade=False
        )
        for c, mk in zip(chunk, masks, strict=True):
            _, msq = norm_square(mk.astype(np.float32), mk, RES_SEARCH)
            res.append((mask_iou(msq, photo_mask_sq), *c))
    res.sort(reverse=True)
    best = res[0]
    # Local refinement around the best coarse pose.
    fine = [
        (best[1] + da, float(np.clip(best[2] + de, -10, 80)), best[3])
        for da in np.arange(-10, 10.1, 2.5)
        for de in np.arange(-7.5, 7.6, 2.5)
    ]
    _, masks = render(
        v, f, None, np.stack([orbit(v, *c) for c in fine]), RES_SEARCH * 2, shade=False
    )
    for c, mk in zip(fine, masks, strict=True):
        _, msq = norm_square(mk.astype(np.float32), mk, RES_SEARCH)
        res.append((mask_iou(msq, photo_mask_sq), *c))
    res.sort(reverse=True)
    out, seen = [], set()
    for r in res:
        key = (round(r[1] / 20), round(r[2] / 10))
        if key not in seen:
            seen.add(key)
            out.append(r)
        if len(out) == 5:
            break
    return out


def project_photo_colours(v, f, rgba: np.ndarray, pose) -> np.ndarray:
    """Vertex colours from the input photo at the found pose; unseen vertices take
    the colour of the nearest seen vertex (the real photo, never a model repaint)."""
    import nvdiffrast.torch as dr
    import torch
    from scipy.spatial import cKDTree

    _, az, el, fov = pose
    mvp = orbit(v, az, el, fov)
    mask = rgba[..., 3] > 127
    x0, y0, side = square_crop(mask)
    photo = crop_pad(rgba[..., :3], x0, y0, side, 255)
    pm = crop_pad(mask.astype(np.uint8), x0, y0, side, 0) > 0
    res = 512
    _, rmask = render(v, f, None, mvp[None], res, shade=False)
    rx0, ry0, rside = square_crop(rmask[0])
    vt = torch.from_numpy(v).cuda().float()
    clip = (
        torch.from_numpy(mvp).cuda().float() @ torch.cat([vt, torch.ones_like(vt[:, :1])], 1).T
    ).T
    ndc = clip[:, :3] / clip[:, 3:]
    px = ((ndc[:, 0] + 1) / 2 * res).cpu().numpy()
    py = ((1 - ndc[:, 1]) / 2 * res).cpu().numpy()
    depth = clip[:, 2].cpu().numpy() / clip[:, 3].cpu().numpy()
    rast, _ = dr.rasterize(
        ctx(), clip[None].contiguous(), torch.from_numpy(f).cuda().int(), (res, res)
    )
    zbuf = rast[0, ..., 2].flip(0).cpu().numpy()
    covered = rast[0, ..., 3].flip(0).cpu().numpy() > 0
    xi = np.clip(px.astype(int), 0, res - 1)
    yi = np.clip(py.astype(int), 0, res - 1)
    visible = covered[yi, xi] & (depth <= zbuf[yi, xi] + 2e-3)
    # Map render pixel -> photo pixel through the two bounding squares.
    u = (px - rx0) / rside * side
    w = (py - ry0) / rside * side
    ui = np.clip(u.astype(int), 0, side - 1)
    wi = np.clip(w.astype(int), 0, side - 1)
    visible &= pm[wi, ui]
    col = np.full((len(v), 3), np.nan, np.float32)
    col[visible] = photo[wi[visible], ui[visible]] / 255.0
    if visible.sum() == 0:
        return np.full((len(v), 3), 0.7, np.float32)
    tree = cKDTree(v[visible])
    _, nn = tree.query(v[~visible], k=1)
    col[~visible] = col[visible][nn]
    return col


def score_view(v, f, col, rgba: np.ndarray, emb_photo: np.ndarray) -> dict:
    mask = rgba[..., 3] > 127
    rgb = rgba[..., :3].astype(np.float32) / 255
    rgb[~mask] = 1.0
    _ph_img, ph_mask = norm_square(rgb, mask, RES_SEARCH)
    poses = search_pose(v, f, ph_mask)
    ph_img_f, ph_mask_f = norm_square(rgb, mask, RES_FINAL)
    best = None
    rgbs, masks = render(v, f, col, np.stack([orbit(v, *p[1:]) for p in poses]), RES_FINAL * 2)
    crops = []
    for rgb_r, mk in zip(rgbs, masks, strict=True):
        im, msq = norm_square(rgb_r, mk, RES_FINAL)
        crops.append((im, msq))
    embs = embed([(c[0] * 255).astype(np.uint8) for c in crops])
    for p, (im, msq), e in zip(poses, crops, embs, strict=True):
        iou = mask_iou(msq, ph_mask_f)
        de = mean_color_delta_e(
            (ph_img_f * 255).astype(np.uint8),
            ph_mask_f & msq,
            (im * 255).astype(np.uint8),
            ph_mask_f & msq,
        )
        sim = float(e @ emb_photo)
        key = iou + sim
        if best is None or key > best["_key"]:
            best = {
                "_key": key,
                "iou": iou,
                "de": de,
                "emb": sim,
                "az": p[1],
                "el": p[2],
                "fov": p[3],
                "_img": im,
            }
    return best


def gate_listing(model: str, lid: str, against: list[str]) -> dict:
    """Score asset `model` of each listing in [lid, *against] against lid's clean views.

    The first is the true pair; the rest are wrong-SKU pairs for calibration.
    """
    import cv2

    item = listing(lid)
    views = json.loads((BK / "cutouts" / lid / "views.json").read_text())
    clean = views["clean"]
    out = {
        "id": lid,
        "model": model,
        "category": item["category"],
        "clean_views": clean,
        "input_view": views["input"],
        "pairs": [],
    }
    if not clean or views["input"] is None:
        out["skipped"] = "no clean view"
        return out
    # Score only on held-out photos: every asset is built from the input photo, so
    # agreeing with that photo proves little. A listing with no other clean photo
    # is unverifiable, never a pass.
    clean = [i for i in clean if i != views["input"]]
    out["held_out_views"] = clean
    if not clean:
        out["unverifiable"] = True
        return out
    photos = {i: load_rgba(lid, i) for i in clean}
    embs = {}
    for i, p in photos.items():
        m = p[..., 3] > 127
        rgb = p[..., :3].copy()
        rgb[~m] = 255
        im, _ = norm_square(rgb.astype(np.float32) / 255, m, RES_FINAL)
        embs[i] = embed([(im * 255).astype(np.uint8)])[0]
    strips = []
    for k, aid in enumerate([lid, *against]):
        path = BK / "assets" / model / aid / "raw.glb"
        if not path.exists():
            out["pairs"].append({"asset": aid, "missing": True})
            continue
        v, f, col = load_mesh(path)
        a_item = listing(aid)
        v, size = to_listing_size(v, a_item["dims_cm"])
        textured = col is not None
        if not textured:
            # Untextured mesh: project the asset's own input photo onto it.
            a_views = json.loads((BK / "cutouts" / aid / "views.json").read_text())
            a_rgba = load_rgba(aid, a_views["input"])
            m = a_rgba[..., 3] > 127
            rgb = a_rgba[..., :3].astype(np.float32) / 255
            _, msq = norm_square(rgb, m, RES_SEARCH)
            pose = search_pose(v, f, msq)[0]
            col = project_photo_colours(v, f, a_rgba, pose)
        per_view = []
        for i in clean:
            s = score_view(v, f, col, photos[i], embs[i])
            img = s.pop("_img")
            s.pop("_key")
            s["view"] = i
            s["is_input"] = False
            per_view.append(s)
            if k == 0:
                ph = photos[i]
                m = ph[..., 3] > 127
                rgb = ph[..., :3].astype(np.float32) / 255
                rgb[~m] = 1
                pim, _ = norm_square(rgb, m, 256)
                strips.append(np.concatenate([pim, cv2.resize(img, (256, 256))], 1))
        out["pairs"].append(
            {
                "asset": aid,
                "true": k == 0,
                "textured_by_model": textured,
                "size": size,
                "views": per_view,
            }
        )
    if strips:
        d = BK / "gate" / model
        d.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(
            str(d / f"{lid}.jpg"),
            cv2.cvtColor((np.concatenate(strips, 0) * 255).astype(np.uint8), cv2.COLOR_RGB2BGR),
        )
        (d / f"{lid}.json").write_text(json.dumps(out, indent=1, default=float))
    return out


def prepare_asset(model: str, lid: str) -> dict:
    """Render-ready asset: mesh scaled by code to the listing size (y up, base at 0),
    vertex colours from the model's texture or, if untextured, projected from the
    listing photo; front direction from the input photo's camera azimuth."""
    import trimesh

    item = listing(lid)
    v, f, col = load_mesh(BK / "assets" / model / lid / "raw.glb")
    v, size = to_listing_size(v, item["dims_cm"])
    views = json.loads((BK / "cutouts" / lid / "views.json").read_text())
    rgba = load_rgba(lid, views["input"])
    m = rgba[..., 3] > 127
    rgb = rgba[..., :3].astype(np.float32) / 255
    _, msq = norm_square(rgb, m, RES_SEARCH)
    pose = search_pose(v, f, msq)[0]
    textured = col is not None
    if not textured:
        col = project_photo_colours(v, f, rgba, pose)
    front_az = float(round(pose[1] / 90.0) * 90.0 % 360)
    mesh = trimesh.Trimesh(
        v, f, vertex_colors=(np.clip(col, 0, 1) * 255).astype(np.uint8), process=False
    )
    d = BK / "assets" / model / lid
    mesh.export(d / "asset.ply")
    meta = {
        "id": lid,
        "model": model,
        "size_m": size["size_m"],
        "front_az_deg": front_az,
        "input_pose_az_el_fov": list(pose[1:]),
        "input_iou": pose[0],
        "textured_by_model": textured,
    }
    (d / "asset.json").write_text(json.dumps(meta, indent=1))
    return meta
