"""The depth step through the gateway, with a fake GPU: no Modal, no keys."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from sajao_gateway import (
    InMemorySpendLedger,
    InvalidOutputError,
    ModelGateway,
    ProviderResult,
    SpendCaps,
)
from sajao_workers.models import DA3_METRIC, MODEL_GPUS, MOGE3, depth_chain
from sajao_workers.steps import LocalArtifactStore, StepFailedError, StepRunner
from sajao_workers.twin.depth_step import depth_step
from sajao_workers.validate import check_depths

ROOMY = SpendCaps(per_user_daily_micro_inr=10**12, global_daily_micro_inr=10**12)
K = [[500.0, 0.0, 320.0], [0.0, 500.0, 240.0], [0.0, 0.0, 1.0]]


def manifest(store: LocalArtifactStore, source: str = "image", frames: int = 3) -> dict[str, Any]:
    return {
        "up_axis": 1,
        "depth_source": source,
        "frames": [
            {
                "keyframe_id": f"k{i}",
                "image": store.put_blob(f"image {i}".encode()),
                "width": 640,
                "height": 480,
                "intrinsics": K,
                "c2w": [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]],
                "depth": store.put_blob(b"lidar") if source == "lidar" else None,
            }
            for i in range(frames)
        ],
    }


def reply(store: LocalArtifactStore, payload: Mapping[str, Any], **change: Any) -> dict[str, Any]:
    frames = [
        {
            "image": f["image"],
            "depth": store.put_blob(f"depth of {f['image']}".encode()),
            "coverage": 0.97,
            "median_m": 2.4,
            **change,
        }
        for f in payload["frames"]
    ]
    return {"frames": frames}


def test_depth_models_share_the_model_gpus_with_moge_first() -> None:
    async def invoke(_model: str, _payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {}

    chain = depth_chain(invoke)
    assert [p.model for p in chain] == [MOGE3, DA3_METRIC]
    assert {p.max_concurrency for p in chain} == {MODEL_GPUS}


@pytest.mark.parametrize(
    "change",
    [
        {"coverage": 0.2},  # most of the frame has no depth
        {"median_m": 0.01},  # not a room
        {"median_m": 80.0},
        {"median_m": float("nan")},
        {"depth": "not a digest"},
    ],
)
def test_bad_depth_is_rejected(tmp_path: Path, change: dict[str, Any]) -> None:
    store = LocalArtifactStore(tmp_path)
    payload = {"frames": [{"image": store.put_blob(b"a"), "intrinsics": K}]}
    with pytest.raises(InvalidOutputError):
        check_depths(payload)(ProviderResult(reply(store, payload, **change)))


def test_depth_for_other_frames_is_rejected(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    payload = {"frames": [{"image": store.put_blob(b"a")}, {"image": store.put_blob(b"b")}]}
    swapped = reply(store, payload)
    swapped["frames"].reverse()
    with pytest.raises(InvalidOutputError):
        check_depths(payload)(ProviderResult(swapped))


async def test_frames_without_lidar_get_model_depth(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    seen: list[tuple[str, Mapping[str, Any]]] = []

    async def invoke(model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append((model, payload))
        return {"output": reply(store, payload), "gpu_seconds": 30.0}

    gateway = ModelGateway(depth_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    given = manifest(store)

    result = await StepRunner(store, max_attempts=1).run(
        depth_step(gateway), {"frames": store.put_blob(json.dumps(given).encode())}, {}
    )

    out = json.loads(store.read_blob(result.outputs["frames"]))
    assert seen[0][0] == MOGE3
    assert seen[0][1]["frames"] == [
        {"image": f["image"], "width": 640, "height": 480, "intrinsics": K} for f in given["frames"]
    ]
    assert out["depth_source"] == "image"
    for before, after in zip(given["frames"], out["frames"], strict=True):
        assert store.read_blob(after["depth"]) == f"depth of {before['image']}".encode()
        assert {k: v for k, v in after.items() if k != "depth"} == {
            k: v for k, v in before.items() if k != "depth"
        }
    assert result.meta == {"model": MOGE3, "frames": 3, "median_coverage": 0.97}


async def test_lidar_depth_is_kept_and_no_model_runs(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    calls = 0

    async def invoke(_model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        return {"output": reply(store, payload), "gpu_seconds": 1.0}

    gateway = ModelGateway(depth_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    frames = store.put_blob(json.dumps(manifest(store, source="lidar")).encode())

    result = await StepRunner(store, max_attempts=1).run(
        depth_step(gateway), {"frames": frames}, {}
    )

    assert calls == 0
    assert result.outputs["frames"] == frames
    assert result.cost_micro_inr == 0


async def test_when_moge_fails_da3_fills_in(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    async def invoke(model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if model == MOGE3:
            return {"output": reply(store, payload, coverage=0.1), "gpu_seconds": 30.0}
        return {"output": reply(store, payload), "gpu_seconds": 5.0}

    gateway = ModelGateway(depth_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    frames = store.put_blob(json.dumps(manifest(store)).encode())

    result = await StepRunner(store, max_attempts=1).run(
        depth_step(gateway), {"frames": frames}, {}
    )

    assert result.meta["model"] == DA3_METRIC


async def test_when_every_depth_model_fails_the_step_fails(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    async def invoke(_model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"output": reply(store, payload, median_m=0.0), "gpu_seconds": 5.0}

    gateway = ModelGateway(depth_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    frames = store.put_blob(json.dumps(manifest(store)).encode())
    with pytest.raises(StepFailedError):
        await StepRunner(store, max_attempts=1).run(depth_step(gateway), {"frames": frames}, {})
