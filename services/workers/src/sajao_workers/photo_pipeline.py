"""The photo-first room pipeline: one photo to a SpaceTwin at the estimated level.

The stages run over the same durable step layer as a scan (`pipeline.run_stages`),
so a room run again resumes at the first unfinished step. The app sees two rows:
`measure` (the camera on the floor, from metric depth) and `inventory` (what is in
the room, the scale check, the twin and what the design engine reads).

Every model call goes through the gateways passed in; no model sets a dimension.
"""

from dataclasses import dataclass

from sajao_gateway import ModelGateway
from sajao_workers.pipeline import TWIN_PARAMS, PipelineStage
from sajao_workers.twin.assemble_step import assemble_step
from sajao_workers.twin.inventory_step import inventory_step
from sajao_workers.twin.objects_step import objects_step
from sajao_workers.twin.single_photo_step import single_photo_scale_step, single_photo_step
from sajao_workers.twin.understanding_step import understanding_step


@dataclass(frozen=True)
class PhotoModels:
    """The gateways the photo stages call."""

    depth: ModelGateway
    lister: ModelGateway
    checker: ModelGateway
    detect: ModelGateway
    segment: ModelGateway


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
