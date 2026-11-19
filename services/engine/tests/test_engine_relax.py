import uuid
from datetime import UTC, datetime

from sajao_engine.relax import ORDER, DesignRequest, SlotOptions, design_with_relaxation
from sajao_engine.testing import (
    OpeningSpec,
    bedroom_kit,
    brief,
    fixture_rooms,
    product,
    rect,
    twin_from_polygon,
)
from sajao_engine.verifier import verify
from sajao_schemas.generated.v1 import MeasurementConfidence, Product, SpaceTwin

WHEN = datetime(2026, 1, 5, tzinfo=UTC)
ROOMS = fixture_rooms()


def req(
    twin: SpaceTwin, archetypes: list[str], options: dict[str, list[Product]], budget: int = 500_000
) -> DesignRequest:
    return DesignRequest(
        twin=twin,
        brief=brief(twin, budget_rupees=budget),
        archetypes=archetypes,
        options=[SlotOptions(slot=k, products=v) for k, v in options.items()],
        design_id=uuid.UUID(int=1),
        space_profile_id=uuid.UUID(int=2),
        created_at=WHEN,
    )


def test_no_relaxation_when_the_first_try_passes() -> None:
    kit = bedroom_kit()
    r = design_with_relaxation(
        req(ROOMS["br_master"], ["br_bed_centered"], {k: [p] for k, p in kit.items()})
    )
    assert r.design is not None
    assert len(r.attempts) == 1 and r.attempts[0].relaxations == []
    assert "reduce_program" not in r.design.relaxations


def test_a_smaller_program_is_used_last_and_shown() -> None:
    # Taped: the room keeps its full error band as margin, so the queen bed does not fit.
    # (An estimated room is placed at nominal sizes, where it would.)
    twin = ROOMS["br_small"].model_copy(
        update={"confidence": MeasurementConfidence(level="taped", basis="tape", tape_values=2)}
    )
    kit = bedroom_kit()
    queen = product("bed", 1.6, 2.05, 0.95, key="queen")
    single = product("bed", 0.9, 1.95, 0.45, key="single")
    options = {k: [p] for k, p in kit.items() if k != "bed"}
    options["bed"] = [queen, single]
    r = design_with_relaxation(req(twin, ["br_bed_centered", "br_bed_corner"], options))
    assert r.design is not None, r.honest
    used = [str(x) for x in r.design.relaxations]
    assert "reduce_program" in used
    # Relaxations are written in the documented order.
    assert used == sorted(used, key=lambda x: ORDER.index(x))
    assert r.design.items[0].product.id == single.id or any(
        i.product.id == single.id for i in r.design.items
    )
    assert verify(r.design, twin, brief(twin, budget_rupees=500_000), checked_at=WHEN).passed


def test_an_impossible_room_gets_an_honest_result() -> None:
    twin = twin_from_polygon(
        "box",
        rect(2.0, 2.2),
        space_type="bedroom",
        openings=[OpeningSpec("door", "door", 0, 0.1, 0.8, "start", "inward")],
        band=0.12,
    )
    queen = product("bed", 1.6, 2.05, 0.95, key="queen")
    r = design_with_relaxation(req(twin, ["br_bed_centered", "br_bed_corner"], {"bed": [queen]}))
    assert r.design is None and r.honest is not None
    kinds = {s.kind for s in r.honest.suggestions}
    assert {"tape_measure", "smaller_item"} <= kinds
    assert "bed" in r.honest.does_not_fit
    assert any("bed" in reason for reason in r.honest.reasons)
    # Every step of the order was tried before giving up.
    assert {x for a in r.attempts for x in a.relaxations} == set(ORDER)


def test_over_budget_is_never_relaxed_away() -> None:
    kit = bedroom_kit()
    r = design_with_relaxation(
        req(
            ROOMS["br_master"], ["br_bed_centered"], {k: [p] for k, p in kit.items()}, budget=10_000
        )
    )
    assert r.design is None and r.honest is not None
    assert any(s.kind == "raise_budget" for s in r.honest.suggestions)
