"""Durable steps: stored results, content-hash keys, resume, retry alone, leases."""

from pathlib import Path

import pytest

from sajao_workers.steps import (
    LocalArtifactStore,
    NonRetryableStepError,
    Step,
    StepBusyError,
    StepContext,
    StepFailedError,
    StepOutput,
    StepRunner,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def no_sleep(_seconds: float) -> None:
    return None


def runner(tmp_path: Path, clock: Clock | None = None, **options: float) -> StepRunner:
    return StepRunner(
        LocalArtifactStore(tmp_path),
        clock=clock or Clock(),
        sleep=no_sleep,
        **options,  # type: ignore[arg-type]
    )


def counting_step(calls: list[str], name: str = "double", version: int = 1) -> Step:
    async def run(context: StepContext) -> StepOutput:
        calls.append(context.params["label"])
        frames = context.read("frames")
        return StepOutput(
            files={"doubled": frames * 2},
            meta={"length": len(frames)},
            gpu_seconds=2.5,
            cost_micro_inr=1300,
        )

    return Step(name=name, version=version, run=run)


async def test_a_step_stores_its_outputs_and_reports_cost(tmp_path: Path) -> None:
    steps = runner(tmp_path)
    frames = steps.store.put_blob(b"abc")

    result = await steps.run(counting_step([]), {"frames": frames}, {"label": "a"})

    assert steps.store.read_blob(result.outputs["doubled"]) == b"abcabc"
    assert result.meta == {"length": 3}
    assert (result.cached, result.gpu_seconds, result.cost_micro_inr) == (False, 2.5, 1300)


async def test_the_same_inputs_run_once_and_the_rerun_costs_nothing(tmp_path: Path) -> None:
    calls: list[str] = []
    steps = runner(tmp_path)
    frames = steps.store.put_blob(b"abc")

    first = await steps.run(counting_step(calls), {"frames": frames}, {"label": "a"})
    second = await steps.run(counting_step(calls), {"frames": frames}, {"label": "a"})

    assert calls == ["a"]
    assert second.cached
    assert (second.gpu_seconds, second.cost_micro_inr) == (0.0, 0)
    assert second.outputs == first.outputs
    assert second.key == first.key


async def test_a_new_runner_on_the_same_store_resumes_from_stored_results(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    frames = runner(tmp_path).store.put_blob(b"abc")
    await runner(tmp_path).run(counting_step(calls), {"frames": frames}, {"label": "a"})

    again = await runner(tmp_path).run(counting_step(calls), {"frames": frames}, {"label": "a"})

    assert calls == ["a"]
    assert again.cached


@pytest.mark.parametrize(
    ("frames", "label", "name", "version"),
    [
        (b"xyz", "a", "double", 1),  # new input bytes
        (b"abc", "b", "double", 1),  # new params
        (b"abc", "a", "double", 2),  # new step version
        (b"abc", "a", "triple", 1),  # another step
    ],
)
async def test_changing_inputs_params_or_step_version_reruns(
    tmp_path: Path, frames: bytes, label: str, name: str, version: int
) -> None:
    calls: list[str] = []
    steps = runner(tmp_path)
    original = steps.store.put_blob(b"abc")
    await steps.run(counting_step(calls), {"frames": original}, {"label": "a"})

    result = await steps.run(
        counting_step(calls, name=name, version=version),
        {"frames": steps.store.put_blob(frames)},
        {"label": label},
    )

    assert not result.cached
    assert len(calls) == 2


async def test_a_failing_step_is_retried_and_succeeds(tmp_path: Path) -> None:
    attempts: list[int] = []

    async def flaky(_context: StepContext) -> StepOutput:
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("GPU preempted")
        return StepOutput(files={"out": b"ok"})

    steps = runner(tmp_path, max_attempts=3)
    result = await steps.run(Step("flaky", 1, flaky), {}, {})

    assert len(attempts) == 3
    assert steps.store.read_blob(result.outputs["out"]) == b"ok"


async def test_a_step_that_keeps_failing_stores_nothing_and_can_run_again(
    tmp_path: Path,
) -> None:
    attempts: list[int] = []
    fail = True

    async def broken(_context: StepContext) -> StepOutput:
        attempts.append(1)
        if fail:
            raise RuntimeError("out of memory")
        return StepOutput(files={"out": b"ok"})

    steps = runner(tmp_path, max_attempts=2)
    with pytest.raises(StepFailedError, match="out of memory"):
        await steps.run(Step("broken", 1, broken), {}, {})
    assert len(attempts) == 2

    fail = False
    result = await steps.run(Step("broken", 1, broken), {}, {})
    assert not result.cached
    assert len(attempts) == 3


async def test_a_non_retryable_error_fails_at_once(tmp_path: Path) -> None:
    attempts: list[int] = []

    async def bad_input(_context: StepContext) -> StepOutput:
        attempts.append(1)
        raise NonRetryableStepError("capture package has no keyframes")

    with pytest.raises(StepFailedError, match="no keyframes"):
        await runner(tmp_path, max_attempts=5).run(Step("bad", 1, bad_input), {}, {})
    assert len(attempts) == 1


async def test_a_step_already_running_elsewhere_is_not_started_twice(tmp_path: Path) -> None:
    clock = Clock()
    steps = runner(tmp_path, clock=clock, lease_seconds=600)
    step = counting_step([])
    frames = steps.store.put_blob(b"abc")
    key = steps.key(step, {"frames": frames}, {"label": "a"})
    assert steps.store.acquire_lease(key, expires_at=clock.now + 600)

    with pytest.raises(StepBusyError):
        await steps.run(step, {"frames": frames}, {"label": "a"})


async def test_an_expired_lease_is_taken_over(tmp_path: Path) -> None:
    clock = Clock()
    steps = runner(tmp_path, clock=clock, lease_seconds=600)
    step = counting_step([])
    frames = steps.store.put_blob(b"abc")
    key = steps.key(step, {"frames": frames}, {"label": "a"})
    steps.store.acquire_lease(key, expires_at=clock.now + 600)

    clock.now += 601
    result = await steps.run(step, {"frames": frames}, {"label": "a"})

    assert not result.cached


async def test_the_lease_is_released_after_success_and_after_failure(tmp_path: Path) -> None:
    async def broken(_context: StepContext) -> StepOutput:
        raise NonRetryableStepError("bad")

    steps = runner(tmp_path)
    ok = await steps.run(counting_step([]), {"frames": steps.store.put_blob(b"a")}, {"label": "a"})
    with pytest.raises(StepFailedError):
        await steps.run(Step("broken", 1, broken), {}, {})

    assert steps.store.acquire_lease(ok.key, expires_at=2000.0)
    assert steps.store.acquire_lease(steps.key(Step("broken", 1, broken), {}, {}), 2000.0)


async def test_an_unknown_input_blob_is_rejected_before_running(tmp_path: Path) -> None:
    with pytest.raises(StepFailedError, match="missing input"):
        await runner(tmp_path).run(counting_step([]), {"frames": "0" * 64}, {"label": "a"})


def test_blobs_are_content_addressed_and_written_once(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    first = store.put_blob(b"same bytes")
    second = store.put_blob(b"same bytes")

    assert first == second
    assert store.read_blob(first) == b"same bytes"
    assert len(list((tmp_path / "blobs").rglob("*"))) == 2  # one shard directory, one blob
