"""The single-photo step: one photo to a frames manifest with a camera on the floor.

Inputs: `capture` (no AR, one keyframe) and `images` (keyframe id to blob). The
photo's field of view comes from the keyframe's intrinsics, else from its EXIF
35 mm focal length, else from the depth model (MoGe-3 estimates it). Metric depth
comes through the gateway; code finds the floor plane, stands the camera on it
and measures the ceiling where the photo shows one (`single_photo.py`).

Outputs: `frames`, the manifest the twin steps read (one frame, `depth_source`
"image", `single_view` true), and `scale`, the ceiling cue for the scale check
that runs once doors are found. The room is `estimated`: no fit is claimed.
"""

import io
import json
import math
from typing import Any

from PIL import Image

from sajao_gateway import ModelGateway, ModelRequest
from sajao_workers.pipeline import StageError
from sajao_workers.steps import Step, StepContext, StepOutput
from sajao_workers.twin.objects import decode_depth_mm
from sajao_workers.twin.single_photo import (
    ceiling_height,
    intrinsics_from_fov,
    level_camera,
    lift,
    to_world,
)
from sajao_workers.validate import check_depths

# Bump when this step's logic or the pinned depth models change.
VERSION = 1
# EXIF tag: focal length in 35 mm film equivalent (a 36 mm wide frame).
EXIF_FOCAL_35MM = 0xA405
EXIF_IFD = 0x8769
FILM_WIDTH_MM = 36.0


def fov_from_exif(photo: bytes) -> float | None:
    """Horizontal field of view (degrees) from the photo's 35 mm equivalent focal length."""
    try:
        with Image.open(io.BytesIO(photo)) as image:
            exif = image.getexif()
            focal = exif.get_ifd(EXIF_IFD).get(EXIF_FOCAL_35MM) or exif.get(EXIF_FOCAL_35MM)
            width, height = image.size
    except (OSError, ValueError):
        return None
    if not focal:
        return None
    # The 35 mm equivalent describes the long side of the frame.
    long_side = 2 * math.degrees(math.atan(FILM_WIDTH_MM / (2 * float(focal))))
    if width >= height:
        return long_side
    return 2 * math.degrees(
        math.atan(math.tan(math.radians(long_side) / 2) * width / max(width, height))
    )


def _size(photo: bytes) -> tuple[int, int]:
    try:
        with Image.open(io.BytesIO(photo)) as image:
            return image.size
    except OSError as error:
        raise StageError("photo_unreadable") from error


def single_photo_step(gateway: ModelGateway) -> Step:
    async def run(context: StepContext) -> StepOutput:
        capture = json.loads(context.read("capture"))
        images: dict[str, str] = json.loads(context.read("images"))
        package = capture.get("package") or {}
        keyframes = package.get("keyframes", [])
        if len(keyframes) != 1 or keyframes[0]["id"] not in images:
            raise StageError("photo_missing")
        keyframe = keyframes[0]
        blob = images[keyframe["id"]]
        photo = context.store.read_blob(blob)
        width, height = _size(photo)
        given = keyframe.get("intrinsics")
        intrinsics: Any = None
        fov_from = "depth_model"
        if given:
            intrinsics = [
                [given["fx"], 0.0, given["cx"]],
                [0.0, given["fy"], given["cy"]],
                [0.0, 0.0, 1.0],
            ]
            fov_from = "capture"
        elif (fov := fov_from_exif(photo)) is not None:
            intrinsics = intrinsics_from_fov(width, height, fov)
            fov_from = "exif"
        payload = {
            "frames": [{"image": blob, "width": width, "height": height, "intrinsics": intrinsics}]
        }
        response = await gateway.call(
            ModelRequest("twin_depth", "vision", "twin_depth@1", payload),
            validate=check_depths(payload),
        )
        found = response.output["frames"][0]
        intrinsics = intrinsics or found["intrinsics"]
        depth = decode_depth_mm(context.store.read_blob(found["depth"]))
        points = lift(depth, intrinsics)
        camera = level_camera(points)
        if camera is None:
            # The app asks for a step back so the floor shows.
            raise StageError("floor_not_visible")
        ceiling = ceiling_height(to_world(points, camera), camera)
        frame = {
            "keyframe_id": keyframe["id"],
            "image": blob,
            "width": width,
            "height": height,
            "intrinsics": [[round(float(v), 4) for v in row] for row in intrinsics],
            "c2w": [[round(float(v), 9) for v in row] for row in camera.c2w],
            "depth": found["depth"],
        }
        manifest = {
            "up_axis": 1,
            "depth_source": "image",
            "single_view": True,
            "frames": [frame],
        }
        cue = {"ceiling_m": None if ceiling is None else round(ceiling, 3)}
        return StepOutput(
            files={
                "frames": json.dumps(manifest, sort_keys=True).encode(),
                "scale": json.dumps(cue, sort_keys=True).encode(),
            },
            meta={
                "model": response.model,
                "fov_from": fov_from,
                "camera_height_m": round(camera.height_m, 3),
                "tilt_deg": round(camera.tilt_deg, 1),
                "ceiling_m": cue["ceiling_m"],
                "landscape": width >= height,
                "coverage": found["coverage"],
            },
            cost_micro_inr=response.cost_micro_inr,
        )

    return Step("twin_single_photo", VERSION, run)
