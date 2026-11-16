"""Recall of the inventory and of the placed objects against a hand-made inventory."""

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
