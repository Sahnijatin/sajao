"""Doors and windows for the AR measurements, from the keyframes.

ARCore does not class planes, so an Android scan has no door or window of
its own. This is the path every phone uses: the vision model finds doors and
windows in the keyframes (a mask in each picture, nothing more), the rays
through each mask are cast from that keyframe's AR pose onto the walls the
phone measured, and code works out the width, height, sill and distance from
the corner. The model never sets a dimension: metres come from the wall
planes and the camera poses.

On an iPhone the result is also compared with the door and window planes
ARKit classed itself, as a cross-check of both.
"""

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np

from sajao_workers.ar_measurements import dimension
from sajao_workers.twin.shell import (
    Frame,
    OpeningKind,
    OpeningSighting,
    fuse_openings,
    sight_opening,
)
from sajao_workers.twin.space import AR_TO_Z_UP, Space

# Rays are kept below this height when the phone found no ceiling plane.
ASSUMED_CEILING_M = 3.5


def measured_space(measurements: Mapping[str, Any]) -> Space | None:
    """The measured walls as a space the keyframes' rays can be cast into.

    None when the phone found no floor or no wall: there is nothing to cast onto.
    """
    floor_y = measurements.get("floor_y_m")
    walls = measurements.get("walls") or []
    if floor_y is None or not walls:
        return None
    ceiling = measurements.get("ceiling_height") or {"value_m": ASSUMED_CEILING_M}
    # Positional: rotation, origin, turn, shell, extent.
    return Space(
        AR_TO_Z_UP,
        np.array([0.0, 0.0, float(floor_y)]),
        0.0,
        {"walls": walls, "ceiling_height": ceiling},
        "part",
    )


def openings_from_keyframes(
    measurements: Mapping[str, Any],
    masks: Iterable[tuple[OpeningKind, np.ndarray, Frame]],
) -> list[dict[str, Any]]:
    """Doors and windows on the measured walls, from masks in posed keyframes.

    Each mask is (kind, the mask at its keyframe's size, that keyframe's
    geometry). An opening must be seen in at least two keyframes.
    """
    space = measured_space(measurements)
    if space is None:
        return []
    sightings: list[OpeningSighting] = []
    for kind, mask, frame in masks:
        seen = sight_opening(kind, mask, frame, space)
        if seen is not None:
            sightings.append(seen)
    walls = {w["id"]: w for w in measurements["walls"]}
    openings = []
    for fused in fuse_openings(sightings, "image"):
        wall = walls[fused["wall_id"]]
        start = fused["offset"]["value_m"]
        width = fused["width"]["value_m"]
        opening: dict[str, Any] = {
            "id": fused["id"],
            "kind": fused["kind"],
            "wall_id": fused["wall_id"],
            "source": "keyframes",
            "width": dimension(width),
            "height": dimension(fused["height"]["value_m"]),
        }
        if "sill_height" in fused:
            opening["sill_height"] = dimension(fused["sill_height"]["value_m"])
        if wall["basis"] == "corner_to_corner":
            # From the nearest corner to the opening's nearest edge, as the tape sheet has it.
            far = wall["length"]["value_m"] - (start + width)
            opening["offset"] = dimension(max(0.0, min(start, far)))
        opening["along_m"] = [round(start, 3), round(start + width, 3)]
        openings.append(opening)
    return openings


def cross_check(
    classed: Iterable[Mapping[str, Any]],
    from_keyframes: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Each door or window the phone classed itself, beside the keyframe reading of it.

    Differences are keyframes minus the phone's own plane, in metres. An
    opening found by only one of the two is listed with `matched` false.
    """
    keyframes = list(from_keyframes)
    used: set[str] = set()
    rows = []
    for plane in classed:
        candidates = [
            k
            for k in keyframes
            if k["id"] not in used
            and k["kind"] == plane["kind"]
            and (plane.get("wall_id") is None or k["wall_id"] == plane["wall_id"])
        ]
        match = min(
            candidates,
            key=lambda k, plane=plane: abs(  # type: ignore[misc]
                k["width"]["value_m"] - plane["width"]["value_m"]
            ),
            default=None,
        )
        row: dict[str, Any] = {
            "kind": plane["kind"],
            "wall_id": plane.get("wall_id"),
            "classed": plane["id"],
            "matched": match is not None,
        }
        if match is not None:
            used.add(match["id"])
            row["keyframes"] = match["id"]
            for key in ("width", "height", "sill_height", "offset"):
                if key in plane and key in match:
                    row[f"{key}_difference_m"] = round(
                        match[key]["value_m"] - plane[key]["value_m"], 3
                    )
        rows.append(row)
    for extra in keyframes:
        if extra["id"] not in used:
            rows.append(
                {
                    "kind": extra["kind"],
                    "wall_id": extra["wall_id"],
                    "keyframes": extra["id"],
                    "matched": False,
                }
            )
    return rows
