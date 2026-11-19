"""Rooms, their design requests and the pipeline's stage status.

A room is a registered capture on its way to a measured room and then to
designs. The API creates rows and reads them; the pipeline worker moves the
stages and stores each result. Ids for writes come from the phone or from the
capture, so creating twice returns what is already there.
"""

from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

StageStatus = Literal["queued", "running", "done", "failed"]

# The room's own stages, in order: what the phone measured, then what is in the room.
ROOM_STAGES: tuple[str, ...] = ("measure", "inventory")
# A design request's stages, in order: the spec and product selection, placement
# and verification, then the renders.
DESIGN_STAGES: tuple[str, ...] = ("spec", "placement", "render")


@dataclass(frozen=True)
class Stage:
    stage: str
    status: StageStatus
    attempts: int = 0
    detail: str | None = None


@dataclass(frozen=True)
class Room:
    room_id: str
    user_id: str
    capture_id: str
    created_at: str
    stages: tuple[Stage, ...] = ()
    space_twin: dict[str, Any] | None = None


@dataclass(frozen=True)
class DesignRequest:
    request_id: str
    room_id: str
    user_id: str
    brief: dict[str, Any]
    created_at: str
    stages: tuple[Stage, ...] = ()
    designs: list[dict[str, Any]] | None = None


class RoomStore(Protocol):
    async def create_room(self, room_id: str, user_id: str, capture_id: str) -> tuple[Room, bool]:
        """The room for this capture and whether this call created it."""
        ...

    async def get_room(self, room_id: str, user_id: str) -> Room | None: ...

    async def list_rooms(self, user_id: str) -> list[Room]:
        """The caller's rooms, newest first."""
        ...

    async def create_design_request(
        self, request_id: str, room_id: str, user_id: str, brief: dict[str, Any]
    ) -> tuple[DesignRequest | None, bool]:
        """The request under this id and whether this call created it; None if the id is taken."""
        ...

    async def latest_design_request(self, room_id: str, user_id: str) -> DesignRequest | None: ...

    async def get_design_request(self, request_id: str, user_id: str) -> DesignRequest | None:
        """One of the caller's design requests, with its designs once ready."""
        ...


def _queued(names: tuple[str, ...]) -> tuple[Stage, ...]:
    return tuple(Stage(name, "queued") for name in names)


@dataclass
class _MemoryRoom:
    room: Room
    requests: list[DesignRequest] = field(default_factory=list)


class InMemoryRoomStore:
    """For local development and tests only: state lives in one process."""

    def __init__(self) -> None:
        self._rooms: dict[str, _MemoryRoom] = {}
        self._clock = 0

    def _now(self) -> str:
        self._clock += 1
        return f"2026-01-01T00:00:{self._clock:02d}+00:00"

    async def create_room(self, room_id: str, user_id: str, capture_id: str) -> tuple[Room, bool]:
        for held in self._rooms.values():
            if held.room.capture_id == capture_id:
                return held.room, False
        room = Room(room_id, user_id, capture_id, self._now(), _queued(ROOM_STAGES))
        self._rooms[room_id] = _MemoryRoom(room)
        return room, True

    async def get_room(self, room_id: str, user_id: str) -> Room | None:
        held = self._rooms.get(room_id)
        return held.room if held is not None and held.room.user_id == user_id else None

    async def list_rooms(self, user_id: str) -> list[Room]:
        rooms = [held.room for held in self._rooms.values() if held.room.user_id == user_id]
        return sorted(rooms, key=lambda room: room.created_at, reverse=True)

    async def create_design_request(
        self, request_id: str, room_id: str, user_id: str, brief: dict[str, Any]
    ) -> tuple[DesignRequest | None, bool]:
        for held in self._rooms.values():
            for request in held.requests:
                if request.request_id == request_id:
                    same = request.user_id == user_id and request.room_id == room_id
                    return (request if same else None), False
        request = DesignRequest(
            request_id, room_id, user_id, brief, self._now(), _queued(DESIGN_STAGES)
        )
        self._rooms[room_id].requests.append(request)
        return request, True

    async def latest_design_request(self, room_id: str, user_id: str) -> DesignRequest | None:
        held = self._rooms.get(room_id)
        if held is None or held.room.user_id != user_id or not held.requests:
            return None
        return held.requests[-1]

    async def get_design_request(self, request_id: str, user_id: str) -> DesignRequest | None:
        for held in self._rooms.values():
            for request in held.requests:
                if request.request_id == request_id and request.user_id == user_id:
                    return request
        return None

    # What the pipeline worker does. Each is safe to repeat.
    async def set_stage(
        self,
        room_id: str,
        stage: str,
        status: StageStatus,
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None:
        held = self._rooms[room_id]

        def moved(stages: tuple[Stage, ...]) -> tuple[Stage, ...]:
            return tuple(
                Stage(s.stage, status, s.attempts + (status == "running"), detail)
                if s.stage == stage
                else s
                for s in stages
            )

        if request_id is None:
            held.room = replace(held.room, stages=moved(held.room.stages))
            return
        held.requests = [
            replace(r, stages=moved(r.stages)) if r.request_id == request_id else r
            for r in held.requests
        ]

    async def set_space_twin(self, room_id: str, twin: dict[str, Any]) -> None:
        held = self._rooms[room_id]
        held.room = replace(held.room, space_twin=twin)

    async def design_request_for_pipeline(
        self, request_id: str
    ) -> tuple[DesignRequest, dict[str, Any] | None] | None:
        for held in self._rooms.values():
            for request in held.requests:
                if request.request_id == request_id:
                    return request, held.room.space_twin
        return None

    async def set_designs(self, request_id: str, designs: list[dict[str, Any]]) -> None:
        for held in self._rooms.values():
            held.requests = [
                replace(r, designs=designs) if r.request_id == request_id else r
                for r in held.requests
            ]


_INSERT_ROOM = """
insert into public.rooms (id, user_id, capture_id)
values (%(id)s, %(user_id)s, %(capture_id)s)
on conflict (capture_id) do nothing
returning id
"""
_INSERT_STAGE = """
insert into public.pipeline_stages (room_id, design_request_id, stage, position, user_id)
values (%(room_id)s, %(request_id)s, %(stage)s, %(position)s, %(user_id)s)
"""
_ROOM_BY_CAPTURE = "select id::text from public.rooms where capture_id = %(capture_id)s"
_READ_ROOM = """
select id::text, user_id::text, capture_id::text, created_at, space_twin
from public.rooms
where id = %(id)s and user_id = %(user_id)s
"""
_LIST_ROOMS = """
select id::text, user_id::text, capture_id::text, created_at, space_twin
from public.rooms
where user_id = %(user_id)s
order by created_at desc
limit 100
"""
_ROOM_STAGES = """
select room_id::text, stage, status, attempts, detail
from public.pipeline_stages
where room_id = any(%(room_ids)s) and design_request_id is null
order by position
"""
_INSERT_REQUEST = """
insert into public.design_requests (id, room_id, user_id, brief)
values (%(id)s, %(room_id)s, %(user_id)s, %(brief)s)
on conflict (id) do nothing
returning id
"""
_READ_REQUEST = """
select id::text, room_id::text, user_id::text, brief, created_at, designs
from public.design_requests
where id = %(id)s
"""
_LATEST_REQUEST = """
select id::text, room_id::text, user_id::text, brief, created_at, designs
from public.design_requests
where room_id = %(room_id)s and user_id = %(user_id)s
order by created_at desc
limit 1
"""
_REQUEST_STAGES = """
select stage, status, attempts, detail
from public.pipeline_stages
where design_request_id = %(request_id)s
order by position
"""


_ROOM_TWIN = """
select space_twin from public.rooms where id = %(room_id)s
"""
_CAPTURE_FOR_ROOM = """
select r.user_id::text, c.capture
from public.rooms r
join public.captures c on c.id = r.capture_id
where r.id = %(room_id)s
"""
_SET_STAGE = """
update public.pipeline_stages
set status = %(status)s,
    detail = %(detail)s,
    attempts = attempts + (%(status)s = 'running')::int,
    updated_at = now()
where room_id = %(room_id)s
  and stage = %(stage)s
  and design_request_id is not distinct from %(request_id)s::uuid
"""


class PostgresRoomStore:
    """Shared across API instances, so the service stays stateless."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def create_room(self, room_id: str, user_id: str, capture_id: str) -> tuple[Room, bool]:
        params = {"id": room_id, "user_id": user_id, "capture_id": capture_id}
        async with self._pool.connection() as connection, connection.transaction():
            created = await (await connection.execute(_INSERT_ROOM, params)).fetchone()
            if created is not None:
                for position, stage in enumerate(ROOM_STAGES):
                    await connection.execute(
                        _INSERT_STAGE,
                        {
                            "room_id": room_id,
                            "request_id": None,
                            "stage": stage,
                            "position": position,
                            "user_id": user_id,
                        },
                    )
            else:
                row = await (await connection.execute(_ROOM_BY_CAPTURE, params)).fetchone()
                if row is None:  # the capture's room vanished between the two statements
                    raise RuntimeError("room for capture not found after conflict")
                room_id = row[0]
        room = await self.get_room(room_id, user_id)
        if room is None:
            raise RuntimeError("room not readable after it was created")
        return room, created is not None

    async def _rooms(self, rows: list[Any]) -> list[Room]:
        if not rows:
            return []
        async with self._pool.connection() as connection:
            stage_rows = await (
                await connection.execute(_ROOM_STAGES, {"room_ids": [row[0] for row in rows]})
            ).fetchall()
        stages: dict[str, list[Stage]] = {}
        for room_id, stage, status, attempts, detail in stage_rows:
            stages.setdefault(room_id, []).append(Stage(stage, status, attempts, detail))
        return [
            Room(
                room_id=row[0],
                user_id=row[1],
                capture_id=row[2],
                created_at=row[3].isoformat(),
                stages=tuple(stages.get(row[0], [])),
                space_twin=row[4],
            )
            for row in rows
        ]

    async def get_room(self, room_id: str, user_id: str) -> Room | None:
        async with self._pool.connection() as connection:
            row = await (
                await connection.execute(_READ_ROOM, {"id": room_id, "user_id": user_id})
            ).fetchone()
        rooms = await self._rooms([row] if row is not None else [])
        return rooms[0] if rooms else None

    async def list_rooms(self, user_id: str) -> list[Room]:
        async with self._pool.connection() as connection:
            rows = await (await connection.execute(_LIST_ROOMS, {"user_id": user_id})).fetchall()
        return await self._rooms(rows)

    async def _request(self, row: Any) -> DesignRequest:
        async with self._pool.connection() as connection:
            stage_rows = await (
                await connection.execute(_REQUEST_STAGES, {"request_id": row[0]})
            ).fetchall()
        return DesignRequest(
            request_id=row[0],
            room_id=row[1],
            user_id=row[2],
            brief=row[3],
            created_at=row[4].isoformat(),
            stages=tuple(Stage(*stage) for stage in stage_rows),
            designs=row[5],
        )

    async def create_design_request(
        self, request_id: str, room_id: str, user_id: str, brief: dict[str, Any]
    ) -> tuple[DesignRequest | None, bool]:
        params = {"id": request_id, "room_id": room_id, "user_id": user_id, "brief": Jsonb(brief)}
        async with self._pool.connection() as connection, connection.transaction():
            created = await (await connection.execute(_INSERT_REQUEST, params)).fetchone()
            if created is not None:
                for position, stage in enumerate(DESIGN_STAGES):
                    await connection.execute(
                        _INSERT_STAGE,
                        {
                            "room_id": room_id,
                            "request_id": request_id,
                            "stage": stage,
                            "position": position,
                            "user_id": user_id,
                        },
                    )
            row = await (await connection.execute(_READ_REQUEST, params)).fetchone()
        if row is None or row[1] != room_id or row[2] != user_id:
            return None, False
        return await self._request(row), created is not None

    async def latest_design_request(self, room_id: str, user_id: str) -> DesignRequest | None:
        async with self._pool.connection() as connection:
            row = await (
                await connection.execute(_LATEST_REQUEST, {"room_id": room_id, "user_id": user_id})
            ).fetchone()
        return await self._request(row) if row is not None else None

    async def get_design_request(self, request_id: str, user_id: str) -> DesignRequest | None:
        async with self._pool.connection() as connection:
            row = await (await connection.execute(_READ_REQUEST, {"id": request_id})).fetchone()
        if row is None or row[2] != user_id:
            return None
        return await self._request(row)

    async def design_request_for_pipeline(
        self, request_id: str
    ) -> tuple[DesignRequest, dict[str, Any] | None] | None:
        """A design request and its room's twin, for the pipeline worker (any user)."""
        async with self._pool.connection() as connection:
            row = await (await connection.execute(_READ_REQUEST, {"id": request_id})).fetchone()
            if row is None:
                return None
            twin = await (
                await connection.execute(_ROOM_TWIN, {"room_id": row[1]})
            ).fetchone()
        return await self._request(row), (twin[0] if twin is not None else None)

    async def capture_for_room(self, room_id: str) -> tuple[str, dict[str, Any]] | None:
        """The room's owner and the capture it was made from, for the pipeline worker."""
        async with self._pool.connection() as connection:
            row = await (
                await connection.execute(_CAPTURE_FOR_ROOM, {"room_id": room_id})
            ).fetchone()
        return (row[0], row[1]) if row is not None else None

    # What the pipeline worker does. Each is safe to repeat.
    async def set_stage(
        self,
        room_id: str,
        stage: str,
        status: StageStatus,
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None:
        params = {
            "room_id": room_id,
            "request_id": request_id,
            "stage": stage,
            "status": status,
            "detail": detail,
        }
        async with self._pool.connection() as connection:
            await connection.execute(_SET_STAGE, params)

    async def set_space_twin(self, room_id: str, twin: dict[str, Any]) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "update public.rooms set space_twin = %(twin)s where id = %(id)s",
                {"id": room_id, "twin": Jsonb(twin)},
            )

    async def set_designs(self, request_id: str, designs: list[dict[str, Any]]) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "update public.design_requests set designs = %(designs)s where id = %(id)s",
                {"id": request_id, "designs": Jsonb(designs)},
            )
