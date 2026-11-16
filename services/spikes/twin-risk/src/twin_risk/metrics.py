"""Matching predicted object boxes to annotated ground truth and summarising errors."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from twin_risk.geometry import UprightBox, center_distance, iou_3d

# The 17 furniture classes annotated in ARKitScenes.
ARKIT_CLASSES: tuple[str, ...] = (
    "cabinet",
    "refrigerator",
    "shelf",
    "stove",
    "bed",
    "sink",
    "washer",
    "toilet",
    "bathtub",
    "oven",
    "dishwasher",
    "fireplace",
    "stool",
    "chair",
    "table",
    "tv_monitor",
    "sofa",
)

_SYNONYMS: dict[str, str] = {
    "tv": "tv_monitor",
    "television": "tv_monitor",
    "monitor": "tv_monitor",
    "couch": "sofa",
    "armchair": "chair",
    "office chair": "chair",
    "desk": "table",
    "coffee table": "table",
    "dining table": "table",
    "side table": "table",
    "bookshelf": "shelf",
    "bookcase": "shelf",
    "wardrobe": "cabinet",
    "dresser": "cabinet",
    "nightstand": "cabinet",
    "drawer": "cabinet",
    "cupboard": "cabinet",
    "fridge": "refrigerator",
    "washing machine": "washer",
    "ottoman": "stool",
    "bench": "stool",
    "tub": "bathtub",
}


def canonical_class(name: str) -> str | None:
    """Map a free-text object name to an ARKitScenes class, or None if it has none."""
    key = " ".join(name.lower().replace("_", " ").split())
    if key.replace(" ", "_") in ARKIT_CLASSES:
        return key.replace(" ", "_")
    if key in _SYNONYMS:
        return _SYNONYMS[key]
    # Multi-word detector phrases such as "wooden chair": use the last known word.
    for word in reversed(key.split()):
        if word in ARKIT_CLASSES:
            return word
        if word in _SYNONYMS:
            return _SYNONYMS[word]
    return None


@dataclass(frozen=True)
class LabelledBox:
    label: str
    box: UprightBox


@dataclass(frozen=True)
class Match:
    gt_index: int
    pred_index: int
    iou: float
    center_error_m: float
    size_errors_m: tuple[float, float, float]
    size_errors_rel: tuple[float, float, float]


def greedy_match(
    preds: Sequence[LabelledBox],
    gts: Sequence[LabelledBox],
    min_iou: float = 0.25,
    class_aware: bool = True,
) -> list[Match]:
    """One-to-one matching, highest IoU first."""
    pairs: list[tuple[float, int, int]] = []
    for gi, g in enumerate(gts):
        for pi, p in enumerate(preds):
            if class_aware and canonical_class(p.label) != canonical_class(g.label):
                continue
            iou = iou_3d(p.box, g.box)
            if iou >= min_iou:
                pairs.append((iou, gi, pi))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_g: set[int] = set()
    used_p: set[int] = set()
    matches: list[Match] = []
    for iou, gi, pi in pairs:
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        gs, ps = gts[gi].box.sorted_sizes(), preds[pi].box.sorted_sizes()
        abs_err = (abs(ps[0] - gs[0]), abs(ps[1] - gs[1]), abs(ps[2] - gs[2]))
        rel_err = tuple(e / g if g > 0 else 0.0 for e, g in zip(abs_err, gs, strict=True))
        matches.append(
            Match(
                gi,
                pi,
                iou,
                center_distance(preds[pi].box, gts[gi].box),
                abs_err,
                (rel_err[0], rel_err[1], rel_err[2]),
            )
        )
    return sorted(matches, key=lambda m: m.gt_index)


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def summarise(
    preds: Sequence[LabelledBox], gts: Sequence[LabelledBox], min_iou: float = 0.25
) -> dict[str, float | int | None]:
    """Recall, precision and median errors for one scene.

    Only predictions that map to an annotated class count towards precision;
    extra objects such as lamps or plants are named but not annotated.
    """
    comparable = [p for p in preds if canonical_class(p.label) is not None]
    aware = greedy_match(comparable, gts, min_iou, class_aware=True)
    agnostic = greedy_match(comparable, gts, min_iou, class_aware=False)
    loose = greedy_match(comparable, gts, 0.05, class_aware=True)
    n_gt = len(gts)
    return {
        "gt_objects": n_gt,
        "predicted_objects": len(preds),
        "predicted_annotated_classes": len(comparable),
        "recall_class_iou25": len(aware) / n_gt if n_gt else None,
        "recall_any_class_iou25": len(agnostic) / n_gt if n_gt else None,
        "recall_class_iou05": len(loose) / n_gt if n_gt else None,
        "precision_class_iou25": len(aware) / len(comparable) if comparable else None,
        "median_iou": _median([m.iou for m in aware]),
        "median_center_error_m": _median([m.center_error_m for m in loose]),
        "median_length_error_m": _median([m.size_errors_m[0] for m in loose]),
        "median_width_error_m": _median([m.size_errors_m[1] for m in loose]),
        "median_height_error_m": _median([m.size_errors_m[2] for m in loose]),
        "median_size_error_rel": _median([sum(m.size_errors_rel) / 3.0 for m in loose]),
    }
