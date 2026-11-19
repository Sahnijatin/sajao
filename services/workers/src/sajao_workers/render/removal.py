"""Taking a design's removed things out of the room photo (render arms C3 and C3L).

The twin's hero masks say where each thing is in the photo. The design's edits say
which things go. Their masks are joined and grown a little, to take the soft edge and
the contact shadow with them, and LaMa fills the hole through the gateway. Fixtures,
built-ins and kept things are never in the mask, so they stay exactly as photographed.
"""

import io
import json
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
from PIL import Image

from sajao_gateway import ModelGateway, ModelRequest
from sajao_workers.steps import ArtifactStore, Step, StepContext, StepOutput
from sajao_workers.twin.objects import decode_mask
from sajao_workers.validate import check_inpaint

# Bump when this step's logic or the pinned model changes.
VERSION = 1
# How far masks grow, as a share of the photo's longer side (about 9 px at 1280).
GROW_SHARE = 0.007
# Shadows fall below things: masks also grow downward by this share of their height.
SHADOW_SHARE = 0.06


def removed_ids(design: Mapping[str, Any]) -> list[str]:
    """Twin objects the design takes out, in edit order."""
    edits = (design.get("twin") or {}).get("edits", [])
    return [e["object_id"] for e in edits if e.get("op") == "remove"]


def _grow(mask: np.ndarray, radius: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(radius):
        g = out.copy()
        g[1:] |= out[:-1]
        g[:-1] |= out[1:]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        out = g
    return out


def removal_mask(
    twin: Mapping[str, Any],
    hero_view_id: str,
    remove: Iterable[str],
    store: ArtifactStore,
    shape: tuple[int, int],
) -> np.ndarray:
    """The pixels to fill: the hero masks of the removed things, grown, with a band below
    each for its shadow."""
    h, w = shape
    out = np.zeros(shape, dtype=bool)
    gone = set(remove)
    grow = max(1, round(GROW_SHARE * max(h, w)))
    for obj in twin["objects"]:
        if obj["id"] not in gone:
            continue
        for hm in obj.get("hero_masks") or []:
            if hm["hero_view_id"] != hero_view_id:
                continue
            mask = decode_mask(store.read_blob(hm["mask"].rsplit("/", 1)[-1]))
            if mask.shape != shape:
                mask = np.asarray(Image.fromarray(mask).resize((w, h), Image.Resampling.NEAREST))
            rows = np.nonzero(mask.any(axis=1))[0]
            if len(rows):
                drop = max(1, round(SHADOW_SHARE * (rows[-1] - rows[0] + 1)))
                shadow = np.zeros_like(mask)
                shadow[drop:] = mask[:-drop]
                mask = mask | shadow
            out |= _grow(mask, grow)
    return out


def _png(mask: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(mask.astype(np.uint8) * 255).save(buf, format="PNG")
    return buf.getvalue()


def photo_removal_step(gateway: ModelGateway) -> Step:
    """Inputs: `twin` and `photo` (the hero photo). Params: `hero_view_id` and `remove`
    (twin object ids). Output `cleaned`: the photo with them taken out. The three designs
    of a room remove the same things, so they share one cached result."""

    async def run(context: StepContext) -> StepOutput:
        twin = json.loads(context.read("twin"))
        photo = context.read("photo")
        size = Image.open(io.BytesIO(photo)).size
        mask = removal_mask(
            twin,
            str(context.params["hero_view_id"]),
            context.params["remove"],
            context.store,
            (size[1], size[0]),
        )
        if not mask.any():
            return StepOutput(refs={"cleaned": context.inputs["photo"]}, meta={"masked_share": 0.0})
        payload = {
            "frames": [
                {"image": context.inputs["photo"], "mask": context.store.put_blob(_png(mask))}
            ]
        }
        response = await gateway.call(
            ModelRequest("photo_inpaint", "vision", "photo_inpaint@1", payload),
            validate=check_inpaint(payload),
        )
        frame = response.output["frames"][0]
        return StepOutput(
            refs={"cleaned": frame["filled"]},
            meta={"model": response.model, "masked_share": round(float(mask.mean()), 4)},
            cost_micro_inr=response.cost_micro_inr,
        )

    return Step("photo_removal", VERSION, run)
