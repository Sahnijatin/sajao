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


def obj(
    category: str, x: float, size: float = 1.0, frames: int = 10, conf: float = 0.8
) -> dict[str, Any]:
    dim = {"value_m": size, "source": "estimated", "error_band_m": 0.05}
    return {"category": category, "confidence": conf, "frames": frames, "up_axis": 2,
            "box": {"center": [x, 0.0, size / 2], "yaw_deg": 0.0,
                    "length": dim, "width": dim, "height": dim}}  # fmt: skip


def test_overlapping_boxes_merge_but_every_listed_item_keeps_its_best_box() -> None:
    from sajao_workers.twin.inventory import dedupe

    items = merge_inventories(
        {"m": [item("painting", "wall_item", 2), item("photo frame", "wall_item")]}
    )
    objects = [
        obj("painting", 0.05, frames=12),
        obj("photo frame", 0.0, frames=4),  # the best photo frame: kept, as listed
        obj("painting", 0.02, frames=6),  # the same painting seen again: merged
        obj("photo frame", 0.03, frames=3),  # merged
    ]

    kept, stats = dedupe(objects, items)

    assert sorted((o["category"], o["frames"]) for o in kept) == [
        ("painting", 12),
        ("photo frame", 4),
    ]
    assert stats == {"merged": 2, "capped": 0}


def test_a_small_thing_on_a_big_one_is_not_merged_into_it() -> None:
    from sajao_workers.twin.inventory import dedupe

    items = merge_inventories({"m": [item("sofa", "furniture"), item("cushion", "textile", 2)]})
    sofa = obj("sofa", 0.0, size=2.0, frames=20)
    cushions = [obj("cushion", -0.5, size=0.4, frames=8), obj("cushion", 0.5, size=0.4, frames=7)]

    kept, _ = dedupe([sofa, *cushions], items, min_volume_ratio=0.5)

    assert sorted(o["category"] for o in kept) == ["cushion", "cushion", "sofa"]


def test_separate_things_side_by_side_are_both_kept() -> None:
    from sajao_workers.twin.inventory import dedupe

    items = merge_inventories({"m": [item("chair", "furniture", 2)]})
    kept, _ = dedupe([obj("chair", 0.0), obj("chair", 1.2)], items)

    assert len(kept) == 2


def test_each_item_keeps_about_as_many_as_were_listed_the_best_seen_first() -> None:
    from sajao_workers.twin.inventory import dedupe

    items = merge_inventories({"m": [item("book", "decor", 1)]})
    books = [obj("book", 2.0 * i, size=0.3, frames=3 + i) for i in range(6)]

    kept, stats = dedupe(books, items, slack=1, min_relative_support=0.0)

    assert sorted(o["frames"] for o in kept) == [7, 8]  # listed 1, plus one of slack
    assert stats == {"merged": 0, "capped": 4}


def test_boxes_seen_far_less_than_the_best_of_their_label_are_dropped() -> None:
    from sajao_workers.twin.inventory import dedupe

    items = merge_inventories({"m": [item("book", "decor", 1)]})
    books = [obj("book", 0.0, 0.3, frames=20), obj("book", 2.0, 0.3, frames=12),
             obj("book", 4.0, 0.3, frames=3)]  # fmt: skip

    kept, stats = dedupe(books, items)

    assert sorted(o["frames"] for o in kept) == [12, 20]
    assert stats == {"merged": 0, "capped": 1}


def test_a_merged_group_takes_the_name_most_of_its_views_gave() -> None:
    from sajao_workers.twin.inventory import dedupe

    items = merge_inventories({"m": [item("sofa", "furniture"), item("armchair", "furniture", 2)]})
    objects = [
        obj("sofa", 0.0, frames=20),  # the sofa
        obj("armchair", 0.0, frames=8),  # the best armchair, on the sofa: kept as listed
        obj("sofa", 3.0, frames=9),  # an armchair the detector also called a sofa
        obj("armchair", 3.02, frames=7),
        obj("armchair", 3.04, frames=6),
    ]

    kept, _ = dedupe(objects, items)

    assert sorted(o["category"] for o in kept) == ["armchair", "armchair", "sofa"]


def test_pieces_of_one_chair_pool_their_views_and_seven_chairs_stay_seven() -> None:
    from sajao_workers.twin.inventory import dedupe

    items = merge_inventories({"m": [item("dining chair", "furniture", 7)]})
    strong = [obj("dining chair", 1.0 * i, size=0.5, frames=20) for i in range(5)]
    # A sixth chair seen only in pieces (back and seat, and once as "armchair").
    pieces = [
        obj("dining chair", 6.0, size=0.45, frames=4, conf=0.5),
        obj("dining chair", 6.12, size=0.35, frames=4, conf=0.4),
        obj("armchair", 6.05, size=0.4, frames=3, conf=0.35),
    ]
    # A seventh seen well in only five frames: real, so kept.
    tall = obj("dining chair", 9.0, size=0.7, frames=5, conf=0.45)
    stray = obj("dining chair", 12.0, size=0.2, frames=3, conf=0.3)  # a wrong label once

    kept, _ = dedupe([*strong, *pieces, tall, stray], items)

    chairs = [o for o in kept if o["category"] in ("dining chair", "armchair")]
    assert len(chairs) == 7
    assert all(o["category"] == "dining chair" for o in chairs)


def stacked(
    category: str, x: float, z0: float, z1: float, length: float, frames: int
) -> dict[str, Any]:
    o = obj(category, x, size=length, frames=frames)
    o["box"]["center"][2] = (z0 + z1) / 2
    o["box"]["height"] = {"value_m": z1 - z0, "source": "estimated", "error_band_m": 0.05}
    return o


def test_a_tv_on_its_stand_stays_two_things() -> None:
    from sajao_workers.twin.inventory import dedupe

    items = merge_inventories({"m": [item("tv", "fixture"), item("tv stand", "furniture")]})
    tv = stacked("tv", 0.0, 0.15, 1.19, 1.1, frames=7)  # noisy depth: its box dips into the stand
    stand = stacked("tv stand", 0.05, 0.0, 0.43, 1.0, frames=12)
    # The best TV and the best stand are elsewhere, so neither box here is protected.
    stand2 = stacked("tv stand", 3.0, 0.0, 0.43, 1.0, frames=20)
    tv2 = stacked("tv", 6.0, 0.42, 1.19, 1.1, frames=20)

    kept, _ = dedupe([tv, stand, stand2, tv2], items)

    assert sorted(o["category"] for o in kept) == ["tv", "tv", "tv stand", "tv stand"]


def test_a_tall_thing_is_not_merged_into_a_lower_neighbour() -> None:
    from sajao_workers.twin.inventory import dedupe

    items = merge_inventories({"m": [item("cabinet", "furniture", 2)]})
    low = stacked("cabinet", 0.0, 0.0, 1.3, 1.3, frames=16)
    tall = stacked("cabinet", 0.2, 0.0, 2.0, 0.5, frames=6)

    kept, _ = dedupe([low, tall], items)

    assert sorted(round(o["box"]["height"]["value_m"], 1) for o in kept) == [1.3, 2.0]
