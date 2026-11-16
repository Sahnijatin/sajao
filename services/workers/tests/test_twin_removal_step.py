"""The removal step through the gateway, with a fake GPU: no Modal, no keys."""

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
from sajao_workers.gpu import gpu_cost_micro_inr
from sajao_workers.models import LAMA, SPLAT_GPUS, removal_chain
from sajao_workers.steps import LocalArtifactStore, StepFailedError, StepRunner
from sajao_workers.twin.removal_step import FINETUNE_STEPS, removal_step
from sajao_workers.validate import check_removal

ROOMY = SpendCaps(per_user_daily_micro_inr=10**12, global_daily_micro_inr=10**12)


def good_output(store: LocalArtifactStore, agreement: float = 26.0) -> dict[str, Any]:
    return {
        "splat": store.put_blob(b"edited ply"),
        "gaussians": 2_400_000,
        "gaussians_removed": 180_000,
        "frames_inpainted": 40,
        "frames_dropped": 12,
        "fill_agreement_psnr": agreement,
        "finetune_seconds": 210.0,
        "inpaint_seconds": 4.0,
    }


def inputs(store: LocalArtifactStore, objects: int = 3) -> dict[str, str]:
    return {
        "splat": store.put_blob(b"ply"),
        "labels": store.put_blob(b"labels"),
        "cameras": store.put_blob(b"[]"),
        "frames": store.put_blob(b"{}"),
        "objects": store.put_blob(json.dumps([{"category": "sofa"}] * objects).encode()),
    }


def test_removal_shares_the_splat_gpu_and_is_charged_at_the_dearer_gpu() -> None:
    async def invoke(_model: str, _payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {}

    (provider,) = removal_chain(invoke)
    assert provider.max_concurrency == SPLAT_GPUS
    assert provider.gpu == "A100-40GB"
    assert provider.model == LAMA
    assert provider.max_attempts == 1


@pytest.mark.parametrize(
    "change",
    [
        {"fill_agreement_psnr": 15.0},  # the fill does not hold together across views
        {"fill_agreement_psnr": float("nan")},
        {"gaussians_removed": 0},  # nothing was removed
        {"frames_inpainted": 0},
        {"splat": "not a digest"},
        {"gaussians": 500},
    ],
)
def test_a_bad_removal_is_rejected(tmp_path: Path, change: dict[str, Any]) -> None:
    output = {**good_output(LocalArtifactStore(tmp_path)), **change}
    with pytest.raises(InvalidOutputError):
        check_removal()(ProviderResult(output))


async def test_the_step_removes_the_named_objects_and_records_the_new_splat(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    seen: list[Mapping[str, Any]] = []

    async def invoke(model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(payload)
        return {"output": good_output(store), "gpu_seconds": 300.0}

    gateway = ModelGateway(removal_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    given = inputs(store)

    result = await StepRunner(store, max_attempts=1).run(
        removal_step(gateway), given, {"object_ids": ["o3", "o1"]}
    )

    assert seen[0] == {**given, "remove": [1, 3], "steps": FINETUNE_STEPS}
    assert store.read_blob(result.outputs["splat"]) == b"edited ply"
    assert result.meta["removed"] == ["o1", "o3"]
    assert result.meta["fill_agreement_psnr"] == 26.0
    assert result.cost_micro_inr == gpu_cost_micro_inr("A100-40GB", 300.0)


@pytest.mark.parametrize("ids", [[], ["o4"], ["sofa"], "o1"])
async def test_a_request_for_objects_the_twin_does_not_have_fails_without_a_gpu(
    tmp_path: Path, ids: Any
) -> None:
    store = LocalArtifactStore(tmp_path)
    calls = 0

    async def invoke(_model: str, _payload: Mapping[str, Any]) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        return {"output": good_output(store), "gpu_seconds": 1.0}

    gateway = ModelGateway(removal_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    with pytest.raises(StepFailedError, match="object"):
        await StepRunner(store, max_attempts=3).run(
            removal_step(gateway), inputs(store), {"object_ids": ids}
        )
    assert calls == 0


async def test_a_fill_that_fails_validation_fails_the_step(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    async def invoke(_model: str, _payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"output": good_output(store, agreement=12.0), "gpu_seconds": 300.0}

    gateway = ModelGateway(removal_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    with pytest.raises(StepFailedError):
        await StepRunner(store, max_attempts=1).run(
            removal_step(gateway), inputs(store), {"object_ids": ["o2"]}
        )
