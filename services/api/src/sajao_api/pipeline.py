"""Starting the durable pipeline for a room or a design request.

The API only asks for work to start; the worker runs the stages, stores each
result and moves the stage rows. Starting twice is safe: a stage that is done
is not run again.
"""

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class PipelineLauncher(Protocol):
    async def start_room(self, room_id: str) -> None: ...

    async def start_designs(self, room_id: str, request_id: str) -> None: ...


class RecordingLauncher:
    """Starts nothing and remembers what was asked: for development and tests."""

    def __init__(self) -> None:
        self.rooms: list[str] = []
        self.designs: list[tuple[str, str]] = []

    async def start_room(self, room_id: str) -> None:
        self.rooms.append(room_id)

    async def start_designs(self, room_id: str, request_id: str) -> None:
        self.designs.append((room_id, request_id))


class ModalLauncher:
    """Spawns the worker's Modal functions by name; returns as soon as they are queued."""

    def __init__(self, app_name: str) -> None:
        self._app_name = app_name

    async def _spawn(self, function: str, *args: str) -> None:
        import modal  # type: ignore[import-not-found,unused-ignore]  # only where the API runs on Modal

        target = modal.Function.from_name(self._app_name, function)
        await target.spawn.aio(*args)

    async def start_room(self, room_id: str) -> None:
        await self._spawn("run_room", room_id)

    async def start_designs(self, room_id: str, request_id: str) -> None:
        await self._spawn("run_designs", room_id, request_id)
