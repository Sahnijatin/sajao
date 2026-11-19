"""Rooms and designs for the app.

A room is created when its capture is registered, and the durable pipeline starts
at once: it measures the room and lists what is in it, then designs it once the app
sends a brief (accepted at any point; designing waits for the room to be read). The
app reads one RoomStatus (stage, failure reason, confidence level, fit checks), the
room's SpaceTwin once it is read, and the designs. Every write is safe to repeat.
"""

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict

from sajao_api.auth import Principal, current_user
from sajao_api.captures import CaptureStore
from sajao_api.errors import ApiError
from sajao_api.pipeline import PipelineLauncher, open_room
from sajao_api.room_status import room_status
from sajao_api.rooms import DesignRequest, Room, RoomStore, Stage
from sajao_api.v1.captures import get_captures
from sajao_schemas import RoomStatus
from sajao_schemas.generated.v1 import Brief

router = APIRouter(prefix="/rooms", tags=["rooms"])
logger = logging.getLogger(__name__)


class CreateRoom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture_id: UUID


class RequestDesigns(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    """Chosen by the phone; asking again with the same id returns the same request."""
    brief: Brief


class StageStatus(BaseModel):
    stage: str
    status: str
    """queued, running, done or failed."""
    detail: str | None = None
    """Why it failed: a short reason code the app turns into words, such as no_walls."""


class RoomList(BaseModel):
    rooms: list[RoomStatus]


class DesignsStatus(BaseModel):
    id: str
    room_id: str
    created_at: str
    status: str
    stages: list[StageStatus]
    designs: list[dict[str, Any]] | None = None
    """The three Designs, each with its renders and shopping list, once ready."""


def get_rooms(request: Request) -> RoomStore:
    store: RoomStore = request.app.state.rooms
    return store


def get_launcher(request: Request) -> PipelineLauncher:
    launcher: PipelineLauncher = request.app.state.pipeline
    return launcher


def overall(stages: tuple[Stage, ...]) -> str:
    if any(stage.status == "failed" for stage in stages):
        return "failed"
    return "ready" if stages and all(stage.status == "done" for stage in stages) else "working"


def _stages(stages: tuple[Stage, ...]) -> list[StageStatus]:
    return [StageStatus(stage=s.stage, status=s.status, detail=s.detail) for s in stages]


async def _status(room: Room, user: Principal, rooms: RoomStore) -> dict[str, Any]:
    return room_status(room, await rooms.latest_design_request(room.room_id, user.user_id))


def _designs(request: DesignRequest) -> DesignsStatus:
    return DesignsStatus(
        id=request.request_id,
        room_id=request.room_id,
        created_at=request.created_at,
        status=overall(request.stages),
        stages=_stages(request.stages),
        designs=request.designs,
    )


User = Annotated[Principal, Depends(current_user)]
Rooms = Annotated[RoomStore, Depends(get_rooms)]
Captures = Annotated[CaptureStore, Depends(get_captures)]
Launcher = Annotated[PipelineLauncher, Depends(get_launcher)]


async def _owned_room(room_id: UUID, user: Principal, rooms: RoomStore) -> Room:
    room = await rooms.get_room(str(room_id), user.user_id)
    if room is None:
        raise ApiError(404, "room_not_found", "This room does not exist.")
    return room


@router.post(
    "",
    operation_id="createRoom",
    status_code=201,
    response_model=RoomStatus,
    response_model_exclude_unset=True,
)
async def create_room(
    body: CreateRoom,
    user: User,
    rooms: Rooms,
    captures: Captures,
    launcher: Launcher,
    response: Response,
) -> dict[str, Any]:
    """The room for a registered capture. Registering the capture already made it and
    started it; this returns it, and starts it again if it failed. Safe to repeat."""
    capture = await captures.get(str(body.capture_id), user.user_id)
    if capture is None:
        raise ApiError(404, "capture_not_found", "This capture does not exist.")
    room, created = await open_room(rooms, launcher, user.user_id, str(body.capture_id))
    if not created:
        response.status_code = 200
    return await _status(room, user, rooms)


@router.get("", operation_id="listRooms", response_model_exclude_unset=True)
async def list_rooms(user: User, rooms: Rooms) -> RoomList:
    """The caller's rooms, newest first, each with its status."""
    found = await rooms.list_rooms(user.user_id)
    return RoomList.model_validate({"rooms": [await _status(room, user, rooms) for room in found]})


@router.get(
    "/{room_id}",
    operation_id="getRoom",
    response_model=RoomStatus,
    response_model_exclude_unset=True,
)
async def get_room(room_id: UUID, user: User, rooms: Rooms) -> dict[str, Any]:
    """One room's status: its stage, why it failed, how it was measured, and per design
    item whether a fit check ran."""
    return await _status(await _owned_room(room_id, user, rooms), user, rooms)


@router.get("/{room_id}/twin", operation_id="getRoomTwin")
async def get_room_twin(room_id: UUID, user: User, rooms: Rooms) -> dict[str, Any]:
    """The room's SpaceTwin: its measurements, what is in it and its hero views."""
    room = await _owned_room(room_id, user, rooms)
    if room.space_twin is None:
        raise ApiError(409, "room_not_ready", "This room is still being measured.")
    return room.space_twin


@router.post("/{room_id}/designs", operation_id="requestDesigns", status_code=201)
async def request_designs(
    room_id: UUID,
    body: RequestDesigns,
    user: User,
    rooms: Rooms,
    launcher: Launcher,
    response: Response,
) -> DesignsStatus:
    """Ask for designs for a room with a brief, at any point: before the room is read,
    designing starts as soon as it is. Safe to repeat with the same id."""
    room = await _owned_room(room_id, user, rooms)
    request, created = await rooms.create_design_request(
        str(body.id), room.room_id, user.user_id, body.brief.model_dump(mode="json")
    )
    if request is None:
        raise ApiError(409, "design_request_id_taken", "Please ask for designs again.")
    if not created:
        response.status_code = 200
    retry = any(stage.status == "failed" for stage in request.stages)
    if room.space_twin is not None and (created or retry):
        try:
            await launcher.start_designs(room.room_id, request.request_id)
        except Exception:
            # Its rows are queued; the sweeper or a repeat of this call starts it.
            logger.exception("pipeline did not start for design request %s", request.request_id)
    return _designs(request)


@router.get("/{room_id}/designs", operation_id="getDesigns")
async def get_designs(room_id: UUID, user: User, rooms: Rooms) -> DesignsStatus:
    """The room's latest design request: its job status and, once ready, the three Designs."""
    room = await _owned_room(room_id, user, rooms)
    request = await rooms.latest_design_request(room.room_id, user.user_id)
    if request is None:
        raise ApiError(404, "designs_not_requested", "No designs have been asked for yet.")
    return _designs(request)
