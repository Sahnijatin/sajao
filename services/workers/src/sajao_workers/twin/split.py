"""Which object each splat Gaussian belongs to, from per-view mask votes.

Ported from the SJ-116 spike. A Gaussian joins an object only when its centre
was visible in enough views and fell inside that object's mask in a clear
majority of them; anything else stays with the room shell (BACKGROUND).
"""

from collections.abc import Mapping

import numpy as np

BACKGROUND = 0
MIN_OBSERVATIONS = 3
MIN_RATIO = 0.5


def decide_label(
    votes: Mapping[int, int],
    visible: int,
    min_observations: int = MIN_OBSERVATIONS,
    min_ratio: float = MIN_RATIO,
) -> int:
    """Object id for one Gaussian, or BACKGROUND. Ties go to the lower id."""
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


def assign_labels(votes: np.ndarray, visible: np.ndarray) -> np.ndarray:
    """`decide_label` for every Gaussian at once.

    `votes` is (Gaussians, objects + 1) with column 0 for BACKGROUND; `visible`
    counts the views where each Gaussian's centre was visible.
    """
    objects = votes[:, 1:]
    best = objects.argmax(axis=1)  # first maximum: the lower id wins ties
    best_votes = objects[np.arange(len(objects)), best]
    ok = (
        (visible >= MIN_OBSERVATIONS)
        & (best_votes >= MIN_OBSERVATIONS)
        & (best_votes >= MIN_RATIO * np.maximum(visible, 1))
    )
    labels: np.ndarray = np.where(ok, best + 1, BACKGROUND).astype(np.int32)
    return labels
