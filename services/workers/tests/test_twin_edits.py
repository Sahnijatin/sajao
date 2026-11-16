"""Twin edits on the server: the same rules as applyEdits in packages/schemas, plus the
splat operations (which objects come out, and the rigid moves of the ones that move)."""

import copy
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sajao_workers.twin.edits import apply_edits, space_transform, splat_ops

FIXTURE = Path(__file__).parents[3] / "packages/schemas/fixtures/v1/valid/space-twin.json"
SIZE = {
    "width": {"value_m": 1.2, "source": "measured", "error_band_m": 0.01},
    "depth": {"value_m": 0.6, "source": "measured", "error_band_m": 0.01},
    "height": {"value_m": 0.8, "source": "measured", "error_band_m": 0.01},
}


def twin(objects: list[str] | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(FIXTURE.read_text())
    if objects is not None:  # worker-style ids, o1 ... on, as the objects step numbers them
        doc["objects"] = [{**doc["objects"][0], "id": oid} for oid in objects]
    return doc


def move(eid: str, oid: str, x: float, y: float, z: float = 0.42) -> dict[str, Any]:
    return {"id": eid, "op": "move", "by": "user", "object_id": oid,
            "to": {"x_m": x, "y_m": y, "z_m": z}}  # fmt: skip


def test_move_keeps_the_measured_size_and_never_changes_the_input() -> None:
    before = twin()
    original = copy.deepcopy(before)

    applied = apply_edits(before, [move("e1", "sofa-1", 3.0, 1.0)])

    sofa = applied.twin["objects"][0]
    assert sofa["box"]["center"] == {"x_m": 3.0, "y_m": 1.0, "z_m": 0.42}
    assert sofa["box"]["width"] == original["objects"][0]["box"]["width"]
    assert sofa["state"] == "move"
    assert before == original


def test_remove_replace_add_and_restyle_follow_the_schema_rules() -> None:
    edits: list[dict[str, Any]] = [
        {"id": "e1", "op": "remove", "by": "user", "object_id": "almirah-1"},
        {"id": "e2", "op": "replace", "by": "solver", "object_id": "sofa-1",
         "product_id": "p-42", "product_size": SIZE},
        {"id": "e3", "op": "add", "by": "user", "product_id": "p-7", "product_size": SIZE,
         "to": {"x_m": 1.0, "y_m": 1.0, "z_m": 0.4}, "yaw_deg": 0, "label": "Side table"},
        {"id": "e4", "op": "restyle_surface", "by": "user", "surface_id": "floor",
         "material": {"kind": "tile", "color": "#AABBCC"}},
    ]  # fmt: skip

    applied = apply_edits(twin(), edits)

    states = {o["id"]: o["state"] for o in applied.twin["objects"]}
    assert states == {"sofa-1": "replace", "almirah-1": "remove", "e3": "keep"}
    assert applied.twin["objects"][0]["box"]["width"] == SIZE["width"]
    assert applied.replacements == {"sofa-1": "p-42"}
    assert applied.added == ["e3"]
    floor = next(s for s in applied.twin["shell"]["surfaces"] if s["id"] == "floor")
    assert floor["material"]["kind"] == "tile"
    assert applied.problems == []


def test_edits_that_cannot_apply_are_skipped_with_a_reason() -> None:
    edits = [
        {"id": "e1", "op": "remove", "by": "user", "object_id": "almirah-1"},
        move("e2", "almirah-1", 1.0, 1.0),  # removed first
        move("e2", "sofa-1", 1.0, 1.0),  # duplicate edit id
        move("e3", "ghost", 1.0, 1.0),
    ]

    applied = apply_edits(twin(), edits)

    assert [(p.edit_id, p.reason) for p in applied.problems] == [
        ("e2", "object was removed"),
        ("e2", "duplicate edit id"),
        ("e3", "unknown object"),
    ]
    assert applied.twin["objects"][0]["state"] == "keep"


def test_the_space_transform_is_recovered_from_the_keyframes() -> None:
    turn = math.radians(30)
    turn_z = np.array(
        [[math.cos(turn), -math.sin(turn), 0], [math.sin(turn), math.cos(turn), 0], [0, 0, 1]]
    )
    rotation = turn_z @ np.array([[1.0, 0, 0], [0, 0, -1], [0, 1, 0]])  # AR y up to z up
    shift = np.array([1.5, -0.5, 0.2])
    manifest, keyframes = [], []
    for i, position in enumerate([[0, 1.4, 0], [2, 1.5, -1], [1, 1.3, 2]]):
        c2w = np.eye(4)
        c2w[:3, 3] = position
        manifest.append({"keyframe_id": f"k{i}", "c2w": c2w.tolist()})
        p = rotation @ np.asarray(position, dtype=float) + shift
        w = math.sqrt(1 + np.trace(rotation)) / 2
        q = [
            (rotation[2, 1] - rotation[1, 2]) / (4 * w),
            (rotation[0, 2] - rotation[2, 0]) / (4 * w),
            (rotation[1, 0] - rotation[0, 1]) / (4 * w),
            w,
        ]  # the twin stores each camera's rotation in the space frame (here identity in AR)
        position_m = {"x_m": p[0], "y_m": p[1], "z_m": p[2]}
        keyframes.append({"id": f"k{i}", "pose": {"position": position_m, "rotation": q}})

    s = space_transform(keyframes, manifest)

    assert np.allclose(s[:3, :3], rotation, atol=1e-6)
    assert np.allclose(s[:3, 3], shift, atol=1e-6)


def test_splat_ops_take_out_every_edited_object_and_move_the_moved_ones() -> None:
    before = twin(["o1", "o2", "o3", "o4"])
    edits = [
        {**move("e1", "o1", 3.0, 1.0), "to": {"x_m": 3.0, "y_m": 1.0, "z_m": 0.42}},
        {"id": "e2", "op": "rotate", "by": "user", "object_id": "o1", "yaw_deg": 90},
        {"id": "e3", "op": "remove", "by": "user", "object_id": "o2"},
        {"id": "e4", "op": "replace", "by": "user", "object_id": "o3",
         "product_id": "p-1", "product_size": SIZE},
    ]  # fmt: skip
    applied = apply_edits(before, edits)

    ops = splat_ops(before, applied.twin, np.eye(4))

    assert ops["remove"] == [1, 2, 3]
    assert set(ops["moves"]) == {1}
    m = np.asarray(ops["moves"][1])
    old = before["objects"][0]["box"]["center"]
    centre = m @ np.array([old["x_m"], old["y_m"], old["z_m"], 1.0])
    assert np.allclose(centre[:3], [3.0, 1.0, 0.42])
    # Turned 90 degrees about the vertical: +x of the object now points along +y.
    assert np.allclose(m[:3, :3] @ [1.0, 0, 0], [0, 1.0, 0], atol=1e-9)


def test_moves_are_expressed_in_the_splat_world() -> None:
    before = twin(["o1"])
    applied = apply_edits(before, [move("e1", "o1", 3.0, 1.0)])
    s = np.eye(4)
    s[:3, 3] = [1.0, 2.0, 0.0]  # the space frame is the splat world shifted

    m = np.asarray(splat_ops(before, applied.twin, s)["moves"][1])

    old = before["objects"][0]["box"]["center"]
    old_world = np.array([old["x_m"] - 1.0, old["y_m"] - 2.0, old["z_m"], 1.0])
    assert np.allclose((m @ old_world)[:3], [2.0, -1.0, 0.42])


@pytest.mark.parametrize("oid", ["sofa-1", "e9"])
def test_objects_without_a_splat_label_are_left_to_the_app(oid: str) -> None:
    before = twin([oid])
    applied = apply_edits(before, [{"id": "e1", "op": "remove", "by": "user", "object_id": oid}])

    assert splat_ops(before, applied.twin, np.eye(4)) == {"remove": [], "moves": {}}
