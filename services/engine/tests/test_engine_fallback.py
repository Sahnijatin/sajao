"""The photo-room fallback ladder (Decision, 20 Nov): one test per rung, then the ladder.

A photo room that the standard layouts cannot furnish in view steps down: a sofa
floating toward the kept TV, a sofa on a side wall at a right angle to it, smaller
seating, then a refresh around the existing seating. All at the estimated level.
"""

import math
import uuid
from typing import Any

from sajao_engine.archetypes import ARCHETYPES, FALLBACK_RUNGS
from sajao_engine.intents import three_designs
from sajao_engine.room import ESTIMATED_CLEARANCE_M
from sajao_engine.solver import PlacementRequest, SlotChoice, place
from sajao_engine.testing import brief, living_kit, product, rect, twin_from_polygon
from sajao_schemas.generated.v1 import Design, Product, SpaceTwin

WHEN = "2026-11-20T00:00:00Z"
W, D = 5.0, 4.0  # edge 0 (w1) is y = 0, edge 1 (w2) x = 5, edge 2 (w3) y = 4, edge 3 (w4) x = 0
# The floor in front of the TV wall, as a photo taken from the far side shows it.
IN_VIEW = [(0.4, 0.2), (4.6, 0.2), (4.6, 3.3), (0.4, 3.3)]


def kept(oid: str, category: str, x: float, y: float, w: float, d: float, on_floor: bool) -> Any:
    def size(v: float) -> dict[str, Any]:
        return {"value_m": v, "source": "estimated", "error_band_m": 0.05}

    return {
        "id": oid,
        "category": category,
        "label": category.title(),
        "object_type": "fixture" if category == "tv" else "furniture",
        "box": {
            "center": {"x_m": x, "y_m": y, "z_m": 0.4},
            "width": size(w),
            "depth": size(d),
            "height": size(0.8),
            "yaw_deg": 0.0,
        },
        "views": [],
        "catalog_matches": [],
        "state": "keep",
        "detection": {"source": "server_segmentation", "confidence": 0.9},
        "footprint": {
            "polygon": [
                {"x_m": x - w / 2, "y_m": y - d / 2},
                {"x_m": x + w / 2, "y_m": y - d / 2},
                {"x_m": x + w / 2, "y_m": y + d / 2},
                {"x_m": x - w / 2, "y_m": y + d / 2},
            ],
            "width": size(w),
            "depth": size(d),
            "on_floor": on_floor,
        },
        "redesign": {"state": "keep", "source": "rule"},
    }


TV = kept("tv", "tv", 2.5, 0.06, 1.2, 0.08, on_floor=False)


def room(**kw: Any) -> SpaceTwin:
    return twin_from_polygon("fallback", rect(W, D), **kw)


def choose(arch: str, kit: dict[str, Product]) -> list[SlotChoice]:
    by_slot = {**kit, "seat": kit["armchair"], "seat_2": kit["armchair_right"]}
    return [
        SlotChoice(slot=s.key, product=by_slot[s.key])
        for s in ARCHETYPES[arch].slots
        if s.key in by_slot
    ]


def placed(twin: SpaceTwin, arch: str, in_view: list[tuple[float, float]] = IN_VIEW) -> Design:
    result = place(
        PlacementRequest(
            twin=twin,
            brief=brief(twin, budget_rupees=500_000),
            archetype=arch,
            in_view=in_view,
            choices=choose(arch, living_kit()),
            design_id=uuid.UUID(int=1),
            space_profile_id=uuid.UUID(int=2),
            created_at=WHEN,  # type: ignore[arg-type]
            walkway_m=0.75,
        )
    )
    assert result.design is not None, (result.unplaced_required, result.violations)
    design = result.design
    assert design.measurement_level == "estimated"
    return design


def item(design: Design, *categories: str) -> Any:
    found = [i for i in design.items if i.product.category in categories]
    assert found, [i.product.category for i in design.items]
    return found[0]


def test_the_ladder_runs_in_the_decided_order() -> None:
    assert FALLBACK_RUNGS == ("floating_sofa", "side_wall_sofa", "smaller_seating", "refresh")


def test_b_a_floating_sofa_faces_the_kept_tv_with_a_walkway_behind_it() -> None:
    # Side walls unseen, the far side open: no wall to back the sofa against.
    twin = room(objects=[TV], unseen_edges=[1, 3], open_edges=[2])
    design = placed(twin, "lr_float_tv")
    sofa = item(design, "sofa")
    assert sofa.position is not None
    # Square on to the TV: facing it across the room.
    assert math.isclose(sofa.rotation_deg % 360, 180.0, abs_tol=1.0)
    # A walkway at the nominal width stays between its back and the open edge.
    back = sofa.position.y_m + sofa.product.dimensions.depth.value_m / 2
    assert D - back >= ESTIMATED_CLEARANCE_M + 0.75 - 1e-6


def test_b_with_an_unseen_far_side_the_sofa_needs_no_walkway_behind() -> None:
    twin = room(objects=[TV], unseen_edges=[1, 2, 3])
    design = placed(twin, "lr_float_tv", in_view=[(0.4, 0.2), (4.6, 0.2), (4.6, 3.9), (0.4, 3.9)])
    assert item(design, "sofa").position is not None


def test_c_a_side_wall_sofa_sits_at_a_right_angle_to_the_tv() -> None:
    twin = room(objects=[TV], open_edges=[2])
    design = placed(twin, "lr_side_wall_tv")
    sofa = item(design, "sofa")
    assert sofa.position is not None
    # Against the left or right wall, so turned a quarter from the TV wall.
    assert min(sofa.position.x_m, W - sofa.position.x_m) < 0.6
    assert math.isclose(sofa.rotation_deg % 180, 90.0, abs_tol=1.0)


def test_d_smaller_seating_uses_a_two_seater_or_armchairs() -> None:
    twin = room(objects=[TV], unseen_edges=[1, 3], open_edges=[2])
    design = placed(twin, "lr_small_facing_tv")
    seats = [i for i in design.items if i.product.category in ("armchair", "loveseat")]
    assert seats and not any(i.product.category == "sofa" for i in design.items)


def test_e_a_refresh_keeps_the_seating_and_adds_around_it() -> None:
    sofa = kept("old-sofa", "sofa", 0.5, 2.0, 2.0, 0.9, on_floor=True)
    twin = room(objects=[TV, sofa], unseen_edges=[1], open_edges=[2])
    design = placed(twin, "lr_refresh", in_view=[(0.3, 0.2), (4.6, 0.2), (4.6, 3.5), (0.3, 3.5)])
    categories = {i.product.category for i in design.items}
    assert categories and not categories & {"sofa", "loveseat", "armchair", "accent_chair"}
    # The kept sofa is not removed or replaced.
    assert design.twin is not None
    touched = {getattr(e, "object_id", None) for e in design.twin.edits}
    assert "old-sofa" not in touched


def test_a_photo_room_steps_down_the_ladder_and_records_the_rung() -> None:
    # Only the TV wall was seen; the standard layouts have no wall for the sofa.
    twin = room(objects=[TV], unseen_edges=[1, 3], open_edges=[2])
    out = three_designs(
        twin,
        brief(twin, budget_rupees=300_000),
        list(living_kit().values()),
        uuid.uuid4(),
        WHEN,
        in_view=IN_VIEW,
    )
    for r in out:
        assert r.result.design is not None, r.result.honest
        assert r.result.design.layout_rung in FALLBACK_RUNGS
        assert r.result.design.measurement_level == "estimated"
    assert out[0].result.design is not None
    assert out[0].result.design.layout_rung == "floating_sofa"


def test_a_room_the_standard_layouts_furnish_records_standard() -> None:
    twin = room(objects=[TV])
    out = three_designs(
        twin,
        brief(twin, budget_rupees=300_000),
        list(living_kit().values()),
        uuid.uuid4(),
        WHEN,
        in_view=[(0.3, 0.2), (4.7, 0.2), (4.7, 3.8), (0.3, 3.8)],
    )
    assert all(r.result.design is not None for r in out)
    assert {r.result.design.layout_rung for r in out if r.result.design} == {"standard"}


def test_the_ladder_fails_only_when_not_even_a_refresh_fits_in_view() -> None:
    twin = room(objects=[TV], unseen_edges=[1, 3], open_edges=[2])
    sliver = [(2.3, 3.5), (2.7, 3.5), (2.7, 3.7), (2.3, 3.7)]
    out = three_designs(
        twin,
        brief(twin, budget_rupees=300_000),
        list(living_kit().values()),
        uuid.uuid4(),
        WHEN,
        in_view=sliver,
    )
    assert all(r.result.design is None for r in out)


def test_kept_seating_never_backs_onto_the_kept_tvs_wall() -> None:
    # A one-wall room: the only wall carries the TV, so the standard layouts fail.
    twin = room(objects=[TV], unseen_edges=[1, 2, 3])
    sofa_only = {"sofa": product("sofa", 2.0, 0.88, 0.85, key="s")}
    result = place(
        PlacementRequest(
            twin=twin,
            brief=brief(twin, budget_rupees=500_000),
            archetype="lr_short_wall",
            in_view=IN_VIEW,
            choices=[SlotChoice(slot="sofa", product=sofa_only["sofa"])],
            design_id=uuid.UUID(int=1),
            space_profile_id=uuid.UUID(int=2),
            created_at=WHEN,  # type: ignore[arg-type]
            walkway_m=0.75,
        )
    )
    assert result.design is None
