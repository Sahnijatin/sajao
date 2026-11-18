"""Vertical planes that belong to things (fridge sides, cabinet fronts) are not walls."""

from typing import Any

from sajao_workers.ar_measurements import measure, read_planes
from sajao_workers.object_planes import (
    object_plane_drop,
    objects_from_boxes,
    objects_from_detections,
    remove_object_planes,
)
from sajao_workers.plane_fixtures import FLOOR_Y, HEIGHT, horizontal, vertical


def room(*extra: dict[str, Any]) -> dict[str, Any]:
    """Floor, ceiling and four walls reaching the ceiling, plus whatever else the phone saw."""
    return {
        "format": "sajao-planes-1",
        "planes": [
            horizontal((0.0, 0.0), (3.8, 3.0), FLOOR_Y, classification="floor"),
            horizontal((0.0, 0.0), (1.0, 1.0), FLOOR_Y + HEIGHT, "horizontal_down"),
            vertical((0.0, -1.7), 90, 2.0, 0.0, HEIGHT - 0.05),  # back wall, z = -1.7
            vertical((0.0, 1.7), -90, 2.0, 0.1, HEIGHT - 0.1),
            vertical((-2.1, 0.0), 0, 1.5, 0.2, HEIGHT - 0.1),
            vertical((2.1, 0.0), 180, 1.5, 0.0, HEIGHT),
            *extra,
        ],
    }


def seen(label: str, x: float, z: float, n: int = 12, score: float = 0.8) -> list[dict[str, Any]]:
    """Live detections whose box centre hit the AR world near (x, z), 1 m above the floor."""
    return [
        {
            "at_ms": 100 * i,
            "detector_class": label,
            "score": score,
            "world": {"x_m": x + 0.02 * (i % 4), "y_m": FLOOR_Y + 1.0, "z_m": z + 0.02 * (i % 3)},
        }
        for i in range(n)
    ]


# A fridge against the back wall: its front at z = -1.0, its sides from z = -1.0 to -1.65.
FRIDGE_SIDES = (
    vertical((0.5, -1.33), 0, 0.65, 0.0, 1.8),
    vertical((1.2, -1.33), 180, 0.65, 0.0, 1.8),
)


def test_the_sides_of_a_detected_fridge_are_removed_and_the_wall_behind_it_stays() -> None:
    doc = room(*FRIDGE_SIDES)

    out = remove_object_planes(doc, objects_from_detections(seen("refrigerator", 0.85, -1.0)))

    assert [r["index"] for r in out["removed"]] == [6, 7]
    assert {r["object"] for r in out["removed"]} == {"refrigerator"}
    assert {r["reason"] for r in out["removed"]} == {"object_face"}
    assert len(out["planes"]["planes"]) == len(doc["planes"]) - 2
    assert out["planes"]["format"] == "sajao-planes-1"
    # The walls the measurement code now sees are only the four real ones.
    walls = measure(out["planes"])["walls"]
    assert len(walls) == 4
    assert all(w["basis"] == "corner_to_corner" for w in walls)


def test_without_the_filter_the_fridge_sides_are_taken_for_walls() -> None:
    assert len(measure(room(*FRIDGE_SIDES))["walls"]) > 4


def test_a_plane_the_phone_classed_as_wall_is_kept_even_beside_a_fridge() -> None:
    doc = room(vertical((0.5, -1.33), 0, 0.65, 0.0, 1.8, classification="wall"))
    out = remove_object_planes(doc, objects_from_detections(seen("refrigerator", 0.85, -1.0)))
    assert out["removed"] == []


def test_a_plane_reaching_the_ceiling_is_a_wall_whatever_stands_near_it() -> None:
    doc = room(vertical((0.5, -1.33), 0, 0.65, 0.0, HEIGHT - 0.1))
    out = remove_object_planes(doc, objects_from_detections(seen("refrigerator", 0.85, -1.0)))
    assert out["removed"] == []


def test_a_long_plane_is_a_wall_even_when_only_its_lower_part_was_tracked() -> None:
    doc = room(vertical((0.0, -1.2), 90, 3.0, 0.0, 1.2))  # 3 m of partition, seen to 1.2 m
    out = remove_object_planes(doc, objects_from_detections(seen("couch", 0.0, -0.9)))
    assert out["removed"] == []


def test_small_things_and_stray_detections_claim_no_plane() -> None:
    near_wall = vertical((-1.6, -1.33), 0, 0.6, 0.8, 1.6)  # a patch of wall above a counter
    doc = room(near_wall)
    evidence = objects_from_detections(
        seen("bowl", -1.3, -1.3, n=40) + seen("refrigerator", -1.3, -1.2, n=3)
    )
    assert evidence == []
    assert remove_object_planes(doc, evidence)["removed"] == []


def test_low_confidence_detections_are_not_evidence() -> None:
    assert objects_from_detections(seen("refrigerator", 0.85, -1.0, score=0.3)) == []


def test_detections_of_one_kind_in_two_places_are_two_objects() -> None:
    evidence = objects_from_detections(seen("chair", 0.0, 0.0) + seen("chair", 2.0, 0.0))
    assert sorted(round(min(p[0] for p in e["points"])) for e in evidence) == [0, 2]


def test_a_placed_cabinet_box_claims_its_front_but_not_the_wall_above_it() -> None:
    # Kitchen base cabinets 2 m long, 0.6 m deep, 0.9 m high against the back wall.
    front = vertical((-0.5, -1.1), 90, 1.8, 0.0, 0.9)
    upper_wall = vertical((-0.5, -1.68), 90, 1.0, 1.0, 1.9)  # tile above the counter
    doc = room(front, upper_wall)
    cabinet = {
        "category": "kitchen cabinet",
        "up_axis": 1,
        "box": {
            "center": [-0.5, FLOOR_Y + 0.45, -1.4],
            "yaw_deg": 0.0,
            "length": {"value_m": 2.0, "source": "estimated", "error_band_m": 0.05},
            "width": {"value_m": 0.6, "source": "estimated", "error_band_m": 0.05},
            "height": {"value_m": 0.9, "source": "estimated", "error_band_m": 0.05},
        },
    }

    out = remove_object_planes(doc, objects_from_boxes([cabinet]))

    assert [(r["index"], r["object"]) for r in out["removed"]] == [(6, "kitchen cabinet")]


def test_the_input_document_is_not_changed() -> None:
    doc = room(*FRIDGE_SIDES)
    before = len(doc["planes"])
    remove_object_planes(doc, objects_from_detections(seen("refrigerator", 0.85, -1.0)))
    assert len(doc["planes"]) == before


def test_the_same_rule_filters_parsed_planes_for_a_shell_builder() -> None:
    doc = room(*FRIDGE_SIDES)
    evidence = objects_from_detections(seen("refrigerator", 0.85, -1.0))
    upright = [p for p in read_planes(doc) if p.kind == "vertical"]

    kept = object_plane_drop(doc, evidence)(upright)

    assert len(kept) == len(upright) - 2
    assert all(p.classification == "none" or p in kept for p in upright)
    assert {round(p.centre[0], 2) for p in upright if p not in kept} == {0.5, 1.2}
