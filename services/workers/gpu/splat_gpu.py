"""Splat training for the twin worker, on the GPU (gsplat 1.5.3, Apache 2.0).

Training, rendering and evaluation are ported from the SJ-116 spike, where they
reached 26 dB on phone captures with pose and exposure refinement. `train` reads
the capture's keyframes from the artifact store and writes the splat, refined
cameras and per-Gaussian object labels back to it.
"""

from __future__ import annotations

import io
import json
import math
import os
import shutil
import time
from pathlib import Path

import numpy as np

C0 = 0.28209479177387814
# gsplat compiles its CUDA kernels on first use. They are cached on the volume and
# copied to local disk, since an open file on the volume blocks volume commits.
KERNELS_ON_VOLUME = Path("/vol/torch_extensions")
KERNELS_LOCAL = Path(os.environ.get("TORCH_EXTENSIONS_DIR", "/root/torch_extensions"))


def load_cached_kernels() -> None:
    if KERNELS_ON_VOLUME.is_dir() and not KERNELS_LOCAL.exists():
        shutil.copytree(KERNELS_ON_VOLUME, KERNELS_LOCAL)


def save_compiled_kernels() -> None:
    if KERNELS_LOCAL.is_dir() and not KERNELS_ON_VOLUME.exists():
        shutil.copytree(KERNELS_LOCAL, KERNELS_ON_VOLUME)


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
    checkpoint=None,
    resume=None,
    interrupt_at=None,
):
    """Train Gaussians. With `cams` (from new_camera_params), also refine each
    camera's pose and a per-image colour gain and bias (exposure).

    `checkpoint(step, state)` is called every CHECKPOINT_EVERY steps with
    everything needed to continue; `resume` is such a state, and training picks
    up from its step. `interrupt_at` stops with Interrupted at that step (for
    the resume test only).
    """
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
    first = 0
    if resume is not None:
        first = _restore(resume, params, opts, sched, cams, cam_opt, cam_sched, state, gen)
        print(f"{log} resumed at step {first}", flush=True)
    t0 = time.time()
    for step in range(first, steps):
        if interrupt_at is not None and step == interrupt_at:
            raise Interrupted(step)
        if checkpoint is not None and step > first and step % CHECKPOINT_EVERY == 0:
            checkpoint(
                step, _snapshot(step, params, opts, sched, cams, cam_opt, cam_sched, state, gen)
            )
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


# A checkpoint of a room is about 2 GB (Gaussians plus Adam state), so it is written
# every 5,000 steps: a preemption loses at most a third of a 15,000-step run.
CHECKPOINT_EVERY = 5000


class Interrupted(Exception):
    """Training stopped on purpose at a step (the resume test)."""


def _snapshot(step, params, opts, sched, cams, cam_opt, cam_sched, state, gen) -> dict:
    """Everything training needs to continue from `step`, on the CPU."""

    def cpu(value):
        return value.detach().cpu() if hasattr(value, "detach") else value

    return {
        "step": step,
        "params": {k: cpu(v) for k, v in params.items()},
        "opts": {k: o.state_dict() for k, o in opts.items()},
        "sched": sched.state_dict(),
        "cams": {k: cpu(v) for k, v in cams.items()} if cams is not None else None,
        "cam_opt": cam_opt.state_dict() if cam_opt is not None else None,
        "cam_sched": cam_sched.state_dict() if cam_sched is not None else None,
        "strategy": {k: cpu(v) for k, v in state.items()},
        "generator": gen.get_state(),
    }


def _restore(saved, params, opts, sched, cams, cam_opt, cam_sched, state, gen) -> int:
    """Load a snapshot into freshly built training objects; returns the next step."""
    import torch

    for key, value in saved["params"].items():
        # Densification changes the number of Gaussians: swap in tensors of the saved size.
        params[key] = torch.nn.Parameter(value.cuda())
        opts[key].param_groups[0]["params"] = [params[key]]
        opts[key].load_state_dict(saved["opts"][key])
    sched.load_state_dict(saved["sched"])
    if cams is not None and saved["cams"] is not None:
        with torch.no_grad():
            for key, value in saved["cams"].items():
                cams[key].copy_(value.cuda())
        cam_opt.load_state_dict(saved["cam_opt"])
        cam_sched.load_state_dict(saved["cam_sched"])
    for key, value in saved["strategy"].items():
        state[key] = value.cuda() if hasattr(value, "cuda") else value
    gen.set_state(saved["generator"])
    return int(saved["step"])


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


class InputError(Exception):
    """The request can never succeed (bad manifest, mixed frame sizes)."""


def _decode_rgb(data: bytes) -> np.ndarray:
    import cv2

    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise InputError("a keyframe is not an image")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _decode_mask(data: bytes) -> np.ndarray:
    import cv2

    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE) > 127


def _vote_labels(params, objects, frames, ks, vms, w, h) -> np.ndarray:
    """Per-Gaussian object label from mask votes where its centre is visible.

    Visibility uses the splat's own rendered depth at the refined poses, so it
    works with or without LiDAR.
    """
    import torch

    from sajao_workers.twin.split import assign_labels

    n = len(params["means"])
    votes = torch.zeros((n, len(objects) + 1), dtype=torch.int32, device="cuda")
    visible = torch.zeros(n, dtype=torch.int32, device="cuda")
    by_frame: dict[int, list[tuple[int, np.ndarray]]] = {}
    index = {f["keyframe_id"]: i for i, f in enumerate(frames)}
    for oid, obj in enumerate(objects, start=1):
        for view in obj["views"]:
            if view["keyframe_id"] in index:
                by_frame.setdefault(index[view["keyframe_id"]], []).append((oid, view["mask"]))
    means = params["means"].detach()
    homo = torch.cat([means, torch.ones(n, 1, device="cuda")], 1)
    for j, views in by_frame.items():
        with torch.no_grad():
            rc, ra, _ = render(params, vms[j : j + 1], ks[j : j + 1], w, h, mode="RGB+ED")
        depth = torch.where(ra[0, ..., 0] > 0.5, rc[0, ..., 3], torch.zeros_like(rc[0, ..., 3]))
        idmap = np.zeros((h, w), np.int32)
        masks = [(oid, m) for oid, m in views]
        masks.sort(key=lambda om: -int(om[1].sum()))  # small masks drawn last win overlaps
        for oid, mask in masks:
            idmap[mask] = oid
        cam = homo @ vms[j].T
        z = cam[:, 2]
        u = (ks[j, 0, 0] * cam[:, 0] / z + ks[j, 0, 2]).long()
        v = (ks[j, 1, 1] * cam[:, 1] / z + ks[j, 1, 2]).long()
        ok = (z > 0.05) & (u >= 0) & (u < w) & (v >= 0) & (v < h)
        uu, vv = u.clamp(0, w - 1), v.clamp(0, h - 1)
        rendered = depth[vv, uu]
        vis = ok & (rendered > 0) & ((z - rendered).abs() < 0.05 * z + 0.03)
        visible += vis.int()
        obj = torch.from_numpy(idmap).cuda()[vv, uu].long()
        hit = vis & (obj > 0)
        votes[hit.nonzero().flatten(), obj[hit]] += 1
    return assign_labels(votes.cpu().numpy(), visible.cpu().numpy())


def train(
    payload: dict,
    store,
    steps: int = 15000,
    checkpoints: Path | None = None,
    persist=None,
    interrupt_at: int | None = None,
) -> dict:
    """Train a splat from a frames manifest and split it by the objects' masks.

    With `checkpoints` (a directory on the volume), training state is saved every
    CHECKPOINT_EVERY steps under a key of the inputs, and `persist()` (the volume
    commit) makes it durable. A run that is preempted and started again with the
    same inputs resumes from the last checkpoint instead of from the start.
    """
    import hashlib

    import cv2
    import torch

    from sajao_workers.twin.objects import decode_depth_mm
    from sajao_workers.twin.splat_inputs import held_out, initial_points

    for key in ("frames", "objects"):
        if not store.has_blob(payload[key]):
            raise InputError(f"{key} is not in the store")
    manifest = json.loads(store.read_blob(payload["frames"]))
    frames = manifest["frames"]
    objects = json.loads(store.read_blob(payload["objects"]))
    rgbs = [_decode_rgb(store.read_blob(f["image"])) for f in frames]
    h, w = rgbs[0].shape[:2]
    if any(r.shape[:2] != (h, w) for r in rgbs):
        raise InputError("keyframes differ in size")
    depths = [decode_depth_mm(store.read_blob(f["depth"])) for f in frames]
    depths = [
        d if d.shape == (h, w) else cv2.resize(d, (w, h), interpolation=cv2.INTER_NEAREST)
        for d in depths
    ]

    torch.manual_seed(0)
    test = set(held_out(len(frames)))
    train_idx = [i for i in range(len(frames)) if i not in test]
    test_idx = sorted(test)
    ks_all = torch.tensor([f["intrinsics"] for f in frames], dtype=torch.float32, device="cuda")
    c2w_all = torch.tensor([f["c2w"] for f in frames], dtype=torch.float32, device="cuda")
    vms_all = torch.linalg.inv(c2w_all)
    imgs = torch.from_numpy(np.stack(rgbs)).cuda()
    points = initial_points(
        [(rgbs[i], depths[i], frames[i]["intrinsics"], frames[i]["c2w"]) for i in train_idx]
    )
    params = init_params(points)
    scale = scene_scale(vms_all[train_idx])
    cams = new_camera_params(len(train_idx))
    saved = resume = None
    if checkpoints is not None:
        key = hashlib.sha256(
            json.dumps([payload["frames"], payload["objects"], steps]).encode()
        ).hexdigest()
        saved = checkpoints / f"splat-{key}.pt"
        if saved.exists():
            resume = torch.load(saved, map_location="cpu", weights_only=False)

    def checkpoint(step: int, state: dict) -> None:
        local = Path("/tmp/splat_checkpoint.pt")  # noqa: S108
        torch.save(state, local)
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, saved.with_suffix(".part"))
        saved.with_suffix(".part").rename(saved)  # never a half-written checkpoint
        local.unlink()
        if persist is not None:
            persist()
        print(f"twin splat checkpoint at step {step}", flush=True)

    started = time.time()
    params = optimise(
        params,
        imgs[train_idx],
        vms_all[train_idx],
        ks_all[train_idx],
        steps,
        scale,
        refine_stop=int(steps * 0.66),
        log="twin splat",
        cams=cams,
        checkpoint=checkpoint if saved is not None else None,
        resume=resume,
        interrupt_at=interrupt_at,
    )
    torch.cuda.synchronize()
    train_seconds = time.time() - started

    result = {
        "gaussians": len(params["means"]),
        "train_seconds": round(train_seconds, 1),
        "gpu": torch.cuda.get_device_name(),
    }
    with torch.no_grad():
        refined = vms_all.clone()
        refined[train_idx] = adjusted_viewmats(vms_all[train_idx], cams["delta"])
    if test_idx:
        timgs, tvms, tks = imgs[test_idx], vms_all[test_idx], ks_all[test_idx]
        result["psnr_heldout_raw"] = round(evaluate(params, timgs, tvms, tks)["psnr"], 2)
        tcams = refine_test_cameras(params, timgs, tvms, tks)
        result["psnr_heldout"] = round(evaluate(params, timgs, tvms, tks, tcams)["psnr"], 2)
        with torch.no_grad():
            refined[test_idx] = adjusted_viewmats(tvms, tcams["delta"])

    if objects:
        for obj in objects:
            for view in obj["views"]:
                view["mask"] = _decode_mask(store.read_blob(view["mask"]))
        labels = _vote_labels(params, objects, frames, ks_all, refined, w, h)
    else:
        labels = np.zeros(len(params["means"]), np.int32)
    result["gaussians_on_objects"] = int((labels > 0).sum())
    result["objects_with_gaussians"] = len(set(labels.tolist()) - {0})

    cameras = [
        {"keyframe_id": f["keyframe_id"], "c2w": c2w.tolist()}
        for f, c2w in zip(frames, torch.linalg.inv(refined).cpu().numpy(), strict=True)
    ]
    ply = Path("/tmp/twin_splat.ply")  # noqa: S108
    export_ply(params, ply)
    labels_buf = io.BytesIO()
    np.save(labels_buf, labels)
    result["splat"] = store.put_blob(ply.read_bytes())
    result["labels"] = store.put_blob(labels_buf.getvalue())
    result["cameras"] = store.put_blob(json.dumps(cameras).encode())
    ply.unlink()
    if saved is not None and saved.exists():
        saved.unlink()  # the splat is stored; its checkpoint is no longer needed
        if persist is not None:
            persist()
    if resume is not None:
        result["resumed_at_step"] = int(resume["step"])
    return result
