"""The phone splat step: decimated, compressed room splats for on-device viewing."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from sajao_workers.steps import LocalArtifactStore, StepFailedError, StepRunner
from sajao_workers.twin.phone_step import BUDGETS, check_variants, phone_splat_step

MB = 1_000_000


def variants(
    store: LocalArtifactStore, sizes: Mapping[int, int] | None = None
) -> list[dict[str, Any]]:
    sizes = sizes or {500_000: 6 * MB, 250_000: 3 * MB}
    return [
        {
            "budget": budget,
            "gaussians": budget,
            "sog": store.put_blob(f"sog {budget}".encode()),
            "bytes": size,
            "decimate_method": "decimate",
            "seconds": 40.0,
        }
        for budget, size in sizes.items()
    ]


def test_budgets_match_the_spike_decision() -> None:
    # 500k for capable phones, 250k for budget Android (SJ-116).
    assert BUDGETS == (500_000, 250_000)


def test_valid_variants_pass(tmp_path: Path) -> None:
    check_variants(variants(LocalArtifactStore(tmp_path)), source_gaussians=2_900_000)


@pytest.mark.parametrize(
    "change",
    [
        {"bytes": 40 * MB},  # too big to download on a phone
        {"bytes": 1_000},  # empty or broken
        {"gaussians": 499_000},  # decimation missed the budget
        {"sog": "nope"},
    ],
)
def test_bad_variants_are_rejected(tmp_path: Path, change: dict[str, Any]) -> None:
    bad = variants(LocalArtifactStore(tmp_path))
    bad[0] = {**bad[0], **change}
    with pytest.raises(ValueError):
        check_variants(bad, source_gaussians=2_900_000)


def test_a_splat_already_under_a_budget_is_compressed_as_is(tmp_path: Path) -> None:
    small = variants(LocalArtifactStore(tmp_path), {250_000: 3 * MB})
    small.append({**small[0], "budget": 500_000, "gaussians": 300_000})
    check_variants(small, source_gaussians=300_000)


async def test_the_step_records_each_variant(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    calls: list[Mapping[str, Any]] = []

    async def compress(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(payload)
        return {"source_gaussians": 2_900_000, "variants": variants(store), "cpu_seconds": 300.0}

    splat = store.put_blob(b"ply")
    result = await StepRunner(store, max_attempts=1).run(
        phone_splat_step(compress), {"splat": splat}, {}
    )

    assert calls == [{"splat": splat, "budgets": [500_000, 250_000]}]
    assert set(result.outputs) == {"sog_500k", "sog_250k"}
    assert result.meta["variants"]["500k"]["bytes"] == 6 * MB
    assert result.cost_micro_inr > 0


async def test_a_failed_compression_fails_the_step(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    async def compress(_payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"error": "splat-transform exited 1"}

    with pytest.raises(StepFailedError, match="splat-transform"):
        await StepRunner(store, max_attempts=1).run(
            phone_splat_step(compress), {"splat": store.put_blob(b"ply")}, {}
        )
