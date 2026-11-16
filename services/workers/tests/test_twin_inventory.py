"""The inventory-first objects step: list, merge, ground, and flag what was not placed."""

import math
from typing import Any

import numpy as np
import pytest

from sajao_gateway import InvalidOutputError, ProviderResult
from sajao_workers.twin.inventory import (
    INVENTORY_SCHEMA,
    check_inventory,
    detector_vocabulary,
    merge_inventories,
    normalise,
    pick_keyframes,
    retry_vocabulary,
    split_built_ins,
    unplaced_items,
)


def item(name: str, type_: str = "decor", count: int = 1, prompts: Any = ()) -> dict[str, Any]:
    return {"name": name, "type": type_, "count": count, "prompts": list(prompts)}


def pose(yaw_deg: float, x: float = 0.0) -> list[list[float]]:
    """A level camera at (x, 0, 1.4) looking along `yaw` in the floor plane (z up)."""
    yaw = math.radians(yaw_deg)
    forward = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    down = np.array([0.0, 0.0, -1.0])
    right = np.cross(down, forward)
    c2w = np.eye(4)
    c2w[:3, :3] = np.column_stack([right, down, forward])
    c2w[:3, 3] = [x, 0.0, 1.4]
    return c2w.tolist()


# Listing ---------------------------------------------------------------------


def test_keyframes_are_picked_to_look_all_round_the_room() -> None:
    # Twenty frames looking roughly the same way, and one each at 90, 180 and 270 degrees.
    poses = [pose(i * 0.5) for i in range(20)] + [pose(90), pose(180), pose(270)]

    picked = pick_keyframes(poses, 4)

    assert len(picked) == 4
    assert {20, 21, 22} <= set(picked)


def test_fewer_frames_than_asked_are_all_used() -> None:
    assert pick_keyframes([pose(0), pose(10)], 6) == [0, 1]


def test_the_response_schema_asks_for_every_type() -> None:
    types = INVENTORY_SCHEMA["properties"]["items"]["items"]["properties"]["type"]["enum"]
    assert set(types) == {"furniture", "fixture", "wall_item", "textile", "decor", "built_in"}


@pytest.mark.parametrize(
    "output",
    [
        {},
        {"items": "sofa"},
        {"items": [item("sofa", "chair")]},  # unknown type
        {"items": [item("", "furniture")]},
        {"items": [item("sofa", "furniture", 0)]},
        {"items": [item("x" * 81, "decor")]},
        {"items": [item(f"thing {i}") for i in range(201)]},
    ],
)
def test_a_bad_inventory_is_rejected(output: dict[str, Any]) -> None:
    with pytest.raises(InvalidOutputError):
        check_inventory(ProviderResult(output=output))


def test_a_good_inventory_passes() -> None:
    check_inventory(ProviderResult(output={"items": [item("gas stove", "fixture", 1, ["stove"])]}))


def test_names_are_normalised_to_one_singular_form() -> None:
    assert normalise("  Cushions ") == "cushion"
    assert normalise("Wall  Shelves") == "wall shelf"
    assert normalise("glass") == "glass"
    assert normalise("Switchboards") == "switchboard"
    assert normalise("batteries") == "battery"
    assert normalise("Idol of Ganesha") == "idol of ganesha"


def test_two_models_lists_are_merged_and_credited() -> None:
    gemini = [
        item("sofa", "furniture"),
        item("cushions", "textile", 4),
        item("ceiling fan", "fixture", 1, ["fan"]),
    ]
    claude = [
        item("Sofa", "furniture"),
        item("cushion", "textile", 5),
        item("fan", "fixture"),
        item("water purifier", "fixture"),
    ]

    merged = merge_inventories({"gemini": gemini, "claude": claude})

    by_name = {m["name"]: m for m in merged}
    assert set(by_name) == {"sofa", "cushion", "ceiling fan", "water purifier"}
    assert by_name["sofa"]["listed_by"] == ["claude", "gemini"]
    assert by_name["cushion"]["count"] == 5  # the larger count: recall matters more
    assert by_name["ceiling fan"]["listed_by"] == ["claude", "gemini"]  # matched by its prompt
    assert by_name["water purifier"]["listed_by"] == ["claude"]


def test_the_first_model_decides_the_type_when_they_disagree() -> None:
    merged = merge_inventories(
        {"gemini": [item("chimney", "built_in")], "claude": [item("chimney", "fixture")]}
    )
    assert merged[0]["type"] == "built_in"


# Grounding -------------------------------------------------------------------


def test_the_detector_vocabulary_is_one_unique_prompt_per_item() -> None:
    items = merge_inventories(
        {"m": [item("sofa", "furniture", 1, ["couch"]), item("tv", "fixture", 1, ["television"])]}
    )

    vocabulary, prompts = detector_vocabulary(items)

    assert vocabulary == ["sofa", "tv"]
    assert prompts == ["sofa", "tv"]


def test_the_retry_uses_each_items_other_names() -> None:
    items = merge_inventories(
        {"m": [item("sofa", "furniture", 1, ["couch", "settee"]), item("idol", "decor")]}
    )

    vocabulary, prompts = retry_vocabulary(items)

    assert vocabulary == ["sofa", "idol"]
    assert prompts == ["couch", "statue"]  # "idol" has no listed alias: a generic one is used


def test_items_not_placed_are_kept_with_a_reason() -> None:
    items = merge_inventories(
        {
            "gemini": [
                item("sofa", "furniture"),
                item("wall clock", "wall_item"),
                item("geyser", "fixture"),
                item("rug", "textile"),
                item("idol", "decor"),
            ]
        }
    )
    objects = [{"category": "sofa"}]
    diagnostics = {
        "wall clock": {"detected": 4, "lifted": 2, "few_frames": 1, "implausible": 0},
        "geyser": {"detected": 0, "lifted": 0, "few_frames": 0, "implausible": 0},
        "rug": {"detected": 6, "lifted": 0, "few_frames": 0, "implausible": 0},
        "idol": {"detected": 5, "lifted": 5, "few_frames": 0, "implausible": 1},
    }
    tried = ["owlv2", "owlv2 retry at 0.1"]

    unplaced = unplaced_items(items, objects, [], diagnostics, tried)

    reasons = {u["name"]: u["reason"] for u in unplaced}
    assert reasons == {
        "wall clock": "not_seen_in_enough_frames",
        "geyser": "not_detected",
        "rug": "no_depth",
        "idol": "implausible_size",
    }
    assert all(u["tried"] == tried and u["listed_by"] == ["gemini"] for u in unplaced)


def test_built_ins_go_to_the_shell_and_objects_get_their_type() -> None:
    items = merge_inventories(
        {"m": [item("chimney", "built_in"), item("sofa", "furniture"), item("rug", "textile")]}
    )
    objects = [
        {"category": "chimney", "label": "Chimney", "confidence": 0.6, "box": {}},
        {"category": "sofa", "label": "Sofa", "confidence": 0.9, "box": {}},
        {"category": "rug", "label": "Rug", "confidence": 0.7, "box": {}},
    ]

    kept, built_ins = split_built_ins(items, objects)

    assert [o["category"] for o in built_ins] == ["chimney"]
    assert [(o["category"], o["object_type"]) for o in kept] == [
        ("sofa", "furniture"),
        ("rug", "textile"),
    ]
