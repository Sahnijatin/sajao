"""Recall of the inventory and of the placed objects against a hand-made inventory."""

import pytest

from sajao_workers.inventory_recall import match_items, recall_report


def hand(*items: tuple[str, str, int, list[str]]) -> dict[str, object]:
    return {
        "room": "r",
        "items": [{"name": n, "type": t, "count": c, "aliases": a} for n, t, c, a in items],
    }


def test_names_match_on_aliases_and_on_a_shorter_name_inside_a_longer_one() -> None:
    truth = hand(
        ("sofa", "furniture", 1, ["couch"]),
        ("ceiling fan", "fixture", 1, []),
        ("wall clock", "wall_item", 1, []),
        ("idol", "decor", 2, ["statue"]),
    )["items"]
    found = [
        {"name": "couch", "prompts": []},
        {"name": "fan", "prompts": []},
        {"name": "analog wall clock", "prompts": []},
        {"name": "vase", "prompts": []},
    ]

    pairs = match_items(truth, found)  # type: ignore[arg-type]

    assert pairs == {"sofa": "couch", "ceiling fan": "fan", "wall clock": "analog wall clock"}


def test_recall_is_per_type_for_items_and_for_instances() -> None:
    truth = hand(
        ("sofa", "furniture", 1, []),
        ("dining chair", "furniture", 4, ["chair"]),
        ("cushion", "textile", 6, []),
        ("geyser", "fixture", 1, []),
    )
    inventory = {
        "items": [
            {"name": "sofa", "count": 1, "prompts": []},
            {"name": "chair", "count": 4, "prompts": []},
            {"name": "cushion", "count": 3, "prompts": []},
        ]
    }
    objects = [{"category": "sofa"}, {"category": "chair"}, {"category": "chair"}]

    report = recall_report(truth, inventory, objects, [])

    listed, placed = report["listed"], report["placed"]
    assert listed["furniture"] == {"items": "2 of 2", "item_recall": 1.0, "instance_recall": 1.0}
    assert listed["textile"]["instance_recall"] == 0.5
    assert listed["fixture"]["item_recall"] == 0.0
    assert placed["furniture"]["instance_recall"] == 0.6  # 1 sofa + 2 of 4 chairs
    assert placed["textile"]["item_recall"] == 0.0
    assert report["missed_by_listing"] == ["geyser"]
    assert listed["all"]["items"] == "3 of 4"


def test_each_hand_item_shows_its_listed_and_placed_counts_so_duplicates_show() -> None:
    truth = hand(("dining chair", "furniture", 4, ["chair"]))
    inventory = {"items": [{"name": "chair", "count": 4, "prompts": []}]}
    objects = [{"category": "chair"}] * 9

    report = recall_report(truth, inventory, objects, [])

    assert report["per_item"] == [
        {"name": "dining chair", "type": "furniture", "hand": 4, "listed": 4, "placed": 9}
    ]
    assert report["placed_total"] == 9 and report["hand_total"] == 4


def test_listed_names_map_to_the_annotated_classes() -> None:
    from sajao_workers.inventory_recall import annotated_class

    assert annotated_class("dining chair") == "chair"
    assert annotated_class("Armchairs") == "chair"
    assert annotated_class("leather sofa") == "sofa"
    assert annotated_class("almirah") == "cabinet"
    assert annotated_class("chest of drawers") == "cabinet"
    assert annotated_class("built-in bookshelf") == "shelf"
    assert annotated_class("tv") == "tv_monitor"
    assert annotated_class("ottoman") == "stool"
    assert annotated_class("table runner") is None
    assert annotated_class("fireplace tool set") is None


def test_listing_recall_counts_annotated_boxes_covered_by_listed_counts() -> None:
    from sajao_workers.inventory_recall import listing_recall_by_geometry

    truth = [{"label": "chair"}] * 3 + [{"label": "sofa"}, {"label": "tv_monitor"}]
    listed = [
        {"name": "dining chair", "count": 2},
        {"name": "armchair", "count": 2},
        {"name": "sofa", "count": 1},
    ]

    report = listing_recall_by_geometry(truth, listed)

    assert report["by_class"]["chair"] == {"annotated": 3, "listed": 4, "covered": 3}
    assert report["by_class"]["tv_monitor"] == {"annotated": 1, "listed": 0, "covered": 0}
    assert report["covered"] == 4 and report["annotated"] == 5


def test_big_items_are_scored_by_where_they_are_and_how_big() -> None:
    from sajao_workers.inventory_recall import big_item_placement

    def box(category: str, x: float, length: float, width: float) -> dict[str, object]:
        def dim(v: float) -> dict[str, object]:
            return {"value_m": v, "source": "estimated", "error_band_m": 0.05}

        sides = {"length": dim(length), "width": dim(width), "height": dim(0.8)}
        return {
            "category": category,
            "up_axis": 2,
            "box": {"center": [x, 0.0, 0.4], "yaw_deg": 0.0, **sides},
        }

    truth = [
        {"label": "sofa", "center": [0.1, 0.0, 0.4], "size_m": [2.0, 0.9, 0.8], "yaw": 0.0},
        {
            "label": "sofa",
            "center": [3.0, 0.0, 0.4],
            "size_m": [0.9, 0.85, 0.8],
            "yaw": 0.0,
        },  # armchair
        {"label": "bed", "center": [8.0, 0.0, 0.3], "size_m": [2.0, 1.6, 0.6], "yaw": 0.0},
    ]
    objects = [
        box("sofa", 0.0, 1.8, 0.9),
        box("armchair", 3.2, 0.8, 0.8),
        box("vase", 3.0, 0.2, 0.2),  # small: not a big item
    ]

    report = big_item_placement(objects, truth)

    assert report["placed"] == "2 of 3"
    assert report["by_class"]["sofa"] == "2 of 2"
    assert report["median_centre_error_m"] == pytest.approx(0.15)
    assert report["median_length_error_pct"] == pytest.approx(-10.0, abs=1.5)
    assert report["big_objects"] == 2
