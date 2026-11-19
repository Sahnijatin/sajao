"""Register a finished scan once its files are in object storage.

The phone uploads every file of the capture package through /v1/uploads,
then registers the capture here with the storage keys. The API checks that
the object is a valid Capture and that every key belongs to the caller, and
stores it. Registering is the upload's completion: it also makes the capture's room
and starts the pipeline, with no further call from the app. The capture id comes from
the phone, so a retry after a lost connection returns the capture already stored and
the same room.

A photo smaller than the render needs is refused here, before anything runs: the render
never enlarges a photo, so a photo below the preview size (1024 px on the long edge)
cannot be shown redesigned at it.
"""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from sajao_api.auth import Principal, current_user
from sajao_api.captures import CaptureStore, Registered
from sajao_api.errors import ApiError
from sajao_api.pipeline import PipelineLauncher, open_room
from sajao_api.rooms import RoomStore
from sajao_api.v1.uploads import is_owned_key
from sajao_schemas.generated.v1 import (
    Capture,
    CaptureDevice,
    CaptureMedia,
    CapturePackage,
    CompassReading,
)

router = APIRouter(prefix="/captures", tags=["captures"])

SCHEMA_VERSION = "1.0"

# The smallest photo the render stage takes: the preview render is 1024 px on the long
# edge and is never made by enlarging the photo; 576 px is that edge at 16:9.
MIN_PHOTO_LONG_EDGE_PX = 1024
MIN_PHOTO_SHORT_EDGE_PX = 576


class RegisterCapture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    """Chosen by the phone when the scan starts; registering it twice is safe."""
    device: CaptureDevice
    media: Annotated[list[CaptureMedia], Field(min_length=1, max_length=40)]
    package: CapturePackage | None = None
    compass: CompassReading | None = None


def get_captures(request: Request) -> CaptureStore:
    store: CaptureStore = request.app.state.captures
    return store


def get_room_store(request: Request) -> RoomStore:
    store: RoomStore = request.app.state.rooms
    return store


def get_pipeline(request: Request) -> PipelineLauncher:
    launcher: PipelineLauncher = request.app.state.pipeline
    return launcher


def too_small(media: list[CaptureMedia]) -> bool:
    """True when a photo is below the minimum the render stage needs."""
    return any(
        max(m.width_px, m.height_px) < MIN_PHOTO_LONG_EDGE_PX
        or min(m.width_px, m.height_px) < MIN_PHOTO_SHORT_EDGE_PX
        for m in media
        if m.kind == "photo"
    )


def storage_keys(body: RegisterCapture) -> list[str]:
    """Every object key the capture points at."""
    keys = [media.storage_key for media in body.media]
    package = body.package
    if package is not None:
        keys.append(package.sensor_log)
        keys.extend(keyframe.image for keyframe in package.keyframes)
        keys.extend(
            key
            for key in (package.video, package.planes, package.scene_mesh, package.depth)
            if key is not None
        )
    return keys


User = Annotated[Principal, Depends(current_user)]
Captures = Annotated[CaptureStore, Depends(get_captures)]
Rooms = Annotated[RoomStore, Depends(get_room_store)]
Launcher = Annotated[PipelineLauncher, Depends(get_pipeline)]


@router.post("", operation_id="registerCapture", status_code=201)
async def register_capture(
    body: RegisterCapture,
    user: User,
    captures: Captures,
    rooms: Rooms,
    launcher: Launcher,
    response: Response,
) -> dict[str, Any]:
    """Store a capture whose files are already uploaded, make its room and start the
    pipeline. Safe to repeat."""
    # One answer for "malformed" and "someone else's": never reveal which keys exist.
    if any(not is_owned_key(key, user.user_id) for key in storage_keys(body)):
        raise ApiError(
            422, "unknown_storage_key", "This capture points at a file that is not yours."
        )
    if too_small(body.media):
        raise ApiError(
            422,
            "photo_too_small",
            f"Each photo needs at least {MIN_PHOTO_LONG_EDGE_PX} by {MIN_PHOTO_SHORT_EDGE_PX}"
            " pixels. Take the photo again with the phone's camera.",
        )
    capture = Capture(
        schema_version=SCHEMA_VERSION,
        id=body.id,
        user_id=UUID(user.user_id),
        created_at=datetime.now(UTC),
        media=body.media,
        device=body.device,
        compass=body.compass,
        package=body.package,
    )
    document = capture.model_dump(mode="json", exclude_none=True)
    outcome, stored = await captures.register(str(body.id), user.user_id, document)
    if outcome is Registered.TAKEN or stored is None:
        raise ApiError(
            409, "capture_id_taken", "This capture could not be saved. Please scan again."
        )
    if outcome is Registered.EXISTING:
        response.status_code = 200
    # The upload is complete: the room and its job start now, on a repeat too.
    await open_room(rooms, launcher, user.user_id, str(body.id))
    return stored.capture


@router.get("/{capture_id}", operation_id="getCapture")
async def get_capture(capture_id: UUID, user: User, captures: Captures) -> dict[str, Any]:
    """The caller's own capture."""
    stored = await captures.get(str(capture_id), user.user_id)
    if stored is None:
        raise ApiError(404, "capture_not_found", "This capture does not exist.")
    return stored.capture
