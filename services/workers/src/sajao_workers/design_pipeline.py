"""A design request through the pipeline: three verified designs for a room.

The API stores the request (its brief) and spawns this. It reads the room's twin,
takes the products this build may show, and runs the design engine: best match,
best value and bold, each verified or left out with the reason on the board. The
rows the app sees are `spec` (the products and the brief, by rules until the
brief-to-spec model exists), `placement` (solver, verifier, relaxation) and
`render` (the picture on the room's photo, its own stage).

On a photo room (estimated, a few keyframes) new items stay where the hero photo
shows the floor, so the render can show what the list sells. Every design copies
the request's profile ids, as the app made them. Pure orchestration over the
engine; nothing here sets a size, position or price.
"""

import json
import logging
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from sajao_engine.intents import three_designs
from sajao_engine.photo import visible_floor
from sajao_schemas import to_json_dict
from sajao_schemas.generated.v1 import Brief, Product, SpaceTwin

logger = logging.getLogger(__name__)

# Photo rooms have at most this many keyframes; a scan has many more.
PHOTO_KEYFRAMES = 3


class DesignBoard(Protocol):
    async def set_stage(
        self,
        room_id: str,
        stage: str,
        status: str,
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None: ...

    async def set_designs(self, request_id: str, designs: list[dict[str, Any]]) -> None: ...


@dataclass(frozen=True)
class DesignOutcome:
    outcome: str  # "done" or "failed"
    designs: list[dict[str, Any]]
    detail: str | None = None


def catalog_products(path: Path, allow_flagged: bool) -> list[Product]:
    """Products a design may use: gate-passing, and development products only where the
    build allows them (SAJAO_SHOW_FLAGGED_PRODUCTS)."""
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("gate", {}).get("result") != "pass":
            continue
        product = entry["product"]
        live = entry.get("stage") == "live" and product.get("image_use_permitted") is True
        if live or allow_flagged:
            out.append(Product.model_validate(product))
    return out


def in_view_for(twin: SpaceTwin) -> list[tuple[float, float]] | None:
    """The floor the hero photo shows, for a photo room; None for a scan."""
    if twin.confidence is None or twin.confidence.level != "estimated":
        return None
    if len(twin.keyframes) > PHOTO_KEYFRAMES:
        return None
    return visible_floor(twin)


async def run_design_request(
    board: DesignBoard,
    room_id: str,
    request_id: str,
    brief: Mapping[str, Any],
    twin: Mapping[str, Any] | None,
    products: Iterable[Product],
    created_at: str,
) -> DesignOutcome:
    """Run the request's spec and placement rows and store the designs. Safe to repeat."""

    async def move(stage: str, status: str, detail: str | None = None) -> None:
        await board.set_stage(room_id, stage, status, detail, request_id)

    await move("spec", "running")
    if twin is None:
        await move("spec", "failed", "room_not_ready")
        return DesignOutcome("failed", [], "room_not_ready")
    try:
        room = SpaceTwin.model_validate(twin)
        parsed = Brief.model_validate(brief)
    except ValueError:
        logger.exception("design request %s has an invalid twin or brief", request_id)
        await move("spec", "failed", "invalid_request")
        return DesignOutcome("failed", [], "invalid_request")
    if room.space_type not in ("living_room", "bedroom"):
        # Designs for other spaces are coming; the app says so (SJ-SCOPE-25).
        await move("spec", "failed", "space_not_supported")
        return DesignOutcome("failed", [], "space_not_supported")
    chosen = list(products)
    if not chosen:
        await move("spec", "failed", "no_products")
        return DesignOutcome("failed", [], "no_products")
    await move("spec", "done")

    await move("placement", "running")
    try:
        results = three_designs(
            room,
            parsed,
            chosen,
            uuid.UUID(str(parsed.space_profile_id.root))
            if hasattr(parsed.space_profile_id, "root")
            else uuid.UUID(str(parsed.space_profile_id)),
            created_at,
            in_view=in_view_for(room),
        )
    except ValidationError:
        # A design that breaks the contract is our bug, not the room's: say so.
        logger.exception("a design for request %s broke the contract", request_id)
        await move("placement", "failed", "internal")
        return DesignOutcome("failed", [], "internal")
    except ValueError as error:
        logger.exception("no design for request %s", request_id)
        await move("placement", "failed", "no_layout_for_room")
        return DesignOutcome("failed", [], str(error))
    designs = []
    for result in results:
        if result.result.design is None:
            continue
        design = to_json_dict(result.result.design)
        design["slot"] = result.intent
        designs.append(design)
    if not designs:
        await move("placement", "failed", "nothing_fits")
        return DesignOutcome("failed", [], "nothing_fits")
    await board.set_designs(request_id, designs)
    await move("placement", "done")
    return DesignOutcome("done", designs)
