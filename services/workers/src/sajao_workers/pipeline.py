"""The durable pipeline: a room's stages, run in order over the step layer.

Each stage is one step: a pure function of named input blobs and params whose
result is stored under a content hash (`steps.py`). Running a room again
therefore costs nothing for the stages that are done and resumes at the first
one that is not. The board is what the app reads as job status; this module
is the only thing that moves it.
"""

import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from sajao_workers.ar_measurements import measure
from sajao_workers.steps import (
    NonRetryableStepError,
    Step,
    StepBusyError,
    StepContext,
    StepFailedError,
    StepOutput,
    StepRunner,
)

logger = logging.getLogger(__name__)

StageStatus = Literal["queued", "running", "done", "failed"]


class StageError(NonRetryableStepError):
    """The stage cannot succeed on this input. `code` is the reason the app shows."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PipelineStage:
    """One step of a room's pipeline and the row of job status it moves."""

    name: str
    step: Step
    # Blob names the step reads: files of the capture or outputs of earlier stages.
    needs: tuple[str, ...]
    # The row the app sees, when several steps make up one (default: `name`). The row
    # reads done only once the last step in a run of the same row is done.
    board: str | None = None
    # Run params this step reads; the others stay out of its cache key.
    params: tuple[str, ...] = ()

    @property
    def row(self) -> str:
        return self.board or self.name


class Board(Protocol):
    """Where stage status lives. Every write is safe to repeat."""

    async def set_stage(
        self,
        room_id: str,
        stage: str,
        status: StageStatus,
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None: ...


Outcome = Literal["done", "failed", "busy"]


@dataclass(frozen=True)
class Run:
    outcome: Outcome
    # Every blob known at the end: the inputs plus each finished stage's outputs.
    blobs: Mapping[str, str]
    gpu_seconds: float = 0.0
    cost_micro_inr: int = 0


def _reason(error: StepFailedError) -> str:
    cause = error.__cause__
    return cause.code if isinstance(cause, StageError) else "stage_failed"


async def run_stages(
    runner: StepRunner,
    board: Board,
    room_id: str,
    stages: Sequence[PipelineStage],
    blobs: Mapping[str, str],
    params: Mapping[str, Any] | None = None,
    request_id: str | None = None,
) -> Run:
    """Run the stages in order, moving the board; stop at the first that does not finish."""
    known = dict(blobs)
    gpu_seconds, cost = 0.0, 0
    given = params or {}
    for index, stage in enumerate(stages):
        missing = sorted(name for name in stage.needs if name not in known)
        if missing:
            logger.error("stage %s of room %s lacks %s", stage.name, room_id, missing)
            await board.set_stage(room_id, stage.row, "failed", "input_missing", request_id)
            return Run("failed", known, gpu_seconds, cost)
        inputs = {name: known[name] for name in stage.needs}
        mine = {k: given[k] for k in stage.params if k in given}
        stored = runner.store.read_manifest(runner.key(stage.step, inputs, mine))
        if stored is None:
            # A stage whose result is stored never shows as running again.
            await board.set_stage(room_id, stage.row, "running", None, request_id)
        try:
            result = await runner.run(stage.step, inputs, mine)
        except StepBusyError:
            # Another worker has it and will move the board when it finishes.
            return Run("busy", known, gpu_seconds, cost)
        except StepFailedError as error:
            logger.exception("stage %s of room %s failed", stage.name, room_id)
            await board.set_stage(room_id, stage.row, "failed", _reason(error), request_id)
            return Run("failed", known, gpu_seconds, cost)
        known.update(result.outputs)
        gpu_seconds += result.gpu_seconds
        cost += result.cost_micro_inr
        last_of_row = index + 1 == len(stages) or stages[index + 1].row != stage.row
        if last_of_row:
            await board.set_stage(room_id, stage.row, "done", None, request_id)
    return Run("done", known, gpu_seconds, cost)


async def _measure(context: StepContext) -> StepOutput:
    try:
        planes = json.loads(context.read("planes"))
    except ValueError as error:
        raise StageError("planes_unreadable") from error
    measurements = measure(planes)
    if not measurements["walls"]:
        # Nothing to check fit against: the person needs to scan again.
        raise StageError("no_walls")
    return StepOutput(
        files={"measurements": json.dumps(measurements, sort_keys=True).encode()},
        meta={"walls": len(measurements["walls"]), "planes": measurements["planes"]},
    )


# Walls, floor, ceiling height and openings from the planes the phone tracked.
# Code only: no model sets a dimension.
MEASURE = PipelineStage("measure", Step("measure", 1, _measure), needs=("planes",))

# The room's stages that have a step today, in the order the API lists them.
# Stages still to be handed over stay queued, so the room reads as working.
ROOM_STAGES: tuple[PipelineStage, ...] = (MEASURE,)


# Twins made from a capture are named from the room, so a run again names the same twin.
TWIN_NAMESPACE = uuid.UUID("3f0d5a8e-1b2c-4d3e-9f4a-5b6c7d8e9f01")
TWIN_PARAMS = ("twin_id", "version", "created_at")


# A capture of this many photos with no AR runs the few-photo stages.
FEW_PHOTOS = (2, 3)


def photo_count(capture: Mapping[str, Any]) -> int:
    """Photos in a capture with no AR and no planes; 0 for a scan."""
    package = capture.get("package") or {}
    no_ar = (package.get("ar") or {}).get("tracking") == "none"
    return len(package.get("keyframes", [])) if no_ar and not package.get("planes") else 0


def is_single_photo(capture: Mapping[str, Any]) -> bool:
    """A capture with no AR and exactly one photo: the photo-first path."""
    package = capture.get("package") or {}
    no_ar = (package.get("ar") or {}).get("tracking") == "none"
    return no_ar and not package.get("planes") and len(package.get("keyframes", [])) == 1


def twin_params(room_id: str, capture: Mapping[str, Any]) -> dict[str, Any]:
    """Params that name the twin the same way every time the room is run."""
    return {
        "twin_id": str(uuid.uuid5(TWIN_NAMESPACE, room_id)),
        "version": 1,
        "created_at": capture["created_at"],
    }


class Rooms(Board, Protocol):
    async def set_space_twin(self, room_id: str, twin: dict[str, Any]) -> None: ...


class CaptureFiles(Protocol):
    """The capture's uploaded files, by storage key."""

    def read(self, storage_key: str) -> bytes: ...


async def run_room(
    runner: StepRunner,
    rooms: Rooms,
    files: CaptureFiles,
    room_id: str,
    capture: Mapping[str, Any],
    stages: Sequence[PipelineStage] = ROOM_STAGES,
    photo_stages: Sequence[PipelineStage] = (),
    few_photo_stages: Sequence[PipelineStage] = (),
) -> Run:
    """Run a room's stages from its registered capture. Safe to call again at any point.

    A scan runs `stages`. A capture of one photo with no AR runs `photo_stages`, of two
    or three photos `few_photo_stages` (see photo_pipeline.py), when they are given;
    other captures without AR wait for theirs."""
    blobs = {"capture": runner.store.put_blob(json.dumps(capture, sort_keys=True).encode())}
    package = capture.get("package") or {}
    planes_key = package.get("planes")
    params: dict[str, Any] = {}
    chosen = (
        photo_stages
        if is_single_photo(capture)
        else few_photo_stages
        if photo_count(capture) in FEW_PHOTOS
        else ()
    )
    if chosen:
        stages = chosen
        try:
            images = {
                k["id"]: runner.store.put_blob(files.read(k["image"])) for k in package["keyframes"]
            }
        except Exception:
            logger.exception("photo of room %s could not be read", room_id)
            await rooms.set_stage(room_id, stages[0].row, "failed", "photo_unreadable")
            return Run("failed", blobs)
        blobs["images"] = runner.store.put_blob(json.dumps(images, sort_keys=True).encode())
        params = twin_params(room_id, capture)
    elif not planes_key and (package.get("ar") or {}).get("tracking") == "none" and stages:
        # Imported photos or video with no single-photo path for them yet.
        await rooms.set_stage(room_id, stages[0].row, "failed", "no_ar_data")
        return Run("failed", blobs)
    if planes_key:
        try:
            blobs["planes"] = runner.store.put_blob(files.read(planes_key))
        except Exception:
            # The first stage then fails with input_missing, which the app can show.
            logger.exception("planes of room %s could not be read", room_id)
    run = await run_stages(runner, rooms, room_id, stages, blobs, params)
    twin = run.blobs.get("space_twin") or (run.blobs.get("twin") if params else None)
    if run.outcome == "done" and twin is not None:
        await rooms.set_space_twin(room_id, json.loads(runner.store.read_blob(twin)))
    return run
