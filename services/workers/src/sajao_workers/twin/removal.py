"""Object removal, fill B: which Gaussians go, and which frames get inpainted.

Ported from the SJ-116 spike and the removal comparison. Removing an object
takes out the Gaussians voted to it, anything else inside its box, and loose
Gaussians in a margin around it, but never the shell it stands on or against
(floor and nearby walls, fitted as planes). The GPU job then renders the hole
in every frame, inpaints a spread of those frames with LaMa, and fine-tunes
the splat on them. Pure NumPy, so the rule is tested without a GPU.
"""

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from sajao_workers.twin.geometry import UprightBox, horizontal_axes

BOX_PAD = 0.03  # of the box length: Gaussians this close count as inside
MARGIN = 0.15  # of the longer horizontal side: loose Gaussians around the object
SUPPORT_CLEARANCE = 0.04  # of the height: what sits this low belongs to the floor
MAX_INPAINT = 48
MIN_HOLE = 0.002  # of the frame; smaller holes are left to the fine-tune

_OBJECT_ID = re.compile(r"^o([1-9][0-9]*)$")


def object_index(object_id: str) -> int:
    """The splat label of a twin object: "o3" is the objects step's third object."""
    match = _OBJECT_ID.match(object_id)
    if match is None:
        raise ValueError(f"not a twin object id: {object_id!r}")
    return int(match.group(1))


def box_of(obj: Mapping[str, Any]) -> UprightBox:
    """The upright box of one object from the objects step's output."""
    box = obj["box"]
    return UprightBox(
        center=tuple(float(c) for c in box["center"]),  # type: ignore[arg-type]
        length=float(box["length"]["value_m"]),
        width=float(box["width"]["value_m"]),
        height=float(box["height"]["value_m"]),
        yaw=math.radians(float(box["yaw_deg"])),
        up_axis=int(obj["up_axis"]),
    )


def inside_box(points: np.ndarray, box: UprightBox, pad: float) -> np.ndarray:
    a, b = horizontal_axes(box.up_axis)
    rel = points - np.asarray(box.center)
    c, s = math.cos(box.yaw), math.sin(box.yaw)
    u = rel[:, a] * c + rel[:, b] * s
    v = -rel[:, a] * s + rel[:, b] * c
    h = rel[:, box.up_axis]
    inside: np.ndarray = (
        (np.abs(u) <= box.length / 2 + pad)
        & (np.abs(v) <= box.width / 2 + pad)
        & (np.abs(h) <= box.height / 2 + pad)
    )
    return inside


def _ransac_planes(
    points: np.ndarray, thr: float, max_planes: int = 4, iters: int = 400, min_frac: float = 0.03
) -> list[tuple[np.ndarray, np.ndarray]]:
    rng = np.random.default_rng(0)
    planes = []
    rest = points
    for _ in range(max_planes):
        if len(rest) < 100:
            break
        best = None
        for _ in range(iters):
            p = rest[rng.choice(len(rest), 3, replace=False)]
            n = np.cross(p[1] - p[0], p[2] - p[0])
            if np.linalg.norm(n) < 1e-9:
                continue
            n /= np.linalg.norm(n)
            inliers = np.abs((rest - p[0]) @ n) < thr
            if best is None or inliers.sum() > best.sum():
                best = inliers
        if best is None or best.sum() < max(100, min_frac * len(points)):
            break
        q = rest[best]
        centre = q.mean(0)
        _, _, vt = np.linalg.svd(q - centre, full_matrices=False)
        planes.append((vt[2], centre))
        rest = rest[~best]
    return planes


def _shell_planes(
    means: np.ndarray, opacity: np.ndarray, keep: np.ndarray, box: UprightBox, camera: np.ndarray
) -> tuple[list[tuple[np.ndarray, np.ndarray]], float]:
    """The object's support and nearby walls, fitted to Gaussians outside it."""
    up = np.zeros(3)
    up[box.up_axis] = 1.0
    diag = math.sqrt(box.length**2 + box.width**2 + box.height**2)
    region = inside_box(means, box, 0.6 * max(box.length, box.height)) & keep & (opacity > 0.3)
    thr = max(0.012 * diag, 0.01)
    centre = np.asarray(box.center)
    bottom = float(centre @ up) - box.height / 2
    planes = []
    for n, origin in _ransac_planes(means[region], thr):
        if np.dot(n, camera - origin) < 0:
            n = -n
        level = abs(float(np.dot(n, up)))
        if level > 0.9:  # floors are level: snap, and keep only the one it stands on
            if float(origin @ up) > bottom + 0.15 * box.height:
                continue
            n = up * np.sign(np.dot(n, up))
        elif level < 0.2:  # walls are vertical: snap, and keep only nearby ones
            n = n - up * float(np.dot(n, up))
            n /= np.linalg.norm(n)
            if abs(float((centre - origin) @ n)) > 0.5 * diag + max(box.length, box.width) / 2:
                continue
        else:
            continue
        planes.append((n, origin))
    return planes, thr


def removal_set(
    means: np.ndarray,
    opacity: np.ndarray,
    labels: np.ndarray,
    index: int,
    box: UprightBox,
    camera_centre: np.ndarray,
) -> np.ndarray:
    """Boolean mask of the Gaussians to remove for object `index`.

    `opacity` is in [0, 1]; `camera_centre` (the mean camera position) orients
    the shell planes towards the room.
    """
    up = np.zeros(3)
    up[box.up_axis] = 1.0
    voted = labels == index
    support = float(np.asarray(box.center) @ up) - box.height / 2
    above = (means @ up) > support + SUPPORT_CLEARANCE * box.height
    in_box = inside_box(means, box, BOX_PAD * max(box.length, 1e-3)) & above
    core = voted | in_box
    planes, thr = _shell_planes(means, opacity, ~core, box, camera_centre)
    on_shell = np.zeros(len(means), bool)
    for n, origin in planes:
        on_shell |= np.abs((means - origin) @ n) < 1.5 * thr
    margin = inside_box(means, box, MARGIN * max(box.length, box.width)) & above & ~on_shell
    result: np.ndarray = core | margin
    return result


def choose_frames(
    hole_fractions: Sequence[float], max_frames: int = MAX_INPAINT, min_hole: float = MIN_HOLE
) -> tuple[list[int], list[int]]:
    """Frames to inpaint (evenly spread over those that see the hole) and to drop.

    Frames that see the hole but are not inpainted are left out of the
    fine-tune, so the old object never comes back from them.
    """
    seen = [i for i, f in enumerate(hole_fractions) if f >= min_hole]
    step = max(1, math.ceil(len(seen) / max_frames))
    inpaint = seen[::step][:max_frames]
    drop = sorted(set(seen) - set(inpaint))
    return inpaint, drop
