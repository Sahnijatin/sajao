"""The removal step: take objects out of the twin's splat (fill B), one durable step.

Inputs are the splat step's outputs (`splat`, `labels`, `cameras`), the frames
manifest and the objects step's output. Params: `object_ids`, twin object ids
such as "o3", and optionally `preview` (a before and after image for review).
The GPU job writes the edited splat to the artifact store and
the step records it by digest. If it fails, nothing changes: the object stays
in the twin and the removal can be asked for again.
"""

import json

from sajao_gateway import ModelGateway, ModelRequest
from sajao_workers.steps import NonRetryableStepError, Step, StepContext, StepOutput
from sajao_workers.twin.removal import object_index
from sajao_workers.validate import check_removal

# Bump when this step's logic or the pinned models change.
VERSION = 1
FINETUNE_STEPS = 5000
REPORTED = (
    "gaussians",
    "gaussians_removed",
    "frames_inpainted",
    "frames_dropped",
    "fill_agreement_psnr",
    "inpaint_seconds",
    "finetune_seconds",
    "gpu",
)


def _indices(ids: object, count: int) -> list[int]:
    if not isinstance(ids, list) or not ids:
        raise NonRetryableStepError("name at least one object id to remove")
    try:
        indices = sorted({object_index(str(i)) for i in ids})
    except ValueError as error:
        raise NonRetryableStepError(str(error)) from error
    if indices[-1] > count:
        raise NonRetryableStepError(f"the twin has no object o{indices[-1]}")
    return indices


def removal_step(gateway: ModelGateway) -> Step:
    async def run(context: StepContext) -> StepOutput:
        objects = json.loads(context.read("objects"))
        indices = _indices(context.params.get("object_ids"), len(objects))
        payload = {
            **{key: context.inputs[key] for key in ("splat", "labels", "cameras", "frames")},
            "objects": context.inputs["objects"],
            "remove": indices,
            "steps": FINETUNE_STEPS,
        }
        if context.params.get("preview"):
            payload["preview"] = True
        response = await gateway.call(
            ModelRequest("twin_remove", "vision", "twin_remove@1", payload),
            validate=check_removal(),
        )
        out = response.output
        return StepOutput(
            refs={key: out[key] for key in ("splat", "preview") if key in out},
            meta={
                "removed": [f"o{i}" for i in indices],
                **{key: out[key] for key in REPORTED if key in out},
            },
            cost_micro_inr=response.cost_micro_inr,
        )

    return Step("twin_remove", VERSION, run)
