"""Object completeness: recall of a twin's inventory against a hand-made one.

The hand inventory (eval/twin-inventory/hand) lists every item in a room with
its type, count and other names. Two recalls are reported per type:

- listed: what the vision models named (the inventory step);
- placed: what was placed in 3D (objects and built-ins).

Item recall counts kinds of things found; instance recall counts the items
themselves (four of six cushions is 0.67). A hand item matches a found name
when one of its names equals one of the found names, or when the shorter name
is the end of the longer ("fan" and "ceiling fan"). Each found name matches at
most one hand item, exact matches first.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from sajao_workers.twin.inventory import TYPES, normalise


def _names(item: Mapping[str, Any], *keys: str) -> set[str]:
    out = {normalise(str(item["name"]))}
    for key in keys:
        out |= {normalise(str(n)) for n in item.get(key, [])}
    return out


def _contained(a: str, b: str) -> bool:
    short, long = sorted((a, b), key=len)
    return long == short or long.endswith(" " + short)


def match_items(
    truth: Sequence[Mapping[str, Any]], found: Sequence[Mapping[str, Any]]
) -> dict[str, str]:
    """Hand item name to the found item name it matches."""
    pairs: dict[str, str] = {}
    used: set[int] = set()
    for exact in (True, False):
        for t in truth:
            if t["name"] in pairs:
                continue
            names = _names(t, "aliases")
            for index, f in enumerate(found):
                if index in used:
                    continue
                candidates = _names(f, "prompts")
                hit = bool(names & candidates) if exact else any(
                    _contained(a, b) for a in names for b in candidates
                )
                if hit:
                    pairs[str(t["name"])] = str(f["name"])
                    used.add(index)
                    break
    return pairs


def _recall(
    truth: Sequence[Mapping[str, Any]], pairs: Mapping[str, str], counts: Mapping[str, int]
) -> dict[str, dict[str, Any]]:
    out = {}
    for kind in (*TYPES, "all"):
        items = [t for t in truth if kind in ("all", t["type"])]
        if not items:
            continue
        found = [t for t in items if t["name"] in pairs]
        instances = sum(int(t["count"]) for t in items)
        hit = sum(min(int(t["count"]), counts.get(pairs[t["name"]], 0)) for t in found)
        out[kind] = {
            "items": f"{len(found)} of {len(items)}",
            "item_recall": round(len(found) / len(items), 2),
            "instance_recall": round(hit / instances, 2),
        }
    return out


def recall_report(
    hand: Mapping[str, Any],
    inventory: Mapping[str, Any],
    objects: Sequence[Mapping[str, Any]],
    built_ins: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    truth = hand["items"]
    listed = inventory["items"]
    listed_pairs = match_items(truth, listed)
    listed_counts = {str(i["name"]): int(i["count"]) for i in listed}

    placed_counts: dict[str, int] = {}
    for o in [*objects, *built_ins]:
        placed_counts[o["category"]] = placed_counts.get(o["category"], 0) + 1
    placed = [{"name": name, "prompts": []} for name in placed_counts]
    placed_pairs = match_items(truth, placed)
    return {
        "listed": _recall(truth, listed_pairs, listed_counts),
        "placed": _recall(truth, placed_pairs, placed_counts),
        "per_item": [
            {
                "name": t["name"],
                "type": t["type"],
                "hand": int(t["count"]),
                "listed": listed_counts.get(listed_pairs.get(t["name"], ""), 0),
                "placed": placed_counts.get(placed_pairs.get(t["name"], ""), 0),
            }
            for t in truth
        ],
        "hand_total": sum(int(t["count"]) for t in truth),
        "listed_total": sum(listed_counts.values()),
        "placed_total": sum(placed_counts.values()),
        "missed_by_listing": [t["name"] for t in truth if t["name"] not in listed_pairs],
        "listed_not_placed": [
            t["name"] for t in truth if t["name"] in listed_pairs and t["name"] not in placed_pairs
        ],
        "matches": {"listed": listed_pairs, "placed": placed_pairs},
    }
