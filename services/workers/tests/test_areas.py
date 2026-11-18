"""A capture through several spaces is split into areas at doorway-width constrictions."""

import math
from typing import Any

import pytest

from sajao_workers.areas import split_areas


def poly(*points: tuple[float, float]) -> list[dict[str, float]]:
    return [{"x_m": x, "y_m": y} for x, y in points]


def area_of(points: list[dict[str, float]]) -> float:
    pts = [(p["x_m"], p["y_m"]) for p in points]
    return (
        abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1], strict=True))) / 2
    )


# Two 4 by 4 m rooms side by side, joined by a 0.9 m doorway through a 0.15 m wall.
TWO_ROOMS = poly(
    (0, 0), (4, 0), (4, 1.5), (4.15, 1.5), (4.15, 0), (8.15, 0),
    (8.15, 4), (4.15, 4), (4.15, 2.4), (4, 2.4), (4, 4), (0, 4),
)  # fmt: skip

# An open-plan L: 6 by 6 m with a 3 by 3 m bite out of one corner (arms 3 m wide).
L_SHAPE = poly((0, 0), (6, 0), (6, 3), (3, 3), (3, 6), (0, 6))


def camera(
    name: str, x: float, y: float, facing_deg: float, sharpness: float = 100
) -> dict[str, Any]:
    a = math.radians(facing_deg)
    return {"id": name, "x_m": x, "y_m": y, "forward": [math.cos(a), math.sin(a)],
            "sharpness": sharpness}  # fmt: skip


def test_two_rooms_joined_by_a_doorway_are_two_areas() -> None:
    out = split_areas(TWO_ROOMS)

    assert len(out["areas"]) == 2
    areas = sorted(area_of(a["floor_polygon"]) for a in out["areas"])
    assert areas[0] == pytest.approx(16.0, abs=0.2) and areas[1] == pytest.approx(16.0, abs=0.4)
    assert len(out["splits"]) == 1
    assert out["splits"][0]["width_m"] == pytest.approx(0.9, abs=0.01)


def test_an_open_plan_l_stays_one_area() -> None:
    out = split_areas(L_SHAPE)
    assert len(out["areas"]) == 1
    assert area_of(out["areas"][0]["floor_polygon"]) == pytest.approx(27.0)
    assert out["splits"] == []


def test_a_shallow_nook_behind_a_narrow_opening_is_not_an_area() -> None:
    # A 4 by 4 room with a 0.8 m wide, 0.6 m deep niche in one wall.
    room = poly((0, 0), (4, 0), (4, 1.6), (4.6, 1.6), (4.6, 2.4), (4, 2.4), (4, 4), (0, 4))
    assert len(split_areas(room)["areas"]) == 1


def test_three_rooms_in_a_row_are_three_areas() -> None:
    row = poly(
        (0, 0), (3, 0), (3, 1), (4, 1), (4, 0), (7, 0), (7, 1), (8, 1), (8, 0), (11, 0),
        (11, 3), (8, 3), (8, 2), (7, 2), (7, 3), (4, 3), (4, 2), (3, 2), (3, 3), (0, 3),
    )  # fmt: skip
    out = split_areas(row)
    assert len(out["areas"]) == 3
    assert [round(s["width_m"], 2) for s in out["splits"]] == [1.0, 1.0]


def test_objects_and_photos_go_to_the_area_they_are_in() -> None:
    objects = [
        {"id": "sofa", "x_m": 2.0, "y_m": 2.0},
        {"id": "bed", "x_m": 6.0, "y_m": 2.0},
        {"id": "outside", "x_m": 20.0, "y_m": 2.0},
    ]
    cameras = [
        camera("k1", 0.5, 0.5, 45),  # in the left room, looking across it
        camera("k2", 3.8, 2.0, 0),  # in the left room, looking through the door
        camera("k3", 7.8, 3.6, 225),  # in the right room, looking across it
        camera("k4", 2.0, 2.0, 90, sharpness=500),  # left room, sharp, but facing a wall close by
    ]

    out = split_areas(TWO_ROOMS, objects, cameras)

    left, right = sorted(out["areas"], key=lambda a: min(p["x_m"] for p in a["floor_polygon"]))
    assert left["object_ids"] == ["sofa"] and right["object_ids"] == ["bed"]
    assert out["unassigned_object_ids"] == ["outside"]
    assert sorted(left["keyframe_ids"]) == ["k1", "k2", "k4"]
    assert right["keyframe_ids"] == ["k3"]
    assert left["photo_keyframe_id"] == "k1"
    assert right["photo_keyframe_id"] == "k3"


def test_every_area_has_an_id_and_its_floor_area() -> None:
    out = split_areas(TWO_ROOMS)
    assert [a["id"] for a in out["areas"]] == ["a1", "a2"]
    for a in out["areas"]:
        assert a["floor_area_m2"] == pytest.approx(area_of(a["floor_polygon"]), abs=0.01)
        assert a["photo_keyframe_id"] is None  # no cameras given


def test_a_polygon_in_either_winding_gives_the_same_split() -> None:
    assert len(split_areas(list(reversed(TWO_ROOMS)))["areas"]) == 2


def test_too_few_points_is_refused() -> None:
    with pytest.raises(ValueError):
        split_areas(poly((0, 0), (1, 0)))


def test_an_outline_that_crosses_itself_is_refused() -> None:
    bow_tie = poly((0, 0), (4, 4), (4, 0), (0, 4))
    with pytest.raises(ValueError, match="crosses itself"):
        split_areas(bow_tie)
