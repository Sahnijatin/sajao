"""The inventory step: vision models list everything in the room, as one durable step.

Input `frames` is the frames manifest (see objects_step). Eight keyframes that
look in the most different directions go, at most 1024 px on the long side, to
the `lister` gateway (Gemini on Vertex AI) and the `checker` gateway (Claude).
Output `inventory` is {"listed_by", "items", "keyframes"}: the merged list, each
item with the pinned models that listed it. If the cross-check fails the list
stands; if the lister fails the cross-check's list is used; both failing fails
the step, which the runner retries.
"""

import io
import json
from typing import Any

from PIL import Image

from sajao_gateway import GatewayError, ModelGateway, ModelRequest, ModelResponse
from sajao_workers.models import (
    INVENTORY_KEYFRAMES,
    INVENTORY_MAX_TOKENS,
    INVENTORY_PROMPT,
    INVENTORY_PROMPT_ID,
)
from sajao_workers.steps import Step, StepContext, StepOutput
from sajao_workers.twin.inventory import (
    INVENTORY_SCHEMA,
    check_inventory,
    merge_inventories,
    pick_keyframes,
)

# Bump when this step's logic, prompt or pinned model chains change.
VERSION = 1
LONG_SIDE = 1024


def _jpeg(data: bytes) -> bytes:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.thumbnail((LONG_SIDE, LONG_SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


def inventory_step(lister: ModelGateway, checker: ModelGateway) -> Step:
    async def run(context: StepContext) -> StepOutput:
        frames = json.loads(context.read("frames"))["frames"]
        picked = pick_keyframes([f["c2w"] for f in frames], INVENTORY_KEYFRAMES)
        blobs = tuple(_jpeg(context.store.read_blob(frames[i]["image"])) for i in picked)
        payload = {
            "prompt": INVENTORY_PROMPT,
            "response_schema": INVENTORY_SCHEMA,
            "max_output_tokens": INVENTORY_MAX_TOKENS,
        }
        request = ModelRequest("twin_inventory", "vision", INVENTORY_PROMPT_ID, payload, blobs)

        answers: dict[str, ModelResponse] = {}
        failed = []
        for role, gateway in (("list", lister), ("cross_check", checker)):
            try:
                answers[role] = await gateway.call(request, validate=check_inventory)
            except GatewayError:
                failed.append(role)
        if not answers:
            raise RuntimeError("no vision model could list the room")

        lists: dict[str, Any] = {r.model: r.output["items"] for r in answers.values()}
        items = merge_inventories(lists)
        inventory = {
            "listed_by": list(lists),
            "items": items,
            "keyframes": [frames[i]["keyframe_id"] for i in picked],
        }
        return StepOutput(
            files={"inventory": json.dumps(inventory, sort_keys=True).encode()},
            meta={
                "items": len(items),
                "keyframes": len(picked),
                "listed_by": {r: a.model for r, a in answers.items()},
                "per_model": {m: len(v) for m, v in lists.items()},
                "failed": failed,
            },
            cost_micro_inr=sum(a.cost_micro_inr for a in answers.values()),
        )

    return Step("twin_inventory", VERSION, run)
