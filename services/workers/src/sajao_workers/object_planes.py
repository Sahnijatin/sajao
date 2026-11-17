"""Vertical AR planes that belong to things in the room, not to its walls.

ARKit and ARCore track any flat upright surface: a fridge's side, a cabinet
front, a table's edge. Taken for walls, they make false corners and rooms
that never close (the first real scan joined fridge sides into its walls).
This module says which vertical planes are faces of an object, so the
measurement code can leave them out.

Evidence for an object is geometry, never a model's guess at a size:

- live detections from the phone, whose box centre was hit-tested onto the
  AR world (`world`): a cluster of confident hits of one large kind is one
  object, at those points;
- objects the twin placed, with their fused 3D boxes.

A vertical plane is an object face when it lies against such an object and
stays below it; it is never one when the phone classed it as a wall (or a
door or a window), when it reaches the ceiling, or when it is longer than any
piece of furniture. The planes document goes in (sajao-planes-1) and a
filtered copy comes out, with what was removed and why.
"""

import copy
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, TypedDict

from sajao_workers.ar_measurements import Plane, _ceiling, _floor, read_planes

# Detections at or above this score count as evidence.
MIN_SCORE = 0.5
# Hits of one kind closer than this (from above) are one object.
CLUSTER_M = 0.5
# Fewer hits than this are a passing misfire, not an object.
MIN_HITS = 5
# Kinds of thing large enough to give the phone an upright plane (the live
# detector's names). Small things on a counter must never claim the wall behind it.
LARGE_KINDS = frozenset(
    {
        "refrigerator",
        "oven",
        "microwave",
        "sink",
        "couch",
        "bed",
        "dining table",
        "chair",
        "tv",
        "toilet",
        "bench",
    }
)
# A face is within this of the detection hits (hits land on the front, the sides run back).
REACH_M = 0.5
# Hits land near the middle of the thing: its faces end at most this far above them.
ABOVE_HIT_M = 1.0
# A face lies inside a placed box grown by this, and ends at most this far above its top.
BOX_MARGIN_M = 0.15
BOX_ABOVE_M = 0.3
# A plane reaching this close to the ceiling is a wall.
CEILING_NEAR_M = 0.3
# Without a ceiling plane, a plane reaching this high above the floor is a wall.
WALL_TOP_M = 2.3
# No piece of furniture has a face longer than this.
MAX_FACE_M = 2.5
KEEP_CLASSES = ("wall", "door", "window")

XZ = tuple[float, float]


class ObjectEvidence(TypedDict):
    """One thing in the room: its kind, points on it from above (x, z), and how high it goes."""

    label: str
    points: list[XZ]
    # Height in the AR world (y up) above which none of its faces reach.
    top_y: float
    # "box": the faces lie inside the points' rectangle; "hits": within reach of the points.
    kind: str


def objects_from_detections(detections: Iterable[Mapping[str, Any]]) -> list[ObjectEvidence]:
    """Objects from the phone's live detections: clusters of confident hits of one large kind."""
    by_kind: dict[str, list[tuple[float, float, float]]] = {}
    for d in detections:
        world = d.get("world")
        label = str(d.get("detector_class", ""))
        if world is None or label not in LARGE_KINDS or float(d.get("score", 0)) < MIN_SCORE:
            continue
        by_kind.setdefault(label, []).append(
            (float(world["x_m"]), float(world["y_m"]), float(world["z_m"]))
        )
    found: list[ObjectEvidence] = []
    for label, hits in sorted(by_kind.items()):
        for cluster in _clusters(hits):
            if len(cluster) < MIN_HITS:
                continue
            heights = sorted(h[1] for h in cluster)
            found.append(
                {
                    "label": label,
                    "points": [(h[0], h[2]) for h in cluster],
                    "top_y": heights[len(heights) // 2] + ABOVE_HIT_M,
                    "kind": "hits",
                }
            )
    return found


def _clusters(
    hits: Sequence[tuple[float, float, float]],
) -> list[list[tuple[float, float, float]]]:
    """Single-linkage groups of hits within CLUSTER_M of each other, seen from above."""
    unseen = set(range(len(hits)))
    groups = []
    while unseen:
        stack = [unseen.pop()]
        group = []
        while stack:
            i = stack.pop()
            group.append(hits[i])
            near = [
                j
                for j in unseen
                if math.hypot(hits[i][0] - hits[j][0], hits[i][2] - hits[j][2]) <= CLUSTER_M
            ]
            for j in near:
                unseen.remove(j)
            stack.extend(near)
        groups.append(group)
    return groups


def objects_from_boxes(objects: Iterable[Mapping[str, Any]]) -> list[ObjectEvidence]:
    """Objects the twin placed (the objects step's output, AR world, y up), by their boxes."""
    found: list[ObjectEvidence] = []
    for obj in objects:
        up = int(obj.get("up_axis", 1))
        if up != 1:
            continue  # only the AR world, where y is up
        box = obj["box"]
        c = [float(v) for v in box["center"]]
        yaw = math.radians(float(box["yaw_deg"]))
        length, width, height = (float(box[k]["value_m"]) for k in ("length", "width", "height"))
        corners = []
        for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            du, dv = u * length / 2, v * width / 2
            # The objects step's yaw: about the up axis, from x towards z.
            corners.append(
                (
                    c[0] + du * math.cos(yaw) - dv * math.sin(yaw),
                    c[2] + du * math.sin(yaw) + dv * math.cos(yaw),
                )
            )
        found.append(
            {
                "label": str(obj.get("category") or obj.get("label") or "object"),
                "points": corners,
                "top_y": c[1] + height / 2,
                "kind": "box",
            }
        )
    return found


def _segment(plane: Plane) -> tuple[XZ, XZ] | None:
    """The plane seen from above: a segment along its horizontal direction."""
    length = math.hypot(plane.normal[0], plane.normal[2])
    if length < 0.5:
        return None
    n = (plane.normal[0] / length, plane.normal[2] / length)
    t = (-n[1], n[0])
    along = [p[0] * t[0] + p[2] * t[1] for p in plane.points]
    c = plane.centre
    offset = c[0] * n[0] + c[2] * n[1]
    low, high = min(along), max(along)
    return (
        (n[0] * offset + t[0] * low, n[1] * offset + t[1] * low),
        (n[0] * offset + t[0] * high, n[1] * offset + t[1] * high),
    )


def _point_to_segment(p: XZ, a: XZ, b: XZ) -> float:
    dx, dz = b[0] - a[0], b[1] - a[1]
    span = dx * dx + dz * dz
    s = 0.0 if span == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dz) / span))
    return math.hypot(p[0] - a[0] - s * dx, p[1] - a[1] - s * dz)


def _outside_rectangle(p: XZ, corners: Sequence[XZ]) -> float:
    """How far a point is outside a convex outline (0 inside)."""
    inside = True
    for i in range(len(corners)):
        a, b = corners[i], corners[(i + 1) % len(corners)]
        cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        if cross < 0:
            inside = False
    if inside:
        return 0.0
    return min(
        _point_to_segment(p, corners[i], corners[(i + 1) % len(corners)])
        for i in range(len(corners))
    )


def _ccw(corners: Sequence[XZ]) -> list[XZ]:
    area = sum(
        corners[i][0] * corners[(i + 1) % len(corners)][1]
        - corners[(i + 1) % len(corners)][0] * corners[i][1]
        for i in range(len(corners))
    )
    return list(corners) if area >= 0 else list(reversed(corners))


def _owner(
    segment: tuple[XZ, XZ], top_y: float, objects: Sequence[ObjectEvidence]
) -> tuple[ObjectEvidence, float] | None:
    """The object this face belongs to, and how far it is from it."""
    a, b = segment
    best: tuple[ObjectEvidence, float] | None = None
    for obj in objects:
        if obj["kind"] == "box":
            if top_y > obj["top_y"] + BOX_ABOVE_M:
                continue
            outline = _ccw(obj["points"])
            samples = [
                (a[0] + (b[0] - a[0]) * s / 4, a[1] + (b[1] - a[1]) * s / 4) for s in range(5)
            ]
            gap = max(_outside_rectangle(p, outline) for p in samples)
            if gap > BOX_MARGIN_M:
                continue
        else:
            if top_y > obj["top_y"]:
                continue
            gap = min(_point_to_segment(p, a, b) for p in obj["points"])
            if gap > REACH_M:
                continue
        if best is None or gap < best[1]:
            best = (obj, gap)
    return best


class Removed(TypedDict):
    index: int  # in the input document's `planes`
    reason: str  # "object_face"
    object: str
    gap_m: float


class Filtered(TypedDict):
    planes: dict[str, Any]  # the document without the removed planes
    removed: list[Removed]


def _wall_top(planes: Sequence[Plane]) -> float:
    """Height in the AR world from which a plane counts as reaching the ceiling."""
    floor_y, _ = _floor(planes)
    ceiling_y = _ceiling(planes, floor_y)
    if ceiling_y is not None:
        return ceiling_y - CEILING_NEAR_M
    if floor_y is not None:
        return floor_y + WALL_TOP_M
    return math.inf


def _face_of(
    plane: Plane, wall_top: float, objects: Sequence[ObjectEvidence]
) -> tuple[ObjectEvidence, float] | None:
    """The object this plane is a face of, and how far from it; None for anything else."""
    if plane.kind != "vertical" or plane.classification in KEEP_CLASSES:
        return None
    segment = _segment(plane)
    top_y = max(p[1] for p in plane.points)
    if segment is None or top_y >= wall_top or math.dist(segment[0], segment[1]) > MAX_FACE_M:
        return None
    return _owner(segment, top_y, objects)


def remove_object_planes(
    planes_doc: Mapping[str, Any], objects: Sequence[ObjectEvidence]
) -> Filtered:
    """The planes document without the vertical planes that are faces of an object.

    Pure: the input is not changed. Horizontal planes are always kept."""
    raw = list(planes_doc.get("planes", []))
    parsed = [read_planes({"planes": [r]}) for r in raw]
    wall_top = _wall_top([p for one in parsed for p in one])

    removed: list[Removed] = []
    kept = []
    for index, (entry, one) in enumerate(zip(raw, parsed, strict=True)):
        owner = _face_of(one[0], wall_top, objects) if one else None
        if owner is None:
            kept.append(entry)
            continue
        removed.append(
            {
                "index": index,
                "reason": "object_face",
                "object": owner[0]["label"],
                "gap_m": round(owner[1], 3),
            }
        )
    out = copy.deepcopy(dict(planes_doc))
    out["planes"] = copy.deepcopy(kept)
    return {"planes": out, "removed": removed}


def object_plane_drop(
    planes_doc: Mapping[str, Any], objects: Sequence[ObjectEvidence]
) -> Callable[[Sequence[Plane]], list[Plane]]:
    """The same rule as a filter over parsed planes, for a shell builder that takes one
    (`drop` in the measured shell): it keeps every plane that is not an object face."""
    wall_top = _wall_top(read_planes(planes_doc))

    def drop(planes: Sequence[Plane]) -> list[Plane]:
        return [p for p in planes if _face_of(p, wall_top, objects) is None]

    return drop
