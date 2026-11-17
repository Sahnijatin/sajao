import json
from pathlib import Path
from typing import Any

from sajao_workers.pipeline import MEASURE, PipelineStage, StageError, run_room, run_stages
from sajao_workers.plane_fixtures import DEPTH, WIDTH, room
from sajao_workers.steps import (
    LocalArtifactStore,
    Step,
    StepContext,
    StepOutput,
    StepRunner,
)

ROOM = "room-1"


class Board:
    def __init__(self) -> None:
        self.moves: list[tuple[str, str, str | None, str | None]] = []

    async def set_stage(
        self,
        room_id: str,
        stage: str,
        status: str,
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None:
        assert room_id == ROOM
        self.moves.append((stage, status, detail, request_id))

    async def set_space_twin(self, room_id: str, twin: dict[str, Any]) -> None:
        self.twin = twin


class Files:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def read(self, storage_key: str) -> bytes:
        return self.files[storage_key]


async def no_sleep(_: float) -> None:
    return None


def runner(tmp_path: Path) -> StepRunner:
    return StepRunner(LocalArtifactStore(tmp_path), sleep=no_sleep)


def stage(
    name: str, needs: tuple[str, ...], calls: list[str], fail: Exception | None = None
) -> PipelineStage:
    async def run(context: StepContext) -> StepOutput:
        calls.append(name)
        if fail is not None:
            raise fail
        joined = b"+".join(context.read(n) for n in needs)
        return StepOutput(files={f"{name}_out": name.encode() + b":" + joined})

    return PipelineStage(name, Step(name, 1, run), needs)


async def test_stages_run_in_order_and_each_reads_what_came_before(tmp_path: Path) -> None:
    steps, board = runner(tmp_path), Board()
    calls: list[str] = []
    blobs = {"capture": steps.store.put_blob(b"scan")}
    stages = [stage("a", ("capture",), calls), stage("b", ("a_out", "capture"), calls)]

    run = await run_stages(steps, board, ROOM, stages, blobs)

    assert run.outcome == "done"
    assert steps.store.read_blob(run.blobs["b_out"]) == b"b:a:scan+scan"
    assert [(s, status) for s, status, _, _ in board.moves] == [
        ("a", "running"),
        ("a", "done"),
        ("b", "running"),
        ("b", "done"),
    ]


async def test_running_again_does_no_work_twice_and_resumes_after_a_failure(
    tmp_path: Path,
) -> None:
    steps, board = runner(tmp_path), Board()
    calls: list[str] = []
    blobs = {"capture": steps.store.put_blob(b"scan")}
    broken = [
        stage("a", ("capture",), calls),
        stage("b", ("a_out",), calls, fail=StageError("no_walls")),
        stage("c", ("b_out",), calls),
    ]

    failed = await run_stages(steps, board, ROOM, broken, blobs)

    assert failed.outcome == "failed"
    assert calls == ["a", "b"]  # not retried: retrying cannot help; c never started
    assert board.moves[-1] == ("b", "failed", "no_walls", None)

    calls.clear()
    fixed = [broken[0], stage("b", ("a_out",), calls), stage("c", ("b_out",), calls)]
    again = await run_stages(steps, board, ROOM, fixed, blobs)

    assert again.outcome == "done"
    assert calls == ["b", "c"]  # a's stored result was reused
    # a went straight to done: the app never sees a finished stage running again.
    assert [m[:2] for m in board.moves[-5:]] == [
        ("a", "done"),
        ("b", "running"),
        ("b", "done"),
        ("c", "running"),
        ("c", "done"),
    ]
    assert board.moves[-1][:2] == ("c", "done")


async def test_an_unexpected_error_is_retried_then_fails_with_a_general_reason(
    tmp_path: Path,
) -> None:
    steps, board = runner(tmp_path), Board()
    calls: list[str] = []
    blobs = {"capture": steps.store.put_blob(b"scan")}
    stages = [stage("a", ("capture",), calls, fail=RuntimeError("socket closed"))]

    run = await run_stages(steps, board, ROOM, stages, blobs, request_id="req-1")

    assert run.outcome == "failed"
    assert calls == ["a", "a", "a"]
    # The technical message goes to the log, never to the app.
    assert board.moves[-1] == ("a", "failed", "stage_failed", "req-1")


async def test_a_stage_whose_input_never_arrived_fails_without_running(tmp_path: Path) -> None:
    steps, board = runner(tmp_path), Board()
    calls: list[str] = []
    run = await run_stages(steps, board, ROOM, [stage("a", ("capture",), calls)], {})
    assert run.outcome == "failed"
    assert calls == []
    assert board.moves == [("a", "failed", "input_missing", None)]


async def test_a_stage_running_elsewhere_is_left_alone(tmp_path: Path) -> None:
    steps, board = runner(tmp_path), Board()
    calls: list[str] = []
    blobs = {"capture": steps.store.put_blob(b"scan")}
    only = stage("a", ("capture",), calls)
    key = steps.key(only.step, {"capture": blobs["capture"]}, {})
    assert steps.store.acquire_lease(key, 4e9)

    run = await run_stages(steps, board, ROOM, [only], blobs)

    assert run.outcome == "busy"
    assert calls == []
    assert board.moves == [("a", "running", None, None)]


async def test_measure_turns_tracked_planes_into_walls_with_error_bands(tmp_path: Path) -> None:
    steps, board = runner(tmp_path), Board()
    blobs = {"planes": steps.store.put_blob(json.dumps(room()).encode())}

    run = await run_stages(steps, board, ROOM, [MEASURE], blobs)

    assert run.outcome == "done"
    measured: dict[str, Any] = json.loads(steps.store.read_blob(run.blobs["measurements"]))
    lengths = sorted(round(w["length"]["value_m"], 1) for w in measured["walls"])
    assert lengths == [DEPTH, DEPTH, WIDTH, WIDTH]
    assert all(
        w["length"]["source"] == "estimated" and w["length"]["error_band_m"] > 0
        for w in measured["walls"]
    )


async def test_measure_fails_plainly_when_the_scan_has_no_walls(tmp_path: Path) -> None:
    steps, board = runner(tmp_path), Board()
    empty = {"format": "sajao-planes-1", "planes": []}
    for name, data in (("none", json.dumps(empty).encode()), ("broken", b"not json")):
        run = await run_stages(
            steps, board, ROOM, [MEASURE], {"planes": steps.store.put_blob(data)}
        )
        assert run.outcome == "failed", name
    assert [m[2] for m in board.moves if m[1] == "failed"] == ["no_walls", "planes_unreadable"]


CAPTURE = {"id": "capture-1", "package": {"planes": "user/planes.json"}}


async def test_a_room_is_measured_from_its_captures_planes_file(tmp_path: Path) -> None:
    steps, board = runner(tmp_path), Board()
    files = Files({"user/planes.json": json.dumps(room()).encode()})

    run = await run_room(steps, board, files, ROOM, CAPTURE)

    assert run.outcome == "done"
    assert "measurements" in run.blobs
    assert not hasattr(board, "twin")  # no stage has produced a SpaceTwin yet

    again = await run_room(steps, board, Files({}), ROOM, CAPTURE)
    # The file is gone, so the stage cannot be fed; nothing stored is lost.
    assert again.outcome == "failed"
    assert board.moves[-1][:3] == ("measure", "failed", "input_missing")


async def test_a_room_stores_the_space_twin_its_last_stage_produced(tmp_path: Path) -> None:
    steps, board = runner(tmp_path), Board()
    files = Files({"user/planes.json": json.dumps(room()).encode()})

    async def assemble(context: StepContext) -> StepOutput:
        walls = len(json.loads(context.read("measurements"))["walls"])
        return StepOutput(files={"space_twin": json.dumps({"walls": walls}).encode()})

    twin = PipelineStage("inventory", Step("assemble", 1, assemble), ("measurements",))
    run = await run_room(steps, board, files, ROOM, CAPTURE, [MEASURE, twin])

    assert run.outcome == "done"
    assert board.twin == {"walls": 4}
