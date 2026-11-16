"""Per-SKU fidelity gate: thresholds and pass rules.

A view passes when silhouette IoU >= iou, colour difference <= de and embedding
similarity >= emb. A SKU passes when every clean view of its listing passes.
Thresholds are calibrated on wrong-SKU pairs (another product of the same
category scored against this listing's photos): choose the thresholds that keep
the wrong-SKU pass rate at or below `max_false_pass` and pass the most true pairs.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Thresholds:
    iou: float
    de: float
    emb: float

    def view_passes(self, v: dict[str, float]) -> bool:
        return bool(v["iou"] >= self.iou and v["de"] <= self.de and v["emb"] >= self.emb)


def sku_passes(views: list[dict[str, float]], th: Thresholds) -> bool:
    return bool(views) and all(th.view_passes(v) for v in views)


def pass_rate(skus: list[list[dict[str, float]]], th: Thresholds) -> float:
    return float(np.mean([sku_passes(v, th) for v in skus])) if skus else 0.0


def calibrate(
    true_skus: list[list[dict[str, float]]],
    wrong_skus: list[list[dict[str, float]]],
    max_false_pass: float = 0.05,
    iou_grid: Sequence[float] | None = None,
    de_grid: Sequence[float] | None = None,
    emb_grid: Sequence[float] | None = None,
) -> tuple[Thresholds, float, float]:
    """Grid search. Returns (thresholds, true pass rate, wrong pass rate).

    Ties on the true pass rate go to the strictest thresholds.
    """
    if iou_grid is None:
        iou_grid = [round(float(x), 3) for x in np.arange(0.60, 0.951, 0.025)]
    if de_grid is None:
        de_grid = [float(x) for x in np.arange(4.0, 30.1, 2.0)]
    if emb_grid is None:
        emb_grid = [round(float(x), 3) for x in np.arange(0.40, 0.951, 0.025)]
    best = None
    for i, d, e in itertools.product(iou_grid, de_grid, emb_grid):
        th = Thresholds(float(i), float(d), float(e))
        fp = pass_rate(wrong_skus, th)
        if fp > max_false_pass:
            continue
        tp = pass_rate(true_skus, th)
        key = (tp, i, -d, e)
        if best is None or key > best[0]:
            best = (key, th, tp, fp)
    if best is None:
        th = Thresholds(float(max(iou_grid)), float(min(de_grid)), float(max(emb_grid)))
        return th, pass_rate(true_skus, th), pass_rate(wrong_skus, th)
    return best[1], best[2], best[3]
