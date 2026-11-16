"""From a capture package to the frames manifest the twin steps read.

AR poses come in the AR session's world frame (metres, gravity aligned, y up)
with the camera's +X right, +Y up and -Z forward (docs/06-room-capture.md).
The twin steps use OpenCV cameras (+Y down, +Z forward), so each pose is
turned half a revolution about its x axis. The world frame stays y up.
"""

import io
from collections.abc import Mapping
from typing import Any

import numpy as np
from PIL import Image

from sajao_workers.capture_depth import read_depth_container
from sajao_workers.steps import ArtifactStore

# AR camera axes to OpenCV camera axes: flip y and z.
AR_TO_OPENCV = np.diag([1.0, -1.0, -1.0])


class CaptureError(Exception):
    """The capture cannot become a twin as it is (no poses, missing images)."""


def _rotation(quaternion: list[float]) -> np.ndarray:
    x, y, z, w = quaternion
    norm = np.sqrt(x * x + y * y + z * z + w * w)
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def opencv_c2w(pose: Mapping[str, Any]) -> list[list[float]]:
    c2w = np.eye(4)
    c2w[:3, :3] = _rotation(pose["rotation"]) @ AR_TO_OPENCV
    p = pose["position"]
    c2w[:3, 3] = [p["x_m"], p["y_m"], p["z_m"]]
    return [[round(float(v), 9) for v in row] for row in c2w]


def _depth_png(metres: np.ndarray) -> bytes:
    millimetres = np.clip(np.round(metres * 1000.0), 0, 65535).astype(np.uint16)
    buf = io.BytesIO()
    Image.fromarray(millimetres).save(buf, format="PNG")
    return buf.getvalue()


def frames_manifest(
    package: Mapping[str, Any],
    images: Mapping[str, str],
    depth_file: bytes | None,
    store: ArtifactStore,
) -> dict[str, Any]:
    """The manifest for the objects and splat steps.

    `images` maps keyframe ids to blob digests of the ingested keyframe images;
    `depth_file` is the package's SJDEPTH1 file, when it has one. Frames without
    depth get None and wait for the depth step.
    """
    keyframes = package["keyframes"]
    no_pose = [k["id"] for k in keyframes if "pose" not in k or "intrinsics" not in k]
    if package["ar"]["tracking"] == "none" or no_pose:
        raise CaptureError("the twin needs AR poses and intrinsics for every keyframe")
    missing = [k["id"] for k in keyframes if k["id"] not in images]
    if missing:
        raise CaptureError(f"keyframe images not ingested: {', '.join(missing)}")
    depth = read_depth_container(depth_file) if depth_file else {}

    frames = []
    for k in keyframes:
        i = k["intrinsics"]
        image = depth.get(k["id"])
        frames.append(
            {
                "keyframe_id": k["id"],
                "image": images[k["id"]],
                "width": i["width_px"],
                "height": i["height_px"],
                "intrinsics": [[i["fx"], 0.0, i["cx"]], [0.0, i["fy"], i["cy"]], [0.0, 0.0, 1.0]],
                "c2w": opencv_c2w(k["pose"]),
                "depth": store.put_blob(_depth_png(image.confident_metres())) if image else None,
            }
        )
    lidar = bool(package["ar"]["lidar"]) and bool(depth)
    return {"up_axis": 1, "depth_source": "lidar" if lidar else "image", "frames": frames}
