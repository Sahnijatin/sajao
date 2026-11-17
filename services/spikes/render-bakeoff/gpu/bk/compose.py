"""Compositor: twin splat + product assets at Design positions -> composite and masks.

Arm A is this composite. C1, C2 and C3 start from it. It is also the reference the
checks compare every arm against: code placed every product here.

Products are rendered with Blender Cycles (bpy) in the space frame (z up), lit by
an environment map rendered from the twin itself, with a floor shadow catcher.
Splat and products are merged in numpy with a depth test.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
from bk.twin import load_twin, room_dir, to_space, to_world

SCALE = 2  # render at twice the keyframe resolution


def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x):
    x = np.clip(x, 0, None)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def splat_params(room: str, variant: str):
    from twin_gpu.common import out_dir
    from twin_gpu.splat import load_params

    if variant == "original":
        return load_params(out_dir(room) / "splat.pt")
    return load_params(room_dir(room) / f"cleared_{variant}.pt")


def camera(scene: dict, fi: int, scale: int = SCALE):
    f = scene["frames"][fi]
    k = np.array(f["K"], np.float64)
    k[:2] *= scale
    return k, np.asarray(f["c2w"], np.float64), int(f["w"] * scale), int(f["h"] * scale)


def render_splat(params, k, c2w, w, h, mask=None):
    """RGB (sRGB 0..1) and expected depth (m, along the optical axis)."""
    import torch
    from twin_gpu.splat import render

    vm = torch.linalg.inv(torch.from_numpy(c2w).float().cuda())[None]
    kt = torch.from_numpy(k).float().cuda()[None]
    with torch.no_grad():
        rc, ra, _ = render(params, vm, kt, w, h, mask=mask, mode="RGB+ED")
    rgb = rc[0, ..., :3].clamp(0, 1).cpu().numpy()
    depth = rc[0, ..., 3].cpu().numpy()
    alpha = ra[0, ..., 0].cpu().numpy()
    return rgb, depth, alpha


def env_map(params, fr: dict, centre_space, res: int = 512) -> np.ndarray:
    """Equirectangular radiance (linear) seen from `centre_space`, from 6 splat cube faces.

    Bright LDR pixels (windows, lamps) are boosted to stand in for clipped highlights.
    """
    import torch
    from twin_gpu.splat import render

    rr = np.asarray(fr["R"])
    eye = to_world(fr, np.asarray(centre_space, np.float64))
    # Face directions in space coordinates: +x, -x, +y, -y, +z, -z
    dirs = [
        np.array(d, float)
        for d in ([1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1])
    ]
    ups = [
        np.array(u, float)
        for u in ([0, 0, 1], [0, 0, 1], [0, 0, 1], [0, 0, 1], [0, -1, 0], [0, 1, 0])
    ]
    k = torch.tensor(
        [[[res / 2, 0, res / 2], [0, res / 2, res / 2], [0, 0, 1]]],
        dtype=torch.float32,
        device="cuda",
    )
    faces = []
    for d, u in zip(dirs, ups, strict=True):
        z = d
        y = -u
        x = np.cross(y, z)
        c2w = np.eye(4)
        c2w[:3, 0], c2w[:3, 1], c2w[:3, 2] = x @ rr, y @ rr, z @ rr
        c2w[:3, 3] = eye
        vm = torch.linalg.inv(torch.from_numpy(c2w).float().cuda())[None]
        with torch.no_grad():
            rc, _, _ = render(params, vm, k, res, res)
        faces.append((rc[0].clamp(0, 1).cpu().numpy(), x, y, z))
    he, we = res, 2 * res
    lon = (np.arange(we) + 0.5) / we * 2 * np.pi - np.pi
    lat = np.pi / 2 - (np.arange(he) + 0.5) / he * np.pi
    lon, lat = np.meshgrid(lon, lat)
    # Blender's equirect convention: u = atan2(y, -x) / 2pi + 0.5, v = elevation (rows flipped on upload).
    d = np.stack([-np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], -1)
    out = np.zeros((he, we, 3))
    best = np.full((he, we), -np.inf)
    for img, x, y, z in faces:
        dz = d @ z
        sel = dz > best
        u = (d @ x) / np.maximum(dz, 1e-6)
        v = (d @ y) / np.maximum(dz, 1e-6)
        ok = sel & (dz > 0) & (np.abs(u) <= 1.001) & (np.abs(v) <= 1.001)
        px = np.clip(((u + 1) / 2 * res).astype(int), 0, res - 1)
        py = np.clip(((v + 1) / 2 * res).astype(int), 0, res - 1)
        out[ok] = img[py[ok], px[ok]]
        best[ok] = dz[ok]
    lin = srgb_to_linear(out)
    lum = lin @ np.array([0.2126, 0.7152, 0.0722])
    boost = np.where(lum > 0.7, 1 + 4 * (lum - 0.7) / 0.3, 1.0)
    return (lin * boost[..., None]).astype(np.float32)


# ---------- Blender ----------


def _bpy_reset(w: int, h: int, samples: int):
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    device = "CPU"
    for kind in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            if any(d.type == kind for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == kind
                device = "GPU"
                break
        except Exception as exc:  # this backend is not available here; try the next one
            print(f"Cycles {kind} unavailable: {exc!r}")
    sc.cycles.device = device
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.film_transparent = True
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "Standard"
    vl = sc.view_layers[0]
    vl.use_pass_z = True
    vl.use_pass_object_index = True
    vl.cycles.use_pass_shadow_catcher = True
    return sc, device


def _set_camera(sc, k, c2w_space, w, h):
    import bpy
    from mathutils import Matrix

    cam = bpy.data.cameras.new("cam")
    cam.sensor_fit = "HORIZONTAL"
    cam.sensor_width = 36.0
    cam.lens = k[0, 0] / w * 36.0
    cam.shift_x = (w / 2 - k[0, 2]) / w
    cam.shift_y = (k[1, 2] - h / 2) / w
    cam.clip_start, cam.clip_end = 0.05, 100
    ob = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(ob)
    # OpenCV camera (x right, y down, z forward) -> Blender camera (x right, y up, -z forward)
    m = c2w_space.copy()
    m[:3, 1] *= -1
    m[:3, 2] *= -1
    ob.matrix_world = Matrix(m.tolist())
    sc.camera = ob
    return ob


def _world_env(env: np.ndarray, rot_z: float = 0.0):
    import bpy

    he, we = env.shape[:2]
    img = bpy.data.images.new("env", we, he, alpha=False, float_buffer=True)
    rgba = np.concatenate([env, np.ones((he, we, 1), np.float32)], -1)
    img.pixels.foreach_set(rgba[::-1].ravel())  # Blender images start at the bottom row
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    tex = nt.nodes.new("ShaderNodeTexEnvironment")
    tex.image = img
    mapping = nt.nodes.new("ShaderNodeMapping")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping.inputs["Rotation"].default_value[2] = rot_z
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    bpy.context.scene.world = world


def _vertex_colour_material(name: str, roughness=0.65):
    import bpy

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def _image_material(name: str, path: str, alpha: bool = False):
    import bpy

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    if alpha:
        nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        mat.blend_method = "CLIP"
    return mat


def _mesh_object(name, verts, faces, colours=None, mat=None, uvs=None):
    import bpy

    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces.tolist())
    me.update()
    if colours is not None:
        attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
        rgba = np.concatenate([colours, np.ones((len(colours), 1))], 1).astype(np.float32)
        attr.data.foreach_set("color", rgba.ravel())
    if uvs is not None:
        uv = me.uv_layers.new(name="UV")
        loop_uv = np.array([uvs[li] for li in [lp.vertex_index for lp in me.loops]], np.float32)
        uv.data.foreach_set("uv", loop_uv.ravel())
    ob = bpy.data.objects.new(name, me)
    if mat is not None:
        ob.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _box(sx, sy, sz):
    """Box centred in x, y with its base at z=0; faces as quads split into triangles; UVs for the top face."""
    x, y = sx / 2, sy / 2
    v = np.array(
        [
            [-x, -y, 0],
            [x, -y, 0],
            [x, y, 0],
            [-x, y, 0],
            [-x, -y, sz],
            [x, -y, sz],
            [x, y, sz],
            [-x, y, sz],
        ]
    )
    f = np.array(
        [
            [0, 2, 1],
            [0, 3, 2],
            [4, 5, 6],
            [4, 6, 7],
            [0, 1, 5],
            [0, 5, 4],
            [1, 2, 6],
            [1, 6, 5],
            [2, 3, 7],
            [2, 7, 6],
            [3, 0, 4],
            [3, 4, 7],
        ]
    )
    uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0], [1, 0], [1, 1], [0, 1]], float)
    return v, f, uv


def place_matrix(x, y, z, yaw_deg):
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    m = np.eye(4)
    m[:2, :2] = [[c, -s], [s, c]]
    m[:3, 3] = [x, y, z]
    return m


def add_item(item: dict, index: int) -> dict:
    """Add one Design item to the Blender scene. Returns its footprint corners (space frame)."""
    import bpy
    import trimesh
    from mathutils import Matrix

    tier = item["tier"]
    x, y = item["position"]
    yaw = item["rotation_deg"]
    z0 = item.get("z", 0.0)
    if tier == "mesh":
        # Render-ready asset: listing-sized mesh, y up, front at +z after `front_rot_deg`.
        mesh = trimesh.load(item["asset_path"], process=False)
        v = np.asarray(mesh.vertices, np.float64) * item.get("scale", 1.0)
        v = np.stack([v[:, 0], -v[:, 2], v[:, 1]], 1)  # y up -> z up; mesh +z (front) -> -y
        col = np.asarray(mesh.visual.vertex_colors[:, :3], np.float64) / 255
        col = srgb_to_linear(col)
        rot = place_matrix(0, 0, 0, item.get("front_rot_deg", 0.0))
        v = v @ rot[:3, :3].T
        ob = _mesh_object(
            f"item{index}", v, np.asarray(mesh.faces), col, _vertex_colour_material(f"m{index}")
        )
        size = v.max(0) - v.min(0)
    elif tier == "rug":
        sx, sy, _ = item["size_m"]
        v = np.array(
            [
                [-sx / 2, -sy / 2, 0.006],
                [sx / 2, -sy / 2, 0.006],
                [sx / 2, sy / 2, 0.006],
                [-sx / 2, sy / 2, 0.006],
            ]
        )
        f = np.array([[0, 1, 2], [0, 2, 3]])
        uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
        ob = _mesh_object(
            f"item{index}", v, f, None, _image_material(f"m{index}", item["texture_path"]), uv
        )
        size = np.array([sx, sy, 0.01])
    elif tier == "art":
        # Vertical panel, picture facing local -y (into the room), bottom edge at z0.
        sx, _, sz = item["size_m"]
        v = np.array([[-sx / 2, 0, 0], [sx / 2, 0, 0], [sx / 2, 0, sz], [-sx / 2, 0, sz]])
        f = np.array([[0, 1, 2], [0, 2, 3]])
        uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
        ob = _mesh_object(
            f"item{index}", v, f, None, _image_material(f"m{index}", item["texture_path"]), uv
        )
        size = np.array([sx, 0.03, sz])
    elif tier == "billboard":
        sx, _, sz = item["size_m"]
        v = np.array([[-sx / 2, 0, 0], [sx / 2, 0, 0], [sx / 2, 0, sz], [-sx / 2, 0, sz]])
        f = np.array([[0, 1, 2], [0, 2, 3]])
        uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
        ob = _mesh_object(
            f"item{index}", v, f, None, _image_material(f"m{index}", item["texture_path"], True), uv
        )
        size = np.array([sx, 0.3, sz])
    else:
        raise ValueError(tier)
    ob.matrix_world = Matrix(place_matrix(x, y, z0, yaw).tolist())
    ob.pass_index = index + 1
    lo, hi = np.array([-size[0] / 2, -size[1] / 2]), np.array([size[0] / 2, size[1] / 2])
    corners = np.array([[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]])
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    corners = corners @ np.array([[c, s], [-s, c]]) + [x, y]
    _ = bpy
    return {"corners": corners.tolist(), "height": float(size[2]), "z0": z0}


CATCHER_INDEX = 100  # pass index of shadow catchers (products use 1..99)


def _add_floor_catcher():
    v = np.array([[-30, -30, 0], [30, -30, 0], [30, 30, 0], [-30, 30, 0]], float)
    f = np.array([[0, 1, 2], [0, 2, 3]])
    ob = _mesh_object("floor", v, f, None, None)
    ob.is_shadow_catcher = True
    ob.pass_index = CATCHER_INDEX
    return ob


def _add_wall_catchers(walls: list[dict]):
    """Vertical shadow catchers on the twin's wall planes (space frame)."""
    for i, w in enumerate(walls):
        (x0, y0), (x1, y1) = w["ends"]
        v = np.array([[x0, y0, 0], [x1, y1, 0], [x1, y1, 2.6], [x0, y0, 2.6]], float)
        f = np.array([[0, 1, 2], [0, 2, 3]])
        ob = _mesh_object(f"wall{i}", v, f, None, None)
        ob.is_shadow_catcher = True
        ob.pass_index = CATCHER_INDEX + 1 + i


def wall_planes(
    params, fr: dict, items: list[dict], max_walls: int = 3, seed: int = 0
) -> list[dict]:
    """Walls near the design: RANSAC lines on the floor plan of opaque Gaussians 0.3 to 2.2 m up."""
    import torch

    means = params["means"].detach().cpu().numpy()
    opac = torch.sigmoid(params["opacities"]).detach().cpu().numpy()
    sp = to_space(fr, means[opac > 0.5])
    centre = np.mean([it["position"] for it in items], axis=0) if items else np.zeros(2)
    sel = (sp[:, 2] > 0.3) & (sp[:, 2] < 2.2) & (np.linalg.norm(sp[:, :2] - centre, axis=1) < 3.5)
    pts = sp[sel, :2]
    rng = np.random.default_rng(seed)
    walls = []
    for _ in range(max_walls):
        if len(pts) < 2000:
            break
        best = None
        for _ in range(400):
            a, b = pts[rng.choice(len(pts), 2, replace=False)]
            d = b - a
            if np.linalg.norm(d) < 0.3:
                continue
            d = d / np.linalg.norm(d)
            n = np.array([-d[1], d[0]])
            inl = np.abs((pts - a) @ n) < 0.03
            if best is None or inl.sum() > best[0]:
                best = (int(inl.sum()), a, d, inl)
        if best is None or best[0] < 1500:
            break
        _, a, d, inl = best
        t = (pts[inl] - a) @ d
        t0, t1 = np.percentile(t, [1, 99])
        if t1 - t0 < 0.8:
            pts = pts[~inl]
            continue
        walls.append(
            {
                "ends": [(a + d * t0).tolist(), (a + d * t1).tolist()],
                "inliers": best[0],
                "point": a.tolist(),
                "normal": [float(-d[1]), float(d[0])],
            }
        )
        pts = pts[~inl]
    return walls


def walls_behind(walls: list[dict], cam_xy, items: list[dict], margin: float = 0.03) -> list[dict]:
    """Keep only walls that stand behind every product as seen from the camera. A shadow
    catcher is solid to camera rays, so a plane in front of a product would hide it."""
    keep = []
    for w in walls:
        a, n = np.asarray(w["point"]), np.asarray(w["normal"])
        side_cam = float((np.asarray(cam_xy) - a) @ n)
        ok = all(
            float((np.asarray(it["position"]) - a) @ n) * np.sign(side_cam) > margin for it in items
        )
        if ok and abs(side_cam) > 0.3:
            keep.append(w)
    return keep


def key_light(env: np.ndarray) -> dict | None:
    """Direction and strength of the brightest part of the twin's environment (a window,
    a lamp), as a soft sun. Blender equirect convention, z up."""
    he, we = env.shape[:2]
    lum = env @ np.array([0.2126, 0.7152, 0.0722])
    thr = np.percentile(lum, 99.7)
    m = lum >= thr
    if lum[m].mean() < 0.8:
        return None
    lon = (np.arange(we) + 0.5) / we * 2 * np.pi - np.pi
    lat = np.pi / 2 - (np.arange(he) + 0.5) / he * np.pi
    lon, lat = np.meshgrid(lon, lat)
    d = np.stack([-np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], -1)
    v = (d[m] * lum[m, None]).sum(0)
    v /= np.linalg.norm(v) + 1e-9
    v[2] = max(v[2], 0.25)  # light from a window still has to reach the floor
    v /= np.linalg.norm(v)
    return {"direction": v.tolist(), "strength": float(min(4.0, 1.2 * lum[m].mean()))}


def _add_sun(light: dict):
    import bpy
    from mathutils import Vector

    sun = bpy.data.lights.new("key", "SUN")
    sun.energy = light["strength"]
    sun.angle = np.radians(12)
    ob = bpy.data.objects.new("key", sun)
    bpy.context.scene.collection.objects.link(ob)
    # A sun shines along its local -z; point that away from the bright direction.
    ob.rotation_euler = Vector(light["direction"]).to_track_quat("Z", "Y").to_euler()


def blender_render(
    items: list[dict],
    k,
    c2w_space,
    w,
    h,
    env: np.ndarray,
    samples: int = 96,
    walls: list[dict] | None = None,
    light: dict | None = None,
) -> dict:
    """Render products over a transparent film. Returns linear RGBA, shadow-catcher
    multiplier, z depth (inf where empty), object index, and timings."""
    import bpy

    t0 = time.time()
    sc, device = _bpy_reset(w, h, samples)
    _set_camera(sc, k, c2w_space, w, h)
    _world_env(env)
    _add_floor_catcher()
    _add_wall_catchers(walls or [])
    if light:
        _add_sun(light)
    foot = [add_item(it, i) for i, it in enumerate(items)]
    # Compositor: write each pass to its own OpenEXR.
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new("CompositorNodeRLayers")
    out = nt.nodes.new("CompositorNodeOutputFile")
    tmp = Path("/tmp/bl")
    tmp.mkdir(exist_ok=True)
    for f in tmp.glob("*"):
        f.unlink()
    out.base_path = str(tmp)
    out.format.file_format = "OPEN_EXR"
    out.format.color_depth = "32"
    out.file_slots.clear()
    for name in ("Image", "Shadow Catcher", "Depth", "IndexOB"):
        out.file_slots.new(name.replace(" ", ""))
        nt.links.new(rl.outputs[name], out.inputs[name.replace(" ", "")])
    bpy.ops.render.render(write_still=False)
    t1 = time.time()

    def load(name):
        """Read a pass with Blender itself (OpenCV's pip build cannot read OpenEXR)."""
        p = next(tmp.glob(f"{name}*.exr"))
        im = bpy.data.images.load(str(p))
        im.colorspace_settings.is_data = True  # raw linear values, no view transform
        a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1].copy()
        bpy.data.images.remove(im)
        return a if name in ("Image",) else a[..., :3]

    img = load("Image")
    shadow = load("ShadowCatcher")
    depth = load("Depth")
    index = load("IndexOB")
    if depth.ndim == 3:
        depth = depth[..., 0]
    if index.ndim == 3:
        index = index[..., 0]
    return {
        "rgba": img,
        "shadow": shadow if shadow.ndim == 3 else shadow[..., None].repeat(3, -1),
        "depth": depth,
        "index": np.rint(index).astype(np.int32),
        "footprints": foot,
        "device": device,
        "render_seconds": round(t1 - t0, 2),
    }


def displaced_ids(room: str, footprints: list[dict], frac: float = 0.25) -> list[int]:
    """Kept objects whose floor box overlaps a new product's footprint by more than `frac`.
    The layout assumes that floor is clear, so such an object (often a mislabelled piece of
    furniture the clear set missed) cannot stay in the redesigned room."""
    import cv2

    boxes = json.loads((room_dir(room) / "survey.json").read_text())["boxes"]
    polys = [np.asarray(f["corners"], np.float32) for f in footprints if f.get("corners")]
    out = []
    g = np.linspace(-0.45, 0.45, 7)
    for b in boxes:
        a = np.radians(b.get("yaw_deg", 0.0))
        ca, sa = np.cos(a), np.sin(a)
        pts = [
            (
                b["center"][0] + u * b["size"][0] * ca - v * b["size"][1] * sa,
                b["center"][1] + u * b["size"][0] * sa + v * b["size"][1] * ca,
            )
            for u in g
            for v in g
        ]
        hit = sum(
            any(cv2.pointPolygonTest(pg, (float(x), float(y)), False) >= 0 for pg in polys)
            for x, y in pts
        )
        if hit / len(pts) > frac:
            out.append(int(b["id"]))
    return out


def kept_object_depth(room, original, labels, variant, k, c2w, w, h, footprints=()) -> np.ndarray:
    """Depth of the furniture the design keeps (labelled objects not removed, and not
    standing where a new product goes); inf elsewhere."""
    import torch

    if labels is None:
        return np.full((h, w), np.inf)
    keep = labels > 0
    rm = room_dir(room) / f"removed_{variant}.npy"
    if variant != "original" and rm.exists():
        keep &= ~np.load(rm)
    if footprints:
        keep &= ~np.isin(labels, displaced_ids(room, list(footprints)))
    if not keep.any():
        return np.full((h, w), np.inf)
    _, depth, alpha = render_splat(original, k, c2w, w, h, mask=torch.from_numpy(keep).cuda())
    return np.where(alpha > 0.5, depth, np.inf)  # ED is already normalised by alpha


def floor_depth(k, c2w_world, w, h, fr: dict) -> np.ndarray:
    """Depth along the optical axis where each pixel ray meets the floor (inf if never)."""
    ys, xs = np.mgrid[0:h, 0:w]
    rays = np.stack(
        [(xs + 0.5 - k[0, 2]) / k[0, 0], (ys + 0.5 - k[1, 2]) / k[1, 1], np.ones_like(xs, float)],
        -1,
    )
    rw = rays @ c2w_world[:3, :3].T
    rs = rw @ np.asarray(fr["R"]).T
    o = to_space(fr, c2w_world[:3, 3])
    t = -o[2] / np.where(np.abs(rs[..., 2]) > 1e-9, rs[..., 2], np.nan)
    return np.where(t > 0, t, np.inf)


def composite(
    room: str,
    design: dict,
    fi: int,
    variant: str,
    background: str = "splat",
    samples: int = 96,
    out: Path | None = None,
) -> dict:
    """Render one design from keyframe `fi`. `background` = splat (arms A, C1, C2) or keyframe (C3)."""
    import cv2

    t0 = time.time()
    scene, original, labels, _ = load_twin(room)
    params = splat_params(room, variant)
    fr = json.loads((room_dir(room) / "survey.json").read_text())["frame"]
    k, c2w, w, h = camera(scene, fi)
    rgb, sdepth, _ = render_splat(params, k, c2w, w, h)
    t_splat = time.time() - t0
    photo = None
    if background == "keyframe":
        rgb, region, photo = keyframe_background(
            room, scene, fi, params, variant, k, c2w, w, h, rgb
        )
    else:
        region = None
    c2w_space = np.eye(4)
    rr = np.asarray(fr["R"])
    c2w_space[:3, :3] = rr @ c2w[:3, :3]
    c2w_space[:3, 3] = to_space(fr, c2w[:3, 3])
    for it in design["render_items"]:
        if it["tier"] == "billboard":  # face the camera
            vx, vy = c2w_space[0, 3] - it["position"][0], c2w_space[1, 3] - it["position"][1]
            it["rotation_deg"] = math.degrees(math.atan2(vx, -vy))
    env_centre = [c2w_space[0, 3], c2w_space[1, 3], 1.2]
    t1 = time.time()
    env = env_map(params, fr, env_centre)
    t_env = time.time() - t1
    walls = walls_behind(
        wall_planes(params, fr, design["render_items"]),
        c2w_space[:2, 3],
        [it for it in design["render_items"] if it["tier"] != "art"],
    )
    light = key_light(env)
    br = blender_render(design["render_items"], k, c2w_space, w, h, env, samples, walls, light)
    a = br["rgba"][..., 3]
    pdepth = np.where(a > 0.01, br["depth"], np.inf)
    # Products are hidden only by furniture the design keeps, never by the room shell or
    # by floaters left where furniture was removed.
    occl = kept_object_depth(room, original, labels, variant, k, c2w, w, h, br["footprints"])
    if region is not None and region.any():
        occl = np.where(region, np.inf, occl)  # C3: nothing stands where the photo was emptied
    visible_px = (a > 0.01) & ~(np.isfinite(occl) & (occl < pdepth - 0.03))
    # Shadows land only where a catcher (floor or wall) is the surface the twin shows there.
    fdepth = floor_depth(k, c2w, w, h, fr)
    catcher = br["index"] >= CATCHER_INDEX
    cdepth = np.where(catcher, br["depth"], fdepth)
    # The cleared splat is unreliable where furniture was removed (floaters), so test only
    # that no kept furniture stands in front of the catcher surface.
    on_catcher = np.isfinite(cdepth) & ~(np.isfinite(occl) & (occl < cdepth - 0.05))
    sh = np.where(on_catcher[..., None], np.clip(br["shadow"], 0, 1), 1.0)
    bg_lin = srgb_to_linear(rgb) * sh
    prod = np.clip(br["rgba"][..., :3], 0, None)
    aa = (a * visible_px)[..., None]
    # Blender's combined pass is premultiplied by alpha.
    lin = prod * visible_px[..., None] + bg_lin * (1 - aa)
    img = (np.clip(linear_to_srgb(lin), 0, 1) * 255 + 0.5).astype(np.uint8)
    masks_full = {i: (br["index"] == i + 1) for i in range(len(design["render_items"]))}
    masks_vis = {i: m & visible_px for i, m in masks_full.items()}
    depth = np.where(visible_px, pdepth, sdepth)
    res = {
        "room": room,
        "design": design["id"],
        "frame": fi,
        "variant": variant,
        "background": background,
        "size": [w, h],
        "device": br["device"],
        "blender_seconds": br["render_seconds"],
        "splat_seconds": round(t_splat, 2),
        "walls": len(walls),
        "debug": {
            "product_alpha_px": int((a > 0.01).sum()),
            "index_max": int(br["index"].max()),
            "index_values": sorted({int(v) for v in np.unique(br["index"])})[:12],
            "depth_min": float(np.min(br["depth"])),
            "visible_px": int(visible_px.sum()),
            "shadow_min": float(br["shadow"].min()),
            "shadowed_px": int(((sh < 0.9).any(-1)).sum()),
        },
        "key_light": light,
        "env_seconds": round(t_env, 2),
        "total_seconds": round(time.time() - t0, 2),
        "items": [
            {
                "index": i,
                "item_id": it["id"],
                "visible_px": int(masks_vis[i].sum()),
                "full_px": int(masks_full[i].sum()),
                **br["footprints"][i],
            }
            for i, it in enumerate(design["render_items"])
        ],
    }
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out / "image.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        cv2.imwrite(
            str(out / "products_raw.png"),
            cv2.cvtColor(
                (np.clip(linear_to_srgb(br["rgba"][..., :3]), 0, 1) * 255).astype(np.uint8),
                cv2.COLOR_RGB2BGR,
            ),
        )
        np.savez_compressed(
            out / "masks.npz",
            vis=np.stack([masks_vis[i] for i in masks_vis])
            if masks_vis
            else np.zeros((0, h, w), bool),
            full=np.stack([masks_full[i] for i in masks_full])
            if masks_full
            else np.zeros((0, h, w), bool),
            depth=depth.astype(np.float16),
            region=region if region is not None else np.zeros((h, w), bool),
        )
        (out / "meta.json").write_text(json.dumps(res, indent=1))
        if photo is not None:
            cv2.imwrite(
                str(out / "photo.png"),
                cv2.cvtColor(
                    (np.clip(photo, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR
                ),
            )
    return res


def keyframe_background(room, scene, fi, cleared_params, variant, k, c2w, w, h, cleared_rgb):
    """C3 background: the real keyframe photo, with only the cleared regions from the
    filled splat (colour-matched to the photo on a ring around each region)."""
    import cv2
    import torch
    from scipy.ndimage import binary_dilation
    from twin_gpu.common import read_rgb, scene_dir
    from twin_gpu.splat import load_params

    f = scene["frames"][fi]
    photo = read_rgb(scene_dir(room) / f["file"]).astype(np.float64) / 255
    photo = cv2.resize(photo, (w, h), interpolation=cv2.INTER_LANCZOS4).clip(0, 1)
    if variant == "original":
        return photo, np.zeros((h, w), bool), photo
    from twin_gpu.common import out_dir

    # Preferred: 2D diffusion inpaint of this keyframe (bk.removal2d), consistent across views.
    inp = room_dir(room) / "c3" / variant / f"{fi}_inpainted.png"
    npz = room_dir(room) / "c3" / variant / f"{fi}.npz"
    if inp.exists() and npz.exists():
        filled = cv2.cvtColor(cv2.imread(str(inp)), cv2.COLOR_BGR2RGB).astype(np.float64) / 255
        if filled.shape[:2] == (h, w):
            fm = room_dir(room) / "c3" / variant / f"{fi}_mask.npy"
            return filled, (np.load(fm) if fm.exists() else np.load(npz)["mask"]), photo
    original = load_params(out_dir(room) / "splat.pt")
    removed = np.load(room_dir(room) / f"removed_{variant}.npy")
    _, _, ra = render_splat(original, k, c2w, w, h, mask=torch.from_numpy(removed).cuda())
    region = binary_dilation(ra > 0.2, iterations=6)
    ring = binary_dilation(region, iterations=12) & ~region
    src = cleared_rgb
    if ring.sum() > 50:
        # per-channel affine colour match, cleared render -> photo, fitted on the ring
        for c in range(3):
            a_, b_ = np.polyfit(src[ring, c], photo[ring, c], 1)
            src[..., c] = np.clip(a_ * src[..., c] + b_, 0, 1)
    soft = cv2.GaussianBlur(region.astype(np.float32), (0, 0), 3)[..., None]
    soft = np.maximum(soft, region[..., None])
    return photo * (1 - soft) + src * soft, region, photo
