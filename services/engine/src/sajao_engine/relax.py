"""Relaxation order and the honest result.

When no design passes, relax in the documented order and stop at the first
step that yields a verified design. Relaxations are cumulative: each step keeps
the ones before it, and every one used is written on the design.

1. Drop optional items.
2. Smaller products in the same categories.
3. Switch layout archetype.
4. Reduce the walkway the layout aims for from 75 cm to the 60 cm minimum.
5. Reduce the furniture program (a loveseat for a sofa, a smaller bed).

Never relaxed: door swings, window access, the 60 cm walkway minimum,
switchboard and AC access, wardrobe and drawer clearance, a strict budget.
When even the last step fails, the result says what fits, why the rest does
not, and which brief changes would help. Nothing here calls a model.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from sajao_engine import archetypes as A
from sajao_engine.categories import category
from sajao_engine.room import Confidence, high
from sajao_engine.solver import PlacementRequest, PlacementResult, SlotChoice, place
from sajao_schemas.generated.v1 import Brief, Design, Product, RedoArea, SpaceTwin

Relaxation = Literal[
    "drop_optional_items",
    "smaller_products",
    "switch_archetype",
    "reduce_walkway",
    "reduce_program",
]
ORDER: tuple[Relaxation, ...] = (
    "drop_optional_items",
    "smaller_products",
    "switch_archetype",
    "reduce_walkway",
    "reduce_program",
)
# A room number with a band wider than this is worth a tape measure.
TAPE_WORTH_M = 0.03


class SlotOptions(BaseModel):
    """The designer's ranked products for one slot, preferred first."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    slot: str
    products: list[Product] = Field(min_length=1)


class DesignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    twin: SpaceTwin
    brief: Brief
    redo: RedoArea | None = None
    in_view: list[tuple[float, float]] | None = None
    intent: Literal["best_value", "best_match", "bold"] = "best_match"
    # Archetypes to try, preferred first; switching moves down this list.
    archetypes: list[str] = Field(min_length=1)
    options: list[SlotOptions]
    design_id: uuid.UUID
    space_profile_id: uuid.UUID
    created_at: AwareDatetime
    # How the room was measured; None reads it from the twin's dimension sources.
    confidence: Confidence | None = None


class Attempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    archetype: str
    relaxations: list[Relaxation]
    walkway_m: float
    passed: bool
    stuck_at: str | None = None
    failed_rules: list[str] = Field(default_factory=list)


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["tape_measure", "smaller_item", "fewer_items", "raise_budget", "remove_kept_item"]
    text: str
    slot: str | None = None


class HonestResult(BaseModel):
    """What fits and why the rest does not, with brief changes that would help."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    fits: list[str]
    does_not_fit: list[str]
    reasons: list[str]
    suggestions: list[Suggestion]


class EngineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    design: Design | None
    attempts: list[Attempt]
    honest: HonestResult | None = None


def _area(p: Product) -> float:
    return high(p.dimensions.width) * high(p.dimensions.depth)


def program(p: Product) -> tuple[str, int]:
    """What the piece is for, by size class: a queen bed, a three-seater, or just its category.

    Smaller products keep the class; only reducing the program may drop it.
    """
    width = p.dimensions.width.value_m
    if p.category == "bed":
        return ("bed", 0 if width < 1.1 else 1 if width < 1.45 else 2 if width < 1.7 else 3)
    if p.category in ("sofa", "loveseat", "sectional_sofa", "diwan"):
        return ("seating", 1 if width < 1.3 else 2 if width < 1.9 else 3)
    if p.category == "wardrobe":
        return ("wardrobe", 1 if width < 0.8 else 2 if width < 1.4 else 3)
    return (p.category, 0)


def _pick(
    arch: A.Archetype, options: dict[str, list[Product]], relaxations: Sequence[Relaxation]
) -> list[SlotChoice]:
    choices = []
    for slot in arch.slots:
        products = [
            p for p in options.get(slot.key, []) if category(p.category).key in slot.categories
        ]
        if not products:
            continue
        if "drop_optional_items" in relaxations and not slot.required:
            continue
        chosen = products[0]
        if "reduce_program" in relaxations:
            chosen = min(products, key=lambda p: (_area(p), products.index(p)))
        elif "smaller_products" in relaxations:
            same = [
                p
                for p in products
                if p.category == products[0].category and program(p) == program(products[0])
            ]
            chosen = min(same, key=lambda p: (_area(p), same.index(p)))
        choices.append(SlotChoice(slot=slot.key, product=chosen))
    return choices


def _attempt(
    req: DesignRequest, arch_key: str, relaxations: list[Relaxation]
) -> tuple[Attempt, PlacementResult]:
    arch = A.ARCHETYPES[arch_key]
    options = {o.slot: o.products for o in req.options}
    walkway = 0.60 if "reduce_walkway" in relaxations else 0.75
    result = place(
        PlacementRequest(
            twin=req.twin,
            brief=req.brief,
            redo=req.redo,
            in_view=req.in_view,
            archetype=arch_key,
            choices=_pick(arch, options, relaxations),
            design_id=req.design_id,
            space_profile_id=req.space_profile_id,
            created_at=req.created_at,
            intent=req.intent,
            walkway_m=walkway,
            relaxations=list(relaxations),
            confidence=req.confidence,
        )
    )
    attempt = Attempt(
        archetype=arch_key,
        relaxations=list(relaxations),
        walkway_m=walkway,
        passed=result.design is not None,
        stuck_at=result.unplaced_required[0] if result.unplaced_required else None,
        failed_rules=sorted(
            {v.rule for v in result.violations} | ({"budget"} if not result.budget_ok else set())
        ),
    )
    return attempt, result


def design_with_relaxation(req: DesignRequest) -> EngineResult:
    """A verified design for the brief, relaxing in order, or an honest result. Pure."""
    for key in req.archetypes:
        arch = A.ARCHETYPES.get(key)
        if arch is None or arch.space != req.twin.space_type:
            raise ValueError(f"Archetype {key!r} does not apply to a {req.twin.space_type}")
    attempts: list[Attempt] = []
    results: list[PlacementResult] = []
    used: list[Relaxation] = []

    def run(arch_key: str) -> Design | None:
        attempt, result = _attempt(req, arch_key, list(used))
        attempts.append(attempt)
        results.append(result)
        return result.design

    design = run(req.archetypes[0])
    if design is not None:
        return EngineResult(design=design, attempts=attempts)
    for step in ORDER:
        used.append(step)
        keys = req.archetypes if "switch_archetype" in used else req.archetypes[:1]
        # Once switching is allowed, every later step tries every archetype, preferred first.
        for key in keys if step != "switch_archetype" else req.archetypes[1:]:
            design = run(key)
            if design is not None:
                return EngineResult(design=design, attempts=attempts)
    return EngineResult(
        design=None, attempts=attempts, honest=honest_result(req, attempts, results)
    )


def honest_result(
    req: DesignRequest, attempts: Sequence[Attempt], results: Sequence[PlacementResult]
) -> HonestResult:
    """Built from the attempts' own findings; never invented."""
    best = (
        max(range(len(results)), key=lambda i: (len(results[i].placed_slots), -i))
        if results
        else None
    )
    fits = list(results[best].placed_slots) if best is not None else []
    stuck = sorted({a.stuck_at for a in attempts if a.stuck_at})
    rules = sorted({r for a in attempts for r in a.failed_rules})
    reasons: list[str] = []
    for slot in stuck:
        reasons.append(
            f"No place for the {slot.replace('_', ' ')} keeps every door, window and walkway clear."
        )
    texts = {
        "walkway_min": (
            "A 60 cm walkway from the door to every seat, bed side and cupboard could not be kept."
        ),
        "door_clear": "A door swing or doorway would be blocked.",
        "window_access": "A window would be blocked by something taller than its sill.",
        "fixture_access": "A switchboard or AC unit would be blocked.",
        "front_clearance": "A wardrobe, drawer or seat would not have room in front.",
        "budget": "The pieces that fit cost more than the budget.",
        "tight_spots_measured": "A piece would sit in a gap tighter than its size is known.",
    }
    reasons += [texts[r] for r in rules if r in texts]

    suggestions: list[Suggestion] = []
    shell = req.twin.shell
    widest = max([w.length.error_band_m for w in shell.walls] + [shell.ceiling_height.error_band_m])
    if widest > TAPE_WORTH_M:
        suggestions.append(
            Suggestion(
                kind="tape_measure",
                text=(
                    "Measure two walls with a tape: the scan's sizes carry up to "
                    f"{widest * 100:.0f} cm of doubt, and the design keeps that much clear."
                ),
            )
        )
    for slot in stuck:
        suggestions.append(
            Suggestion(
                kind="smaller_item", slot=slot, text=f"Choose a smaller {slot.replace('_', ' ')}."
            )
        )
    if "budget" in rules:
        suggestions.append(
            Suggestion(kind="raise_budget", text="Raise the budget or allow it to stretch by 10%.")
        )
    if any(a.failed_rules for a in attempts) and not stuck:
        suggestions.append(
            Suggestion(kind="fewer_items", text="Ask for fewer pieces in this room.")
        )
    keep = {k.root for k in req.brief.keep_item_ids}
    kept = [o for o in req.twin.objects if o.id in keep]
    big_kept = [o for o in kept if category(o.category).mount == "floor"]
    if big_kept:
        suggestions.append(
            Suggestion(
                kind="remove_kept_item",
                text=f"Let the design replace your {big_kept[0].label.lower()}.",
            )
        )
    does_not_fit = sorted({o.slot for o in req.options} - set(fits))
    return HonestResult(
        fits=fits, does_not_fit=does_not_fit, reasons=reasons, suggestions=suggestions
    )
