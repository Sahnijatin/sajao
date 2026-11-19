"""Three designs for one room: best value, best match and bold (docs/08, step 6).

Until the brief-to-spec model and the AI designer exist, the slot options come
from rules, the fallback the design doc names: for each slot of an archetype,
the catalog products of its categories, ordered by what the intent wants. The
solver, verifier and relaxation order then do all placing and checking; nothing
here sets a size, position or price.

- Best match: products closest to each slot's share of the budget, at budget.
- Best value: the cheapest products, at about 80% of the budget.
- Bold: another archetype first, the dearer products, up to 10% over budget, and
  none of best match's large pieces where another product can take the slot.

The three must differ in archetype or in at least half of their large pieces.
Pure and deterministic.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sajao_engine import archetypes as A
from sajao_engine.categories import category
from sajao_engine.geometry import polygon_area
from sajao_engine.relax import (
    DesignRequest,
    EngineResult,
    SlotOptions,
    _pick,
    design_with_relaxation,
)
from sajao_engine.solver import PlacementRequest, place
from sajao_schemas.generated.v1 import Brief, Design, Product, SpaceTwin

Intent = Literal["best_value", "best_match", "bold"]
INTENTS: tuple[Intent, ...] = ("best_match", "best_value", "bold")
BUDGET_SHARE: dict[Intent, float] = {"best_value": 0.8, "best_match": 1.0, "bold": 1.1}
# How a budget splits across slots, by category. Others share what is left.
WEIGHT = {
    "sectional_sofa": 0.40,
    "sofa": 0.35,
    "bed": 0.35,
    "loveseat": 0.25,
    "wardrobe": 0.25,
    "tv_unit": 0.12,
    "sideboard": 0.10,
    "dresser": 0.10,
    "armchair": 0.10,
    "accent_chair": 0.08,
    "bookshelf": 0.07,
    "coffee_table": 0.06,
    "rug": 0.05,
    "nightstand": 0.04,
}
OTHER_WEIGHT = 0.03
LARGE = {
    "sofa",
    "sectional_sofa",
    "loveseat",
    "bed",
    "wardrobe",
    "tv_unit",
    "sideboard",
    "bookshelf",
    "dresser",
}
OPTIONS_PER_SLOT = 6
NAMESPACE = uuid.UUID("6a1f0c2e-8d3b-4e5f-9a7c-1b2d3e4f5a6b")


# A budget when the person has not set one: the middle of the development listings'
# living-room totals, provisional until briefs carry real ones.
DEFAULT_BUDGET_RUPEES = 150_000


def default_brief(
    twin: SpaceTwin,
    created_at: str,
    budget_rupees: int = DEFAULT_BUDGET_RUPEES,
    taste_profile_id: uuid.UUID | None = None,
) -> Brief:
    """The brief a room gets before the person says anything: a full makeover at a
    middle budget, with some room to stretch, nothing required, nothing kept beyond the
    twin's own keep choices, Vastu off (it needs a confirmed direction)."""
    return Brief.model_validate(
        {
            "schema_version": "1.0",
            "id": str(uuid.uuid5(NAMESPACE, f"brief:{twin.id}:{twin.version}")),
            "space_profile_id": str(uuid.uuid5(NAMESPACE, f"profile:{twin.id}:{twin.version}")),
            "taste_profile_id": str(taste_profile_id or uuid.uuid5(NAMESPACE, "no taste profile")),
            "created_at": created_at,
            "intent": "full_makeover",
            "budget": {
                "limit": {"currency": "INR", "amount_minor": budget_rupees * 100},
                "flexibility": "stretch_10",
            },
            "must_haves": [],
            "keep_item_ids": [],
            "consider_vastu": False,
        }
    )


def archetypes_for(twin: SpaceTwin) -> list[str]:
    """Archetypes for the room's space type whose minimum floor the room has, in order."""
    floor = polygon_area([(p.x_m, p.y_m) for p in twin.shell.floor_polygon])
    return [
        key
        for key, arch in A.ARCHETYPES.items()
        if arch.space == twin.space_type and arch.min_area_m2 <= floor
    ]


def _weight(slot: A.Slot) -> float:
    return max(WEIGHT.get(c, OTHER_WEIGHT) for c in slot.categories)


def slot_options(
    arch: A.Archetype,
    products: Sequence[Product],
    budget_minor: int,
    intent: Intent,
    avoid: frozenset[str] = frozenset(),
) -> list[SlotOptions]:
    """Each slot's products, best first for the intent. Slots with none are left out."""
    candidates = {
        slot.key: [p for p in products if category(p.category).key in slot.categories]
        for slot in arch.slots
    }
    total = sum(_weight(s) for s in arch.slots if candidates[s.key]) or 1.0
    out = []
    for slot in arch.slots:
        found = candidates[slot.key]
        if not found:
            continue
        target = budget_minor * _weight(slot) / total

        def order(p: Product, target: float = target) -> tuple[float, ...]:
            price = float(p.price.amount_minor)
            shunned = 1.0 if str(p.id) in avoid else 0.0
            if intent == "best_value":
                return (shunned, price)
            if intent == "bold":
                # The dearest that stays within half again of the slot's share.
                return (shunned, float(price > 1.5 * target), -price)
            return (shunned, abs(price - target))

        ranked = sorted(found, key=lambda p: (*order(p), str(p.id)))
        out.append(SlotOptions(slot=slot.key, products=ranked[:OPTIONS_PER_SLOT]))
    return out


def large_pieces(design: Design) -> set[str]:
    return {
        str(item.product.id)
        for item in design.items
        if category(item.product.category).key in LARGE
    }


def distinct(a: Design, b: Design) -> bool:
    """Different archetypes, or at least half of the large pieces differ."""
    if a.archetype != b.archetype:
        return True
    pa, pb = large_pieces(a), large_pieces(b)
    if not pa and not pb:
        return False
    return len(pa ^ pb) >= max(len(pa), len(pb))


def _brief(brief: Brief, intent: Intent) -> Brief:
    limit = brief.budget.limit
    scaled = round(limit.amount_minor * BUDGET_SHARE[intent])
    return brief.model_copy(
        update={
            "budget": brief.budget.model_copy(
                update={"limit": limit.model_copy(update={"amount_minor": scaled})}
            )
        }
    )


def seed_order(
    twin: SpaceTwin,
    brief: Brief,
    keys: Sequence[str],
    options: dict[str, list[Product]],
    created_at: str,
    in_view: list[tuple[float, float]] | None = None,
) -> list[str]:
    """Archetypes best first: those that verify with nothing relaxed, most slots placed,
    then the rest in their own order. The designer's seed, by rules."""
    scored = []
    for rank, key in enumerate(keys):
        arch = A.ARCHETYPES[key]
        result = place(
            PlacementRequest(
                twin=twin,
                brief=brief,
                in_view=in_view,
                archetype=key,
                walkway_m=0.75,
                choices=_pick(arch, options, []),
                design_id=uuid.uuid5(NAMESPACE, f"seed:{key}"),
                space_profile_id=uuid.uuid5(NAMESPACE, "seed"),
                created_at=created_at,  # type: ignore[arg-type]
            )
        )
        placed = len(result.placed_slots) if result.design is not None else -1
        scored.append((-placed, rank, key))
    return [key for *_, key in sorted(scored)]


@dataclass(frozen=True)
class IntentResult:
    intent: Intent
    result: EngineResult
    # False when bold or best value came out too close to best match.
    distinct: bool = True


def three_designs(
    twin: SpaceTwin,
    brief: Brief,
    products: Sequence[Product],
    space_profile_id: uuid.UUID,
    created_at: str,
    intents: Sequence[Intent] = INTENTS,
    in_view: list[tuple[float, float]] | None = None,
) -> list[IntentResult]:
    """Best match first, then the others, each verified or an honest result. `in_view`
    (a photo room: sajao_engine.photo.visible_floor) keeps new items where the photo
    shows them."""
    keys = archetypes_for(twin)
    if not keys:
        raise ValueError(f"no archetype for a {twin.space_type} of this size")
    out: list[IntentResult] = []
    anchor: Design | None = None
    for intent in intents:
        avoid: frozenset[str] = frozenset()
        if intent == "bold" and anchor is not None:
            avoid = frozenset(large_pieces(anchor))
        scaled = _brief(brief, intent)
        budget = scaled.budget.limit.amount_minor
        options: dict[str, list[Product]] = {}
        for key in keys:
            for o in slot_options(A.ARCHETYPES[key], products, budget, intent, avoid):
                options.setdefault(o.slot, o.products)
        order = seed_order(twin, scaled, keys, options, created_at, in_view)
        if intent == "bold" and anchor is not None:
            order = [k for k in order if k != anchor.archetype] + [anchor.archetype]
        request = DesignRequest(
            twin=twin,
            brief=scaled,
            in_view=in_view,
            intent=intent,
            archetypes=order,
            options=[SlotOptions(slot=k, products=v) for k, v in options.items()],
            design_id=uuid.uuid5(NAMESPACE, f"{twin.id}:{twin.version}:{intent}"),
            space_profile_id=space_profile_id,
            created_at=created_at,  # type: ignore[arg-type]
        )
        result = design_with_relaxation(request)
        ok = True
        if result.design is not None and anchor is not None:
            ok = distinct(result.design, anchor)
        if intent == "best_match":
            anchor = result.design
        out.append(IntentResult(intent, result, ok))
    return out
