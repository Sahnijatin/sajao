"""Where registered captures are kept.

A capture is registered once its files are in object storage. The row holds
the validated Capture object; the twin worker reads it from there. The id is
chosen by the phone, so registering the same capture again changes nothing.
"""

import enum
from dataclasses import dataclass
from typing import Any, Protocol

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool


class Registered(enum.Enum):
    CREATED = "created"
    EXISTING = "existing"  # Same id, same owner: a retry.
    TAKEN = "taken"  # The id belongs to someone else.


@dataclass(frozen=True)
class StoredCapture:
    capture_id: str
    user_id: str
    capture: dict[str, Any]


class CaptureStore(Protocol):
    async def register(
        self, capture_id: str, user_id: str, capture: dict[str, Any]
    ) -> tuple[Registered, StoredCapture | None]:
        """Store a capture, or return the one already stored under this id."""
        ...

    async def get(self, capture_id: str, user_id: str) -> StoredCapture | None:
        """The caller's own capture, or None."""
        ...


class InMemoryCaptureStore:
    """For local development and tests only: state lives in one process."""

    def __init__(self) -> None:
        self._rows: dict[str, StoredCapture] = {}

    async def register(
        self, capture_id: str, user_id: str, capture: dict[str, Any]
    ) -> tuple[Registered, StoredCapture | None]:
        existing = self._rows.get(capture_id)
        if existing is None:
            stored = StoredCapture(capture_id, user_id, capture)
            self._rows[capture_id] = stored
            return Registered.CREATED, stored
        if existing.user_id != user_id:
            return Registered.TAKEN, None
        return Registered.EXISTING, existing

    async def get(self, capture_id: str, user_id: str) -> StoredCapture | None:
        stored = self._rows.get(capture_id)
        return stored if stored is not None and stored.user_id == user_id else None


_INSERT = """
insert into public.captures (id, user_id, capture)
values (%(id)s, %(user_id)s, %(capture)s)
on conflict (id) do nothing
returning id
"""
_READ = "select user_id::text, capture from public.captures where id = %(id)s"


class PostgresCaptureStore:
    """Shared across API instances, so the service stays stateless."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def register(
        self, capture_id: str, user_id: str, capture: dict[str, Any]
    ) -> tuple[Registered, StoredCapture | None]:
        params = {"id": capture_id, "user_id": user_id, "capture": Jsonb(capture)}
        async with self._pool.connection() as connection:
            if await (await connection.execute(_INSERT, params)).fetchone() is not None:
                return Registered.CREATED, StoredCapture(capture_id, user_id, capture)
            row = await (await connection.execute(_READ, params)).fetchone()
        if row is None or row[0] != user_id:
            return Registered.TAKEN, None
        return Registered.EXISTING, StoredCapture(capture_id, user_id, row[1])

    async def get(self, capture_id: str, user_id: str) -> StoredCapture | None:
        async with self._pool.connection() as connection:
            row = await (await connection.execute(_READ, {"id": capture_id})).fetchone()
        if row is None or row[0] != user_id:
            return None
        return StoredCapture(capture_id, user_id, row[1])
