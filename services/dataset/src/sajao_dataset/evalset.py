"""The Indian-home eval set: 200 hand-checked frames, then a per-class score of the
listing step on them.

Stages, each a durable JSON-lines ledger that a rerun resumes:

1. tag: a cheap model says which taxonomy classes each pool frame shows.
2. select: a stratified pick that covers every target class, few frames per video.
3. label: Gemini proposes a class and a 2D box for every taxonomy object.
4. check: Claude gives a second opinion on each label and adds missed objects.
5. review: the disagreements go to a hand-check sheet; the founder's decisions
   come back as a JSON-lines file.
6. listing: the listing step's own prompt and models (Gemini lists, Claude
   cross-checks) run on each frame; listed names map to classes and are scored
   per class against the labels.

Labels are classes and 2D boxes only; no model sets a size or a position in the
room. Every output is validated before it is kept. Claude calls are charged to a
monthly ledger with a hard cap.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import random
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sajao_gateway import InvalidOutputError, ProviderResult
from sajao_gateway.spend import Reservation

EVALSET_VERSION = "evalset-v1"

# The classes the launch needs most: Indian-specific items the listing step must find.
TARGETS = (
    "gas_stove",
    "water_purifier",
    "geyser",
    "pooja_unit",
    "diwan",
    "modular_kitchen",
    "ceiling_fan",
    "ac_unit",
)

# Every class, with what it is (for the prompts) and the names that count as it
# when the listing step names it (normalised: lower case, singular head noun).
TAXONOMY: dict[str, tuple[str, tuple[str, ...]]] = {
    "gas_stove": (
        "a gas stove or hob with burners, on a counter or built in",
        ("gas stove", "stove", "gas hob", "hob", "cooktop", "gas burner", "burner", "gas chulha"),
    ),
    "water_purifier": (
        "a wall-mounted or counter water purifier (RO or UV unit), not a plain water bottle",
        ("water purifier", "water filter", "ro purifier", "ro water purifier", "purifier"),
    ),
    "geyser": (
        "an electric or gas water heater (geyser), usually mounted high on a bathroom wall",
        ("geyser", "water heater", "electric geyser"),
    ),
    "pooja_unit": (
        "a pooja unit: a mandir cabinet, shrine shelf or puja alcove with idols or pictures",
        (
            "pooja unit",
            "puja unit",
            "mandir",
            "pooja mandir",
            "temple",
            "shrine",
            "puja alcove",
            "pooja shelf",
            "puja shelf",
            "pooja cabinet",
        ),
    ),
    "diwan": (
        "a diwan: a low backless or single-back day bed used as seating in a living room",
        ("diwan", "divan", "daybed", "day bed"),
    ),
    "modular_kitchen": (
        "a run of fitted kitchen cabinets and counter (one box per continuous run)",
        (
            "modular kitchen",
            "kitchen cabinet",
            "kitchen counter",
            "kitchen countertop",
            "countertop",
            "overhead cabinet",
            "kitchen unit",
            "base cabinet",
            "wall cabinet",
        ),
    ),
    "ceiling_fan": ("a fan fixed to the ceiling", ("ceiling fan", "fan")),
    "ac_unit": (
        "an air conditioner: a split AC indoor unit or a window AC",
        ("ac unit", "air conditioner", "ac", "split ac", "window ac", "air conditioning unit"),
    ),
    "sofa": ("a sofa or couch", ("sofa", "couch", "sectional sofa", "sofa set", "l-shaped sofa")),
    "bed": ("a bed (frame or mattress)", ("bed", "double bed", "single bed", "bunk bed")),
    "chair": ("a chair or armchair", ("chair", "armchair", "dining chair", "office chair")),
    "dining_table": ("a dining table", ("dining table",)),
    "coffee_table": (
        "a low centre or coffee table",
        ("coffee table", "centre table", "center table"),
    ),
    "almirah": (
        "a free-standing or fitted wardrobe, almirah or cupboard for clothes",
        ("almirah", "wardrobe", "cupboard", "fitted wardrobe", "closet"),
    ),
    "tv": ("a television", ("tv", "television", "led tv", "smart tv")),
    "tv_unit": (
        "a TV unit or console under or around a TV",
        ("tv unit", "tv cabinet", "tv console"),
    ),
    "shoe_rack": ("a shoe rack or shoe cabinet", ("shoe rack", "shoe cabinet")),
    "dressing_table": ("a dressing table with a mirror", ("dressing table", "vanity")),
    "refrigerator": ("a refrigerator", ("refrigerator", "fridge")),
    "washing_machine": ("a washing machine", ("washing machine", "washer")),
    "air_cooler": ("a portable air cooler", ("air cooler", "cooler", "desert cooler")),
    "chimney": ("a kitchen chimney or range hood", ("chimney", "kitchen chimney", "range hood")),
    "curtain": ("a curtain or drape", ("curtain", "drape")),
    "rug": ("a rug, carpet or dhurrie on the floor", ("rug", "carpet", "dhurrie", "mat")),
}
CLASSES = tuple(TAXONOMY)

ALIAS_TO_CLASS: dict[str, str] = {
    alias: name for name, (_, aliases) in TAXONOMY.items() for alias in aliases
}

# Where each target class is likely to be seen, for the pool.
TARGET_ROOMS = {
    "kitchen",
    "bathroom",
    "puja_room",
    "living_room",
    "bedroom",
    "dining",
    "utility",
    "kids_room",
    "study",
}


def _singular(word: str) -> str:
    if len(word) <= 3 or word.endswith(("ss", "us", "is")):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "xes")):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def normalise(name: str) -> str:
    """Lower case, single spaces, the head noun singular (as the listing step does)."""
    words = re.sub(r"\s+", " ", name.lower().strip()).split(" ")
    words[-1] = _singular(words[-1])
    return " ".join(words)


def class_of(name: str) -> str | None:
    """The taxonomy class a listed name means, or None."""
    return ALIAS_TO_CLASS.get(normalise(name))


# --- The pool ---------------------------------------------------------------


def pool_frames(
    frames: Sequence[Mapping[str, Any]], *, per_clip: int = 2, min_gap_s: float = 3.0
) -> list[dict[str, Any]]:
    """The sharpest frames of each clip, at least `min_gap_s` apart, from rooms where
    a target class is likely. Portrait and small frames are left out."""
    by_clip: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for f in frames:
        if f["room_type"] in TARGET_ROOMS and int(f["width"]) >= 1280:
            by_clip[str(f["clip_path"])].append(f)
    out: list[dict[str, Any]] = []
    for clip in sorted(by_clip):
        picked: list[Mapping[str, Any]] = []
        for f in sorted(by_clip[clip], key=lambda f: -float(f["sharpness"])):
            if all(abs(float(f["t_s"]) - float(p["t_s"])) >= min_gap_s for p in picked):
                picked.append(f)
            if len(picked) == per_clip:
                break
        out.extend(dict(f) for f in picked)
    return out


# --- Prompts and validation -------------------------------------------------


def _class_lines(classes: Iterable[str]) -> str:
    return "\n".join(f"- {c}: {TAXONOMY[c][0]}" for c in classes)


TAG_PROMPT_ID = "evalset_tag@1"
TAG_PROMPT = f"""This is one frame from a video tour of an Indian home.

Which of these classes can you see in it (at least partly, and clearly enough to
recognise)? Answer only with classes from this list:
{_class_lines(CLASSES)}
"""
TAG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "present": {"type": "array", "items": {"type": "string", "enum": list(CLASSES)}}
    },
    "required": ["present"],
}

LABEL_PROMPT_ID = "evalset_label@1"
LABEL_PROMPT = f"""This is one frame from a video tour of an Indian home.

Find every object of these classes that is visible, and give a 2D box for each:
{_class_lines(CLASSES)}

Rules:
- One entry per physical object; two chairs are two entries.
- box_2d is [ymin, xmin, ymax, xmax], each from 0 to 1000 across the image.
- Include an object only if you can recognise its class; skip tiny or doubtful ones.
- Leave out anything not in the list.
"""
LABEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "class": {"type": "string", "enum": list(CLASSES)},
                    "box_2d": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["class", "box_2d"],
            },
        }
    },
    "required": ["objects"],
}

CHECK_PROMPT_ID = "evalset_check@1"
VERDICTS = ("agree", "wrong_class", "bad_box", "not_present")


def check_prompt(labels: Sequence[Mapping[str, Any]]) -> str:
    listed = "\n".join(f"{i + 1}: {o['class']}" for i, o in enumerate(labels)) or "(none)"
    return f"""This is one frame from a video tour of an Indian home. Another model labelled
objects in it; each label is drawn as a numbered box. Review the labels.

Classes:
{_class_lines(CLASSES)}

Labels:
{listed}

For every label give a verdict:
- agree: the box is on an object of that class and fits it reasonably
- wrong_class: there is an object, but of another class (give correct_class from the
  list, or "none" if it is not in the list)
- bad_box: right class, but the box misses most of the object or covers several
- not_present: there is no such object there

Then list any object of these classes that has no label (missed), with a box_2d
[ymin, xmin, ymax, xmax] from 0 to 1000. Skip tiny or doubtful objects.
"""


CHECK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                    "correct_class": {"type": "string", "enum": [*CLASSES, "none"]},
                },
                "required": ["id", "verdict", "correct_class"],
                "additionalProperties": False,
            },
        },
        "missed": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "class": {"type": "string", "enum": list(CLASSES)},
                    "box_2d": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["class", "box_2d"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["reviews", "missed"],
    "additionalProperties": False,
}


def _fail(what: str) -> None:
    raise InvalidOutputError(f"evalset: {what}")


def valid_box(box: object) -> bool:
    """[ymin, xmin, ymax, xmax] inside 0..1000, with some area."""
    if not isinstance(box, list) or len(box) != 4:
        return False
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in box):
        return False
    y0, x0, y1, x1 = (int(v) for v in box)
    return 0 <= y0 < y1 <= 1000 and 0 <= x0 < x1 <= 1000 and (y1 - y0) * (x1 - x0) >= 25


def check_tag(result: ProviderResult) -> None:
    present = result.output.get("present")
    if not isinstance(present, list) or not all(p in TAXONOMY for p in present):
        _fail("present is not a list of classes")


MAX_OBJECTS = 60


def check_labels(result: ProviderResult) -> None:
    objects = result.output.get("objects")
    if not isinstance(objects, list) or len(objects) > MAX_OBJECTS:
        _fail("objects is not a list of at most 60")
        return
    for o in objects:
        if not isinstance(o, Mapping) or o.get("class") not in TAXONOMY:
            _fail("an object class is not in the taxonomy")
        elif not valid_box(o.get("box_2d")):
            _fail("a box is not inside the frame")


def check_review_for(n_labels: int) -> Any:
    def check(result: ProviderResult) -> None:
        reviews = result.output.get("reviews")
        missed = result.output.get("missed")
        if not isinstance(reviews, list) or not isinstance(missed, list):
            _fail("reviews or missed is not a list")
            return
        ids = sorted(int(r.get("id", 0)) for r in reviews if isinstance(r, Mapping))
        if ids != list(range(1, n_labels + 1)):
            _fail("there is not exactly one review per label")
        for r in reviews:
            if r.get("verdict") not in VERDICTS:
                _fail("a verdict is not one of the verdicts")
            if r.get("correct_class") not in (*TAXONOMY, "none"):
                _fail("a correct_class is not in the taxonomy")
        for m in missed:
            if not isinstance(m, Mapping) or m.get("class") not in TAXONOMY:
                _fail("a missed class is not in the taxonomy")
            elif not valid_box(m.get("box_2d")):
                _fail("a missed box is not inside the frame")

    return check


# --- Selection --------------------------------------------------------------


@dataclass(frozen=True)
class Selection:
    frames: list[dict[str, Any]]
    per_class: dict[str, int]
    short: dict[str, int]  # target classes below their quota, and by how many


def select_stratified(
    tagged: Sequence[Mapping[str, Any]],
    *,
    total: int = 200,
    quota: int = 20,
    max_per_video: int = 8,
    seed: int = 7,
) -> Selection:
    """A deterministic stratified pick.

    Target classes are filled rarest first, up to `quota` frames each, preferring
    frames that show more target classes; then the rest is filled round-robin over
    room types. At most one frame per clip and `max_per_video` per video, so no
    tour dominates.
    """
    rng = random.Random(seed)  # noqa: S311 (a reproducible sample, not security)
    pool = [dict(f) for f in tagged]
    rng.shuffle(pool)
    chosen: list[dict[str, Any]] = []
    clips: set[str] = set()
    videos: Counter[str] = Counter()
    counts: Counter[str] = Counter()

    def can_take(f: Mapping[str, Any]) -> bool:
        return (
            f["clip_path"] not in clips
            and videos[str(f["video_id"])] < max_per_video
            and len(chosen) < total
        )

    def take(f: dict[str, Any]) -> None:
        chosen.append(f)
        clips.add(str(f["clip_path"]))
        videos[str(f["video_id"])] += 1
        counts.update(set(f["present"]))

    supply = Counter(c for f in pool for c in set(f["present"]) if c in TARGETS)
    for target in sorted(TARGETS, key=lambda c: (supply[c], c)):
        options = sorted(
            (f for f in pool if target in f["present"]),
            key=lambda f: -len(set(f["present"]) & set(TARGETS)),
        )
        for f in options:
            if counts[target] >= quota:
                break
            if can_take(f):
                take(f)

    by_room: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in pool:
        by_room[str(f["room_type"])].append(f)
    rooms = sorted(by_room)
    while len(chosen) < total and any(by_room.values()):
        for room in rooms:
            while by_room[room]:
                f = by_room[room].pop()
                if can_take(f):
                    take(f)
                    break
    short = {c: quota - counts[c] for c in TARGETS if counts[c] < quota}
    return Selection(chosen, {c: counts[c] for c in CLASSES}, short)


# --- Disagreements and truth ------------------------------------------------


def disagreements(
    labels: Sequence[Mapping[str, Any]], review: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Every label Claude did not agree with, and every object it says was missed."""
    out: list[dict[str, Any]] = []
    verdict = {int(r["id"]): r for r in review["reviews"]}
    for i, o in enumerate(labels, start=1):
        r = verdict[i]
        if r["verdict"] != "agree":
            out.append(
                {
                    "item": f"label-{i}",
                    "class": o["class"],
                    "box_2d": o["box_2d"],
                    "verdict": r["verdict"],
                    "suggested_class": r["correct_class"],
                }
            )
    for k, m in enumerate(review["missed"], start=1):
        out.append(
            {
                "item": f"missed-{k}",
                "class": m["class"],
                "box_2d": m["box_2d"],
                "verdict": "missed",
                "suggested_class": m["class"],
            }
        )
    return out


HAND_DECISIONS = ("keep", "drop", "relabel")


def final_objects(
    labels: Sequence[Mapping[str, Any]],
    review: Mapping[str, Any],
    decisions: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[list[dict[str, Any]], int]:
    """The frame's objects after review: labels both models agree on, plus each
    disagreement as the hand-check decided. Without decisions, disagreements are
    left out and counted as unresolved."""
    verdict = {int(r["id"]): r for r in review["reviews"]}
    out: list[dict[str, Any]] = []
    unresolved = 0
    items = [
        (f"label-{i}", o, verdict[i]["verdict"] == "agree") for i, o in enumerate(labels, start=1)
    ]
    items += [(f"missed-{k}", m, False) for k, m in enumerate(review["missed"], start=1)]
    for key, obj, agreed in items:
        if agreed:
            out.append({"class": obj["class"], "box_2d": obj["box_2d"], "source": "agreed"})
            continue
        d = (decisions or {}).get(key)
        if d is None:
            unresolved += 1
        elif d["decision"] == "keep":
            out.append({"class": obj["class"], "box_2d": obj["box_2d"], "source": "hand"})
        elif d["decision"] == "relabel" and d.get("class") in TAXONOMY:
            out.append({"class": d["class"], "box_2d": obj["box_2d"], "source": "hand"})
    return out, unresolved


# --- Listing score ----------------------------------------------------------


def listed_classes(items: Sequence[Mapping[str, Any]]) -> tuple[set[str], list[str]]:
    """Classes a listing names (by its name or its other names), and names that
    map to no class."""
    found: set[str] = set()
    other: list[str] = []
    for item in items:
        names = [str(item["name"]), *[str(p) for p in item.get("prompts", [])]]
        classes = {c for c in (class_of(n) for n in names) if c}
        if classes:
            found.add(sorted(classes)[0] if len(classes) > 1 else next(iter(classes)))
        else:
            other.append(normalise(str(item["name"])))
    return found, other


def score_listing(
    truth: Mapping[str, set[str]], listed: Mapping[str, set[str]], classes: Sequence[str] = CLASSES
) -> dict[str, dict[str, Any]]:
    """Per class over frames: recall (frames with the class where it was listed) and
    precision (frames where it was listed that have it)."""
    out: dict[str, dict[str, Any]] = {}
    frames = [f for f in truth if f in listed]
    for c in (*classes, "all"):
        tp = fp = fn = 0
        for f in frames:
            want = truth[f] if c == "all" else truth[f] & {c}
            got = listed[f] & set(classes) if c == "all" else listed[f] & {c}
            tp += len(want & got)
            fp += len(got - want)
            fn += len(want - got)
        if tp + fn == 0 and fp == 0:
            continue
        out[c] = {
            "frames_with_class": tp + fn,
            "listed_right": tp,
            "missed": fn,
            "listed_wrongly": fp,
            "recall": round(tp / (tp + fn), 2) if tp + fn else None,
            "precision": round(tp / (tp + fp), 2) if tp + fp else None,
        }
    return out


# --- Ledgers ----------------------------------------------------------------


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def utc_month() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m")


class MonthlySpendLedger:
    """A hard monthly cap on one provider's spend, kept in a JSON-lines file so it
    holds across runs.

    The gateway reserves each call's worst case here before the call. What was
    really billed is recorded by `BilledProvider`, including calls whose output is
    later rejected (the gateway settles those at zero, but they were billed).
    """

    def __init__(self, path: Path, cap_micro_inr: int, month: str | None = None) -> None:
        self._path = path
        self.cap = cap_micro_inr
        self.month = month or utc_month()
        self._reserved = 0
        self._lock = asyncio.Lock()

    def spent(self) -> int:
        return sum(
            int(r["micro_inr"]) for r in read_jsonl(self._path) if r.get("month") == self.month
        )

    def record(self, micro_inr: int, task: str) -> None:
        if micro_inr > 0:
            append_jsonl(self._path, {"month": self.month, "micro_inr": micro_inr, "task": task})

    async def reserve(self, user_id: str | None, amount_micro_inr: int) -> Reservation:
        from sajao_gateway import SpendCapExceededError

        async with self._lock:
            if self.spent() + self._reserved + amount_micro_inr > self.cap:
                raise SpendCapExceededError("global")
            self._reserved += amount_micro_inr
            return Reservation(datetime.date.today(), user_id, amount_micro_inr)

    async def settle(self, reservation: Reservation, actual_micro_inr: int) -> None:
        async with self._lock:
            self._reserved -= reservation.amount_micro_inr


class BilledProvider:
    """Wraps a provider so every billed call is recorded in a monthly ledger. A
    call that fails inside the provider after it may have been billed (a refusal
    or a cut-off answer) is recorded at its estimate, to stay on the safe side."""

    def __init__(self, inner: Any, ledger: MonthlySpendLedger) -> None:
        self._inner = inner
        self._ledger = ledger
        self.name = inner.name
        self.model = inner.model
        self.modalities = inner.modalities
        self.timeout_seconds = inner.timeout_seconds
        self.max_concurrency = getattr(inner, "max_concurrency", 2)
        if hasattr(inner, "max_attempts"):
            self.max_attempts = inner.max_attempts

    def estimate_cost_micro_inr(self, request: Any) -> int:
        return int(self._inner.estimate_cost_micro_inr(request))

    async def call(self, request: Any) -> ProviderResult:
        try:
            result: ProviderResult = await self._inner.call(request)
        except InvalidOutputError:
            self._ledger.record(self.estimate_cost_micro_inr(request), request.task)
            raise
        self._ledger.record(result.cost_micro_inr, request.task)
        return result
