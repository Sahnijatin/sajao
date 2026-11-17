"""The objects step: detect, segment, lift and fuse, as one durable step.

Input `frames` is a JSON manifest built from the capture package:

    {"up_axis": 1, "depth_source": "lidar" | "image",
     "frames": [{"keyframe_id", "image", "width", "height", "intrinsics", "c2w", "depth"}]}

`image` and `depth` are blob digests; depth is a 16-bit PNG in millimetres, from
LiDAR or from the depth step on phones without it. Output `objects` is the JSON
list from `build_objects`. With an `inventory` input (the inventory step),
the detector looks for the listed items by name; items not placed are retried
under other names at a lower threshold, and the output `inventory` keeps every
one still not placed, with what was tried and why. Each object gets its type;
built-ins go to `built_ins`, for the shell. Model calls go through the gateways passed in, so
fallbacks, caps, caching and validation apply.
"""

import json
from collections.abc import Sequence
from typing import Any

import numpy as np

from sajao_gateway import ModelGateway, ModelRequest
from sajao_workers.models import SHELL_VOCABULARY, VOCABULARY, prompts_for
from sajao_workers.steps import NonRetryableStepError, Step, StepContext, StepOutput
from sajao_workers.twin.inventory import (
    dedupe,
    retry_vocabulary,
    split_built_ins,
    unplaced_items,
)
from sajao_workers.twin.objects import (
    FrameMasks,
    build_objects,
    decode_depth_mm,
    decode_mask,
    depth_at,
)
from sajao_workers.validate import check_detections, check_masks

# Bump when this step's logic, prompts or pinned model chains change.
VERSION = 10
# The retry for listed items not placed: other names and a lower score threshold.
RETRY_MIN_SCORE = 0.1
# Listed items of these types may be small (a clock, a switchboard, an idol).
SMALL_TYPES = {"fixture", "wall_item", "decor", "textile"}
SMALL_MIN_SIZE_M = 0.05

Found = list[list[tuple[dict[str, Any], dict[str, Any]]]]  # per frame: (detection, mask)


async def _detect_and_segment(
    detect: ModelGateway,
    segment: ModelGateway,
    images: list[dict[str, Any]],
    vocabulary: list[str],
    prompts: list[str],
    min_score: float | None = None,
) -> tuple[Found, str, str | None, int]:
    """Masks per frame for one detection pass, the detector and segmenter used, the cost."""
    payload: dict[str, Any] = {"images": images, "vocabulary": vocabulary, "prompts": prompts}
    if min_score is not None:
        payload["min_score"] = min_score
    detected = await detect.call(
        ModelRequest("twin_detect", "vision", "twin_detect@1", payload),
        validate=check_detections(payload),
    )
    frames = detected.output["frames"]
    if not any(f["detections"] for f in frames):
        return [[] for _ in images], detected.provider, None, detected.cost_micro_inr
    segment_payload = {
        "frames": [
            {**image, "boxes": [d["box"] for d in frame["detections"]]}
            for image, frame in zip(images, frames, strict=True)
        ]
    }
    masked = await segment.call(
        ModelRequest("twin_segment", "vision", "twin_segment@1", segment_payload),
        validate=check_masks(segment_payload),
    )
    found = [
        list(zip(det["detections"], seg["masks"], strict=True))
        for det, seg in zip(frames, masked.output["frames"], strict=True)
    ]
    cost = detected.cost_micro_inr + masked.cost_micro_inr
    return found, detected.provider, masked.provider, cost


def objects_step(detect: ModelGateway, segment: ModelGateway) -> Step:
    async def run(context: StepContext) -> StepOutput:
        manifest: dict[str, Any] = json.loads(context.read("frames"))
        frames = manifest["frames"]
        missing = [f["keyframe_id"] for f in frames if not f.get("depth")]
        if missing:
            raise NonRetryableStepError(
                f"{len(missing)} frames have no depth; run the depth step first"
            )
        inventory = json.loads(context.read("inventory")) if "inventory" in context.inputs else None
        items: list[dict[str, Any]] = []
        if inventory is None:
            vocabulary = [*VOCABULARY, *SHELL_VOCABULARY]
            prompts = prompts_for(vocabulary)
        else:
            items = [i for i in inventory["items"] if i["name"] not in SHELL_VOCABULARY]
            names = [i["name"] for i in items]
            vocabulary = [*names, *SHELL_VOCABULARY]
            prompts = [*names, *prompts_for(SHELL_VOCABULARY)]

        images = [{"image": f["image"], "width": f["width"], "height": f["height"]} for f in frames]
        found, detector, segmenter, cost = await _detect_and_segment(
            detect, segment, images, vocabulary, prompts
        )
        depths = [
            depth_at(
                decode_depth_mm(context.store.read_blob(f["depth"])), (f["height"], f["width"])
            )
            for f in frames
        ]
        min_size = {i["name"]: SMALL_MIN_SIZE_M for i in items if i["type"] in SMALL_TYPES}

        def fuse(
            passes: Sequence[Found], per_label: dict[str, dict[str, int]], fusion: dict[str, int]
        ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            frame_masks, openings = [], []
            for index, frame in enumerate(frames):
                masks: list[tuple[str, float, np.ndarray, str]] = []
                for found_pass in passes:
                    for d, m in found_pass[index]:
                        if d["label"] in SHELL_VOCABULARY:  # doors and windows go to the shell
                            openings.append(
                                {
                                    "keyframe_id": frame["keyframe_id"],
                                    "kind": d["label"],
                                    "mask": m["mask"],
                                }
                            )
                            continue
                        mask = decode_mask(context.store.read_blob(m["mask"]))
                        masks.append((d["label"], d["score"], mask, m["mask"]))
                frame_masks.append(
                    FrameMasks(
                        frame["keyframe_id"],
                        frame["c2w"],
                        frame["intrinsics"],
                        depths[index],
                        masks,
                    )
                )
            objects = build_objects(
                frame_masks,
                manifest["up_axis"],
                manifest["depth_source"],
                stats=fusion,
                min_size=min_size,
                per_label=per_label,
            )
            return objects, openings

        passes = [found]
        per_label: dict[str, dict[str, int]] = {}
        fusion: dict[str, int] = {}
        objects, openings = fuse(passes, per_label, fusion)
        tried = {i["name"]: [f"{detector}: {i['name']}"] for i in items}
        placed = {o["category"] for o in objects}
        retry_labels, retry_prompts = retry_vocabulary(
            [i for i in items if i["name"] not in placed]
        )
        if retry_labels:
            retried, retry_detector, _, retry_cost = await _detect_and_segment(
                detect, segment, images, retry_labels, retry_prompts, RETRY_MIN_SCORE
            )
            cost += retry_cost
            for label, prompt in zip(retry_labels, retry_prompts, strict=True):
                tried[label].append(f"{retry_detector}: {prompt} (min score {RETRY_MIN_SCORE:g})")
            passes.append(retried)
            per_label, fusion = {}, {}
            objects, openings = fuse(passes, per_label, fusion)

        files: dict[str, bytes] = {"openings": json.dumps(openings, sort_keys=True).encode()}
        meta: dict[str, Any] = {"detector": detector, "segmenter": segmenter, "fusion": fusion}
        built_ins: list[dict[str, Any]] = []
        if inventory is not None:
            objects, merged = dedupe(objects, items)
            meta["dedupe"] = merged
            objects, built_ins = split_built_ins(items, objects)
            unplaced = [
                {**u, "tried": tried[u["name"]]}
                for u in unplaced_items(items, objects, built_ins, per_label, [])
            ]
            placement = {
                "listed_by": inventory["listed_by"],
                "items_listed": len(items),
                "unplaced": unplaced,
            }
            files["inventory"] = json.dumps(placement, sort_keys=True).encode()
            meta.update(built_ins=len(built_ins), unplaced=len(unplaced), retried=len(retry_labels))
        files["objects"] = json.dumps(objects, sort_keys=True).encode()
        files["built_ins"] = json.dumps(built_ins, sort_keys=True).encode()
        meta.update(objects=len(objects), opening_masks=len(openings))
        return StepOutput(files=files, meta=meta, cost_micro_inr=cost)

    return Step("twin_objects", VERSION, run)
