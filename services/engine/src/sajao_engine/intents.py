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
        if arch.space == twin.space_type and arch.min_area_m2 <= floor and arch.rung is None
    ]


def _weight(slot: A.Slot) -> float:
    return max(WEIGHT.get(c, OTHER_WEIGHT) for c in slot.categories)


def slot_options(
    arch: A.Archetype,
    products: Sequence[Product],
    budget_minor: int,
    intent: Intent,
    avoid: frozenset[str] = frozenset(),
    styles: Sequence[str] = (),
) -> list[SlotOptions]:
    """Each slot's products, best first for the intent. Products in a style the person
    picked come before the rest; the intent orders within each group. Slots with none
    are left out."""
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
            tags = {str(getattr(t, "value", t)) for t in (p.style_tags or [])}
            off_style = 0.0 if not styles or tags & set(styles) else 1.0
            if intent == "best_value":
                return (shunned, off_style, price)
            if intent == "bold":
                # The dearest that stays within half again of the slot's share.
                return (shunned, off_style, float(price > 1.5 * target), -price)
            return (shunned, off_style, abs(price - target))

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


@dataclass(frozen=True)
class _Ask:
    """One intent's fixed inputs to an attempt."""

    twin: SpaceTwin
    products: Sequence[Product]
    intent: Intent
    budget: int
    avoid: frozenset[str]
    styles: list[str]
    anchor: Design | None
    in_view: list[tuple[float, float]] | None


def _attempt(
    ask: _Ask,
    arch_keys: list[str],
    brief: Brief,
    seed: bool,
    space_profile_id: uuid.UUID,
    created_at: str,
) -> EngineResult:
    """Design one intent over some archetypes, with the relaxation order."""
    options: dict[str, list[Product]] = {}
    for key in arch_keys:
        found = slot_options(
            A.ARCHETYPES[key], ask.products, ask.budget, ask.intent, ask.avoid, ask.styles
        )
        for o in found:
            options.setdefault(o.slot, o.products)
    order = (
        seed_order(ask.twin, brief, arch_keys, options, created_at, ask.in_view)
        if seed
        else list(arch_keys)
    )
    if ask.intent == "bold" and ask.anchor is not None and ask.anchor.archetype in order:
        # Bold tries another archetype first; best match's own comes last.
        order = [k for k in order if k != ask.anchor.archetype] + [ask.anchor.archetype]
    request = DesignRequest(
        twin=ask.twin,
        brief=brief,
        in_view=ask.in_view,
        intent=ask.intent,
        archetypes=order,
        options=[SlotOptions(slot=k, products=v) for k, v in options.items()],
        design_id=uuid.uuid5(NAMESPACE, f"{ask.twin.id}:{ask.twin.version}:{ask.intent}"),
        space_profile_id=space_profile_id,
        created_at=created_at,  # type: ignore[arg-type]
    )
    return design_with_relaxation(request)


def _keep_seating(twin: SpaceTwin, brief: Brief) -> Brief:
    """The brief with the room's own seating kept: a refresh builds around it."""
    from sajao_engine.room import KEPT_GROUPS

    seats = KEPT_GROUPS["seating"]
    ids = [o.id for o in twin.objects if o.category.lower().replace("_", " ") in seats]
    keep = [k.root for k in brief.keep_item_ids]
    merged = keep + [i for i in ids if i not in keep]
    return brief.model_validate({**brief.model_dump(mode="json"), "keep_item_ids": merged})


def _with_rung(design: Design, rung: str) -> Design:
    data = design.model_dump(mode="json", exclude_unset=True)
    data["layout_rung"] = rung
    return Design.model_validate(data)


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
    shows them, and a photo room that the standard layouts cannot furnish steps down
    the fallback ladder (A.FALLBACK_RUNGS) per intent; the rung used is on the design."""
    keys = archetypes_for(twin)
    if not keys:
        raise ValueError(f"no archetype for a {twin.space_type} of this size")
    answers = brief.taste_answers
    styles = [str(getattr(s, "value", s)) for s in (answers.styles or [])] if answers else []
    out: list[IntentResult] = []
    anchor: Design | None = None
    for intent in intents:
        avoid: frozenset[str] = frozenset()
        if intent == "bold" and anchor is not None:
            avoid = frozenset(large_pieces(anchor))
        scaled = _brief(brief, intent)
        budget = scaled.budget.limit.amount_minor

        ask = _Ask(twin, products, intent, budget, avoid, styles, anchor, in_view)
        result = _attempt(ask, keys, scaled, True, space_profile_id, created_at)
        rung = "standard"
        if result.design is None and in_view is not None:
            for step in A.FALLBACK_RUNGS:
                rung_keys = A.for_rung(step, twin.space_type)
                if not rung_keys:
                    continue
                rung_brief = _keep_seating(twin, scaled) if step == "refresh" else scaled
                tried = _attempt(ask, rung_keys, rung_brief, False, space_profile_id, created_at)
                if tried.design is not None:
                    result, rung = tried, step
                    break
        if result.design is not None:
            result = result.model_copy(update={"design": _with_rung(result.design, rung)})
        ok = True
        if result.design is not None and anchor is not None:
            ok = distinct(result.design, anchor)
        if intent == "best_match":
            anchor = result.design
        out.append(IntentResult(intent, result, ok))
    return out
