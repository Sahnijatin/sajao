import math
from typing import Any

from sajao_workers.ar_shell import measured_shell
from sajao_workers.plane_fixtures import FLOOR_Y, HEIGHT, horizontal, vertical

FULL = (0.0, HEIGHT)  # a wall patch from the floor to the ceiling


def wall(centre: tuple[float, float], facing: float, wide: float, **kw: Any) -> dict[str, Any]:
    bottom, top = kw.get("span", FULL)
    return vertical(centre, facing, wide, bottom, top, kw.get("classification", "wall"))


def doc(*planes: dict[str, Any], size: tuple[float, float] = (4.0, 3.0)) -> dict[str, Any]:
    floor = horizontal((size[0] / 2, size[1] / 2), size, FLOOR_Y, classification="floor")
    ceiling = horizontal(
        (size[0] / 2, size[1] / 2), (2.0, 2.0), FLOOR_Y + HEIGHT, "horizontal_down", "ceiling"
    )
    return {"format": "sajao-planes-1", "planes": [floor, ceiling, *planes]}


# A 4 by 3 m room: one patch of each wall, short of every corner.
BOX = [
    wall((2.0, 0.0), 90, 3.2),
    wall((4.0, 1.5), 180, 2.4),
    wall((2.0, 3.0), -90, 3.4),
    wall((0.0, 1.5), 0, 2.2),
]
INSIDE = [(2.0, 1.5), (1.5, 1.2), (2.5, 1.8)]


def lengths(shell: dict[str, Any], kind: str = "wall") -> list[float]:
    return sorted(round(e["length"]["value_m"], 2) for e in shell["edges"] if e["kind"] == kind)


def test_a_box_room_closes_corner_to_corner_with_every_length_a_dimension() -> None:
    shell = measured_shell(doc(*BOX), INSIDE)
    assert shell["closed"] is True
    assert lengths(shell) == [3.0, 3.0, 4.0, 4.0]
    assert shell["floor_area_m2"] == 12.0
    assert len(shell["floor_polygon"]) == 4
    for edge in shell["edges"]:
        assert edge["basis"] == "corner_to_corner"
        assert edge["length"]["source"] == "estimated"
        assert edge["length"]["error_band_m"] >= 0.05
    assert shell["ceiling_height"]["value_m"] == HEIGHT


def test_an_l_shaped_room_keeps_its_six_walls() -> None:
    # 5 by 4 m with a 2 by 2 m bite out of one corner.
    planes = [
        wall((2.5, 0.0), 90, 4.0),
        wall((5.0, 1.0), 180, 1.4),
        wall((4.0, 2.0), -90, 1.4),
        wall((3.0, 3.0), 180, 1.4),
        wall((1.5, 4.0), -90, 2.4),
        wall((0.0, 2.0), 0, 3.0),
    ]
    shell = measured_shell(doc(*planes, size=(5.0, 4.0)), [(1.5, 2.0), (2.0, 1.0), (4.0, 1.0)])
    assert shell["closed"] is True
    assert lengths(shell) == [2.0, 2.0, 2.0, 3.0, 4.0, 5.0]
    assert shell["floor_area_m2"] == 16.0


def test_a_missing_wall_is_an_open_edge_not_a_guess() -> None:
    # Three walls seen; the fourth side opens into the next area.
    shell = measured_shell(doc(*BOX[:3]), INSIDE)
    assert shell["closed"] is False
    assert lengths(shell, "open") == [3.0]
    kinds = [e["kind"] for e in shell["edges"]]
    assert kinds.count("wall") == 3 and kinds.count("open") == 1
    # The walls that end at the opening are only known as far as they were seen.
    assert sorted(e["basis"] for e in shell["edges"] if e["kind"] == "wall") == [
        "corner_to_corner",
        "seen",
        "seen",
    ]
    assert any("open" in note for note in shell["notes"])


def test_furniture_planes_are_not_walls() -> None:
    fridge_side = wall((1.0, 1.0), 0, 0.8, span=(0.0, 1.8), classification="none")
    cabinet_front = wall((3.0, 2.4), -90, 1.6, span=(0.9, 2.3), classification="none")
    shell = measured_shell(doc(*BOX, fridge_side, cabinet_front), INSIDE)
    assert lengths(shell) == [3.0, 3.0, 4.0, 4.0]
    assert shell["dropped"]["not_floor_to_ceiling"] == 2


def test_planes_of_inventory_objects_are_dropped_by_the_callers_function() -> None:
    wardrobe = wall((2.0, 2.4), -90, 1.8, classification="none")  # floor to ceiling
    with_it = measured_shell(doc(*BOX, wardrobe), INSIDE)
    assert len([e for e in with_it["edges"] if e["kind"] == "wall"]) == 5

    def drop(planes: Any) -> Any:
        return [p for p in planes if not (abs(p.centre[2] - 2.4) < 0.01)]

    without = measured_shell(doc(*BOX, wardrobe), INSIDE, drop)
    assert lengths(without) == [3.0, 3.0, 4.0, 4.0]
    assert without["dropped"]["object_planes"] == 1


def test_patches_of_one_wall_join_across_a_doorway_and_whichever_way_they_face() -> None:
    planes = [
        wall((0.9, 0.0), 90, 1.4),
        wall((3.2, 0.0), -90, 1.2),  # same wall, 0.9 m doorway between, facing away
        *BOX[1:],
    ]
    shell = measured_shell(doc(*planes), INSIDE)
    assert shell["closed"] is True
    assert lengths(shell) == [3.0, 3.0, 4.0, 4.0]


def test_a_wall_seen_only_at_the_top_or_only_at_the_bottom_still_counts_when_joined() -> None:
    low = wall((1.0, 0.0), 90, 1.6, span=(0.0, 1.2))
    high = wall((2.6, 0.0), 90, 1.6, span=(1.4, HEIGHT))
    shell = measured_shell(doc(low, high, *BOX[1:]), INSIDE)
    assert lengths(shell) == [3.0, 3.0, 4.0, 4.0]


def test_no_planes_and_no_walls_say_so() -> None:
    assert measured_shell({"format": "sajao-planes-1", "planes": []})["floor_polygon"] is None
    short = wall((2.0, 0.0), 90, 3.0, span=(0.0, 1.0))
    shell = measured_shell(doc(short), INSIDE)
    assert shell["floor_polygon"] is None
    assert any("No wall" in note for note in shell["notes"])


def test_the_plan_is_the_ar_world_seen_from_above() -> None:
    shell = measured_shell(doc(*BOX), INSIDE)
    xs = [p["x_m"] for p in shell["floor_polygon"]]
    ys = [p["y_m"] for p in shell["floor_polygon"]]
    assert math.isclose(max(xs) - min(xs), 4.0, abs_tol=0.01)
    assert math.isclose(max(ys) - min(ys), 3.0, abs_tol=0.01)
