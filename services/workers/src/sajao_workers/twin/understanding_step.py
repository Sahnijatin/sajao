"""The room understanding step, durable: what the design engine and the render read.

Inputs: `twin` (an assembled SpaceTwin), `objects` (the objects step's output, in
the frames' world, same order as the twin's objects) and `frames` (the frames
manifest). Output `twin`: the SpaceTwin with footprints, keep or replace, free
floor, and a mask per object in each hero view where it is visible. Masks the
detector already made are reused; the rest come from one segmenter call through
the gateway, prompted with each object's box projected into the hero photo.
"""

import json

from sajao_gateway import ModelGateway, ModelRequest
from sajao_workers.steps import NonRetryableStepError, Step, StepContext, StepOutput
from sajao_workers.twin.assemble import storage_key
from sajao_workers.twin.objects import decode_depth_mm, depth_at
from sajao_workers.twin.understanding import attach_hero_masks, hero_mask_plan, understand_room
from sajao_workers.validate import check_masks

# Bump when this step's logic or pinned model chain changes.
VERSION = 2


def understanding_step(segment: ModelGateway) -> Step:
    async def run(context: StepContext) -> StepOutput:
        twin = understand_room(json.loads(context.read("twin")))
        objects = json.loads(context.read("objects"))
        if len(objects) != len(twin["objects"]):
            raise NonRetryableStepError("the objects do not match the twin's objects")
        manifest = json.loads(context.read("frames"))
        heroes = {h["id"]: h["keyframe_id"] for h in twin.get("viewing", {}).get("hero_views", [])}
        frames = {
            f["keyframe_id"]: f for f in manifest["frames"] if f["keyframe_id"] in heroes.values()
        }
        depths = {
            k: depth_at(
                decode_depth_mm(context.store.read_blob(f["depth"])), (f["height"], f["width"])
            )
            for k, f in frames.items()
            if f.get("depth")
        }
        plan = hero_mask_plan(objects, list(frames.values()), heroes, depths)

        prompted = [p for p in plan if p["source"] == "prompted"]
        order = sorted({p["keyframe_id"] for p in prompted})
        cost = 0
        masks: dict[int, str] = {}
        if prompted:
            payload = {
                "frames": [
                    {
                        "image": frames[k]["image"],
                        "width": frames[k]["width"],
                        "height": frames[k]["height"],
                        "boxes": [p["box_px"] for p in prompted if p["keyframe_id"] == k],
                    }
                    for k in order
                ]
            }
            answer = await segment.call(
                ModelRequest("twin_hero_masks", "vision", "twin_segment@1", payload),
                validate=check_masks(payload),
            )
            cost = answer.cost_micro_inr
            for k, frame in zip(order, answer.output["frames"], strict=True):
                asked = [
                    i
                    for i, p in enumerate(plan)
                    if p.get("keyframe_id") == k and p["source"] == "prompted"
                ]
                for i, mask in zip(asked, frame["masks"], strict=True):
                    masks[i] = mask["mask"]

        results = []
        for i, p in enumerate(plan):
            digest = p["mask"] if p["source"] == "detected" else masks.get(i)
            if digest is None:
                continue
            results.append(
                {
                    "object_id": twin["objects"][p["object"]]["id"],
                    "hero_view_id": p["hero_view_id"],
                    "mask": storage_key(digest),
                    "visible_share": p["visible_share"],
                    "source": p["source"],
                }
            )
        twin = attach_hero_masks(twin, results)
        counts = {"detected": 0, "prompted": 0}
        for r in results:
            counts[r["source"]] += 1
        return StepOutput(
            files={"twin": json.dumps(twin, sort_keys=True).encode()},
            meta={
                "hero_masks": counts,
                "free_floor_m2": twin["free_floor"]["area_m2"],
                "floor_m2": twin["free_floor"]["floor_area_m2"],
                "kept": len(twin["free_floor"]["kept_ids"]),
            },
            cost_micro_inr=cost,
        )

    return Step("twin_understanding", VERSION, run)
