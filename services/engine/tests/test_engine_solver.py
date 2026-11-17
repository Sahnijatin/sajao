import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from sajao_engine.archetypes import ARCHETYPES, for_space
from sajao_engine.geometry import Rect, polygon_inside
from sajao_engine.room import high
from sajao_engine.solver import PlacementRequest, PlacementResult, SlotChoice, place
from sajao_engine.testing import (
    OpeningSpec,
    bedroom_kit,
    brief,
    fixture_rooms,
    living_kit,
    rect,
    sectional_kit,
    twin_from_polygon,
)
from sajao_engine.verifier import verify
from sajao_schemas import to_json_dict
from sajao_schemas.generated.v1 import AddEdit, Product, RedoArea, RemoveEdit, SpaceTwin

WHEN = datetime(2026, 1, 5, tzinfo=UTC)
ROOMS = fixture_rooms()
BUNDLE: dict[str, Any] = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "packages"
        / "schemas"
        / "generated"
        / "v1.schema.json"
    ).read_text()
)
DESIGN_SCHEMA = Draft202012Validator(
    {"$ref": "#/$defs/Design", "$defs": BUNDLE["$defs"]},
    format_checker=Draft202012Validator.FORMAT_CHECKER,
)


def kit_for(arch_key: str, room: str) -> dict[str, Product]:
    arch = ARCHETYPES[arch_key]
    if arch_key == "lr_corner_sectional":
        return sectional_kit()
    if arch.space == "living_room":
        return living_kit(small=room == "lr_1bhk_compact")
    return bedroom_kit(bed_width=1.2 if room == "br_small" else 1.6)


def request(twin: SpaceTwin, arch_key: str, kit: dict[str, Product], **kw: Any) -> PlacementRequest:
    slots = {s.key for s in ARCHETYPES[arch_key].slots}
    return PlacementRequest(
        twin=twin,
        brief=kw.pop("brief", None) or brief(twin, budget_rupees=500_000),
        archetype=arch_key,
        choices=[SlotChoice(slot=k, product=p) for k, p in kit.items() if k in slots],
        design_id=uuid.UUID(int=1),
        space_profile_id=uuid.UUID(int=2),
        created_at=WHEN,
        **kw,
    )


def assert_sound(req: PlacementRequest, result: PlacementResult) -> None:
    """A returned design passes the verifier again, validates, and was placed by code."""
    design = result.design
    assert design is not None
    assert design.check_report.passed
    again = verify(design, req.twin, req.brief, redo=req.redo, checked_at=WHEN)
    assert again.passed, again.violations
    errors = list(DESIGN_SCHEMA.iter_errors(to_json_dict(design)))
    assert not errors, errors[:3]
    assert all(item.placed_by == "solver" for item in design.items)
    assert design.twin is not None
    assert all(e.by == "solver" for e in design.twin.edits)
    assert design.total_cost.amount_minor == sum(i.product.price.amount_minor for i in design.items)


# Pairs that must keep passing. Rooms and archetypes not listed fail for reasons the
# relaxation order and the honest result handle (see test_engine_relax.py).
MUST_PASS = [
    ("lr_2bhk_hall", "lr_sofa_tv"),
    ("lr_2bhk_hall", "lr_short_wall"),
    ("lr_1bhk_compact", "lr_short_wall"),
    ("lr_3bhk_large", "lr_sofa_tv"),
    ("lr_3bhk_large", "lr_conversation"),
    ("lr_3bhk_large", "lr_corner_sectional"),
    ("lr_l_shape", "lr_sofa_tv"),
    ("lr_l_shape", "lr_diwan_lounge"),
    ("schema_fixture", "lr_sofa_tv"),
    ("br_master", "br_bed_centered"),
    ("br_master", "br_dresser_opposite"),
    ("br_standard", "br_bed_corner"),
    ("br_standard", "br_bed_study"),
]


@pytest.mark.parametrize(("room", "arch"), MUST_PASS)
def test_fixture_rooms_get_a_verified_design(room: str, arch: str) -> None:
    req = request(ROOMS[room], arch, kit_for(arch, room))
    result = place(req)
    assert_sound(req, result)
    required = {s.key for s in ARCHETYPES[arch].slots if s.required}
    assert required <= set(result.placed_slots)


def test_placement_is_deterministic() -> None:
    req = request(ROOMS["lr_2bhk_hall"], "lr_sofa_tv", living_kit())
    a, b = place(req), place(req)
    assert a.design is not None and b.design is not None
    assert to_json_dict(a.design) == to_json_dict(b.design)


def test_explanations_come_from_the_layout() -> None:
    result = place(request(ROOMS["lr_2bhk_hall"], "lr_sofa_tv", living_kit()))
    assert result.design is not None
    text = " ".join(e.root if hasattr(e, "root") else str(e) for e in result.design.explanations)
    assert "TV unit is" in text and "walkways of at least" in text


def test_kept_items_stay_and_are_avoided() -> None:
    twin = ROOMS["schema_fixture"]
    b = brief(twin, budget_rupees=500_000, keep=["almirah-1"])
    req = request(twin, "lr_sofa_tv", living_kit(), brief=b)
    result = place(req)
    assert_sound(req, result)
    assert result.design is not None and result.design.twin is not None
    removed = {e.object_id for e in result.design.twin.edits if isinstance(e, RemoveEdit)}
    assert "almirah-1" not in removed and "sofa-1" in removed


def test_just_a_part_places_new_items_only_inside_it() -> None:
    twin = ROOMS["lr_3bhk_large"]
    part = [
        {"x_m": 0.0, "y_m": 0.0},
        {"x_m": 4.25, "y_m": 0.0},
        {"x_m": 4.25, "y_m": 3.4},
        {"x_m": 0.0, "y_m": 3.4},
    ]
    redo = RedoArea.model_validate({"scope": "part", "polygon": part})
    req = request(twin, "lr_short_wall", living_kit(), redo=redo)
    result = place(req)
    assert_sound(req, result)
    assert result.design is not None
    poly = tuple((p["x_m"], p["y_m"]) for p in part)
    for item in result.design.items:
        d = item.product.dimensions
        fp = Rect(
            item.position.x_m, item.position.y_m, high(d.width), high(d.depth), item.rotation_deg
        )
        assert polygon_inside(fp.corners(), poly) or item.product.category in (
            "pendant_light",
            "ceiling_light",
        )


def test_every_archetype_is_for_a_launch_room() -> None:
    assert {a.space for a in ARCHETYPES.values()} == {"living_room", "bedroom"}
    assert len(for_space("living_room")) >= 8 and len(for_space("bedroom")) >= 8
    assert for_space("balcony") == ()


def test_wrong_room_type_is_refused() -> None:
    with pytest.raises(ValueError, match="bedroom"):
        place(request(ROOMS["br_master"], "lr_sofa_tv", living_kit()))


@st.composite
def random_rooms(draw: st.DrawFn) -> SpaceTwin:
    w = round(draw(st.floats(3.0, 5.0)), 2)
    d = round(draw(st.floats(3.4, 6.0)), 2)
    door_wall = draw(st.integers(0, 3))
    length = w if door_wall % 2 == 0 else d
    offset = round(draw(st.floats(0.05, length - 1.05)), 2)
    win_wall = (door_wall + draw(st.integers(1, 3))) % 4
    win_length = w if win_wall % 2 == 0 else d
    win_offset = round(draw(st.floats(0.2, max(0.21, win_length - 1.4))), 2)
    return twin_from_polygon(
        f"random-{w}-{d}-{door_wall}-{offset}-{win_wall}-{win_offset}",
        rect(w, d),
        openings=[
            OpeningSpec("door", "door", door_wall, offset, 0.9, "start", "inward"),
            OpeningSpec("win", "window", win_wall, win_offset, 1.2, sill=0.9),
        ],
        band=draw(st.sampled_from([0.01, 0.05, 0.10])),
    )


@given(random_rooms(), st.sampled_from(["lr_sofa_tv", "lr_short_wall", "lr_compact"]))
@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_the_solver_never_returns_a_design_that_fails(twin: SpaceTwin, arch: str) -> None:
    req = request(twin, arch, living_kit())
    result = place(req)
    if result.design is not None:
        assert_sound(req, result)
    else:
        assert result.unplaced_required or result.violations or not result.budget_ok


def test_add_edits_carry_catalog_sizes() -> None:
    result = place(request(ROOMS["br_master"], "br_bed_centered", bedroom_kit()))
    assert result.design is not None and result.design.twin is not None
    by_product = {str(i.product.id): i.product for i in result.design.items}
    for e in result.design.twin.edits:
        if isinstance(e, AddEdit):
            assert e.product_size.model_dump() == by_product[e.product_id].dimensions.model_dump()
