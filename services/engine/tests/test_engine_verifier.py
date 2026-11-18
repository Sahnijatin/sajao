import random
from datetime import UTC, datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sajao_engine.geometry import Rect, point_in_polygon
from sajao_engine.room import room_from_twin
from sajao_engine.testing import Pose, brief, design, fixture_rooms, product
from sajao_engine.verifier import HARD_RULES, Verification, verify, wall_gap
from sajao_schemas.generated.v1 import Design, RedoArea, SpaceTwin

WHEN = datetime(2026, 1, 5, tzinfo=UTC)
ROOMS = fixture_rooms()
HALL = ROOMS["lr_2bhk_hall"]

SOFA = product("sofa", 2.1, 0.9, 0.85, price_rupees=45_000)
TABLE = product("coffee_table", 1.0, 0.5, 0.42, price_rupees=9_000)
TV = product("tv_unit", 1.6, 0.4, 0.5, price_rupees=15_000)
GOOD = [
    Pose("sofa", SOFA, 1.6, 0.54, 0),
    Pose("table", TABLE, 1.6, 1.65, 0),
    Pose("tv", TV, 2.4, 4.31, 180),
]


def run(twin: SpaceTwin, poses: list[Pose], **kw: object) -> Verification:
    b = kw.pop("brief", None) or brief(twin)
    d = kw.pop("design", None) or design(twin, poses)
    assert isinstance(d, Design)
    return verify(d, twin, b, checked_at=WHEN, **kw)  # type: ignore[arg-type]


def failed(result: Verification) -> set[str]:
    return {r.rule for r in result.report.rules if r.kind == "hard" and not r.passed}


def test_a_sound_living_room_passes_every_rule() -> None:
    result = run(HALL, GOOD)
    assert result.passed, result.violations
    assert {r.rule for r in result.report.rules if r.kind == "hard"} == set(HARD_RULES)
    assert result.report.budget_ok and result.report.stock_ok


def test_collision_fails() -> None:
    result = run(HALL, [GOOD[0], Pose("table", TABLE, 1.6, 1.0, 0), GOOD[2]])
    assert "no_overlap" in failed(result)
    assert not result.passed


def test_item_in_door_swing_fails() -> None:
    chair = product("armchair", 0.7, 0.7, 0.8)
    result = run(HALL, [*GOOD, Pose("chair", chair, 0.5, 4.0, 270)])
    assert "door_clear" in failed(result)


def test_item_in_front_of_a_door_without_swing_fails() -> None:
    plant = product("plant", 0.4, 0.4, 1.2)
    result = run(HALL, [*GOOD, Pose("plant", plant, 3.05, 2.3)])
    assert "door_clear" in failed(result)


def test_rug_may_lie_in_a_doorway_but_not_under_a_swing() -> None:
    rug = product("rug", 1.6, 2.3, 0.01)
    ok = run(HALL, [*GOOD, Pose("rug", rug, 2.4, 2.3, 90)])
    assert "door_clear" not in failed(ok)
    swing = run(HALL, [*GOOD, Pose("rug", rug, 0.95, 3.8, 90)])
    assert "door_clear" in failed(swing)


def test_tall_item_under_a_window_fails_and_a_low_one_passes() -> None:
    tall = product("bookshelf", 1.0, 0.35, 1.8)
    low = product("sideboard", 1.0, 0.4, 0.8)
    assert "window_access" in failed(run(HALL, [*GOOD[:2], Pose("shelf", tall, 1.2, 4.335, 180)]))
    assert "window_access" not in failed(run(HALL, [*GOOD[:2], Pose("board", low, 1.2, 4.31, 180)]))


def test_tall_item_over_a_switchboard_fails() -> None:
    shelf = product("bookshelf", 0.8, 0.35, 1.8)
    assert "fixture_access" in failed(run(HALL, [*GOOD, Pose("shelf", shelf, 0.27, 3.0, 270)]))


def test_doors_cut_off_by_a_narrow_gap_fail() -> None:
    console = product("console_table", 2.76, 0.25, 0.8)
    result = run(HALL, [*GOOD, Pose("console", console, 1.47, 3.17, 0)])
    assert "walkway_min" in failed(result)


def test_too_close_to_a_wall_for_its_error_band_fails() -> None:
    result = run(HALL, [Pose("sofa", SOFA, 1.6, 0.50, 0), *GOOD[1:]])
    assert "inside_room" in failed(result)


def test_outside_the_room_fails() -> None:
    assert "inside_room" in failed(run(HALL, [Pose("sofa", SOFA, 1.6, -0.2, 0)]))


def test_seat_without_knee_room_fails() -> None:
    result = run(HALL, [GOOD[0], Pose("table", TABLE, 1.6, 1.25, 0), GOOD[2]])
    assert "front_clearance" in failed(result)


def test_wardrobe_needs_room_to_open() -> None:
    room = ROOMS["br_small"]
    wardrobe = product("wardrobe", 1.5, 0.6, 2.1)
    bed = product("bed", 1.6, 2.1, 0.9)
    blocked = run(
        room, [Pose("wardrobe", wardrobe, 1.0, 0.39, 0), Pose("bed", bed, 1.4, 1.95, 180)]
    )
    assert "front_clearance" in failed(blocked)


@pytest.mark.parametrize(("measured", "passes"), [(False, False), (True, True)])
def test_tight_spot_needs_a_measured_size(measured: bool, passes: bool) -> None:
    room = ROOMS["br_small"]
    wardrobe = product("wardrobe", 2.55, 0.6, 2.1, measured=measured, band=0.01)
    result = run(room, [Pose("wardrobe", wardrobe, 1.375, 0.39, 0)])
    assert ("tight_spots_measured" not in failed(result)) is passes


def test_budget_and_stock() -> None:
    over = run(HALL, GOOD, brief=brief(HALL, budget_rupees=60_000))
    assert not over.report.budget_ok and not over.passed
    stretch = run(HALL, GOOD, brief=brief(HALL, budget_rupees=63_000, flexibility="stretch_10"))
    assert stretch.report.budget_ok
    gone = product("sofa", 2.1, 0.9, 0.85, price_rupees=45_000, in_stock=False, key="gone")
    assert not run(HALL, [Pose("sofa", gone, 1.6, 0.54, 0)]).report.stock_ok


def test_total_must_match_the_items() -> None:
    d = design(HALL, GOOD)
    bad = d.model_copy(update={"total_cost": d.total_cost.model_copy(update={"amount_minor": 1})})
    assert "total_matches_items" in failed(run(HALL, GOOD, design=bad))


def test_twin_edits_must_match_the_items() -> None:
    d = design(HALL, GOOD)
    assert d.twin is not None
    edits = [e for e in d.twin.edits if getattr(e, "id", "") != "add-tv"]
    bad = d.model_copy(update={"twin": d.twin.model_copy(update={"edits": edits})})
    assert "twin_matches_items" in failed(run(HALL, GOOD, design=bad))
    moved = d.model_copy(
        update={
            "items": [d.items[0].model_copy(update={"position": d.items[1].position}), *d.items[1:]]
        }
    )
    assert "twin_matches_items" in failed(run(HALL, GOOD, design=moved))


def test_wall_art_must_not_cover_a_window() -> None:
    art = product("art", 1.0, 0.04, 0.7)
    on_window = run(HALL, [*GOOD, Pose("art", art, 1.2, 4.58, 180)])
    assert "wall_items_clear" in failed(on_window)
    above_sofa = run(HALL, [*GOOD, Pose("art", art, 1.6, 0.02, 0)])
    assert "wall_items_clear" not in failed(above_sofa)


def test_kept_items_are_obstacles() -> None:
    room = ROOMS["schema_fixture"]
    table = product("side_table", 0.5, 0.5, 0.5)
    # The almirah stays; a table placed on it fails.
    d = design(room, [Pose("t", table, 0.4, 3.0)], remove=["sofa-1"])
    assert "no_overlap" in failed(run(room, [], design=d))


def test_items_outside_the_redo_area_fail() -> None:
    redo = RedoArea.model_validate(
        {
            "scope": "part",
            "polygon": [
                {"x_m": 0, "y_m": 0},
                {"x_m": 3.35, "y_m": 0},
                {"x_m": 3.35, "y_m": 2},
                {"x_m": 0, "y_m": 2},
            ],
        }
    )
    result = run(HALL, GOOD, redo=redo)
    assert "inside_redo_area" in failed(result)
    assert any(v.item_ids == ("tv",) for v in result.violations)


# Property tests.

CATS = [
    "sofa",
    "armchair",
    "coffee_table",
    "side_table",
    "sideboard",
    "plant",
    "floor_lamp",
    "bookshelf",
]


@st.composite
def random_poses(draw: st.DrawFn) -> list[Pose]:
    n = draw(st.integers(1, 5))
    poses = []
    for i in range(n):
        cat = draw(st.sampled_from(CATS))
        w = draw(st.floats(0.3, 2.2))
        d = draw(st.floats(0.3, 1.0))
        h = draw(st.floats(0.3, 2.0))
        x = draw(st.floats(0.0, 3.35))
        y = draw(st.floats(0.0, 4.6))
        rot = draw(st.sampled_from([0.0, 90.0, 180.0, 270.0, 30.0]))
        poses.append(
            Pose(
                f"i{i}", product(cat, round(w, 2), round(d, 2), round(h, 2), key=f"p{i}"), x, y, rot
            )
        )
    return poses


# Three cells clear of every door, window and fixture zone in the hall, with a walkway between.
CELLS = [((0.1, 1.6), (0.1, 1.3)), ((1.75, 3.25), (0.1, 1.3)), ((0.1, 1.4), (1.9, 3.0))]
LOOSE = ["side_table", "plant", "floor_lamp", "coffee_table", "pouf"]


@st.composite
def layout_poses(draw: st.DrawFn) -> list[Pose]:
    """Items inside separate cells: mostly passing designs."""
    poses = []
    for i, ((x0, x1), (y0, y1)) in enumerate(CELLS[: draw(st.integers(1, 3))]):
        w = round(draw(st.floats(0.3, x1 - x0)), 2)
        d = round(draw(st.floats(0.3, y1 - y0)), 2)
        x = draw(st.floats(x0 + w / 2, max(x0 + w / 2, x1 - w / 2)))
        y = draw(st.floats(y0 + d / 2, max(y0 + d / 2, y1 - d / 2)))
        cat = draw(st.sampled_from(LOOSE))
        poses.append(
            Pose(
                f"c{i}",
                product(cat, w, d, 0.6, key=f"c{i}"),
                x,
                y,
                draw(st.sampled_from([0.0, 180.0])),
            )
        )
    return poses


def _footprint(p: Pose) -> Rect:
    dims = p.product.dimensions
    return Rect(
        p.x,
        p.y,
        dims.width.value_m + dims.width.error_band_m,
        dims.depth.value_m + dims.depth.error_band_m,
        p.rotation,
    )


@given(st.one_of(random_poses(), layout_poses()))
@settings(max_examples=60, deadline=None)
def test_a_passing_design_has_no_overlap_and_stays_inside(poses: list[Pose]) -> None:
    result = run(HALL, poses)
    if not result.passed:
        return
    room = room_from_twin(HALL)
    rng = random.Random(1)  # noqa: S311
    rects = [_footprint(p).grown(-1e-3) for p in poses]
    for i, r in enumerate(rects):
        for _ in range(300):
            u, v = rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5)
            ux, uy = r.axis_x
            fx, fy = r.front
            pt = (
                r.cx + ux * u * r.width + fx * v * r.depth,
                r.cy + uy * u * r.width + fy * v * r.depth,
            )
            assert point_in_polygon(pt, room.floor)
            for other in rects[i + 1 :]:
                assert not point_in_polygon(pt, other.corners())
        for w in room.walls:
            assert wall_gap(r.corners(), w) >= w.margin_m - 2e-3


@given(random_poses(), st.integers(0, 4))
@settings(max_examples=30, deadline=None)
def test_a_collision_never_passes(poses: list[Pose], k: int) -> None:
    p = poses[k % len(poses)]
    twin = Pose("twin-of-" + p.item_id, p.product, p.x + 0.01, p.y, p.rotation)
    assert not run(HALL, [*poses, twin]).passed


@given(random_poses(), st.floats(0.15, 0.85), st.floats(3.55, 4.4))
@settings(max_examples=30, deadline=None)
def test_a_blocked_door_never_passes(poses: list[Pose], x: float, y: float) -> None:
    box = product("side_table", 0.3, 0.3, 0.5, key="blocker")
    result = run(HALL, [*poses, Pose("blocker", box, x, y)])
    assert not result.passed
    assert "door_clear" in failed(result) or "inside_room" in failed(result)


@given(st.floats(0.20, 0.58))
@settings(max_examples=25, deadline=None)
def test_a_narrow_walkway_never_passes(gap: float) -> None:
    # A console across the room leaves ``gap`` to the right wall's band; the doors are cut off.
    right_margin = room_from_twin(HALL).wall_by_id["w2"].margin_m
    length = 3.35 - right_margin - gap - 0.085
    console = product("console_table", round(length, 3), 0.25, 0.8, key="console")
    result = run(HALL, [*GOOD, Pose("console", console, 0.085 + (length + 0.01) / 2, 3.17, 0)])
    assert "walkway_min" in failed(result)


@given(st.floats(0.80, 1.0))
@settings(max_examples=10, deadline=None)
def test_a_wide_walkway_passes(gap: float) -> None:
    right_margin = room_from_twin(HALL).wall_by_id["w2"].margin_m
    length = 3.35 - right_margin - gap - 0.085
    console = product("console_table", round(length, 3), 0.25, 0.8, key="console")
    result = run(HALL, [*GOOD, Pose("console", console, 0.085 + (length + 0.01) / 2, 3.17, 0)])
    assert "walkway_min" not in failed(result), result.violations


@given(random_poses())
@settings(max_examples=10, deadline=None)
def test_the_verifier_is_deterministic(poses: list[Pose]) -> None:
    a, b = run(HALL, poses), run(HALL, poses)
    assert a.report == b.report and a.violations == b.violations
