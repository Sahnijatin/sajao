"""Room measurements from AR planes, on rooms whose true sizes are known."""

import math
from typing import Any

import pytest

from sajao_workers.ar_measurements import measure
from sajao_workers.plane_fixtures import DEPTH, FLOOR_Y, HEIGHT, WIDTH, horizontal, room, vertical


def lengths(result: dict[str, Any]) -> list[float]:
    return sorted(w["length"]["value_m"] for w in result["walls"])


def test_wall_lengths_come_from_the_corners_not_from_the_patches_seen() -> None:
    result = measure(room())
    assert lengths(result) == pytest.approx([DEPTH, DEPTH, WIDTH, WIDTH], abs=0.001)
    assert {w["basis"] for w in result["walls"]} == {"corner_to_corner"}
    # No wall was seen end to end: the patches alone would have said less.
    assert all(w["seen_m"] < w["length"]["value_m"] for w in result["walls"])
    for w in result["walls"]:
        assert w["length"]["source"] == "estimated"
        assert w["length"]["error_band_m"] >= 0.05


def test_the_floor_size_is_the_room_between_the_corners() -> None:
    floor = measure(room())["floor"]
    assert floor["basis"] == "corner_to_corner"
    assert floor["area_m2"] == pytest.approx(WIDTH * DEPTH, abs=0.01)
    assert floor["width"]["value_m"] == pytest.approx(WIDTH, abs=0.001)
    assert floor["depth"]["value_m"] == pytest.approx(DEPTH, abs=0.001)
    assert len(floor["polygon"]) == 4


def test_ceiling_height_is_measured_from_the_floor_plane() -> None:
    ceiling = horizontal((2, 1.5), (1.5, 1.5), FLOOR_Y + HEIGHT, classification="ceiling")
    assert measure(room(ceiling))["ceiling_height"]["value_m"] == pytest.approx(HEIGHT)
    without = measure(room())
    assert without["ceiling_height"] is None
    assert any("ceiling" in note for note in without["notes"])


def test_a_table_top_is_neither_the_floor_nor_the_ceiling() -> None:
    table = horizontal((2, 1.5), (1.2, 0.8), FLOOR_Y + 0.75, classification="table")
    underside = horizontal((2, 1.5), (1.2, 0.8), FLOOR_Y + 0.7, kind="horizontal_down")
    ceiling = horizontal((2, 1.5), (2, 2), FLOOR_Y + HEIGHT, kind="horizontal_down")
    result = measure(room(table, underside, ceiling))
    assert result["ceiling_height"]["value_m"] == pytest.approx(HEIGHT)


def test_doors_and_windows_carry_width_height_sill_and_distance_from_the_corner() -> None:
    door = vertical((0.0, 0.75), 0, 0.9, 0.0, 2.05, "door")  # 0.3 m from the corner at z = 0
    window = vertical((2.0, DEPTH), -90, 1.2, 0.9, 2.1, "window")
    result = measure(room(door, window))
    found = {o["kind"]: o for o in result["openings"]}

    assert found["door"]["width"]["value_m"] == pytest.approx(0.9)
    assert found["door"]["height"]["value_m"] == pytest.approx(2.05)
    assert found["door"]["offset"]["value_m"] == pytest.approx(0.3)
    assert "sill_height" not in found["door"]

    assert found["window"]["width"]["value_m"] == pytest.approx(1.2)
    assert found["window"]["height"]["value_m"] == pytest.approx(1.2)
    assert found["window"]["sill_height"]["value_m"] == pytest.approx(0.9)
    assert found["window"]["offset"]["value_m"] == pytest.approx(1.4)

    walls = {w["id"]: w for w in result["walls"]}
    assert walls[found["door"]["wall_id"]]["length"]["value_m"] == pytest.approx(DEPTH)
    assert walls[found["window"]["wall_id"]]["length"]["value_m"] == pytest.approx(WIDTH)
    # A door or window plane never counts as a stretch of wall.
    assert lengths(result) == pytest.approx([DEPTH, DEPTH, WIDTH, WIDTH], abs=0.001)


def test_a_room_seen_in_part_reports_lower_bounds_and_says_so() -> None:
    doc = room()
    # Drop the wall along x = 0: its two neighbours lose a corner each.
    doc["planes"] = [p for p in doc["planes"] if p["transform"][12] != 0.0]
    result = measure(doc)
    by_basis: dict[str, list[float]] = {}
    for w in result["walls"]:
        by_basis.setdefault(w["basis"], []).append(w["length"]["value_m"])
    assert by_basis["corner_to_corner"] == pytest.approx([DEPTH], abs=0.001)
    assert len(by_basis["seen"]) == 2
    assert all(value < WIDTH for value in by_basis["seen"])
    assert result["floor"]["basis"] == "seen"
    assert any("lower bound" in note for note in result["notes"])


def test_planes_without_classes_still_give_walls_floor_and_ceiling() -> None:
    """ARCore: vertical and horizontal planes only, the ceiling facing down."""
    ceiling = horizontal((2, 1.5), (2, 2), FLOOR_Y + HEIGHT, kind="horizontal_down")
    wardrobe_side = vertical((3.9, 2.9), 90, 0.5, 0.0, 2.0)  # too short to be a wall
    result = measure(room(ceiling, wardrobe_side, classed=False))
    assert lengths(result) == pytest.approx([DEPTH, DEPTH, WIDTH, WIDTH], abs=0.001)
    assert result["ceiling_height"]["value_m"] == pytest.approx(HEIGHT)
    assert result["openings"] == []
    assert any("does not class planes" in note for note in result["notes"])


def test_a_turned_room_measures_the_same() -> None:
    def turn(doc: dict[str, Any], degrees: float) -> dict[str, Any]:
        a = math.radians(degrees)
        c, s = math.cos(a), math.sin(a)
        turned = []
        for plane in doc["planes"]:
            m = list(plane["transform"])
            for column in range(4):
                x, z = m[column * 4], m[column * 4 + 2]
                m[column * 4], m[column * 4 + 2] = c * x - s * z, s * x + c * z
            turned.append({**plane, "transform": m})
        return {**doc, "planes": turned}

    door = vertical((0.0, 0.75), 0, 0.9, 0.0, 2.05, "door")
    for degrees in (17, 133, 251):
        result = measure(turn(room(door), degrees))
        assert lengths(result) == pytest.approx([DEPTH, DEPTH, WIDTH, WIDTH], abs=0.001)
        assert result["floor"]["area_m2"] == pytest.approx(WIDTH * DEPTH, abs=0.01)
        assert result["openings"][0]["offset"]["value_m"] == pytest.approx(0.3, abs=0.001)


def test_no_planes_means_no_measurements_and_a_plain_reason() -> None:
    result = measure({"format": "sajao-planes-1", "planes": []})
    assert (result["walls"], result["floor"], result["openings"]) == ([], None, [])
    assert "no planes" in result["notes"][0]


def test_broken_planes_are_skipped() -> None:
    doc = room()
    doc["planes"] += [
        {"type": "vertical", "transform": [1, 2, 3], "polygon_xz": [0, 0, 1, 0, 1, 1]},
        {"type": "vertical", "transform": [float("nan")] * 16, "polygon_xz": [0, 0, 1, 0, 1, 1]},
        {"type": "vertical", "transform": [1] * 16, "polygon_xz": [0, 0]},
    ]
    assert lengths(measure(doc)) == pytest.approx([DEPTH, DEPTH, WIDTH, WIDTH], abs=0.001)
