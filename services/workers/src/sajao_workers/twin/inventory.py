"""Inventory-first objects: a vision model lists everything in the room, then
open-vocabulary detection and segmentation place each listed item in 3D.

The list is written from a few keyframes chosen to look all round the room.
Two models list independently (the first is primary, the second a cross-check);
their lists are merged and each item records who listed it. Items grounding
could not place are retried under other names and a lower threshold, then kept
in the twin's inventory with the reason, never dropped silently.

No model sets a size here: sizes come from the lifted, fused geometry.
"""

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from sajao_gateway import InvalidOutputError, ProviderResult

TYPES = ("furniture", "fixture", "wall_item", "textile", "decor", "built_in")
MAX_ITEMS = 200
MAX_NAME = 60  # a twin object category is at most 60 characters
MAX_PROMPTS = 3

INVENTORY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": list(TYPES)},
                    "count": {"type": "integer"},
                    "prompts": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "type", "count", "prompts"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

# A generic name to retry with when an item has no other name listed.
GENERIC_ALIASES = {
    "idol": "statue",
    "murti": "statue",
    "geyser": "water heater",
    "chimney": "range hood",
    "switchboard": "light switch",
    "water purifier": "water filter",
    "almirah": "wardrobe",
    "diwan": "daybed",
    "puja unit": "shrine",
    "cooler": "air cooler",
}


def pick_keyframes(poses: Sequence[Sequence[Sequence[float]]], n: int) -> list[int]:
    """Frames that look in the most different directions (farthest-point sampling
    on view direction, with a small weight on position), in capture order."""
    if len(poses) <= n:
        return list(range(len(poses)))
    c2w = np.asarray(poses, dtype=np.float64)
    forward = c2w[:, :3, 2] / np.linalg.norm(c2w[:, :3, 2], axis=1, keepdims=True)
    position = c2w[:, :3, 3]

    def distance(i: int) -> np.ndarray:
        angle = np.arccos(np.clip(forward @ forward[i], -1.0, 1.0))
        result: np.ndarray = angle + 0.25 * np.linalg.norm(position - position[i], axis=1)
        return result

    picked = [0]
    nearest = distance(0)
    while len(picked) < n:
        nxt = int(np.argmax(nearest))
        picked.append(nxt)
        nearest = np.minimum(nearest, distance(nxt))
    return sorted(picked)


def _fail(what: str) -> None:
    raise InvalidOutputError(f"inventory: {what}")


def check_inventory(result: ProviderResult) -> None:
    """Validate a model's inventory: types from the list, names and counts sane."""
    items = result.output.get("items")
    if not isinstance(items, list):
        _fail("items is not a list")
        return
    if len(items) > MAX_ITEMS:
        _fail(f"more than {MAX_ITEMS} items")
    for entry in items:
        if not isinstance(entry, Mapping):
            _fail("an item is not an object")
            return
        name = entry.get("name")
        if not isinstance(name, str) or not 0 < len(name.strip()) <= MAX_NAME:
            _fail("an item name is empty or too long")
        if entry.get("type") not in TYPES:
            _fail("an item type is not one of the types")
        count = entry.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 100:
            _fail("an item count is not between 1 and 100")
        prompts = entry.get("prompts", [])
        if not isinstance(prompts, list) or not all(
            isinstance(p, str) and 0 < len(p.strip()) <= MAX_NAME for p in prompts
        ):
            _fail("prompts are not short strings")


def _singular(word: str) -> str:
    if len(word) <= 3 or word.endswith(("ss", "us", "is")):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("ves") and word[:-3] in {"shel", "hal", "lea"}:
        return word[:-3] + "f"
    if word.endswith(("ches", "shes", "xes", "sses")):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def normalise(name: str) -> str:
    """Lower case, single spaces, the head noun singular ("Wall Shelves" -> "wall shelf")."""
    words = re.sub(r"\s+", " ", name.lower().strip()).split(" ")
    # The head noun is the last word before "of" ("idols of ganesha" -> "idol of ganesha").
    head = words.index("of") - 1 if "of" in words[1:] else len(words) - 1
    words[head] = _singular(words[head])
    return " ".join(words)


def merge_inventories(lists: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """One list from several models' lists, in the order given (the first is primary).

    Items match on their normalised name or on any of their other names. The
    first model to list an item names it and gives its type; the count is the
    largest any model gave, since a missed item costs more than an extra search.
    """
    merged: list[dict[str, Any]] = []
    for model, items in lists.items():
        for entry in items:
            name = normalise(str(entry["name"]))
            prompts = [normalise(str(p)) for p in entry.get("prompts", [])]
            keys = {name, *prompts}
            match = next(
                (m for m in merged if keys & {m["name"], *m["prompts"]}),
                None,
            )
            if match is None:
                merged.append(
                    {
                        "name": name,
                        "type": entry["type"],
                        "count": int(entry["count"]),
                        "prompts": [p for p in dict.fromkeys(prompts) if p != name][:MAX_PROMPTS],
                        "listed_by": [model],
                    }
                )
                continue
            match["count"] = max(match["count"], int(entry["count"]))
            match["listed_by"] = sorted({*match["listed_by"], model})
            extra = [p for p in [name, *prompts] if p != match["name"]]
            match["prompts"] = list(dict.fromkeys([*match["prompts"], *extra]))[:MAX_PROMPTS]
    return merged


def detector_vocabulary(items: Sequence[Mapping[str, Any]]) -> tuple[list[str], list[str]]:
    """Labels and detector prompts for the first pass: each item under its own name."""
    names = [str(i["name"]) for i in items]
    return names, list(names)


def retry_vocabulary(items: Sequence[Mapping[str, Any]]) -> tuple[list[str], list[str]]:
    """Labels and prompts for the retry: each item under another name, unique per pass."""
    labels, prompts, used = [], [], set()
    for entry in items:
        name = str(entry["name"])
        options = [*entry.get("prompts", []), GENERIC_ALIASES.get(name, f"a {name}")]
        prompt = next((p for p in options if p not in used and p != name), None)
        if prompt is None:
            continue
        used.add(prompt)
        labels.append(name)
        prompts.append(prompt)
    return labels, prompts


def unplaced_items(
    items: Sequence[Mapping[str, Any]],
    objects: Sequence[Mapping[str, Any]],
    built_ins: Sequence[Mapping[str, Any]],
    diagnostics: Mapping[str, Mapping[str, int]],
    tried: Sequence[str],
) -> list[dict[str, Any]]:
    """Every listed item with nothing placed under its name, and why."""
    placed = {o["category"] for o in [*objects, *built_ins]}
    out = []
    for entry in items:
        if entry["name"] in placed:
            continue
        d = diagnostics.get(entry["name"], {})
        if d.get("implausible", 0):
            reason = "implausible_size"
        elif d.get("few_frames", 0):
            reason = "not_seen_in_enough_frames"
        elif d.get("detected", 0) and not d.get("lifted", 0):
            reason = "no_depth"
        elif d.get("detected", 0):
            reason = "not_seen_in_enough_frames"
        else:
            reason = "not_detected"
        out.append(
            {
                "name": entry["name"],
                "type": entry["type"],
                "count": entry["count"],
                "listed_by": list(entry["listed_by"]),
                "tried": list(tried),
                "reason": reason,
            }
        )
    return out


def split_built_ins(
    items: Sequence[Mapping[str, Any]], objects: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Objects with their type, and the built-ins, which belong to the shell."""
    type_of = {i["name"]: i["type"] for i in items}
    kept, built_ins = [], []
    for obj in objects:
        kind = type_of.get(obj["category"], "furniture")
        if kind == "built_in":
            built_ins.append(dict(obj))
        else:
            kept.append({**obj, "object_type": kind})
    return kept, built_ins


def _upright(obj: Mapping[str, Any]) -> Any:
    from sajao_workers.twin.geometry import UprightBox

    box = obj["box"]
    return UprightBox(
        tuple(box["center"]),
        box["length"]["value_m"],
        box["width"]["value_m"],
        box["height"]["value_m"],
        math.radians(box["yaw_deg"]),
        int(obj["up_axis"]),
    )


def _support(obj: Mapping[str, Any]) -> float:
    return float(obj["frames"]) * float(obj["confidence"])


def _kind(name: str) -> str:
    """What kind of thing a name is: its head noun, grouped as fusion groups names
    (armchair and dining chair are both chairs; photo frame and painting are not)."""
    from sajao_workers.twin.fusion import GROUPS

    words = normalise(name).split(" ")
    head = words[words.index("of") - 1] if "of" in words[1:] else words[-1]
    whole = " ".join(words)
    return GROUPS.get(whole, GROUPS.get(head, head))


def dedupe(
    objects: Sequence[Mapping[str, Any]],
    items: Sequence[Mapping[str, Any]],
    *,
    contain: float = 0.6,
    iou: float = 0.3,
    min_volume_ratio: float = 0.3,
    near_m: float = 0.3,
    min_relative_support: float = 0.35,
    min_frames: int = 4,
    slack: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """One object per real thing (defaults tuned in eval/twin-inventory).

    1. Boxes are one thing when they overlap (IoU at least `iou`, or at least
       `contain` of the smaller inside the larger when their volumes are within
       `min_volume_ratio`: a cushion on a sofa is not the sofa), or when they are
       the same kind of thing with centres within `near_m` and overlapping
       heights (the back and the seat of one chair). The best-seen box (frames
       times confidence) stays, the group pools its views, and it takes the name
       most of its views gave.
    2. The best box of each listed item is never merged into a different kind of
       thing, so every listed item keeps one object.
    3. A group seen far less than the best of its name (pooled support below
       `min_relative_support` of it) and in fewer than `min_frames` frames is
       dropped: a common name (book, box) gets put on many things briefly.
    4. With `slack`, each item keeps at most its listed count plus `slack`.
    """
    from sajao_workers.twin.geometry import box_overlap, horizontal_axes

    ranked: list[dict[str, Any]] = [dict(o) for o in sorted(objects, key=_support, reverse=True)]
    boxes = [_upright(o) for o in ranked]
    kinds = [_kind(o["category"]) for o in ranked]

    def near(i: int, k: int) -> bool:
        if kinds[i] != kinds[k]:
            return False
        a, b = horizontal_axes(boxes[i].up_axis)
        ci, ck = boxes[i].center, boxes[k].center
        if math.hypot(ci[a] - ck[a], ci[b] - ck[b]) > near_m:
            return False
        (lo_i, hi_i), (lo_k, hi_k) = boxes[i].vertical_range(), boxes[k].vertical_range()
        return bool(min(hi_i, hi_k) > max(lo_i, lo_k))

    def same_thing(i: int, k: int) -> bool:
        if i in protected and kinds[i] != kinds[k]:
            return False
        overlap_iou, contained = box_overlap(boxes[i], boxes[k])
        small, large = sorted((boxes[i].volume(), boxes[k].volume()))
        similar = large > 0 and small / large >= min_volume_ratio
        return overlap_iou >= iou or (contained >= contain and similar) or near(i, k)

    first: dict[str, int] = {}
    for i, o in enumerate(ranked):
        first.setdefault(o["category"], i)
    protected = set(first.values())
    kept: list[int] = []
    votes: dict[int, dict[str, float]] = {}
    pooled: dict[int, float] = {}
    frames: dict[int, int] = {}
    merged = 0
    for i in range(len(boxes)):
        into = next((k for k in kept if same_thing(i, k)), None)
        if into is None:
            kept.append(i)
            votes[i] = {ranked[i]["category"]: _support(ranked[i])}
            pooled[i], frames[i] = _support(ranked[i]), int(ranked[i]["frames"])
            continue
        merged += 1
        name = ranked[i]["category"]
        votes[into][name] = votes[into].get(name, 0.0) + _support(ranked[i])
        pooled[into] += _support(ranked[i])
        frames[into] = max(frames[into], int(ranked[i]["frames"]))
    # A group takes the name most of its views gave, unless that would take away
    # the last object of a listed item of another kind.
    for k in kept:
        name = max(votes[k], key=lambda n: votes[k][n])
        if name != ranked[k]["category"] and not (k in protected and _kind(name) != kinds[k]):
            ranked[k]["category"], ranked[k]["label"] = name, name.capitalize()
    big = 10**9
    limit = {str(i["name"]): int(i["count"]) + (big if slack is None else slack) for i in items}
    best: dict[str, float] = {}
    for k in kept:
        name = ranked[k]["category"]
        best[name] = max(best.get(name, 0.0), pooled[k])
    counts: dict[str, int] = {}
    out, capped = [], 0
    for k in sorted(kept, key=lambda k: -pooled[k]):
        name = ranked[k]["category"]
        if pooled[k] < min_relative_support * best[name] and frames[k] < min_frames:
            capped += 1
            continue
        counts[name] = counts.get(name, 0) + 1
        if counts[name] > limit.get(name, big):
            capped += 1
            continue
        out.append(dict(ranked[k]))
    return out, {"merged": merged, "capped": capped}
