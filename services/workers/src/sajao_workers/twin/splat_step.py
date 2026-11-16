"""The splat step: train the room splat and split it by object, as one durable step.

Inputs are the frames manifest and the objects step's output. The GPU function
writes the splat (PLY), per-Gaussian object labels and refined cameras straight
to the artifact store; the step records them by digest, so hundreds of
megabytes never pass through the orchestrator.
"""

from sajao_gateway import ModelGateway, ModelRequest
from sajao_workers.steps import Step, StepContext, StepOutput
from sajao_workers.validate import check_splat

# Bump when this step's logic or the pinned trainer changes.
VERSION = 1
STEPS = 15_000
REPORTED = (
    "gaussians",
    "psnr_heldout",
    "psnr_heldout_raw",
    "train_seconds",
    "gaussians_on_objects",
    "objects_with_gaussians",
    "gpu",
)


def splat_step(gateway: ModelGateway) -> Step:
    async def run(context: StepContext) -> StepOutput:
        payload = {
            "frames": context.inputs["frames"],
            "objects": context.inputs["objects"],
            "steps": STEPS,
        }
        response = await gateway.call(
            ModelRequest("twin_splat", "vision", "twin_splat@1", payload), validate=check_splat()
        )
        out = response.output
        return StepOutput(
            refs={key: out[key] for key in ("splat", "labels", "cameras")},
            meta={key: out[key] for key in REPORTED if key in out},
            cost_micro_inr=response.cost_micro_inr,
        )

    return Step("twin_splat", VERSION, run)
