"""Any room shape: floor polygons whose edges are walls or open (SJ-SCOPE-31)."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sajao_engine.archetypes import ARCHETYPES
from sajao_engine.categories import category
from sajao_engine.geometry import Rect
from sajao_engine.room import room_from_twin
from sajao_engine.solver import PlacementRequest, PlacementResult, SlotChoice, place
from sajao_engine.testing import (
    OpeningSpec,
    Pose,
    bedroom_kit,
    brief,
    design,
    living_kit,
    open_plan_rooms,
    product,
    rect,
    twin_from_polygon,
)
from sajao_engine.verifier import verify, wall_gap
from sajao_schemas.generated.v1 import MeasurementConfidence, Product, SpaceTwin

WHEN = datetime(2026, 1, 5, tzinfo=UTC)
OPEN = open_plan_rooms()


def request(twin: SpaceTwin, arch: str, kit: dict[str, Product], **kw: Any) -> PlacementRequest:
    slots = {s.key for s in ARCHETYPES[arch].slots}
    return PlacementRequest(
        twin=twin,
        brief=brief(twin, budget_rupees=500_000),
        archetype=arch,
        choices=[SlotChoice(slot=k, product=p) for k, p in kit.items() if k in slots],
        design_id=uuid.UUID(int=1),
        space_profile_id=uuid.UUID(int=2),
        created_at=WHEN,
        **kw,
    )


def no_back_on_an_open_edge(twin: SpaceTwin, result: PlacementResult) -> None:
    """Every wall-backed piece has a real wall behind it, never just an open edge."""
    assert result.design is not None
    room = room_from_twin(twin)
    for item in result.design.items:
        cat = category(item.product.category)
        if not cat.wall_backed:
            continue
        d = item.product.dimensions
        fp = Rect(
            item.position.x_m,
            item.position.y_m,
            d.width.value_m + d.width.error_band_m,
            d.depth.value_m + d.depth.error_band_m,
            item.rotation_deg,
        )
        back = fp.strip("back", 0.02).corners()
        assert any(wall_gap(back, w) <= w.margin_m + 0.01 for w in room.walls), item.id


def test_open_edges_are_read_from_the_walls_the_scan_found() -> None:
    plan = room_from_twin(OPEN["lr_open_plan"])
    assert len(plan.walls) == 3 and len(plan.open_edges) == 1
    arch = room_from_twin(OPEN["lr_archway"])
    (edge,) = arch.open_edges
    assert edge.length == pytest.approx(1.4) and edge.passable
    assert not room_from_twin(OPEN["br_l_shape"]).open_edges


@pytest.mark.parametrize(
    ("room", "arch"),
    [
        ("lr_open_plan", "lr_sofa_tv"),
        ("lr_open_plan", "lr_conversation"),
        ("lr_open_l", "lr_sofa_tv"),
        ("lr_open_l", "lr_reading_wall"),
        ("lr_archway", "lr_conversation"),
        ("br_l_shape", "br_bed_corner"),
        ("br_l_shape", "br_bed_study"),
    ],
)
def test_open_plan_and_l_shaped_rooms_get_verified_designs(room: str, arch: str) -> None:
    twin = OPEN[room]
    kit = bedroom_kit() if ARCHETYPES[arch].space == "bedroom" else living_kit()
    req = request(twin, arch, kit)
    result = place(req)
    assert result.design is not None, (result.unplaced_required, result.violations)
    assert verify(result.design, twin, req.brief, checked_at=WHEN).passed
    no_back_on_an_open_edge(twin, result)


def test_wall_items_never_hang_on_an_open_edge() -> None:
    twin = OPEN["lr_open_plan"]
    art = product("art", 1.0, 0.04, 0.7)
    result = verify(
        design(twin, [Pose("art", art, 2.0, 4.5, 180)]), twin, brief(twin), checked_at=WHEN
    )
    assert any(v.rule == "wall_items_clear" for v in result.violations)


def test_an_open_edge_is_passable_and_must_stay_reachable() -> None:
    twin = OPEN["lr_open_plan"]
    sofa = product("sofa", 2.0, 0.88, 0.85, key="sofa")
    ok = verify(
        design(twin, [Pose("sofa", sofa, 2.6, 0.55, 0)]), twin, brief(twin), checked_at=WHEN
    )
    assert ok.passed, ok.violations
    # A row of sideboards along the whole open side cuts the dining area off.
    board = product("sideboard", 1.9, 0.45, 0.8, key="board")
    wall = [Pose("b1", board, 1.05, 3.8, 180), Pose("b2", board, 2.97, 3.8, 180)]
    cut = verify(design(twin, wall), twin, brief(twin), checked_at=WHEN)
    assert any(v.rule == "walkway_min" for v in cut.violations)


def test_items_stay_in_the_area_by_the_open_edge_band() -> None:
    twin = OPEN["lr_open_plan"]
    table = product("side_table", 0.5, 0.5, 0.5, key="t")
    over = verify(design(twin, [Pose("t", table, 2.0, 4.33)]), twin, brief(twin), checked_at=WHEN)
    assert any(v.rule == "inside_room" and "open edge" in v.detail for v in over.violations)


def test_an_open_edge_does_not_make_a_tight_spot() -> None:
    # A shelf between a wall and the open edge is not boxed in: the floor runs on.
    twin = OPEN["lr_open_plan"]
    shelf = product("bookshelf", 0.8, 0.35, 1.8, measured=False, key="shelf")
    result = verify(
        design(twin, [Pose("s", shelf, 3.7, 4.10, 270)]), twin, brief(twin), checked_at=WHEN
    )
    assert not any(v.rule == "tight_spots_measured" for v in result.violations)


# Fit claims by confidence level.


def test_an_estimated_room_never_claims_a_fit() -> None:
    twin = OPEN["lr_open_l"]
    result = place(request(twin, "lr_sofa_tv", living_kit()))
    assert result.design is not None
    assert not result.fit_claims and result.item_fits == {}
    text = " ".join(str(e.root) for e in result.design.explanations)
    assert "measure the room to confirm" in text
    assert "fits with" not in text.lower()


def test_a_taped_room_claims_fits_from_the_verifier() -> None:
    corners = [(0.0, 0.0), (5.5, 0.0), (5.5, 3.2), (3.2, 3.2), (3.2, 6.0), (0.0, 6.0)]
    twin = twin_from_polygon(
        "taped_l",
        corners,
        openings=[OpeningSpec("main", "door", 0, 0.2, 1.0, "start", "inward")],
        open_edges=[4],
        measured=True,
    )
    assert room_from_twin(twin).confidence == "taped"
    result = place(request(twin, "lr_sofa_tv", living_kit()))
    assert result.design is not None and result.fit_claims
    floor_items = {
        i.id for i in result.design.items if category(i.product.category).mount == "floor"
    }
    assert set(result.item_fits) == floor_items
    assert all(f.status in ("fits", "tight") and f.spare_m >= 0 for f in result.item_fits.values())


def test_an_ar_measured_level_passed_in_allows_fit_claims() -> None:
    twin = OPEN["lr_open_plan"]
    result = place(request(twin, "lr_sofa_tv", living_kit(), confidence="ar_measured"))
    assert result.design is not None and result.fit_claims and result.item_fits


@st.composite
def l_rooms(draw: st.DrawFn) -> SpaceTwin:
    """Random L-shaped areas, sometimes with one side open to the next area."""
    w = round(draw(st.floats(4.0, 6.0)), 2)
    d = round(draw(st.floats(4.0, 6.5)), 2)
    cw = round(draw(st.floats(1.0, w - 2.8)), 2)
    cd = round(draw(st.floats(1.0, d - 3.0)), 2)
    corners = [(0.0, 0.0), (w, 0.0), (w, d - cd), (w - cw, d - cd), (w - cw, d), (0.0, d)]
    open_edge = draw(st.sampled_from([None, 1, 2, 3, 4, 5]))
    door_wall = 0 if open_edge != 0 else 5
    return twin_from_polygon(
        f"l-{w}-{d}-{cw}-{cd}-{open_edge}",
        corners,
        openings=[OpeningSpec("main", "door", door_wall, 0.2, 0.95, "start", "inward")],
        open_edges=[] if open_edge is None else [open_edge],
        band=draw(st.sampled_from([0.02, 0.08])),
    )


@given(l_rooms(), st.sampled_from(["lr_sofa_tv", "lr_conversation", "lr_short_wall"]))
@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_l_rooms_never_get_a_design_that_fails_or_backs_onto_an_open_edge(
    twin: SpaceTwin, arch: str
) -> None:
    req = request(twin, arch, living_kit())
    result = place(req)
    if result.design is None:
        assert result.unplaced_required or result.violations
        return
    assert verify(result.design, twin, req.brief, checked_at=WHEN).passed
    no_back_on_an_open_edge(twin, result)


def test_a_partial_scan_with_one_wall_is_still_a_room() -> None:
    # One wall seen; the rest of the floor edge is open (a corner of a bigger space).
    twin = twin_from_polygon(
        "one_wall",
        rect(3.5, 3.0),
        openings=[],
        open_edges=[1, 2, 3],
    )
    room = room_from_twin(twin)
    assert len(room.walls) == 1 and len(room.open_edges) == 3
    result = place(request(twin, "lr_short_wall", living_kit()))
    assert result.design is not None, (result.unplaced_required, result.violations)
    no_back_on_an_open_edge(twin, result)


@pytest.mark.parametrize("level", ["taped", "ar_measured", "estimated"])
def test_room_reads_the_twins_own_confidence_level(level: str) -> None:
    twin = twin_from_polygon(
        "level",
        rect(4.0, 3.5),
        openings=[OpeningSpec("d1", "door", 0, 0.5, 0.9, "start", "inward")],
    )
    basis = {"taped": "tape", "ar_measured": "ar_planes", "estimated": "depth_model"}[level]
    twin = twin.model_copy(
        update={"confidence": MeasurementConfidence(level=level, basis=basis)}  # type: ignore[arg-type]
    )
    room = room_from_twin(twin)
    assert room.confidence == level
    assert room.fit_claims == (level != "estimated")
