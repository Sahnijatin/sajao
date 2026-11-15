"""Download public datasets on Modal and convert each scene to the common format."""

from __future__ import annotations

import glob
import itertools
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
from twin_gpu.common import VOL, read_rgb, save_json, scene_dir, write_rgb

from twin_risk.geometry import parse_arkit_traj_line

ARKIT_URL = "https://docs-assets.developer.apple.com/ml-research/datasets/arkitscenes/v1/raw"
MIP_URL = "http://storage.googleapis.com/gresearch/refraw360/360_v2.zip"
REPLICA_URL = "https://github.com/facebookresearch/Replica-Dataset/releases/download/v1.0/replica_v1_0.tar.gz.part"


def _curl(url: str, dst: Path) -> None:
    if dst.exists() and dst.stat().st_size > 0:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    subprocess.run(["curl", "-sSfL", "--retry", "5", "-o", str(tmp), url], check=True)
    tmp.rename(dst)


def _ts(path: str) -> float:
    return float(Path(path).stem.split("_")[-1])


def _sharpness(rgb: np.ndarray) -> float:
    import cv2

    g = cv2.cvtColor(cv2.resize(rgb, (320, 240)), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def _pick_sharp(paths: list[str], n: int) -> list[str]:
    """Split the sequence into n windows and keep the sharpest frame of each."""
    if len(paths) <= n:
        return paths
    edges = np.linspace(0, len(paths), n + 1).astype(int)
    chosen = []
    for a, b in itertools.pairwise(edges):
        window = paths[a:b:2] or paths[a:b]
        chosen.append(max(window, key=lambda p: _sharpness(read_rgb(Path(p)))))
    return chosen


def _nearest(sorted_ts: np.ndarray, t: float) -> tuple[int, float]:
    i = int(np.searchsorted(sorted_ts, t))
    cands = [j for j in (i - 1, i) if 0 <= j < len(sorted_ts)]
    j = min(cands, key=lambda k: abs(sorted_ts[k] - t))
    return j, abs(float(sorted_ts[j]) - t)


def _up_from_cameras(c2ws: list[np.ndarray]) -> np.ndarray:
    # OpenCV cameras: +y is down in the image; phones are held roughly upright.
    down = np.mean([c[:3, 1] for c in c2ws], axis=0)
    return -down / np.linalg.norm(down)


def _init_points_from_depth(frames, sd: Path, every: int, stride: int):
    from twin_gpu.common import read_depth_m, unproject

    pts, cols = [], []
    for f in frames[::every]:
        if not f.get("depth"):
            continue
        d = read_depth_m(sd / f["depth"])
        rgb = read_rgb(sd / f["file"])
        ys, xs = np.mgrid[0 : d.shape[0] : stride, 0 : d.shape[1] : stride]
        ys, xs = ys.ravel(), xs.ravel()
        ok = d[ys, xs] > 0.1
        ys, xs = ys[ok], xs[ok]
        pts.append(unproject(d, np.asarray(f["K"]), np.asarray(f["c2w"]), ys, xs))
        cols.append(rgb[ys, xs] / 255.0)
    p = np.concatenate(pts)
    c = np.concatenate(cols)
    keys = np.floor(p / 0.02).astype(np.int64)
    _, idx = np.unique(keys, axis=0, return_index=True)
    p, c = p[idx], c[idx]
    if len(p) > 300_000:
        sel = np.random.default_rng(0).choice(len(p), 300_000, replace=False)
        p, c = p[sel], c[sel]
    return np.concatenate([p, c], axis=1).astype(np.float32)


def prep_arkit(video_id: str, name: str, n_frames: int = 270) -> dict:
    import cv2

    raw = VOL / "raw" / "arkit" / video_id
    base = f"{ARKIT_URL}/Validation/{video_id}"
    for asset in (
        "vga_wide.zip",
        "vga_wide_intrinsics.zip",
        "lowres_depth.zip",
        "confidence.zip",
        "lowres_wide_intrinsics.zip",
    ):
        z = raw / asset
        _curl(f"{base}/{asset}", z)
        marker = raw / (asset + ".done")
        if not marker.exists():
            subprocess.run(["unzip", "-q", "-o", str(z), "-d", str(raw)], check=True)
            marker.touch()
    _curl(f"{base}/lowres_wide.traj", raw / "lowres_wide.traj")
    _curl(f"{base}/{video_id}_3dod_annotation.json", raw / "annotation.json")

    traj = [
        parse_arkit_traj_line(x)
        for x in (raw / "lowres_wide.traj").read_text().splitlines()
        if x.strip()
    ]
    traj_ts = np.array([t for t, _ in traj])
    order = np.argsort(traj_ts)
    traj_ts = traj_ts[order]
    traj_m = [np.asarray(traj[i][1]) for i in order]

    vga = sorted(glob.glob(str(raw / "**/vga_wide/*.png"), recursive=True), key=_ts)
    depth = sorted(glob.glob(str(raw / "**/lowres_depth/*.png"), recursive=True), key=_ts)
    conf_dir = Path(glob.glob(str(raw / "**/confidence"), recursive=True)[0])
    vga_k_dir = Path(glob.glob(str(raw / "**/vga_wide_intrinsics"), recursive=True)[0])
    low_k_dir = Path(glob.glob(str(raw / "**/lowres_wide_intrinsics"), recursive=True)[0])
    depth_ts = np.array([_ts(p) for p in depth])

    usable = []
    for p in vga:
        t = _ts(p)
        _, dt_pose = _nearest(traj_ts, t)
        _, dt_depth = _nearest(depth_ts, t)
        if dt_pose < 0.02 and dt_depth < 0.02:
            usable.append(p)
    chosen = _pick_sharp(usable, n_frames)

    sd = scene_dir(name)
    if sd.exists():
        shutil.rmtree(sd)
    (sd / "images").mkdir(parents=True)
    (sd / "depth").mkdir()
    frames = []
    k_ratio = []
    for i, p in enumerate(chosen):
        t = _ts(p)
        stem = Path(p).stem
        w, h, fx, fy, cx, cy = (
            float(v) for v in (vga_k_dir / f"{stem}.pincam").read_text().split()
        )
        k = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]])
        j, _ = _nearest(traj_ts, t)
        dj, _ = _nearest(depth_ts, t)
        dstem = Path(depth[dj]).stem
        d = cv2.imread(depth[dj], cv2.IMREAD_UNCHANGED)
        c = cv2.imread(str(conf_dir / f"{dstem}.png"), cv2.IMREAD_UNCHANGED)
        d = np.where(c >= 2, d, 0).astype(np.uint16)
        lw = (low_k_dir / f"{dstem}.pincam").read_text().split()
        k_ratio.append(fx / float(lw[2]))
        d = cv2.resize(d, (int(w), int(h)), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(str(sd / "depth" / f"{i:04d}.png"), d)
        write_rgb(sd / "images" / f"{i:04d}.jpg", read_rgb(Path(p)), 95)
        frames.append(
            {
                "file": f"images/{i:04d}.jpg",
                "depth": f"depth/{i:04d}.png",
                "K": k.tolist(),
                "c2w": traj_m[j].tolist(),
                "w": int(w),
                "h": int(h),
                "split": "test" if i % 9 == 4 else "train",
                "timestamp": t,
            }
        )
    up = _up_from_cameras([np.asarray(f["c2w"]) for f in frames])

    ann = json.loads((raw / "annotation.json").read_text())
    gt = []
    for o in ann["data"]:
        seg = o.get("segments", {}).get("obbAligned", o)
        rows = np.asarray(seg["normalizedAxes"], dtype=float).reshape(3, 3)
        gt.append(
            {
                "label": o["label"],
                "center": seg["centroid"],
                "axes_columns": rows.tolist(),  # rows of the stored matrix are the box axes
                "lengths": seg["axesLengths"],
            }
        )
    save_json(sd / "gt_boxes.json", gt)
    meta = {
        "name": name,
        "source": "arkitscenes",
        "video_id": video_id,
        "metric": True,
        "up": up.tolist(),
        "frames": frames,
        "vga_to_lowres_focal_ratio": float(np.median(k_ratio)),
        "usable_vga_frames": len(usable),
    }
    save_json(sd / "cameras.json", meta)
    pts = _init_points_from_depth(frames, sd, every=3, stride=4)
    np.save(sd / "points.npy", pts)
    return {
        "scene": name,
        "frames": len(frames),
        "points": len(pts),
        "gt_boxes": len(gt),
        "up": up.tolist(),
    }


def _rotation_to(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Rotation taking unit vector a onto unit vector b."""
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))


def prep_mip360(scene: str) -> dict:
    import pycolmap

    raw = VOL / "raw" / "mip360"
    z = raw / "360_v2.zip"
    _curl(MIP_URL, z)
    if not (raw / scene / "sparse").exists():
        subprocess.run(
            [
                "unzip",
                "-q",
                "-o",
                str(z),
                f"{scene}/images_4/*",
                f"{scene}/sparse/*",
                "-d",
                str(raw),
            ],
            check=True,
        )
    rec = pycolmap.Reconstruction(str(raw / scene / "sparse" / "0"))
    imgs = sorted(rec.images.values(), key=lambda im: im.name)
    c2ws = []
    for im in imgs:
        w2c = np.eye(4)
        w2c[:3, :4] = im.cam_from_world.matrix()
        c2ws.append(np.linalg.inv(w2c))
    up = _up_from_cameras(c2ws)
    rot = np.eye(4)
    rot[:3, :3] = _rotation_to(up, np.array([0.0, 1.0, 0.0]))
    sd = scene_dir(scene)
    if sd.exists():
        shutil.rmtree(sd)
    (sd / "images").mkdir(parents=True)
    frames = []
    for i, (im, c2w) in enumerate(zip(imgs, c2ws, strict=True)):
        cam = rec.cameras[im.camera_id]
        src = raw / scene / "images_4" / im.name
        rgb = read_rgb(src)
        h, w = rgb.shape[:2]
        s = w / cam.width
        p = cam.params
        if cam.model.name in ("SIMPLE_PINHOLE", "SIMPLE_RADIAL"):
            fx = fy = p[0]
            cx, cy = p[1], p[2]
        else:
            fx, fy, cx, cy = p[0], p[1], p[2], p[3]
        k = np.array([[fx * s, 0, cx * s], [0, fy * s, cy * s], [0, 0, 1.0]])
        write_rgb(sd / "images" / f"{i:04d}.jpg", rgb, 95)
        frames.append(
            {
                "file": f"images/{i:04d}.jpg",
                "depth": None,
                "K": k.tolist(),
                "c2w": (rot @ c2w).tolist(),
                "w": w,
                "h": h,
                "split": "test" if i % 8 == 0 else "train",
                "camera_model": cam.model.name,
            }
        )
    xyz = np.array([p.xyz for p in rec.points3D.values()])
    rgb = np.array([p.color for p in rec.points3D.values()]) / 255.0
    xyz = xyz @ rot[:3, :3].T
    np.save(sd / "points.npy", np.concatenate([xyz, rgb], axis=1).astype(np.float32))
    save_json(
        sd / "cameras.json",
        {
            "name": scene,
            "source": "mip360",
            "metric": False,
            "up": [0.0, 1.0, 0.0],
            "frames": frames,
        },
    )
    return {"scene": scene, "frames": len(frames), "points": len(xyz)}


def fetch_replica(scenes: list[str]) -> dict:
    """Stream the 17 release parts once and keep only each scene's mesh.ply."""
    dst = VOL / "raw" / "replica"
    dst.mkdir(parents=True, exist_ok=True)
    missing = [s for s in scenes if not (dst / s / "mesh.ply").exists()]
    if missing:
        parts = " ".join(f"{REPLICA_URL}a{c}" for c in "abcdefghijklmnopq")
        patterns = " ".join(f"'*{s}/mesh.ply'" for s in missing)
        cmd = (
            f"for u in {parts}; do curl -sSfL --retry 5 $u; done | unpigz -p 8 | "
            f"tar -x -C {dst} --wildcards --no-anchored {patterns}"
        )
        subprocess.run(["bash", "-o", "pipefail", "-c", cmd], check=True)
        for s in missing:
            found = glob.glob(str(dst / "**" / s / "mesh.ply"), recursive=True)
            found = [f for f in found if Path(f).parent.name == s]
            if found and Path(found[0]) != dst / s / "mesh.ply":
                (dst / s).mkdir(exist_ok=True)
                shutil.move(found[0], dst / s / "mesh.ply")
    return {s: (dst / s / "mesh.ply").exists() for s in scenes}


def render_replica(scene: str, width: int = 640, height: int = 480, focal: float = 500.0) -> dict:
    """Render an inside-out phone-like capture of one room with CPU ray casting."""
    import open3d as o3d
    import trimesh

    mesh = trimesh.load(VOL / "raw" / "replica" / scene / "mesh.ply", process=False, force="mesh")
    verts = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.faces, dtype=np.uint32)
    vcol = np.asarray(mesh.visual.vertex_colors[:, :3], dtype=np.float32) / 255.0
    ext = verts.max(0) - verts.min(0)
    upi = int(np.argmin(ext))
    up = np.zeros(3)
    up[upi] = 1.0
    floor = float(np.percentile(verts[:, upi], 1))
    rc = o3d.t.geometry.RaycastingScene()
    rc.add_triangles(o3d.core.Tensor(verts), o3d.core.Tensor(faces))

    def cast(origins: np.ndarray, dirs: np.ndarray):
        rays = np.concatenate([origins, dirs], axis=1).astype(np.float32)
        return rc.cast_rays(o3d.core.Tensor(rays))

    a, b = (i for i in range(3) if i != upi)
    lo, hi = verts.min(0), verts.max(0)
    eye_h = floor + 1.4
    grid = []
    for u in np.arange(lo[a] + 0.5, hi[a] - 0.5, 0.25):
        for v in np.arange(lo[b] + 0.5, hi[b] - 0.5, 0.25):
            p = np.zeros(3)
            p[a], p[b], p[upi] = u, v, eye_h
            grid.append(p)
    grid = np.array(grid)
    angs = np.linspace(0, 2 * math.pi, 36, endpoint=False)
    hdirs = np.zeros((36, 3))
    hdirs[:, a], hdirs[:, b] = np.cos(angs), np.sin(angs)
    o = np.repeat(grid, 36, axis=0)
    d = np.tile(hdirs, (len(grid), 1))
    t = cast(o, d)["t_hit"].numpy().reshape(len(grid), 36)
    t = np.where(np.isfinite(t), t, 0.0)  # escaping rays mean an opening, treat as blocked
    down = np.zeros((len(grid), 3))
    down[:, upi] = -1
    tdown = cast(grid, down)["t_hit"].numpy()
    valid = (t.min(1) > 0.6) & (np.abs(tdown - 1.4) < 0.15)
    score = np.where(valid, np.minimum(t, 4.0).mean(1), -1)
    center = grid[int(np.argmax(score))]
    spots = [center]
    for idx in np.argsort(-score):
        if score[idx] < 0 or len(spots) >= 4:
            break
        p = grid[idx]
        if np.linalg.norm(p - center) < 1.6 and all(np.linalg.norm(p - s) > 0.6 for s in spots):
            spots.append(p)

    sd = scene_dir(scene)
    if sd.exists():
        shutil.rmtree(sd)
    (sd / "images").mkdir(parents=True)
    (sd / "depth").mkdir()
    k = np.array([[focal, 0, width / 2], [0, focal, height / 2], [0, 0, 1.0]])
    ys, xs = np.mgrid[0:height, 0:width]
    dcam = np.stack(
        [(xs + 0.5 - k[0, 2]) / focal, (ys + 0.5 - k[1, 2]) / focal, np.ones_like(xs, float)], -1
    )
    dcam = dcam.reshape(-1, 3)
    dnorm = dcam / np.linalg.norm(dcam, axis=1, keepdims=True)
    frames = []
    i = 0
    for spot in spots:
        for yaw in np.linspace(0, 2 * math.pi, 20, endpoint=False):
            for pitch in (-0.40, 0.05):
                fwd = np.zeros(3)
                fwd[a], fwd[b] = math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch)
                fwd[upi] = math.sin(pitch)
                right = np.cross(fwd, up)
                right /= np.linalg.norm(right)
                downv = np.cross(fwd, right)
                c2w = np.eye(4)
                c2w[:3, 0], c2w[:3, 1], c2w[:3, 2], c2w[:3, 3] = right, downv, fwd, spot
                dirs = dnorm @ c2w[:3, :3].T
                ans = cast(np.repeat(spot[None], len(dirs), 0), dirs)
                th = ans["t_hit"].numpy()
                prim = ans["primitive_ids"].numpy()
                uv = ans["primitive_uvs"].numpy()
                hit = np.isfinite(th)
                col = np.zeros((len(dirs), 3), np.float32)
                tri = faces[prim[hit]]
                w1, w2 = uv[hit, 0:1], uv[hit, 1:2]
                col[hit] = (
                    (1 - w1 - w2) * vcol[tri[:, 0]] + w1 * vcol[tri[:, 1]] + w2 * vcol[tri[:, 2]]
                )
                z = np.where(hit, th * dnorm[:, 2], 0.0)
                rgb = (col.reshape(height, width, 3).clip(0, 1) * 255).astype(np.uint8)
                write_rgb(sd / "images" / f"{i:04d}.jpg", rgb, 95)
                import cv2

                cv2.imwrite(
                    str(sd / "depth" / f"{i:04d}.png"),
                    (z.reshape(height, width) * 1000).clip(0, 65535).astype(np.uint16),
                )
                frames.append(
                    {
                        "file": f"images/{i:04d}.jpg",
                        "depth": f"depth/{i:04d}.png",
                        "K": k.tolist(),
                        "c2w": c2w.tolist(),
                        "w": width,
                        "h": height,
                        "split": "test" if i % 8 == 3 else "train",
                    }
                )
                i += 1
    meta = {
        "name": scene,
        "source": "replica",
        "metric": True,
        "up": up.tolist(),
        "frames": frames,
        "spots": [s.tolist() for s in spots],
        "renderer": "Open3D ray casting of mesh vertex colours",
    }
    save_json(sd / "cameras.json", meta)
    pts = _init_points_from_depth(frames, sd, every=2, stride=4)
    np.save(sd / "points.npy", pts)
    return {"scene": scene, "frames": len(frames), "spots": len(spots), "points": len(pts)}
