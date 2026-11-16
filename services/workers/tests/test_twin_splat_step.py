"""The splat step through the gateway, with a fake GPU: no Modal, no keys."""

import io
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sajao_gateway import (
    InMemorySpendLedger,
    InvalidOutputError,
    ModelGateway,
    ProviderResult,
    SpendCaps,
)
from sajao_workers.gpu import gpu_cost_micro_inr
from sajao_workers.models import MODEL_GPUS, SPLAT_GPUS, detect_chain, splat_chain
from sajao_workers.steps import LocalArtifactStore, StepFailedError, StepRunner
from sajao_workers.twin.splat_step import splat_step
from sajao_workers.validate import check_splat

ROOMY = SpendCaps(per_user_daily_micro_inr=10**12, global_daily_micro_inr=10**12)


def good_output(store: LocalArtifactStore, psnr: float = 25.5) -> dict[str, Any]:
    labels = io.BytesIO()
    np.save(labels, np.zeros(1000, np.int32))
    return {
        "splat": store.put_blob(b"ply bytes"),
        "labels": store.put_blob(labels.getvalue()),
        "cameras": store.put_blob(b"[]"),
        "gaussians": 250_000,
        "psnr_heldout": psnr,
        "psnr_heldout_raw": 18.0,
        "train_seconds": 400.0,
        "gaussians_on_objects": 30_000,
        "objects_with_gaussians": 12,
    }


def test_the_gpu_cap_is_shared_by_models_and_splats() -> None:
    async def invoke(_model: str, _payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {}

    assert MODEL_GPUS + SPLAT_GPUS == 3
    assert {p.max_concurrency for p in detect_chain(invoke)} == {MODEL_GPUS}
    assert {p.max_concurrency for p in splat_chain(invoke)} == {SPLAT_GPUS}
    assert all(p.model.startswith("gsplat@") for p in splat_chain(invoke))


def test_a_splat_is_charged_at_the_dearer_of_its_gpus() -> None:
    async def invoke(_model: str, _payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {}

    (provider,) = splat_chain(invoke)
    assert provider.gpu == "A100-40GB"  # Modal may fall back to it; charge the upper bound
    assert gpu_cost_micro_inr("A100-40GB", 1.0) > gpu_cost_micro_inr("L40S", 1.0)


def test_a_valid_splat_passes(tmp_path: Path) -> None:
    check_splat()(ProviderResult(good_output(LocalArtifactStore(tmp_path))))


@pytest.mark.parametrize(
    "change",
    [
        {"psnr_heldout": 15.0},  # not good enough to show anyone
        {"psnr_heldout": float("nan")},
        {"gaussians": 500},
        {"splat": "not a digest"},
    ],
)
def test_a_bad_splat_is_rejected(tmp_path: Path, change: dict[str, Any]) -> None:
    output = {**good_output(LocalArtifactStore(tmp_path)), **change}
    with pytest.raises(InvalidOutputError):
        check_splat()(ProviderResult(output))


async def test_the_step_records_the_gpu_blobs_and_reports_quality(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    seen: list[Mapping[str, Any]] = []

    async def invoke(model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(payload)
        return {"output": good_output(store), "gpu_seconds": 420.0}

    gateway = ModelGateway(splat_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    inputs = {"frames": store.put_blob(b"{}"), "objects": store.put_blob(b"[]")}

    result = await StepRunner(store, max_attempts=1).run(splat_step(gateway), inputs, {})

    assert seen[0] == {**inputs, "steps": 15000, "holdout": "spread"}
    assert set(result.outputs) == {"splat", "labels", "cameras"}
    assert store.read_blob(result.outputs["splat"]) == b"ply bytes"
    assert result.meta["psnr_heldout"] == 25.5
    assert result.cost_micro_inr == gpu_cost_micro_inr("A100-40GB", 420.0)
    assert json.loads(store.read_blob(result.outputs["cameras"])) == []


async def test_golden_rooms_ask_for_the_near_and_far_split(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    seen: list[Mapping[str, Any]] = []
    heldout = {"near": {"views": 6, "psnr": 25.5}, "far": {"views": 6, "psnr": 19.0}}

    async def invoke(model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(payload)
        return {"output": {**good_output(store), "heldout": heldout}, "gpu_seconds": 420.0}

    gateway = ModelGateway(splat_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    inputs = {"frames": store.put_blob(b"{}"), "objects": store.put_blob(b"[]")}

    result = await StepRunner(store, max_attempts=1).run(
        splat_step(gateway), inputs, {"holdout": "split"}
    )

    assert seen[0]["holdout"] == "split"
    assert result.meta["heldout"] == heldout


async def test_a_benchmark_can_switch_quality_steps_off(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    seen: list[Mapping[str, Any]] = []

    async def invoke(model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(payload)
        return {"output": good_output(store), "gpu_seconds": 420.0}

    gateway = ModelGateway(splat_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    inputs = {"frames": store.put_blob(b"{}"), "objects": store.put_blob(b"[]")}
    runner = StepRunner(store, max_attempts=1)

    plain = await runner.run(splat_step(gateway), inputs, {})
    off = await runner.run(splat_step(gateway), inputs, {"quality": {"depth": False}})

    assert "quality" not in seen[0]  # the trainer's defaults: everything on
    assert seen[1]["quality"] == {"depth": False}
    assert not off.cached and plain.outputs["splat"] == off.outputs["splat"]


async def test_a_splat_below_the_quality_bar_fails_the_step(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    async def invoke(_model: str, _payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"output": good_output(store, psnr=14.0), "gpu_seconds": 400.0}

    gateway = ModelGateway(splat_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    inputs = {"frames": store.put_blob(b"{}"), "objects": store.put_blob(b"[]")}

    with pytest.raises(StepFailedError):
        await StepRunner(store, max_attempts=1).run(splat_step(gateway), inputs, {})


def test_gpu_calls_get_their_own_time_limit_and_splats_are_not_retried() -> None:
    async def invoke(_model: str, _payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {}

    (splat,) = splat_chain(invoke)
    detector = detect_chain(invoke)[0]
    assert splat.timeout_seconds > splat.max_seconds  # room for a cold start
    assert detector.timeout_seconds > detector.max_seconds
    assert splat.max_attempts == 1  # the durable step retries a failed splat, not the gateway
    assert detector.max_attempts is None
