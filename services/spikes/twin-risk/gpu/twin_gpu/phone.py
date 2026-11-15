"""Budget phones: on-device compressed splats versus server-rendered views.

On-device: export the splat, prune to Gaussian budgets, compress with
PlayCanvas splat-transform (SOG, compressed PLY, SPZ), and measure size, the
quality lost (PSNR on held-out views after decoding) and GPU render time.
Server-rendered: render a phone-sized orbit, encode H.264 and JPEG, and measure
render time, bitrate and GPU cost per viewing minute. The light mesh for
dragging is the shell plus object boxes as a GLB.
"""

from __future__ import annotations

import math
import subprocess
import time
from pathlib import Path

import numpy as np
from twin_gpu.common import load_json, load_scene, out_dir, save_json
from twin_gpu.splat import export_ply, load_frames, load_params, render

BUDGETS = [None, 1_000_000, 500_000, 250_000]
PHONE_W, PHONE_H = 720, 1280


def subset(params, keep, sh_degree=3):
    import torch

    if keep is None:
        sel = torch.arange(len(params["means"]), device="cuda")
    else:
        sel = torch.from_numpy(keep).cuda()
    out = {k: v.detach()[sel] for k, v in params.items()}
    if sh_degree == 0:
        out["shN"] = out["shN"][:, :0, :]
    return out


def psnr_on_test(p, timgs, tks, tvms, sh_degree=3) -> float:
    import torch

    h, w = timgs.shape[1:3]
    vals = []
    with torch.no_grad():
        for i in range(len(timgs)):
            rc, _, _ = render(p, tvms[i : i + 1], tks[i : i + 1], w, h, sh_degree=sh_degree)
            mse = ((rc[0].clamp(0, 1) - timgs[i].float() / 255.0) ** 2).mean()
            vals.append(float(-10 * torch.log10(mse)))
    return float(np.mean(vals))


def orbit(scene: dict, n: int = 120):
    """Phone-sized views on a slow orbit through the capture positions."""
    import torch

    c2ws = np.array([f["c2w"] for f in scene["frames"]])
    centers = c2ws[:, :3, 3]
    up = np.asarray(scene["up"], float)
    mid = centers.mean(0)
    radius = float(np.median(np.linalg.norm(centers - mid, axis=1))) * 0.6
    fwd0 = c2ws[:, :3, 2].mean(0)
    vms = []
    for t in np.linspace(0, 2 * math.pi, n, endpoint=False):
        a = np.cross(up, fwd0)
        a /= np.linalg.norm(a)
        b = np.cross(up, a)
        pos = mid + radius * (math.cos(t) * a + math.sin(t) * b)
        fwd = (math.cos(t + math.pi / 2) * a + math.sin(t + math.pi / 2) * b) * 0.7 + (
            mid - pos
        ) * 0.3
        fwd -= up * float(fwd @ up) * 0.8
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, up)
        right /= np.linalg.norm(right)
        down = np.cross(fwd, right)
        c2w = np.eye(4)
        c2w[:3, 0], c2w[:3, 1], c2w[:3, 2], c2w[:3, 3] = right, down, fwd, pos
        vms.append(np.linalg.inv(c2w))
    f = PHONE_H * 0.75
    k = np.array([[f, 0, PHONE_W / 2], [0, f, PHONE_H / 2], [0, 0, 1.0]])
    return (
        torch.tensor(np.array(vms), dtype=torch.float32, device="cuda"),
        torch.tensor(np.repeat(k[None], n, 0), dtype=torch.float32, device="cuda"),
    )


def time_render(p, vms, ks, sh_degree=3, repeats=1) -> float:
    import torch

    with torch.no_grad():
        for i in range(5):
            render(p, vms[i : i + 1], ks[i : i + 1], PHONE_W, PHONE_H, sh_degree=sh_degree)
        torch.cuda.synchronize()
        t0 = time.time()
        for _ in range(repeats):
            for i in range(len(vms)):
                render(p, vms[i : i + 1], ks[i : i + 1], PHONE_W, PHONE_H, sh_degree=sh_degree)
        torch.cuda.synchronize()
    return (time.time() - t0) / (len(vms) * repeats) * 1000.0


def export_variants(name: str) -> dict:
    """GPU job: write the full splat as PLY; decimated variants come from the CPU job."""
    scene = load_scene(name)
    od = out_dir(name)
    params = load_params(od / "splat.pt")
    _, timgs, tks, tvms = load_frames(scene, name, "test")
    vdir = od / "phone"
    vdir.mkdir(parents=True, exist_ok=True)
    count = export_ply(params, vdir / "full.ply")
    rows = [
        {
            "variant": "full",
            "gaussians": count,
            "ply_bytes": (vdir / "full.ply").stat().st_size,
            "psnr_sh3": psnr_on_test(params, timgs, tks, tvms, 3),
            "psnr_sh0": psnr_on_test(subset(params, None, 0), timgs, tks, tvms, 0),
        }
    ]
    save_json(od / "phone_variants.json", rows)
    return {"scene": name, "variants": rows}


def _ply_count(path: Path) -> int:
    with open(path, "rb") as fh:
        for line in fh:
            if line.startswith(b"element vertex"):
                return int(line.split()[-1])
            if line.startswith(b"end_header"):
                break
    return 0


def _splat_transform(args: list[str]) -> tuple[bool, str]:
    res = subprocess.run(
        ["splat-transform", "-w", "-g", "cpu", *args], capture_output=True, text=True
    )
    return res.returncode == 0, (res.stderr or res.stdout)[-600:]


def compress_variants(name: str) -> dict:
    """CPU job: decimate to Gaussian budgets (adaptive, mass-preserving), then
    compress each variant to SOG (SH3 and SH0), compressed PLY and SPZ."""
    od = out_dir(name)
    vdir = od / "phone"
    rows = load_json(od / "phone_variants.json", [])
    full = next(r for r in rows if r["variant"] == "full")
    rows = [full]
    for budget in BUDGETS:
        if budget is None or budget >= full["gaussians"]:
            continue
        tag = f"{budget // 1000}k"
        dst = vdir / f"{tag}.ply"
        t0 = time.time()
        ok, err = _splat_transform(
            [str(vdir / "full.ply"), "--decimate-adaptive", str(budget), str(dst)]
        )
        row = {"variant": tag, "decimate_seconds": round(time.time() - t0, 1)}
        if not ok:
            row["decimate_error"] = err
            rows.append(row)
            continue
        row.update(gaussians=_ply_count(dst), ply_bytes=dst.stat().st_size)
        rows.append(row)
    for r in rows:
        src = vdir / f"{r['variant']}.ply"
        if not src.exists():
            continue
        # Fast formats first; SOG with full spherical harmonics clusters colours on
        # the CPU (no WebGPU here), so it runs last with fewer iterations.
        outs = {
            "spz": (vdir / f"{r['variant']}.spz", []),
            "compressed_ply": (vdir / f"{r['variant']}.compressed.ply", []),
            "sog_sh0": (vdir / f"{r['variant']}_sh0.sog", ["-H", "0"]),
            "sog_sh3": (vdir / f"{r['variant']}.sog", ["-i", "3", "--max-workers", "16"]),
        }
        for key, (dst, actions) in outs.items():
            t0 = time.time()
            ok, err = _splat_transform([str(src), *actions, str(dst)])
            save_json(od / "phone_variants.json", rows)  # keep partial results
            if not ok:
                r[f"{key}_error"] = err
                continue
            r[f"{key}_bytes"] = dst.stat().st_size
            r[f"{key}_seconds"] = round(time.time() - t0, 1)
        # Decode the SOG back to PLY so the GPU job can measure what compression costs.
        _splat_transform([str(outs["sog_sh3"][0]), str(vdir / f"{r['variant']}_sog_decoded.ply")])
    save_json(od / "phone_variants.json", rows)
    return {"scene": name, "variants": rows}


def read_ply_params(path: Path):
    """Read a 3DGS PLY (float properties) back into render-ready tensors."""
    import torch

    with open(path, "rb") as fh:
        header = b""
        while not header.endswith(b"end_header\n"):
            header += fh.readline()
        lines = header.decode().splitlines()
        n = int(next(x for x in lines if x.startswith("element vertex")).split()[-1])
        props = [x.split() for x in lines if x.startswith("property")]
        types = {"float": "<f4", "uchar": "u1", "int": "<i4", "uint": "<u4", "double": "<f8"}
        dt = np.dtype([(p[2], types[p[1]]) for p in props])
        data = np.frombuffer(fh.read(n * dt.itemsize), dtype=dt, count=n)

    def col(name: str) -> np.ndarray:
        return np.asarray(data[name], dtype=np.float32)

    rest = sorted(
        [p[2] for p in props if p[2].startswith("f_rest_")], key=lambda s: int(s.split("_")[-1])
    )
    means = np.stack([col("x"), col("y"), col("z")], 1)
    sh0 = np.stack([col("f_dc_0"), col("f_dc_1"), col("f_dc_2")], 1)[:, None, :]
    shn = (
        np.stack([col(r) for r in rest], 1).reshape(n, 3, -1).transpose(0, 2, 1)
        if rest
        else np.zeros((n, 0, 3))
    )
    if "opacity" in data.dtype.names:
        op = col("opacity")
    else:
        lin = np.clip(col("opacity_linear"), 1e-6, 1 - 1e-6)
        op = np.log(lin / (1 - lin))
    t = lambda a: torch.from_numpy(np.ascontiguousarray(a, dtype=np.float32)).cuda()  # noqa: E731
    return {
        "means": t(means),
        "sh0": t(sh0),
        "shN": t(shn),
        "opacities": t(op),
        "scales": t(np.stack([col("scale_0"), col("scale_1"), col("scale_2")], 1)),
        "quats": t(np.stack([col("rot_0"), col("rot_1"), col("rot_2"), col("rot_3")], 1)),
    }


def measure(name: str, gpu: str) -> dict:
    """GPU job: render speed per variant at phone resolution, SOG quality loss,
    and the server-rendered stream (on whichever GPU this runs)."""
    import cv2

    scene = load_scene(name)
    od = out_dir(name)
    vdir = od / "phone"
    rows = load_json(od / "phone_variants.json", [])
    _, timgs, tks, tvms = load_frames(scene, name, "test")
    vms, ks = orbit(scene)
    for r in rows:
        if not (vdir / f"{r['variant']}.ply").exists():
            continue
        p = read_ply_params(vdir / f"{r['variant']}.ply")
        if "psnr_sh3" not in r:
            r["psnr_sh3"] = psnr_on_test(p, timgs, tks, tvms, 3)
            r["psnr_sh0"] = psnr_on_test(p, timgs, tks, tvms, 0)
        r[f"render_ms_{gpu}_sh3"] = time_render(p, vms, ks, 3)
        r[f"render_ms_{gpu}_sh0"] = time_render(p, vms, ks, 0)
        dec = vdir / f"{r['variant']}_sog_decoded.ply"
        if dec.exists() and "psnr_sog_decoded" not in r:
            r["psnr_sog_decoded"] = psnr_on_test(read_ply_params(dec), timgs, tks, tvms, 3)
    save_json(od / "phone_variants.json", rows)

    # Server-rendered stream from the full splat.
    p = read_ply_params(vdir / "full.ply")
    ms = time_render(p, vms, ks, 3)
    frames_dir = od / "stream" / gpu
    frames_dir.mkdir(parents=True, exist_ok=True)
    jpg_sizes = []
    import torch

    with torch.no_grad():
        for i in range(len(vms)):
            rc, _, _ = render(p, vms[i : i + 1], ks[i : i + 1], PHONE_W, PHONE_H)
            img = (rc[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
            bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            _, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
            jpg_sizes.append(len(buf))
            cv2.imwrite(str(frames_dir / f"{i:04d}.png"), bgr)
    mp4 = od / "stream" / f"orbit_{gpu}.mp4"
    t0 = time.time()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            "30",
            "-i",
            str(frames_dir / "%04d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            str(mp4),
        ],
        check=True,
    )
    enc_s = time.time() - t0
    from twin_risk.costs import bitrate_mbps, gpu_cost_usd, stream_gpu_cost_per_minute

    seconds = len(vms) / 30.0
    stream = {
        "gpu": gpu,
        "resolution": [PHONE_W, PHONE_H],
        "gaussians": len(p["means"]),
        "render_ms_per_frame": ms,
        "max_fps_single_stream": 1000.0 / ms,
        "jpeg_q80_mean_kb": float(np.mean(jpg_sizes) / 1024),
        "h264_crf23_mbps": bitrate_mbps(mp4.stat().st_size, seconds),
        "h264_bytes_for_4s": mp4.stat().st_size,
        "encode_seconds_cpu": round(enc_s, 2),
        "gpu_cost_per_view_minute_usd_30fps": stream_gpu_cost_per_minute(gpu, ms, 30.0),
        "gpu_cost_per_still_view_usd": gpu_cost_usd(gpu, ms / 1000.0),
    }
    streams = load_json(od / "stream.json", {}) or {}
    streams[gpu] = stream
    save_json(od / "stream.json", streams)
    return {"scene": name, "gpu": gpu, "stream": stream}


def light_mesh(name: str) -> dict:
    """GLB of the shell (floor rectangle) and object boxes, for dragging on the phone."""
    import gzip

    import trimesh

    scene = load_scene(name)
    od = out_dir(name)
    objs = next(
        (x for d in ("gdino", "yoloe") if (x := load_json(od / f"objects_{d}_lidar.json"))),
        {},
    )
    boxes = objs.get("boxes", [])
    up = np.asarray(scene["up"], float)
    upi = int(np.argmax(np.abs(up)))
    meshes = []
    for b in boxes:
        ext = [0.0, 0.0, 0.0]
        a_, b_ = (i for i in range(3) if i != upi)
        ext[a_], ext[b_], ext[upi] = b["length"], b["width"], b["height"]
        m = trimesh.creation.box(extents=ext)
        rot = np.eye(4)
        c, s = math.cos(b["yaw"]), math.sin(b["yaw"])
        rot[a_, a_], rot[a_, b_], rot[b_, a_], rot[b_, b_] = c, -s, s, c
        m.apply_transform(rot)
        m.apply_translation(b["center"])
        meshes.append(m)
    cams = np.array([f["c2w"] for f in scene["frames"]])[:, :3, 3]
    lo, hi = cams.min(0) - 2, cams.max(0) + 2
    floor_ext = (hi - lo).tolist()
    floor_ext[upi] = 0.01
    fl = trimesh.creation.box(extents=floor_ext)
    fl.apply_translation((lo + hi) / 2)
    meshes.append(fl)
    glb = trimesh.util.concatenate(meshes).export(file_type="glb")
    (od / "phone").mkdir(exist_ok=True)
    (od / "phone" / "light_mesh.glb").write_bytes(glb)
    res = {"objects": len(boxes), "glb_bytes": len(glb), "glb_gzip_bytes": len(gzip.compress(glb))}
    save_json(od / "light_mesh.json", res)
    return res
