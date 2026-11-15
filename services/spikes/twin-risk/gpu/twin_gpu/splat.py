"""Gaussian splat training and rendering with gsplat (Apache 2.0)."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
from twin_gpu.common import load_scene, out_dir, read_rgb, save_json, scene_dir, write_rgb

C0 = 0.28209479177387814


def rgb_to_sh(rgb):
    return (rgb - 0.5) / C0


def _knn_scale(xyz):
    import torch

    n = len(xyz)
    out = torch.empty(n, device=xyz.device)
    for s in range(0, n, 4096):
        d = torch.cdist(xyz[s : s + 4096], xyz)
        out[s : s + 4096] = d.topk(4, largest=False).values[:, 1:].pow(2).mean(1).sqrt()
    return out.clamp_min(1e-4)


def init_params(points: np.ndarray, sh_degree: int = 3):
    import torch

    xyz = torch.from_numpy(points[:, :3]).float().cuda()
    rgb = torch.from_numpy(points[:, 3:6]).float().cuda()
    n = len(xyz)
    dist = _knn_scale(xyz)
    quats = torch.nn.functional.normalize(torch.randn(n, 4, device="cuda"), dim=-1)
    k = (sh_degree + 1) ** 2
    return torch.nn.ParameterDict(
        {
            "means": torch.nn.Parameter(xyz),
            "scales": torch.nn.Parameter(torch.log(dist)[:, None].repeat(1, 3)),
            "quats": torch.nn.Parameter(quats),
            "opacities": torch.nn.Parameter(torch.logit(torch.full((n,), 0.1, device="cuda"))),
            "sh0": torch.nn.Parameter(rgb_to_sh(rgb)[:, None, :]),
            "shN": torch.nn.Parameter(torch.zeros(n, k - 1, 3, device="cuda")),
        }
    )


def load_frames(scene: dict, name: str, split: str | None):
    import torch

    sd = scene_dir(name)
    idx = [i for i, f in enumerate(scene["frames"]) if split is None or f["split"] == split]
    imgs = torch.stack(
        [torch.from_numpy(read_rgb(sd / scene["frames"][i]["file"])) for i in idx]
    ).cuda()
    ks = torch.tensor([scene["frames"][i]["K"] for i in idx], dtype=torch.float32, device="cuda")
    c2w = torch.tensor([scene["frames"][i]["c2w"] for i in idx], dtype=torch.float32, device="cuda")
    return idx, imgs, ks, torch.linalg.inv(c2w)


def render(params, viewmats, ks, w, h, mask=None, sh_degree=3, mode="RGB", camera_model="pinhole"):
    import torch
    from gsplat import rasterization

    sel = slice(None) if mask is None else mask
    colors = torch.cat([params["sh0"], params["shN"]], 1)[sel]
    deg = min(sh_degree, int(math.sqrt(colors.shape[1])) - 1)
    rc, ra, info = rasterization(
        params["means"][sel],
        params["quats"][sel],
        torch.exp(params["scales"][sel]),
        torch.sigmoid(params["opacities"][sel]),
        colors,
        viewmats,
        ks,
        w,
        h,
        sh_degree=deg,
        packed=False,
        render_mode=mode,
        camera_model=camera_model,
    )
    return rc, ra, info


def scene_scale(c2w_inv) -> float:
    import torch

    centers = torch.linalg.inv(c2w_inv)[:, :3, 3]
    return float((centers - centers.mean(0)).norm(dim=1).max() * 1.1)


def se3(delta):
    """(N, 6) axis-angle rotation and translation -> (N, 4, 4) transforms."""
    import torch

    n = len(delta)
    w, t = delta[:, :3], delta[:, 3:]
    zero = torch.zeros(n, device=delta.device)
    k = torch.stack(
        [zero, -w[:, 2], w[:, 1], w[:, 2], zero, -w[:, 0], -w[:, 1], w[:, 0], zero], 1
    ).view(n, 3, 3)
    r = torch.linalg.matrix_exp(k)
    top = torch.cat([r, t[:, :, None]], 2)
    bottom = torch.tensor([0.0, 0, 0, 1], device=delta.device).expand(n, 1, 4)
    return torch.cat([top, bottom], 1)


def adjusted_viewmats(viewmats, delta):
    """Apply per-camera pose corrections: c2w' = c2w @ T(delta)."""
    import torch

    return torch.linalg.inv(torch.linalg.inv(viewmats) @ se3(delta))


def new_camera_params(n: int):
    import torch

    return {
        "delta": torch.nn.Parameter(torch.zeros(n, 6, device="cuda")),
        "color": torch.nn.Parameter(torch.zeros(n, 6, device="cuda")),
    }


def apply_color(pred, color_row):
    return pred * (1.0 + color_row[:3]) + color_row[3:]


def optimise(
    params,
    imgs,
    viewmats,
    ks,
    steps,
    scale,
    refine_stop,
    refine_start=500,
    reset_every=3000,
    log="",
    cams=None,
):
    """Train Gaussians. With `cams` (from new_camera_params), also refine each
    camera's pose and a per-image colour gain and bias (exposure)."""
    import torch
    from gsplat.strategy import DefaultStrategy
    from pytorch_msssim import ssim

    lrs = {
        "means": 1.6e-4 * scale,
        "scales": 5e-3,
        "quats": 1e-3,
        "opacities": 5e-2,
        "sh0": 2.5e-3,
        "shN": 2.5e-3 / 20,
    }
    opts = {
        k: torch.optim.Adam([{"params": params[k], "lr": lr, "name": k}], eps=1e-15)
        for k, lr in lrs.items()
    }
    sched = torch.optim.lr_scheduler.ExponentialLR(opts["means"], gamma=0.01 ** (1.0 / steps))
    cam_opt = cam_sched = None
    if cams is not None:
        cam_opt = torch.optim.Adam(
            [{"params": [cams["delta"]], "lr": 1e-3}, {"params": [cams["color"]], "lr": 1e-3}]
        )
        cam_sched = torch.optim.lr_scheduler.ExponentialLR(cam_opt, gamma=0.1 ** (1.0 / steps))
    strategy = DefaultStrategy(
        verbose=False,
        refine_start_iter=refine_start,
        refine_stop_iter=refine_stop,
        reset_every=reset_every,
        refine_every=100,
    )
    strategy.check_sanity(params, opts)
    state = strategy.initialize_state(scene_scale=scale)
    h, w = imgs.shape[1:3]
    gen = torch.Generator(device="cpu").manual_seed(0)
    t0 = time.time()
    for step in range(steps):
        i = int(torch.randint(len(imgs), (1,), generator=gen))
        gt = imgs[i].float() / 255.0
        sh_deg = min(step // 1000, 3)
        vm = viewmats[i : i + 1]
        use_cams = cams is not None and step >= 500
        if use_cams:
            vm = adjusted_viewmats(vm, cams["delta"][i : i + 1])
        rc, _, info = render(params, vm, ks[i : i + 1], w, h, sh_degree=sh_deg)
        strategy.step_pre_backward(params, opts, state, step, info)
        pred = rc[0]
        if use_cams:
            pred = apply_color(pred, cams["color"][i])
        pred = pred.clamp(0, 1)
        l1 = (pred - gt).abs().mean()
        s = ssim(
            pred.permute(2, 0, 1)[None],
            gt.permute(2, 0, 1)[None],
            data_range=1.0,
            size_average=True,
        )
        loss = 0.8 * l1 + 0.2 * (1.0 - s)
        loss.backward()
        for o in opts.values():
            o.step()
            o.zero_grad(set_to_none=True)
        sched.step()
        if cam_opt is not None:
            cam_opt.step()
            cam_opt.zero_grad(set_to_none=True)
            cam_sched.step()
        strategy.step_post_backward(params, opts, state, step, info, packed=False)
        if step % 2000 == 0:
            print(
                f"{log} step {step} loss {loss.item():.4f} "
                f"n={len(params['means'])} {time.time() - t0:.0f}s",
                flush=True,
            )
    return params


def refine_test_cameras(params, imgs, viewmats, ks, steps: int = 300):
    """Fit pose and exposure of held-out views with the splat frozen (standard
    when training refines poses), so the score measures the splat, not pose noise."""
    import torch

    cams = new_camera_params(len(imgs))
    frozen = {k: v.detach() for k, v in params.items()}
    h, w = imgs.shape[1:3]
    opt = torch.optim.Adam(
        [{"params": [cams["delta"]], "lr": 1e-3}, {"params": [cams["color"]], "lr": 1e-3}]
    )
    for i in range(len(imgs)):
        gt = imgs[i].float() / 255.0
        for _ in range(steps):
            vm = adjusted_viewmats(viewmats[i : i + 1], cams["delta"][i : i + 1])
            rc, _, _ = render(frozen, vm, ks[i : i + 1], w, h)
            loss = (apply_color(rc[0], cams["color"][i]).clamp(0, 1) - gt).abs().mean()
            loss.backward()
            opt.step()
            opt.zero_grad(set_to_none=True)
    return cams


def evaluate(params, imgs, viewmats, ks, cams=None):
    import torch
    from pytorch_msssim import ssim

    h, w = imgs.shape[1:3]
    psnrs, ssims = [], []
    with torch.no_grad():
        for i in range(len(imgs)):
            vm = viewmats[i : i + 1]
            if cams is not None:
                vm = adjusted_viewmats(vm, cams["delta"][i : i + 1])
            rc, _, _ = render(params, vm, ks[i : i + 1], w, h)
            pred = rc[0] if cams is None else apply_color(rc[0], cams["color"][i])
            pred = pred.clamp(0, 1)
            gt = imgs[i].float() / 255.0
            mse = ((pred - gt) ** 2).mean()
            psnrs.append(float(-10 * torch.log10(mse)))
            ssims.append(
                float(ssim(pred.permute(2, 0, 1)[None], gt.permute(2, 0, 1)[None], data_range=1.0))
            )
    return {"psnr": float(np.mean(psnrs)), "ssim": float(np.mean(ssims)), "views": len(imgs)}


def save_params(params, path: Path) -> None:
    import torch

    torch.save({k: v.detach().cpu() for k, v in params.items()}, path)


def load_params(path: Path):
    import torch

    d = torch.load(path, map_location="cuda")
    return torch.nn.ParameterDict({k: torch.nn.Parameter(v.cuda()) for k, v in d.items()})


def train_scene(name: str, steps: int = 15000) -> dict:
    """Train on raw poses; for phone captures (ARKitScenes) also refine poses and
    exposure, then save the refined cameras for the edit and phone stages."""
    import torch

    scene = load_scene(name, refined=False)
    refine = scene["source"] == "arkitscenes"
    torch.manual_seed(0)
    pts = np.load(scene_dir(name) / "points.npy")
    idx, imgs, ks, vms = load_frames(scene, name, "train")
    tidx, timgs, tks, tvms = load_frames(scene, name, "test")
    scale = scene_scale(vms)
    params = init_params(pts)
    cams = new_camera_params(len(idx)) if refine else None
    t0 = time.time()
    params = optimise(
        params, imgs, vms, ks, steps, scale, refine_stop=int(steps * 0.66), log=name, cams=cams
    )
    torch.cuda.synchronize()
    train_s = time.time() - t0
    raw = evaluate(params, timgs, tvms, tks)
    ev = dict(raw)
    tcams = None
    if refine:
        t1 = time.time()
        tcams = refine_test_cameras(params, timgs, tvms, tks)
        ev = evaluate(params, timgs, tvms, tks, tcams)
        ev["test_pose_refine_seconds"] = round(time.time() - t1, 1)
        # Save refined camera-to-world matrices for every frame.
        with torch.no_grad():
            new_train = torch.linalg.inv(adjusted_viewmats(vms, cams["delta"])).cpu().numpy()
            new_test = torch.linalg.inv(adjusted_viewmats(tvms, tcams["delta"])).cpu().numpy()
        refined = json.loads(json.dumps(scene))
        for j, fi in enumerate(idx):
            refined["frames"][fi]["c2w"] = new_train[j].tolist()
        for j, fi in enumerate(tidx):
            refined["frames"][fi]["c2w"] = new_test[j].tolist()
        delta = cams["delta"].detach()
        ev["pose_correction_median_cm"] = float(delta[:, 3:].norm(dim=1).median() * 100)
        ev["pose_correction_median_deg"] = float(delta[:, :3].norm(dim=1).median() * 180 / math.pi)
        save_json(out_dir(name) / "cameras_refined.json", refined)
    od = out_dir(name)
    save_params(params, od / "splat.pt")
    h, w = timgs.shape[1:3]
    with torch.no_grad():
        for j in range(min(3, len(timgs))):
            vm = (
                tvms[j : j + 1]
                if tcams is None
                else adjusted_viewmats(tvms[j : j + 1], tcams["delta"][j : j + 1])
            )
            rc, _, _ = render(params, vm, tks[j : j + 1], w, h)
            pred = rc[0] if tcams is None else apply_color(rc[0], tcams["color"][j])
            pred = (pred.clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
            gt = timgs[j].cpu().numpy()
            write_rgb(od / "splat" / f"test_{j}.jpg", np.concatenate([gt, pred], axis=1))
    result = {
        "scene": name,
        "train_views": len(idx),
        "test_views": len(tidx),
        "init_points": len(pts),
        "gaussians": len(params["means"]),
        "steps": steps,
        "train_seconds": round(train_s, 1),
        "scene_scale": scale,
        "pose_and_exposure_refined": refine,
        "psnr_raw_poses": raw["psnr"],
        "ssim_raw_poses": raw["ssim"],
        **ev,
    }
    save_json(od / "splat.json", result)
    return result


def export_ply(params, path: Path, keep=None, sh_degree: int = 3) -> int:
    """Standard 3DGS PLY (positions, normals, f_dc, f_rest, opacity, scales, rotation)."""
    means = params["means"].detach().cpu().numpy()
    sel = np.arange(len(means)) if keep is None else keep
    sh0 = params["sh0"].detach().cpu().numpy()[sel, 0, :]
    rest = params["shN"].detach().cpu().numpy()[sel]
    k = (sh_degree + 1) ** 2 - 1
    rest = rest[:, :k, :].transpose(0, 2, 1).reshape(len(sel), -1)
    cols = [
        means[sel],
        np.zeros((len(sel), 3), np.float32),
        sh0,
        rest,
        params["opacities"].detach().cpu().numpy()[sel, None],
        params["scales"].detach().cpu().numpy()[sel],
        params["quats"].detach().cpu().numpy()[sel],
    ]
    names = ["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2"]
    names += [f"f_rest_{i}" for i in range(rest.shape[1])]
    names += ["opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
    data = np.concatenate(cols, axis=1).astype(np.float32)
    header = f"ply\nformat binary_little_endian 1.0\nelement vertex {len(sel)}\n"
    header += "".join(f"property float {n}\n" for n in names) + "end_header\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(header.encode())
        fh.write(data.tobytes())
    return len(sel)
