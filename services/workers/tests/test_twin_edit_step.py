"""The edit step: a design's edits applied to a twin, with the splat changed on the GPU."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from sajao_gateway import InMemorySpendLedger, ModelGateway, SpendCaps
from sajao_schemas.generated.v1 import SpaceTwin
from sajao_workers.models import removal_chain
from sajao_workers.steps import LocalArtifactStore, StepFailedError, StepRunner
from sajao_workers.twin.edit_step import FINETUNE_STEPS, edit_step, with_phone_splats

FIXTURE = Path(__file__).parents[3] / "packages/schemas/fixtures/v1/valid/space-twin.json"
ROOMY = SpendCaps(per_user_daily_micro_inr=10**12, global_daily_micro_inr=10**12)


def setup(store: LocalArtifactStore) -> tuple[dict[str, Any], dict[str, str]]:
    twin: dict[str, Any] = json.loads(FIXTURE.read_text())
    twin["objects"] = [
        {**twin["objects"][0], "id": "o1"},
        {**twin["objects"][1], "id": "o2"},
    ]
    # The splat world is the space frame shifted by (1, 2, 0): manifest cameras say so.
    frames = [
        {
            "keyframe_id": k["id"],
            "c2w": [
                [1, 0, 0, k["pose"]["position"]["x_m"] - 1.0],
                [0, 1, 0, k["pose"]["position"]["y_m"] - 2.0],
                [0, 0, 1, k["pose"]["position"]["z_m"]],
                [0, 0, 0, 1],
            ],
        }
        for k in twin["keyframes"]
    ]
    inputs = {
        "twin": store.put_blob(json.dumps(twin).encode()),
        "splat": store.put_blob(b"room ply"),
        "labels": store.put_blob(b"labels"),
        "cameras": store.put_blob(b"[]"),
        "frames": store.put_blob(json.dumps({"frames": frames}).encode()),
        "objects": store.put_blob(b"[{}, {}]"),
    }
    return twin, inputs


def reference(twin: Mapping[str, Any], edits: list[dict[str, Any]]) -> dict[str, Any]:
    return {"twin_id": twin["id"], "twin_version": twin["version"], "edits": edits}


def gpu(store: LocalArtifactStore, seen: list[Mapping[str, Any]]) -> Any:
    async def invoke(_model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(payload)
        output = {
            "splat": store.put_blob(b"edited ply"),
            "gaussians": 2_000_000,
            "gaussians_removed": 90_000,
            "gaussians_moved": 60_000,
            "frames_inpainted": 30,
            "frames_dropped": 4,
            "fill_agreement_psnr": 27.0,
        }
        return {"output": output, "gpu_seconds": 240.0}

    return ModelGateway(removal_chain(invoke), ledger=InMemorySpendLedger(ROOMY))


async def test_moves_and_removals_go_to_the_gpu_in_the_splat_world(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    twin, inputs = setup(store)
    seen: list[Mapping[str, Any]] = []
    to = {"x_m": 3.0, "y_m": 1.0, "z_m": twin["objects"][0]["box"]["center"]["z_m"]}
    edits: list[dict[str, Any]] = [
        {"id": "e1", "op": "move", "by": "user", "object_id": "o1", "to": to},
        {"id": "e2", "op": "remove", "by": "user", "object_id": "o2"},
    ]

    result = await StepRunner(store, max_attempts=1).run(
        edit_step(gpu(store, seen)), inputs, {"reference": reference(twin, edits)}
    )

    payload = seen[0]
    assert payload["remove"] == [1, 2] and payload["steps"] == FINETUNE_STEPS
    old = twin["objects"][0]["box"]["center"]
    m = payload["moves"]["1"]
    # The old centre, in the splat world, lands on the new centre in the splat world.
    x = m[0][0] * (old["x_m"] - 1) + m[0][1] * (old["y_m"] - 2) + m[0][2] * old["z_m"] + m[0][3]
    y = m[1][0] * (old["x_m"] - 1) + m[1][1] * (old["y_m"] - 2) + m[1][2] * old["z_m"] + m[1][3]
    assert (round(x, 6), round(y, 6)) == (2.0, -1.0)
    view = json.loads(store.read_blob(result.outputs["view"]))
    assert view["splat"]["key"].endswith(result.outputs["splat"])
    assert "phone_splats" not in view  # the old ones show the old room
    assert {o["id"]: o["state"] for o in view["objects"]} == {"o1": "move", "o2": "remove"}
    assert result.meta["moved"] == ["o1"] and result.meta["removed"] == ["o2"]


async def test_edits_that_change_no_gaussians_keep_the_splat_and_skip_the_gpu(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    twin, inputs = setup(store)
    seen: list[Mapping[str, Any]] = []
    edits: list[dict[str, Any]] = [
        {"id": "e1", "op": "restyle_surface", "by": "user", "surface_id": "floor",
         "material": {"kind": "wood"}},
        {"id": "e2", "op": "remove", "by": "user", "object_id": "ghost"},
    ]  # fmt: skip

    result = await StepRunner(store, max_attempts=1).run(
        edit_step(gpu(store, seen)), inputs, {"reference": reference(twin, edits)}
    )

    assert seen == []
    assert result.outputs["splat"] == inputs["splat"]
    assert result.meta["problems"] == [{"edit_id": "e2", "reason": "unknown object"}]
    assert result.cost_micro_inr == 0


@pytest.mark.parametrize(
    "change",
    [
        {"twin_version": 9},  # edits made on another version of this twin
        {"edits": [{"id": "e1", "op": "move", "by": "model", "object_id": "o1",
                    "to": {"x_m": 0, "y_m": 0, "z_m": 0}}]},  # a model never edits
    ],
)  # fmt: skip
async def test_a_bad_reference_fails_without_a_gpu(tmp_path: Path, change: dict[str, Any]) -> None:
    store = LocalArtifactStore(tmp_path)
    twin, inputs = setup(store)
    seen: list[Mapping[str, Any]] = []

    with pytest.raises(StepFailedError):
        await StepRunner(store, max_attempts=3).run(
            edit_step(gpu(store, seen)), inputs, {"reference": {**reference(twin, []), **change}}
        )
    assert seen == []


def test_phone_splats_of_the_edited_room_join_the_view() -> None:
    twin = json.loads(FIXTURE.read_text())
    twin.pop("phone_splats", None)
    phone = [{"budget": 500_000, "sog": "a" * 64, "gaussians": 500_000, "bytes": 6_000_000}]

    view = with_phone_splats(twin, phone)

    SpaceTwin.model_validate(view)
    assert view["phone_splats"][0]["tier"] == "capable"
    assert view["phone_splats"][0]["key"].endswith("a" * 64)
