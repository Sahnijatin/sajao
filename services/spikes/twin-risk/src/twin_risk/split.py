"""Deciding which object each splat Gaussian belongs to from per-view mask votes."""

from __future__ import annotations

from collections.abc import Mapping

BACKGROUND = 0


def decide_label(
    votes: Mapping[int, int], visible: int, min_observations: int = 3, min_ratio: float = 0.5
) -> int:
    """Object id for one Gaussian, or BACKGROUND.

    `votes` counts, per object id, the views where the Gaussian's centre was
    visible and fell inside that object's mask; `visible` counts all views
    where it was visible. An object wins only with enough views and a clear
    majority of them, so stray Gaussians default to the shell.
    """
    if visible < min_observations:
        return BACKGROUND
    best_id, best_votes = BACKGROUND, 0
    for obj_id, n in votes.items():
        if obj_id == BACKGROUND:
            continue
        if n > best_votes or (n == best_votes and obj_id < best_id):
            best_id, best_votes = obj_id, n
    if best_votes >= min_observations and best_votes / visible >= min_ratio:
        return best_id
    return BACKGROUND


def mask_iou(a: list[list[bool]], b: list[list[bool]]) -> float:
    inter = union = 0
    for row_a, row_b in zip(a, b, strict=True):
        for x, y in zip(row_a, row_b, strict=True):
            inter += x and y
            union += x or y
    return inter / union if union else 0.0
