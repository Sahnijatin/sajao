"""The depth step: metric depth for every keyframe on phones without LiDAR.

Input `frames` is the frames manifest. With LiDAR depth (`depth_source`
"lidar") it is passed on unchanged and no model runs. Otherwise every keyframe
gets depth from a geometry model (MoGe-3, falling back to DA3 Metric) given the
AR intrinsics, written as a 16-bit PNG in millimetres like LiDAR depth, and the
objects step then uses the wider "image" error bands. Depth is an estimate:
code fits every box from it, and no model sets a dimension.
"""

import json
import statistics
from typing import Any

from sajao_gateway import ModelGateway, ModelRequest
from sajao_workers.steps import Step, StepContext, StepOutput
from sajao_workers.validate import check_depths

# Bump when this step's logic or the pinned depth models change.
VERSION = 1


def depth_step(gateway: ModelGateway) -> Step:
    async def run(context: StepContext) -> StepOutput:
        manifest: dict[str, Any] = json.loads(context.read("frames"))
        if manifest["depth_source"] == "lidar":
            return StepOutput(refs={"frames": context.inputs["frames"]}, meta={"model": "lidar"})
        frames = manifest["frames"]
        payload = {
            "frames": [
                {key: f[key] for key in ("image", "width", "height", "intrinsics")} for f in frames
            ]
        }
        response = await gateway.call(
            ModelRequest("twin_depth", "vision", "twin_depth@1", payload),
            validate=check_depths(payload),
        )
        found = response.output["frames"]
        out = {
            **manifest,
            "depth_source": "image",
            "frames": [{**f, "depth": d["depth"]} for f, d in zip(frames, found, strict=True)],
        }
        return StepOutput(
            files={"frames": json.dumps(out, sort_keys=True).encode()},
            meta={
                "model": response.model,
                "frames": len(found),
                "median_coverage": round(statistics.median(d["coverage"] for d in found), 3),
            },
            cost_micro_inr=response.cost_micro_inr,
        )

    return Step("twin_depth", VERSION, run)
