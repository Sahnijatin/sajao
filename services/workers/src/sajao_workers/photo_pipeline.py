"""The photo-first room pipeline: one photo to a SpaceTwin at the estimated level.

The stages run over the same durable step layer as a scan (`pipeline.run_stages`),
so a room run again resumes at the first unfinished step. The app sees two rows:
`measure` (the camera on the floor, from metric depth) and `inventory` (what is in
the room, the scale check, the twin and what the design engine reads).

Every model call goes through the gateways passed in; no model sets a dimension.
"""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sajao_gateway import InMemorySpendLedger, ModelGateway, SpendCaps, SpendLedger
from sajao_workers.gpu import Invoke
from sajao_workers.models import depth_chain, detect_chain, pose_chain, segment_chain
from sajao_workers.pipeline import TWIN_PARAMS, PipelineStage
from sajao_workers.twin.assemble_step import assemble_step
from sajao_workers.twin.depth_step import depth_step
from sajao_workers.twin.inventory_step import inventory_step
from sajao_workers.twin.objects_step import objects_step
from sajao_workers.twin.photo_frames import photo_poses_step, photo_scale_step
from sajao_workers.twin.single_photo_step import single_photo_scale_step, single_photo_step
from sajao_workers.twin.understanding_step import understanding_step
from sajao_workers.vision import (
    CLAUDE_OPUS,
    GEMINI_3_FLASH,
    GEMINI_35_FLASH_LITE,
    ClaudeVision,
    GoogleTokens,
    VertexGeminiVision,
)


@dataclass(frozen=True)
class PhotoModels:
    """The gateways the photo stages call."""

    depth: ModelGateway
    lister: ModelGateway
    checker: ModelGateway
    detect: ModelGateway
    segment: ModelGateway
    # Cameras for two or more photos (MapAnything); None when only single photos run.
    poses: ModelGateway | None = None


# The most one photo room's stages may spend, in micro-rupees. The first real run cost
# Rs 5; the cap leaves room for retries and fallbacks, not for a runaway loop. The
# workspace's global daily cap comes with the launch spend controls.
ROOM_CAP_MICRO_INR = 40_000_000


def room_ledger() -> InMemorySpendLedger:
    """A ledger for one room run, capped at ROOM_CAP_MICRO_INR."""
    return InMemorySpendLedger(
        SpendCaps(
            per_user_daily_micro_inr=ROOM_CAP_MICRO_INR, global_daily_micro_inr=ROOM_CAP_MICRO_INR
        )
    )


def photo_models(
    gpu: Callable[[str], Invoke],
    ledger: SpendLedger,
    env: Mapping[str, str] | None = None,
    poses_gpu: Invoke | None = None,
) -> PhotoModels:
    """The pinned model chains for the photo stages. `gpu(task)` reaches the GPU worker's
    model function for a task; the item lists use Gemini on Vertex AI (project from
    GCP_PROJECT_ID) with Claude as the cross-check."""
    project = (env if env is not None else os.environ)["GCP_PROJECT_ID"]
    tokens = GoogleTokens()
    return PhotoModels(
        depth=ModelGateway(depth_chain(gpu("twin_depth")), ledger=ledger),
        lister=ModelGateway(
            [
                VertexGeminiVision("gemini-flash", GEMINI_3_FLASH, project=project, tokens=tokens),
                VertexGeminiVision(
                    "gemini-flash-lite", GEMINI_35_FLASH_LITE, project=project, tokens=tokens
                ),
            ],
            ledger=ledger,
        ),
        checker=ModelGateway([ClaudeVision("claude", CLAUDE_OPUS)], ledger=ledger),
        detect=ModelGateway(detect_chain(gpu("twin_detect")), ledger=ledger),
        segment=ModelGateway(segment_chain(gpu("twin_segment")), ledger=ledger),
        poses=ModelGateway(pose_chain(poses_gpu), ledger=ledger) if poses_gpu else None,
    )


def photo_room_stages(models: PhotoModels) -> tuple[PipelineStage, ...]:
    """The stages for a capture of one photo, in order. Later outputs of the same name
    (`frames`, `inventory`, `twin`) replace earlier ones for the stages after them."""
    return (
        PipelineStage(
            "single_photo",
            single_photo_step(models.depth),
            ("capture", "images"),
            board="measure",
        ),
        PipelineStage(
            "list_items",
            inventory_step(models.lister, models.checker),
            ("frames",),
            board="inventory",
        ),
        PipelineStage(
            "objects",
            objects_step(models.detect, models.segment),
            ("frames", "inventory"),
            board="inventory",
        ),
        PipelineStage(
            "scale_check",
            single_photo_scale_step(),
            ("frames", "scale", "objects", "built_ins", "openings"),
            board="inventory",
        ),
        PipelineStage(
            "assemble",
            assemble_step(),
            ("capture", "frames", "objects", "built_ins", "openings", "scale", "inventory"),
            board="inventory",
            params=TWIN_PARAMS,
        ),
        PipelineStage(
            "understand",
            understanding_step(models.segment),
            ("twin", "objects", "frames"),
            board="inventory",
        ),
    )


def few_photo_stages(models: PhotoModels) -> tuple[PipelineStage, ...]:
    """The stages for two or three photos of one room: cameras and depth from the pose
    model, metres from metric depth, then the same item list, objects, assembly and room
    understanding as one photo. The room is estimated; nothing is claimed to fit."""
    if models.poses is None:
        raise ValueError("few-photo rooms need the pose model")
    return (
        PipelineStage(
            "poses", photo_poses_step(models.poses), ("capture", "images"), board="measure"
        ),
        PipelineStage("depth", depth_step(models.depth), ("frames",), board="measure"),
        PipelineStage("scale", photo_scale_step(), ("frames",), board="measure"),
        PipelineStage(
            "list_items",
            inventory_step(models.lister, models.checker),
            ("frames",),
            board="inventory",
        ),
        PipelineStage(
            "objects",
            objects_step(models.detect, models.segment),
            ("frames", "inventory"),
            board="inventory",
        ),
        PipelineStage(
            "assemble",
            assemble_step(),
            ("capture", "frames", "objects", "built_ins", "openings", "inventory"),
            board="inventory",
            params=TWIN_PARAMS,
        ),
        PipelineStage(
            "understand",
            understanding_step(models.segment),
            ("twin", "objects", "frames"),
            board="inventory",
        ),
    )
