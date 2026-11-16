"""The objects step: detect, segment, lift and fuse, as one durable step.

Input `frames` is a JSON manifest built from the capture package:

    {"up_axis": 1, "depth_source": "lidar" | "image",
     "frames": [{"keyframe_id", "image", "width", "height", "intrinsics", "c2w", "depth"}]}

`image` and `depth` are blob digests; depth is a 16-bit PNG in millimetres, from
LiDAR or from the depth step on phones without it. Output `objects` is the JSON
list from `build_objects`. Model calls go through the gateways passed in, so
fallbacks, caps, caching and validation apply.
"""

import json
from typing import Any

from sajao_gateway import ModelGateway, ModelRequest
from sajao_workers.models import VOCABULARY
from sajao_workers.steps import NonRetryableStepError, Step, StepContext, StepOutput
from sajao_workers.twin.objects import FrameMasks, build_objects, decode_depth_mm, decode_mask
from sajao_workers.validate import check_detections, check_masks

# Bump when this step's logic, prompts or pinned model chains change.
VERSION = 3


def objects_step(detect: ModelGateway, segment: ModelGateway) -> Step:
    async def run(context: StepContext) -> StepOutput:
        manifest: dict[str, Any] = json.loads(context.read("frames"))
        frames = manifest["frames"]
        missing = [f["keyframe_id"] for f in frames if not f.get("depth")]
        if missing:
            raise NonRetryableStepError(
                f"{len(missing)} frames have no depth; run the depth step first"
            )

        images = [{"image": f["image"], "width": f["width"], "height": f["height"]} for f in frames]
        detect_payload = {"images": images, "vocabulary": list(VOCABULARY)}
        detected = await detect.call(
            ModelRequest("twin_detect", "vision", "twin_detect@1", detect_payload),
            validate=check_detections(detect_payload),
        )
        found = detected.output["frames"]
        segment_payload = {
            "frames": [
                {**image, "boxes": [d["box"] for d in frame["detections"]]}
                for image, frame in zip(images, found, strict=True)
            ]
        }
        masked = await segment.call(
            ModelRequest("twin_segment", "vision", "twin_segment@1", segment_payload),
            validate=check_masks(segment_payload),
        )

        frame_masks = []
        for frame, det, seg in zip(frames, found, masked.output["frames"], strict=True):
            masks = [
                (d["label"], d["score"], decode_mask(context.store.read_blob(m["mask"])), m["mask"])
                for d, m in zip(det["detections"], seg["masks"], strict=True)
            ]
            frame_masks.append(
                FrameMasks(
                    frame["keyframe_id"],
                    frame["c2w"],
                    frame["intrinsics"],
                    decode_depth_mm(context.store.read_blob(frame["depth"])),
                    masks,
                )
            )
        fusion: dict[str, int] = {}
        objects = build_objects(
            frame_masks, manifest["up_axis"], manifest["depth_source"], stats=fusion
        )
        return StepOutput(
            files={"objects": json.dumps(objects, sort_keys=True).encode()},
            meta={
                "objects": len(objects),
                "detector": detected.provider,
                "segmenter": masked.provider,
                "fusion": fusion,
            },
            cost_micro_inr=detected.cost_micro_inr + masked.cost_micro_inr,
        )

    return Step("twin_objects", VERSION, run)
