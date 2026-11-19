"""Photo-first rooms: open edges by kind, keep or replace, floor-free objects, the floor a
photo shows, and three designs that stay in it."""

import math
import uuid
from typing import Any

import pytest

from sajao_engine.geometry import ccw, clip_convex, point_in_polygon, polygon_area
from sajao_engine.intents import distinct, three_designs
from sajao_engine.photo import visible_floor
from sajao_engine.room import room_from_twin
from sajao_engine.solver import removed_objects
from sajao_engine.testing import OpeningSpec, brief, living_kit, rect, twin_from_polygon
from sajao_schemas.generated.v1 import SpaceTwin

WHEN = "2026-11-19T00:00:00Z"


def room_twin(**kw: Any) -> SpaceTwin:
    return twin_from_polygon(
        "photo",
        rect(5.0, 4.0),
        openings=[OpeningSpec("d1", "door", 3, 0.4, 0.9, "start", "inward")],
        **kw,
    )


def with_open_wall(twin: SpaceTwin, index: int) -> SpaceTwin:
    data = twin.model_dump(mode="json", exclude_unset=True)
    data["shell"]["walls"][index]["kind"] = "open"
    data["shell"]["openings"] = [
        o for o in data["shell"]["openings"] if o["wall_id"] != data["shell"]["walls"][index]["id"]
    ]
    return SpaceTwin.model_validate(data)


def with_camera(
    twin: SpaceTwin, at: tuple[float, float, float], yaw_deg: float, tilt_deg: float
) -> SpaceTwin:
    """One keyframe at `at` (space frame, z up) looking along `yaw_deg` from +x, tilted
    down by `tilt_deg`; it is the hero view."""
    yaw, tilt = math.radians(yaw_deg), math.radians(tilt_deg)
    forward = (math.cos(yaw) * math.cos(tilt), math.sin(yaw) * math.cos(tilt), -math.sin(tilt))
    right = (math.sin(yaw), -math.cos(yaw), 0.0)
    down = (
        forward[1] * right[2] - forward[2] * right[1],
        forward[2] * right[0] - forward[0] * right[2],
        forward[0] * right[1] - forward[1] * right[0],
    )
    # Columns: camera x (right), y (down), z (forward) in the space frame.
    m = [[right[i], down[i], forward[i]] for i in range(3)]
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        s = 2 * math.sqrt(tr + 1)
        q = [(m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, s / 4]
    else:
        i = max(range(3), key=lambda k: m[k][k])
        j, k = (i + 1) % 3, (i + 2) % 3
        s = 2 * math.sqrt(1 + m[i][i] - m[j][j] - m[k][k])
        q = [0.0, 0.0, 0.0, (m[k][j] - m[j][k]) / s]
        q[i], q[j], q[k] = s / 4, (m[j][i] + m[i][j]) / s, (m[k][i] + m[i][k]) / s
    data = twin.model_dump(mode="json", exclude_unset=True)
    data["keyframes"] = [
        {
            "id": "k0",
            "image": "twins/k0.jpg",
            "captured_at_ms": 0,
            "pose": {"position": {"x_m": at[0], "y_m": at[1], "z_m": at[2]}, "rotation": q},
            "intrinsics": {
                "fx": 900.0,
                "fy": 900.0,
                "cx": 640.0,
                "cy": 480.0,
                "width_px": 1280,
                "height_px": 960,
            },
        }
    ]
    data.pop("viewing", None)
    return SpaceTwin.model_validate(data)


def test_an_edge_marked_open_is_an_open_edge_not_a_wall() -> None:
    twin = with_open_wall(room_twin(), 1)
    room = room_from_twin(twin)
    assert "w2" not in {w.id for w in room.walls}
    assert len(room.open_edges) == 1


def test_each_objects_own_keep_or_replace_decides_what_goes() -> None:
    twin = room_twin(
        objects=[
            _object("o1", "sofa", "furniture", "keep"),
            _object("o2", "armchair", "furniture", "replace"),
            _object("o3", "fan", "fixture", "replace"),
            _object("o4", "table", "furniture", None),
        ]
    )
    gone = removed_objects(twin, brief(twin))
    assert gone == ["o2", "o3", "o4"]
    assert removed_objects(twin, brief(twin, keep=["o2"])) == ["o3", "o4"]


def test_a_kept_thing_off_the_floor_does_not_block_it() -> None:
    twin = room_twin(
        objects=[
            _object("lamp", "chandelier", "fixture", "keep", on_floor=False),
            _object("chest", "chest_of_drawers", "furniture", "keep"),
        ]
    )
    room = room_from_twin(twin)
    assert [o.id for o in room.obstacles] == ["chest"]


def test_the_floor_a_photo_shows() -> None:
    # Standing at the middle of one short wall, looking across the room, 15 degrees down.
    twin = with_camera(room_twin(), (0.2, 2.0, 1.4), 0.0, 15.0)
    seen = visible_floor(twin)
    assert seen is not None
    poly = ccw(seen)
    # The far wall's middle is in view; the floor at the camera's feet and behind it is not.
    assert point_in_polygon((4.5, 2.0), poly)
    assert not point_in_polygon((0.3, 2.0), poly)
    assert 3.0 < polygon_area(poly) < 20.0


def test_a_photo_of_the_ceiling_shows_no_floor() -> None:
    twin = with_camera(room_twin(), (2.5, 2.0, 1.4), 0.0, -60.0)
    assert visible_floor(twin) is None


def test_three_designs_keep_new_items_where_the_photo_shows_them() -> None:
    twin = with_camera(with_open_wall(room_twin(), 3), (0.3, 2.0, 1.4), 0.0, 12.0)
    view = ccw(visible_floor(twin) or [])
    kit = living_kit()
    out = three_designs(
        twin,
        brief(twin, budget_rupees=200_000),
        list(kit.values()),
        uuid.uuid4(),
        WHEN,
        in_view=list(view),
    )
    assert [r.intent for r in out] == ["best_match", "best_value", "bold"]
    for r in out:
        design = r.result.design
        assert design is not None, r.result.honest
        assert design.measurement_level == "estimated"
        # No gap or spare-space claim on an estimated room; the walkway rule may be stated.
        assert not any(
            "to spare" in str(e.root) or "cm in front" in str(e.root) for e in design.explanations
        )
        for item in design.items:
            if item.position is not None and item.product.category in (
                "sofa",
                "coffee_table",
                "armchair",
            ):
                assert point_in_polygon((item.position.x_m, item.position.y_m), view)


def test_designs_differ_by_archetype_or_half_the_large_pieces() -> None:
    twin = room_twin()
    out = three_designs(
        twin, brief(twin, budget_rupees=300_000), list(living_kit().values()), uuid.uuid4(), WHEN
    )
    match, value, bold = (r.result.design for r in out)
    assert match is not None and bold is not None and value is not None
    assert distinct(match, match) is False
    assert out[2].distinct == distinct(bold, match)


def test_clip_convex_keeps_the_overlap() -> None:
    square = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    shifted = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
    assert polygon_area(clip_convex(shifted, square)) == pytest.approx(1.0)


def _object(
    oid: str, category: str, kind: str, state: str | None, on_floor: bool = True
) -> dict[str, Any]:
    dim = {"value_m": 0.8, "source": "estimated", "error_band_m": 0.05}
    obj: dict[str, Any] = {
        "id": oid,
        "category": category,
        "label": category.title(),
        "object_type": kind,
        "box": {
            "center": {"x_m": 2.5, "y_m": 2.0, "z_m": 0.4},
            "width": dim,
            "depth": dim,
            "height": dim,
            "yaw_deg": 0.0,
        },
        "views": [],
        "catalog_matches": [],
        "state": "keep",
        "detection": {"source": "server_segmentation", "confidence": 0.9},
        "footprint": {
            "polygon": [
                {"x_m": 2.1, "y_m": 1.6},
                {"x_m": 2.9, "y_m": 1.6},
                {"x_m": 2.9, "y_m": 2.4},
                {"x_m": 2.1, "y_m": 2.4},
            ],
            "width": dim,
            "depth": dim,
            "on_floor": on_floor,
        },
    }
    if state is not None:
        obj["redesign"] = {"state": state, "source": "rule"}
    return obj


def test_picked_styles_come_first_within_the_intent() -> None:
    from sajao_engine import archetypes as A
    from sajao_engine.intents import slot_options

    kit = living_kit()
    sofas = [p for p in kit.values() if p.category == "sofa"]
    assert sofas
    tagged = sofas[0].model_copy(update={"style_tags": ["japandi"], "id": uuid.uuid4()})
    plain = sofas[0].model_copy(update={"style_tags": [], "id": uuid.uuid4()})
    arch = A.ARCHETYPES["lr_sofa_tv"]
    picked = slot_options(arch, [plain, tagged], 30_000_000, "best_value", styles=["japandi"])
    sofa_slot = next(o for o in picked if o.slot == "sofa")
    assert sofa_slot.products[0].id == tagged.id
    neutral = slot_options(arch, [plain, tagged], 30_000_000, "best_value")
    assert {p.id for p in next(o for o in neutral if o.slot == "sofa").products} == {
        plain.id,
        tagged.id,
    }
