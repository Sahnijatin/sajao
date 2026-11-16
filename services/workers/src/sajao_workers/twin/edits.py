"""Twin edits on the server: apply a design's edits to a twin and plan the splat change.

`apply_edits` follows the same rules as `applyEdits` in packages/schemas (twin.ts):
edits are applied in order to a copy, moved and turned boxes keep their measured
size, replaced and added items take their catalog size, and an edit that cannot
apply is skipped with a reason, never half applied. No model makes or changes an
edit; the user or the solver does.

`splat_ops` turns the applied twin into what the splat needs: the objects to take
out (removed, replaced and moved ones), and for each moved object a rigid transform
in the splat's world, so its own Gaussians are put back where the user moved it.
Added and replacing catalog products have no Gaussians: the app draws them.
"""

import copy
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from sajao_workers.twin.removal import object_index

ADDED_CATEGORY = "catalog_product"


@dataclass(frozen=True)
class EditProblem:
    edit_id: str
    reason: str


@dataclass
class AppliedTwin:
    twin: dict[str, Any]
    replacements: dict[str, str] = field(default_factory=dict)
    added: list[str] = field(default_factory=list)
    problems: list[EditProblem] = field(default_factory=list)


def apply_edits(twin: Mapping[str, Any], edits: Sequence[Mapping[str, Any]]) -> AppliedTwin:
    out = AppliedTwin(copy.deepcopy(dict(twin)))
    objects = {o["id"]: o for o in out.twin["objects"]}
    seen: set[str] = set()
    for edit in edits:
        eid = edit["id"]
        if eid in seen:
            out.problems.append(EditProblem(eid, "duplicate edit id"))
            continue
        seen.add(eid)
        op = edit["op"]
        if op in ("move", "rotate", "remove", "replace"):
            target = objects.get(edit["object_id"])
            if target is None:
                out.problems.append(EditProblem(eid, "unknown object"))
                continue
            if target["state"] == "remove":
                out.problems.append(EditProblem(eid, "object was removed"))
                continue
            box = target["box"]
            if op == "move":
                box["center"] = dict(edit["to"])
                target["state"] = "move" if target["state"] == "keep" else target["state"]
            elif op == "rotate":
                box["yaw_deg"] = edit["yaw_deg"]
                target["state"] = "move" if target["state"] == "keep" else target["state"]
            elif op == "remove":
                target["state"] = "remove"
                out.replacements.pop(target["id"], None)
            else:
                target["state"] = "replace"
                for side in ("width", "depth", "height"):
                    box[side] = dict(edit["product_size"][side])
                out.replacements[target["id"]] = edit["product_id"]
        elif op == "add":
            if eid in objects:
                out.problems.append(EditProblem(eid, "id already used by an object"))
                continue
            size = edit["product_size"]
            added = {
                "id": eid,
                "category": ADDED_CATEGORY,
                "label": edit["label"],
                "box": {
                    "center": dict(edit["to"]),
                    "yaw_deg": edit["yaw_deg"],
                    **{side: dict(size[side]) for side in ("width", "depth", "height")},
                },
                "detection": {"source": "user", "confidence": 1},
                "views": [],
                "catalog_matches": [
                    {"product_id": edit["product_id"], "similarity": 1, "fits_box": True}
                ],
                "state": "keep",
            }
            out.twin["objects"].append(added)
            objects[eid] = added
            out.added.append(eid)
        elif op == "restyle_surface":
            surface = next(
                (s for s in out.twin["shell"]["surfaces"] if s["id"] == edit["surface_id"]), None
            )
            if surface is None:
                out.problems.append(EditProblem(eid, "unknown surface"))
                continue
            surface["material"] = copy.deepcopy(dict(edit["material"]))
    return out


def _matrix(q: Sequence[float]) -> np.ndarray:
    """Rotation matrix of a unit quaternion (x, y, z, w), the twin's order."""
    x, y, z, w = (float(v) for v in q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def space_transform(
    keyframes: Sequence[Mapping[str, Any]], manifest_frames: Sequence[Mapping[str, Any]]
) -> np.ndarray:
    """4x4 transform from the splat's world (the AR world) to the twin's space frame.

    Each keyframe's pose is stored both ways (camera to world in the manifest, and
    position plus rotation in the twin), so one keyframe fixes the transform; more
    are averaged. Rigid, no scale.
    """
    world = {f["keyframe_id"]: np.asarray(f["c2w"], dtype=np.float64) for f in manifest_frames}
    rotations, pairs = [], []
    for k in keyframes:
        if k["id"] not in world:
            continue
        c2w = world[k["id"]]
        position = np.array([k["pose"]["position"][a] for a in ("x_m", "y_m", "z_m")])
        rotations.append(_matrix(k["pose"]["rotation"]) @ c2w[:3, :3].T)
        pairs.append((c2w[:3, 3], position))
    if not pairs:
        raise ValueError("no keyframe is in both the twin and the frames manifest")
    u, _, vt = np.linalg.svd(np.sum(rotations, axis=0))
    rotation = u @ np.diag([1.0, 1.0, float(np.sign(np.linalg.det(u @ vt)))]) @ vt
    shift = np.mean([q - rotation @ p for p, q in pairs], axis=0)
    out = np.eye(4)
    out[:3, :3] = rotation
    out[:3, 3] = shift
    return out


def _box_pose(box: Mapping[str, Any]) -> np.ndarray:
    c = box["center"]
    t = math.radians(float(box["yaw_deg"]))
    pose = np.eye(4)
    pose[:3, :3] = np.array(
        [[math.cos(t), -math.sin(t), 0.0], [math.sin(t), math.cos(t), 0.0], [0.0, 0.0, 1.0]]
    )
    pose[:3, 3] = [c["x_m"], c["y_m"], c["z_m"]]
    return pose


def splat_ops(
    before: Mapping[str, Any], after: Mapping[str, Any], world_to_space: np.ndarray
) -> dict[str, Any]:
    """Objects to take out of the splat (1-based labels) and rigid moves in its world."""
    old = {o["id"]: o for o in before["objects"]}
    remove: list[int] = []
    moves: dict[int, list[list[float]]] = {}
    space_to_world = np.linalg.inv(world_to_space)
    for obj in after["objects"]:
        if obj["state"] == "keep" or obj["id"] not in old:
            continue
        try:
            index = object_index(obj["id"])
        except ValueError:
            continue  # not from the objects step, so it has no Gaussians of its own
        remove.append(index)
        if obj["state"] == "move":
            in_space = _box_pose(obj["box"]) @ np.linalg.inv(_box_pose(old[obj["id"]]["box"]))
            moves[index] = (space_to_world @ in_space @ world_to_space).tolist()
    return {"remove": sorted(remove), "moves": moves}
