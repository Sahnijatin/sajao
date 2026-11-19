"""Imported photos and video frames to the frames manifest the twin steps read.

A capture with no AR (`ar.tracking` none: photos from the gallery, or frames
the phone took from a video) has no poses. Two steps make its manifest:

1. `photo_poses_step`: the pose model (MapAnything, Apache 2.0 checkpoint,
   through the gateway) gives every photo a camera, intrinsics and a depth map
   in its own frame and scale. Frames go out with `depth` empty for the depth
   step, which adds metric depth (MoGe-3) as for any phone without LiDAR.
2. `photo_scale_step`: code turns the pose model's world into metres (the
   median ratio of metric depth to the pose model's depth) and stands it up
   (the photos' average up becomes +y). The manifest is then like a scan's.

The room that comes out is at the estimated confidence level: nothing is
claimed to fit until a measurement confirms it. No model sets a dimension.
"""

import io
import json
from typing import Any

import numpy as np

from sajao_gateway import ModelGateway, ModelRequest
from sajao_workers.steps import NonRetryableStepError, Step, StepContext, StepOutput
from sajao_workers.twin.objects import decode_depth_mm
from sajao_workers.twin.photos import (
    floor_normal,
    level_rotation,
    metric_scale,
    up_from_floor_normals,
)
from sajao_workers.validate import check_poses

# Bump when these steps' logic or the pinned pose model change.
VERSION = 5
# A pose model world this far from metres (either way) is a failure, not a scale.
SCALE_RANGE = (0.02, 50.0)
# A photo whose depth covers less than this is left out of the geometry (a blank
# wall, a dark corner); the room needs at least MIN_PHOTOS left.
MIN_PHOTO_COVERAGE = 0.1
MIN_PHOTOS = 2


def photo_poses_step(gateway: ModelGateway) -> Step:
    """Inputs: `capture` (its package, with no AR) and `images` (keyframe id to blob)."""

    async def run(context: StepContext) -> StepOutput:
        capture = json.loads(context.read("capture"))
        images: dict[str, str] = json.loads(context.read("images"))
        package = capture.get("package") or {}
        if (package.get("ar") or {}).get("tracking") != "none":
            raise NonRetryableStepError("this capture has AR poses: use the scan's frames")
        keyframes = package.get("keyframes", [])
        missing = [k["id"] for k in keyframes if k["id"] not in images]
        if not keyframes or missing:
            raise NonRetryableStepError(f"photos not ingested: {', '.join(missing) or 'none'}")
        payload = {"frames": [{"image": images[k["id"]]} for k in keyframes]}
        response = await gateway.call(
            ModelRequest("twin_poses", "vision", "twin_poses@1", payload),
            validate=check_poses(payload),
        )
        frames, left_out = [], []
        for k, f in zip(keyframes, response.output["frames"], strict=True):
            if f["coverage"] < MIN_PHOTO_COVERAGE:
                left_out.append(k["id"])
                continue
            frames.append(
                {
                    "keyframe_id": k["id"],
                    "image": images[k["id"]],
                    "width": f["width"],
                    "height": f["height"],
                    "intrinsics": f["intrinsics"],
                    "c2w": f["c2w"],
                    "pose_depth": f["pose_depth"],
                    "depth": None,
                }
            )
        if len(frames) < MIN_PHOTOS:
            raise NonRetryableStepError("too few photos with depth to place the cameras")
        manifest = {"up_axis": 1, "depth_source": "image", "frames": frames}
        return StepOutput(
            files={"frames": json.dumps(manifest, sort_keys=True).encode()},
            meta={"model": response.model, "photos": len(frames), "left_out": left_out},
            cost_micro_inr=response.cost_micro_inr,
        )

    return Step("twin_photo_poses", VERSION, run)


def photo_scale_step() -> Step:
    """Input `frames`: the manifest after the depth step. Output: in metres, y up."""

    async def run(context: StepContext) -> StepOutput:
        manifest: dict[str, Any] = json.loads(context.read("frames"))
        frames = manifest["frames"]
        if any(f.get("depth") is None or "pose_depth" not in f for f in frames):
            raise NonRetryableStepError("every photo needs both depths before scaling")
        model = [np.load(io.BytesIO(context.store.read_blob(f["pose_depth"]))) for f in frames]
        metric = [decode_depth_mm(context.store.read_blob(f["depth"])) for f in frames]
        resized = [_at(m, d.shape) for m, d in zip(model, metric, strict=True)]
        try:
            scale = metric_scale(resized, metric)
        except ValueError as error:
            raise NonRetryableStepError(str(error)) from error
        if not SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
            raise NonRetryableStepError(f"the photos' scale {scale:.3f} is not plausible")
        c2ws = []
        for f in frames:
            c = np.asarray(f["c2w"], dtype=np.float64)
            c[:3, 3] *= scale
            c2ws.append(c)
        turn = level_rotation(c2ws)
        # The cameras' up leans when the photos look down; the floor straightens it.
        # Each photo's floor comes from its own depth, which agrees with itself even
        # where the cameras do not quite agree with each other.
        y = np.array([0.0, 1.0, 0.0])
        normals = [
            n
            for d, f, c in zip(metric, frames, c2ws, strict=True)
            if (n := floor_normal(_lift(d, f["intrinsics"], turn, c, stride=8), y)) is not None
        ]
        floor = up_from_floor_normals(normals, y)
        correction_deg = 0.0
        if floor is not None:
            turn = floor @ turn
            correction_deg = float(np.degrees(np.arccos(np.clip(floor[1, 1], -1.0, 1.0))))
        out_frames = []
        for f, c in zip(frames, c2ws, strict=True):
            c[:3, :3] = turn @ c[:3, :3]
            c[:3, 3] = turn @ c[:3, 3]
            out_frames.append(
                {
                    **{k: v for k, v in f.items() if k != "pose_depth"},
                    "c2w": [[round(float(v), 9) for v in row] for row in c],
                }
            )
        out = {
            **manifest,
            "up_axis": 1,
            "depth_source": "image",
            "from_photos": True,
            "frames": out_frames,
        }
        return StepOutput(
            files={"frames": json.dumps(out, sort_keys=True).encode()},
            meta={
                "scale": round(scale, 4),
                "photos": len(out_frames),
                "up_from": "floor" if floor is not None else "cameras",
                "up_correction_deg": round(correction_deg, 2),
                "floor_photos": len(normals),
            },
        )

    return Step("twin_photo_scale", VERSION, run)


def _at(depth: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    """Depth resampled to another size by nearest neighbour."""
    if depth.shape == shape:
        return depth
    h, w = shape[:2]
    ys = (np.arange(h) * depth.shape[0] / h).astype(int)
    xs = (np.arange(w) * depth.shape[1] / w).astype(int)
    resampled: np.ndarray = depth[ys][:, xs]
    return resampled


def _lift(
    depth: np.ndarray, intrinsics: Any, turn: np.ndarray, c2w: np.ndarray, stride: int = 16
) -> np.ndarray:
    """Depth to world points (every `stride`th pixel), in the world `turn` stands up."""
    k = np.asarray(intrinsics, dtype=np.float64)
    ys, xs = np.mgrid[0 : depth.shape[0] : stride, 0 : depth.shape[1] : stride]
    z = depth[ys, xs]
    ok = z > 0.1
    xs, ys, z = xs[ok], ys[ok], z[ok]
    cam = np.stack([(xs + 0.5 - k[0, 2]) / k[0, 0] * z, (ys + 0.5 - k[1, 2]) / k[1, 1] * z, z], 1)
    world = cam @ c2w[:3, :3].T + c2w[:3, 3]
    lifted: np.ndarray = world @ turn.T
    return lifted
