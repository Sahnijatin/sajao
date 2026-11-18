"""The confidence level of a room's measurements, and whether fit may be claimed.

- `taped`: tape values the person entered check or set the lengths fit uses.
- `ar_measured`: the phone's AR planes or LiDAR measured them.
- `estimated`: a depth model guessed them from pictures (phones without AR,
  imported photos and videos). The app shows sizes with measure to confirm.

Fit is claimed only for taped and AR-measured rooms. One tape value fixes an
estimated room's scale but not its shape (on ARKitScenes rooms the other
walls were still off by a median 17%), so an estimated room is taped only
once every wall length fit needs has its own tape value.
"""

from collections.abc import Mapping
from typing import Any, Literal, TypedDict

Basis = Literal["ar_planes", "lidar", "depth_model"]
MEASURED: frozenset[str] = frozenset({"ar_planes", "lidar"})
FIT_LEVELS = frozenset({"taped", "ar_measured"})


class Confidence(TypedDict):
    level: str
    basis: str
    tape_values: int


def confidence_level(
    walls_from: Basis,
    *,
    tape_values: int = 0,
    tape_agrees: bool = True,
    walls_needing_tape: int = 2,
) -> Confidence:
    """The level for a room whose walls came from `walls_from`.

    `tape_agrees`: every tape value matched its wall within the bands.
    `walls_needing_tape`: tape values an estimated room needs before it counts
    as taped (two for a rectangle: one per pair of walls)."""
    if walls_from not in MEASURED and walls_from != "depth_model":
        raise ValueError(f"unknown measurement basis {walls_from!r}")
    if tape_values > 0 and not tape_agrees:
        # The tape says the room is not what was measured: claim nothing until measured again.
        return {"level": "estimated", "basis": walls_from, "tape_values": tape_values}
    if walls_from in MEASURED:
        if tape_values > 0:
            return {"level": "taped", "basis": "tape", "tape_values": tape_values}
        return {"level": "ar_measured", "basis": walls_from, "tape_values": 0}
    if tape_values >= walls_needing_tape:
        return {"level": "taped", "basis": "tape", "tape_values": tape_values}
    return {"level": "estimated", "basis": walls_from, "tape_values": tape_values}


def fit_claims(confidence: Mapping[str, Any] | None) -> bool:
    """Whether the app and the verifier may claim that something fits."""
    return confidence is not None and confidence.get("level") in FIT_LEVELS
