"""The edit step: show a twin with a design's edits, as one durable step.

Inputs: `twin` (the stored SpaceTwin), the splat step's `splat`, `labels` and
`cameras`, the `frames` manifest and the objects step's `objects`. Param:
`reference`, a TwinReference (twin id, version and ordered edits) as a design
holds it, and optionally `preview` (before and after images for review). The
stored twin never changes: the output `view` is the twin with the edits applied
(see twin/edits.py) and an edited splat.

Removed, replaced and moved objects are taken out of the splat and the room
behind them is filled (fill B, LaMa); moved objects' own Gaussians are then put
back where the user moved them. Catalog products (replace, add) have no
Gaussians: the app draws them at their catalog size in their box. Phone splats
of the edited room come from the phone step, joined with `with_phone_splats`.
Edits that change no Gaussians (restyle, add) keep the splat and use no GPU.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from sajao_gateway import ModelGateway, ModelRequest
from sajao_schemas import to_json_dict
from sajao_schemas.generated.v1 import SpaceTwin, TwinReference
from sajao_workers.steps import NonRetryableStepError, Step, StepContext, StepOutput
from sajao_workers.twin.assemble import TIERS, storage_key
from sajao_workers.twin.edits import apply_edits, space_transform, splat_ops
from sajao_workers.validate import check_removal

# Bump when this step's logic or the pinned models change.
VERSION = 1
FINETUNE_STEPS = 5000
STATE_NAMES = (("moved", "move"), ("removed", "remove"), ("replaced", "replace"))


def _reference(raw: object, twin: Mapping[str, Any]) -> list[dict[str, Any]]:
    try:
        reference = TwinReference.model_validate(raw)
    except ValidationError as error:
        raise NonRetryableStepError(f"the twin reference is not valid: {error}") from error
    if str(reference.twin_id) != twin["id"] or reference.twin_version != twin["version"]:
        raise NonRetryableStepError("the edits were made on another twin or version")
    edits: list[dict[str, Any]] = to_json_dict(reference)["edits"]
    return edits


def with_phone_splats(view: Mapping[str, Any], phone_splats: Sequence[Mapping[str, Any]]) -> Any:
    """The view with the edited room's phone splats (phone step variants with their SOG)."""
    out = {
        **view,
        "phone_splats": [
            {
                "key": storage_key(p["sog"]),
                "format": "sog",
                "tier": TIERS[p["budget"]],
                "gaussians": p["gaussians"],
                "bytes": p["bytes"],
            }
            for p in phone_splats
        ],
    }
    return to_json_dict(SpaceTwin.model_validate(out))


def edit_step(gateway: ModelGateway) -> Step:
    async def run(context: StepContext) -> StepOutput:
        twin = json.loads(context.read("twin"))
        edits = _reference(context.params.get("reference"), twin)
        applied = apply_edits(twin, edits)
        manifest = json.loads(context.read("frames"))
        try:
            world_to_space = space_transform(twin["keyframes"], manifest["frames"])
        except ValueError as error:
            raise NonRetryableStepError(str(error)) from error
        ops = splat_ops(twin, applied.twin, world_to_space)
        states = {o["id"]: o["state"] for o in applied.twin["objects"]}
        meta: dict[str, Any] = {
            "problems": [{"edit_id": p.edit_id, "reason": p.reason} for p in applied.problems],
            **{
                name: sorted(i for i, s in states.items() if s == state and i not in applied.added)
                for name, state in (
                    ("moved", "move"),
                    ("removed", "remove"),
                    ("replaced", "replace"),
                )
            },
            "added": applied.added,
        }
        splat, refs, cost = context.inputs["splat"], {}, 0
        if ops["remove"]:
            payload = {
                **{
                    k: context.inputs[k]
                    for k in ("splat", "labels", "cameras", "frames", "objects")
                },
                "remove": ops["remove"],
                "moves": {str(k): v for k, v in ops["moves"].items()},
                "steps": FINETUNE_STEPS,
            }
            if context.params.get("preview"):
                payload["preview"] = True
            response = await gateway.call(
                ModelRequest("twin_remove", "vision", "twin_remove@1", payload),
                validate=check_removal(),
            )
            out = response.output
            splat, cost = out["splat"], response.cost_micro_inr
            meta.update(
                {k: out[k] for k in ("gaussians_removed", "gaussians_moved", "fill_agreement_psnr")
                 if k in out}
            )  # fmt: skip
            if "preview" in out:
                refs["preview"] = out["preview"]
        view = {**applied.twin, "splat": {"key": storage_key(splat), "format": "ply"}}
        view.pop("phone_splats", None)  # they show the room before the edits
        try:
            checked = to_json_dict(SpaceTwin.model_validate(view))
        except ValidationError as error:
            raise NonRetryableStepError(f"the edited twin does not validate: {error}") from error
        return StepOutput(
            files={"view": json.dumps(checked, sort_keys=True).encode()},
            refs={"splat": splat, **refs},
            meta=meta,
            cost_micro_inr=cost,
        )

    return Step("twin_edit", VERSION, run)
