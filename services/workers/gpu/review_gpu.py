"""Renders for a visual review of a twin: a fly-through, novel stills, removal before
and after, and the object boxes drawn on a still.

Every viewpoint is chosen by a fixed rule, not by eye, and none is a training
camera; the distance to the nearest training camera is reported for each. The
best and worst of a set of random viewpoints are scored by a no-reference proxy
(rendered coverage times sharpness), so the pack shows the weak views too.
"""

import json
import math

import numpy as np
from splat_gpu import InputError, render

W, H = 960, 720
FPS = 24
SECONDS = 25
CANDIDATES = 48


def _look_at(position: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    """OpenCV camera-to-world (x right, y down, z forward) at `position` facing `target`."""
    forward = target - position
    forward = forward / np.linalg.norm(forward)
    down = -up
    right = np.cross(down, forward)
    right = right / np.linalg.norm(right)
    down = np.cross(forward, right)
    c2w = np.eye(4)
    c2w[:3, :3] = np.column_stack([right, down, forward])
    c2w[:3, 3] = position
    return c2w


def _jpeg(rgb: np.ndarray, quality: int = 92) -> bytes:
    import cv2

    ok, data = cv2.imencode(
        ".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality]
    )
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return data.tobytes()


class Scene:
    """The room's frame: up axis, camera centroid, horizontal radius, eye height."""

    def __init__(self, c2w: np.ndarray, up_axis: int, k: np.ndarray, width: int) -> None:
        self.up = np.zeros(3)
        self.up[up_axis] = 1.0
        self.axes = [a for a in range(3) if a != up_axis]
        positions = c2w[:, :3, 3]
        self.positions = positions
        self.forwards = c2w[:, :3, 2]
        self.centre = positions.mean(0)
        flat = positions - self.centre
        flat[:, up_axis] = 0.0
        self.radius = float(np.clip(np.median(np.linalg.norm(flat, axis=1)), 0.4, 1.5))
        self.eye = float(np.median(positions[:, up_axis]))
        self.up_axis = up_axis
        scale = W / width
        self.k = np.array([[k[0, 0] * scale, 0, W / 2], [0, k[1, 1] * scale, H / 2], [0, 0, 1.0]])

    def point(self, angle: float, radius: float, height: float) -> np.ndarray:
        p = self.centre.copy()
        p[self.axes[0]] += radius * math.cos(angle)
        p[self.axes[1]] += radius * math.sin(angle)
        p[self.up_axis] = height
        return p

    def outward(self, angle: float, radius: float, height: float, look: float) -> np.ndarray:
        """A camera on the circle, looking out across the room at `look` radians."""
        position = self.point(angle, radius, height)
        target = self.point(look, radius + 3.0, height - 0.15)
        return _look_at(position, target, self.up)

    def novelty(self, c2w: np.ndarray) -> dict[str, float]:
        """How far a view is from the nearest training camera (metres, degrees)."""
        d = np.linalg.norm(self.positions - c2w[:3, 3], axis=1)
        cos = np.clip(self.forwards @ c2w[:3, 2], -1.0, 1.0)
        angle = np.degrees(np.arccos(cos))
        nearest = int(np.argmin(d + angle / 30.0))
        return {
            "nearest_m": round(float(d[nearest]), 2),
            "nearest_deg": round(float(angle[nearest]), 1),
        }


def _renderer(params):
    import torch

    def shot(c2w: np.ndarray, k: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        vm = torch.linalg.inv(torch.tensor(c2w, dtype=torch.float32, device="cuda"))[None]
        ks = torch.tensor(k, dtype=torch.float32, device="cuda")[None]
        with torch.no_grad():
            rc, ra, _ = render(params, vm, ks, W, H)
        rgb = (rc[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
        return rgb, ra[0, ..., 0].cpu().numpy()

    return shot


def _quality(rgb: np.ndarray, alpha: np.ndarray) -> dict[str, float]:
    import cv2

    coverage = float((alpha > 0.5).mean())
    sharp = float(cv2.Laplacian(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var())
    return {
        "coverage": round(coverage, 3),
        "sharpness": round(sharp, 1),
        "score": round(coverage * math.log1p(sharp), 3),
    }


def _box_corners(obj: dict, up_axis: int) -> np.ndarray:
    from sajao_workers.twin.geometry import UprightBox

    box = obj["box"]
    upright = UprightBox(
        tuple(box["center"]),
        box["length"]["value_m"],
        box["width"]["value_m"],
        box["height"]["value_m"],
        math.radians(box["yaw_deg"]),
        up_axis,
    )
    a, b = _axes(up_axis)
    corners = []
    for dz in (-0.5, 0.5):
        for u, v in upright.footprint():
            p = np.asarray(box["center"], dtype=np.float64).copy()
            p[a], p[b] = u, v
            p[up_axis] += dz * upright.height
            corners.append(p)
    return np.array(corners)


def _axes(up_axis: int) -> tuple[int, int]:
    from sajao_workers.twin.geometry import horizontal_axes

    a, b = horizontal_axes(up_axis)
    return a, b


def _project(points: np.ndarray, c2w: np.ndarray, k: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    w2c = np.linalg.inv(c2w)
    cam = points @ w2c[:3, :3].T + w2c[:3, 3]
    z = cam[:, 2]
    uv = (cam[:, :2] / np.maximum(z[:, None], 1e-6)) * [k[0, 0], k[1, 1]] + [k[0, 2], k[1, 2]]
    return uv, z


EDGES = [
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 0),
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 4),
    (0, 4),
    (1, 5),
    (2, 6),
    (3, 7),
]


def _draw_boxes(rgb: np.ndarray, objects: list, c2w: np.ndarray, k: np.ndarray, up_axis: int):
    """Boxes in front of the camera, with labels; returns the image and the labels drawn."""
    import cv2

    out = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    palette = [
        (66, 135, 245),
        (245, 166, 35),
        (80, 200, 120),
        (230, 80, 80),
        (170, 110, 230),
        (40, 200, 220),
        (240, 220, 60),
        (200, 120, 160),
    ]
    drawn = []
    for index, obj in enumerate(objects):
        uv, z = _project(_box_corners(obj, up_axis), c2w, k)
        if (z < 0.2).any():
            continue
        inside = (
            (uv[:, 0] > -W * 0.25)
            & (uv[:, 0] < W * 1.25)
            & (uv[:, 1] > -H * 0.25)
            & (uv[:, 1] < H * 1.25)
        )
        if inside.sum() < 4:
            continue
        colour = palette[index % len(palette)]
        for a, b in EDGES:
            cv2.line(
                out,
                tuple(int(x) for x in uv[a]),
                tuple(int(x) for x in uv[b]),
                colour,
                2,
                cv2.LINE_AA,
            )
        dims = [obj["box"][s]["value_m"] for s in ("length", "width", "height")]
        text = f"{obj['category']} {dims[0]:.2f}x{dims[1]:.2f}x{dims[2]:.2f} m"
        top = uv[np.argmin(uv[:, 1])]
        x, y = int(np.clip(top[0], 4, W - 200)), int(np.clip(top[1] - 8, 18, H - 4))
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(out, (x - 2, y - th - 4), (x + tw + 2, y + 4), colour, -1)
        cv2.putText(out, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        drawn.append(obj["category"])
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB), drawn


def _offset(
    c2w: np.ndarray, right_m: float, back_m: float, up_m: float, yaw_deg: float, up: np.ndarray
) -> np.ndarray:
    """A training-style camera moved and turned, so it is not a training view."""
    out = c2w.copy()
    r = np.radians(yaw_deg)
    # Turn about the world up axis (Rodrigues).
    k = up / np.linalg.norm(up)
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    turn = np.eye(3) + math.sin(r) * kx + (1 - math.cos(r)) * kx @ kx
    out[:3, :3] = turn @ c2w[:3, :3]
    out[:3, 3] = c2w[:3, 3] + right_m * c2w[:3, 0] - back_m * c2w[:3, 2] + up_m * up
    return out


def _smooth_path(c2w: np.ndarray, count: int, sigma: float = 6.0) -> list[np.ndarray]:
    """The capture path, smoothed and resampled; each pose looks along the smoothed view."""
    n = len(c2w)
    idx = np.arange(n)
    poses = []
    for t in np.linspace(0, n - 1, count):
        w = np.exp(-0.5 * ((idx - t) / sigma) ** 2)
        w = w / w.sum()
        position = (w[:, None] * c2w[:, :3, 3]).sum(0)
        forward = (w[:, None] * c2w[:, :3, 2]).sum(0)
        down = (w[:, None] * c2w[:, :3, 1]).sum(0)
        forward = forward / np.linalg.norm(forward)
        right = np.cross(down, forward)
        right = right / np.linalg.norm(right)
        down = np.cross(forward, right)
        pose = np.eye(4)
        pose[:3, :3] = np.column_stack([right, down, forward])
        pose[:3, 3] = position
        poses.append(pose)
    return poses


def _still(store, scene, shot, name, pose, kind) -> dict:
    rgb, alpha = shot(pose, scene.k)
    return {
        "name": name,
        "kind": kind,
        "c2w": pose.tolist(),
        "image": store.put_blob(_jpeg(rgb)),
        **_quality(rgb, alpha),
        **scene.novelty(pose),
    }


def review(payload: dict, store) -> dict:
    """All renders for one twin; images and frames go to the store as JPEG blobs."""
    from removal_gpu import load_ply
    from splat_gpu import _decode_rgb as decode_rgb

    for key in ("splat", "removed", "cameras", "frames", "objects"):
        if not store.has_blob(payload[key]):
            raise InputError(f"{key} is not in the store")
    frames = json.loads(store.read_blob(payload["frames"]))
    cameras = {c["keyframe_id"]: c["c2w"] for c in json.loads(store.read_blob(payload["cameras"]))}
    objects = json.loads(store.read_blob(payload["objects"]))
    c2w = np.array([cameras[f["keyframe_id"]] for f in frames["frames"]], dtype=np.float64)
    first = frames["frames"][0]
    k0 = np.asarray(first["intrinsics"], dtype=np.float64)
    scene = Scene(c2w, frames["up_axis"], k0, first["width"])
    shot = _renderer(load_ply(store.read_blob(payload["splat"])))
    up = scene.up
    rng = np.random.default_rng(0)

    # 0. Control: one training camera, the photo beside the render, to calibrate the eye.
    mid = len(c2w) // 2
    photo = decode_rgb(store.read_blob(frames["frames"][mid]["image"]))
    import cv2

    photo = cv2.resize(photo, (W, H), interpolation=cv2.INTER_AREA)
    rendered, _ = shot(c2w[mid], scene.k)
    control = store.put_blob(
        _jpeg(np.concatenate([photo, np.full((H, 8, 3), 255, np.uint8), rendered], axis=1))
    )

    # 1. Fly-through: the capture path, smoothed, moved 0.2 m right and 0.1 m up.
    video = []
    path = _smooth_path(c2w, FPS * SECONDS)
    novelty = []
    for pose in path:
        moved = _offset(pose, 0.2, 0.0, 0.1, 0.0, up)
        rgb, _ = shot(moved, scene.k)
        video.append(store.put_blob(_jpeg(rgb, 90)))
        novelty.append(scene.novelty(moved)["nearest_m"])

    # 2. Six stills by a fixed rule: three near the capture path (0.3 m right, 0.2 m back,
    # turned 12 degrees) and three far from it (the middle of the room, looking out).
    stills = []
    for j, t in enumerate((1 / 6, 3 / 6, 5 / 6)):
        pose = _offset(path[int(t * (len(path) - 1))], 0.3, 0.2, 0.0, 12.0, up)
        stills.append(_still(store, scene, shot, f"still_{j + 1}_near_path", pose, "near"))
    for j in range(3):
        angle = 2 * math.pi * j / 3 + 0.3
        pose = scene.outward(angle + math.pi, 0.35 * scene.radius, scene.eye, angle)
        stills.append(_still(store, scene, shot, f"still_{j + 4}_room_middle", pose, "far"))

    # Best and worst of random views: a training camera moved up to 1 m and turned up to 40 deg.
    candidates = []
    for _ in range(CANDIDATES):
        base = c2w[rng.integers(len(c2w))]
        pose = _offset(
            base,
            rng.uniform(-0.5, 0.5),
            rng.uniform(0, 1.0),
            rng.uniform(-0.2, 0.2),
            rng.uniform(-40, 40),
            up,
        )
        rgb, alpha = shot(pose, scene.k)
        candidates.append((_quality(rgb, alpha), pose, rgb))
    candidates.sort(key=lambda c: c[0]["score"])
    extremes = []
    for name, (quality, pose, rgb) in (("worst", candidates[0]), ("best", candidates[-1])):
        extremes.append(
            {
                "name": f"{name}_of_{CANDIDATES}",
                "kind": "random",
                "c2w": pose.tolist(),
                "image": store.put_blob(_jpeg(rgb)),
                **quality,
                **scene.novelty(pose),
            }
        )
    scores = [c[0]["score"] for c in candidates]

    # 4. Boxes on the near-path still that shows the most objects.
    best_boxes = None
    for still in stills[:3]:
        pose = np.asarray(still["c2w"])
        rgb, _ = shot(pose, scene.k)
        drawn_rgb, drawn = _draw_boxes(rgb, objects, pose, scene.k, scene.up_axis)
        if best_boxes is None or len(drawn) > len(best_boxes[1]):
            best_boxes = (drawn_rgb, drawn, still["name"])
    boxes = {
        "from": best_boxes[2],
        "labels": best_boxes[1],
        "image": store.put_blob(_jpeg(best_boxes[0])),
    }

    # 3. Removal before and after, from the training cameras that see the object best:
    # the nearest (close) and the farthest (wide), each moved 0.2 m back so neither is a
    # training view.
    target = objects[int(payload["removed_index"]) - 1]
    centre = np.asarray(target["box"]["center"], dtype=np.float64)
    seeing = []
    for j, pose in enumerate(c2w):
        uv, z = _project(centre[None], pose, scene.k)
        if z[0] > 0.5 and 0.1 * W < uv[0, 0] < 0.9 * W and 0.1 * H < uv[0, 1] < 0.9 * H:
            seeing.append((float(z[0]), j))
    if not seeing:
        raise InputError("no training camera sees the removed object")
    seeing.sort()
    views = {
        "close": _offset(c2w[seeing[0][1]], 0.0, 0.2, 0.0, 0.0, up),
        # The farthest camera that sees it, moved 0.5 m back for more of the room.
        "wide": _offset(c2w[seeing[-1][1]], 0.0, 0.5, 0.1, 0.0, up),
    }
    removed_shot = _renderer(load_ply(store.read_blob(payload["removed"])))
    removal = {}
    for name, pose in views.items():
        before, _ = shot(pose, scene.k)
        after, _ = removed_shot(pose, scene.k)
        removal[name] = {
            "before": store.put_blob(_jpeg(before)),
            "after": store.put_blob(_jpeg(after)),
            **scene.novelty(pose),
            "distance_to_object_m": round(float(np.linalg.norm(pose[:3, 3] - centre)), 2),
        }

    return {
        "control": control,
        "video_frames": video,
        "video_nearest_m": {
            "min": round(min(novelty), 2),
            "median": round(float(np.median(novelty)), 2),
        },
        "fps": FPS,
        "stills": stills,
        "extremes": extremes,
        "candidate_scores": {
            "min": round(min(scores), 3),
            "median": round(float(np.median(scores)), 3),
            "max": round(max(scores), 3),
        },
        "boxes": boxes,
        "removal": removal,
        "room": {"radius_m": round(scene.radius, 2), "eye_m": round(scene.eye, 2)},
    }
