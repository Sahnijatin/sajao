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
                hit = (
                    bool(names & candidates)
                    if exact
                    else any(_contained(a, b) for a in names for b in candidates)
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


# The classes ARKitScenes annotates with 3D boxes, and the head nouns that name them.
ANNOTATED_CLASSES: dict[str, str] = {
    **dict.fromkeys(("chair", "armchair", "recliner"), "chair"),
    **dict.fromkeys(("stool", "ottoman", "pouf"), "stool"),
    **dict.fromkeys(("sofa", "couch", "loveseat", "diwan", "settee", "futon"), "sofa"),
    **dict.fromkeys(("table", "desk"), "table"),
    "bed": "bed",
    **dict.fromkeys(
        (
            "cabinet",
            "cupboard",
            "almirah",
            "wardrobe",
            "dresser",
            "chest",
            "sideboard",
            "nightstand",
            "stand",
            "console",
        ),
        "cabinet",
    ),
    **dict.fromkeys(("shelf", "bookshelf", "bookcase", "rack"), "shelf"),
    **dict.fromkeys(("tv", "television", "monitor"), "tv_monitor"),
    "fireplace": "fireplace",
    **dict.fromkeys(("refrigerator", "fridge"), "refrigerator"),
    **dict.fromkeys(("stove", "cooktop"), "stove"),
    "oven": "oven",
    "sink": "sink",
    "washer": "washer",
    "toilet": "toilet",
    **dict.fromkeys(("bathtub", "tub"), "bathtub"),
    "dishwasher": "dishwasher",
}


def annotated_class(name: str) -> str | None:
    """The ARKitScenes class a listed name belongs to, by its head noun, or None."""
    words = normalise(name).split(" ")
    head = words[words.index("of") - 1] if "of" in words[1:] else words[-1]
    return ANNOTATED_CLASSES.get(head.split("-")[-1])


def listing_recall_by_geometry(
    truth: Sequence[Mapping[str, Any]], listed: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Recall of a listing against annotated 3D boxes: each box the capture saw is one
    real item; listed items of the same class cover them, up to their listed count."""
    annotated: dict[str, int] = {}
    for box in truth:
        annotated[box["label"]] = annotated.get(box["label"], 0) + 1
    counts: dict[str, int] = {}
    for item in listed:
        kind = annotated_class(str(item["name"]))
        if kind is not None:
            counts[kind] = counts.get(kind, 0) + int(item["count"])
    by_class = {
        kind: {
            "annotated": n,
            "listed": counts.get(kind, 0),
            "covered": min(n, counts.get(kind, 0)),
        }
        for kind, n in sorted(annotated.items())
    }
    return {
        "annotated": sum(annotated.values()),
        "covered": sum(c["covered"] for c in by_class.values()),
        "by_class": by_class,
    }


# ARKitScenes calls a one-seat armchair a sofa: seating is scored as one family.
FAMILIES = {"chair": "seating", "sofa": "seating", "stool": "seating",
            "cabinet": "storage", "shelf": "storage"}  # fmt: skip
BIG_M = 0.2  # shorter than this is a fragment, not a placed big item


def _family(kind: str | None) -> str | None:
    return None if kind is None else FAMILIES.get(kind, kind)


def big_item_placement(
    objects: Sequence[Mapping[str, Any]], truth: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Rough placement of big items against annotated 3D boxes (same world).

    Big objects are those of an annotated class whose longer side is at least
    `BIG_M`. Each annotated box takes the nearest unmatched big object of the
    same family within half its diagonal (at least 0.5 m), nearest pairs first;
    centre error is
    horizontal; size errors are twin minus truth over truth."""
    import math
    import statistics

    big = []
    for o in objects:
        family = _family(annotated_class(str(o["category"])))
        if family and o["box"]["length"]["value_m"] >= BIG_M:
            big.append((family, o))
    up = int(big[0][1]["up_axis"]) if big else 2
    a, b = [i for i in range(3) if i != up]
    pairs = []
    for gi, g in enumerate(truth):
        family = _family(str(g["label"]))
        reach = max(0.5, 0.5 * math.hypot(g["size_m"][0], g["size_m"][1]))
        for oi, (f, o) in enumerate(big):
            c = o["box"]["center"]
            d = math.hypot(c[a] - g["center"][a], c[b] - g["center"][b])
            if f == family and d <= reach:
                pairs.append((d, gi, oi))
    match: dict[int, tuple[int, float]] = {}
    used: set[int] = set()
    for d, gi, oi in sorted(pairs):  # nearest pairs first, one to one
        if gi not in match and oi not in used:
            match[gi] = (oi, d)
            used.add(oi)
    rows = []
    for gi, g in enumerate(truth):
        row: dict[str, Any] = {"label": g["label"], "found": gi in match}
        if gi in match:
            oi, d = match[gi]
            box = big[oi][1]["box"]
            row.update(
                centre_error_m=round(d, 3),
                length_error_pct=round(100 * (box["length"]["value_m"] / g["size_m"][0] - 1), 1),
                width_error_pct=round(100 * (box["width"]["value_m"] / g["size_m"][1] - 1), 1),
            )
        rows.append(row)
    found = [r for r in rows if r["found"]]
    by_class: dict[str, list[int]] = {}
    for r in rows:
        counts = by_class.setdefault(str(r["label"]), [0, 0])
        counts[0] += r["found"]
        counts[1] += 1

    def median(key: str) -> float | None:
        return round(statistics.median(r[key] for r in found), 3) if found else None

    return {
        "placed": f"{len(found)} of {len(rows)}",
        "by_class": {k: f"{v[0]} of {v[1]}" for k, v in sorted(by_class.items())},
        "median_centre_error_m": median("centre_error_m"),
        "median_length_error_pct": median("length_error_pct"),
        "median_width_error_pct": median("width_error_pct"),
        "big_objects": len(big),
        "rows": rows,
    }
