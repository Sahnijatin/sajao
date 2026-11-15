"""Idempotency keys: a retried write runs once and replays the first answer.

Mobile networks drop requests after the server has acted on them. Every
write carries an Idempotency-Key; the first response is stored and returned
for any retry with the same key and the same request.
"""

import asyncio
import enum
import json
import time
from dataclasses import dataclass
from typing import Protocol

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool


@dataclass(frozen=True)
class StoredResponse:
    status_code: int
    headers: list[tuple[str, str]]
    body: bytes


class Outcome(enum.Enum):
    STARTED = "started"  # First time: run the request.
    IN_PROGRESS = "in_progress"  # Another request with this key is still running.
    MISMATCH = "mismatch"  # The key was used for a different request.
    COMPLETED = "completed"  # Replay the stored response.


@dataclass(frozen=True)
class Reservation:
    outcome: Outcome
    response: StoredResponse | None = None


class IdempotencyStore(Protocol):
    async def reserve(
        self, scope: str, key: str, fingerprint: str, in_progress_seconds: int
    ) -> Reservation: ...

    async def complete(
        self, scope: str, key: str, response: StoredResponse, ttl_seconds: int
    ) -> None: ...

    async def release(self, scope: str, key: str) -> None: ...


@dataclass
class _Entry:
    fingerprint: str
    expires_at: float
    response: StoredResponse | None = None


class InMemoryIdempotencyStore:
    """For local development and tests only: state lives in one process."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], _Entry] = {}
        self._lock = asyncio.Lock()

    async def reserve(
        self, scope: str, key: str, fingerprint: str, in_progress_seconds: int
    ) -> Reservation:
        async with self._lock:
            now = time.monotonic()
            entry = self._entries.get((scope, key))
            if entry is None or entry.expires_at <= now:
                self._entries[(scope, key)] = _Entry(fingerprint, now + in_progress_seconds)
                return Reservation(Outcome.STARTED)
            if entry.fingerprint != fingerprint:
                return Reservation(Outcome.MISMATCH)
            if entry.response is None:
                return Reservation(Outcome.IN_PROGRESS)
            return Reservation(Outcome.COMPLETED, entry.response)

    async def complete(
        self, scope: str, key: str, response: StoredResponse, ttl_seconds: int
    ) -> None:
        async with self._lock:
            entry = self._entries.get((scope, key))
            if entry is not None:
                entry.response = response
                entry.expires_at = time.monotonic() + ttl_seconds

    async def release(self, scope: str, key: str) -> None:
        async with self._lock:
            self._entries.pop((scope, key), None)


# One statement decides atomically: insert a new key, or take over an expired
# one. Nothing is returned when a live row already holds the key.
_RESERVE = """
insert into private.idempotency_keys as k (scope, key, fingerprint, expires_at)
values (%(scope)s, %(key)s, %(fingerprint)s, now() + make_interval(secs => %(seconds)s))
on conflict (scope, key) do update
    set fingerprint = excluded.fingerprint,
        status_code = null,
        headers = null,
        body = null,
        created_at = now(),
        expires_at = excluded.expires_at
    where k.expires_at <= now()
returning 1
"""

_READ = """
select fingerprint, status_code, headers, body
from private.idempotency_keys
where scope = %(scope)s and key = %(key)s
"""

_COMPLETE = """
update private.idempotency_keys
set status_code = %(status_code)s,
    headers = %(headers)s,
    body = %(body)s,
    expires_at = now() + make_interval(secs => %(seconds)s)
where scope = %(scope)s and key = %(key)s
"""

_RELEASE = "delete from private.idempotency_keys where scope = %(scope)s and key = %(key)s"


class PostgresIdempotencyStore:
    """Shared across API instances, so the service stays stateless."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def reserve(
        self, scope: str, key: str, fingerprint: str, in_progress_seconds: int
    ) -> Reservation:
        params = {
            "scope": scope,
            "key": key,
            "fingerprint": fingerprint,
            "seconds": in_progress_seconds,
        }
        async with self._pool.connection() as connection:
            if await (await connection.execute(_RESERVE, params)).fetchone() is not None:
                return Reservation(Outcome.STARTED)
            row = await (await connection.execute(_READ, params)).fetchone()
        if row is None:
            # Released between the two statements: the caller may simply retry.
            return Reservation(Outcome.IN_PROGRESS)
        stored_fingerprint, status_code, headers, body = row
        if stored_fingerprint != fingerprint:
            return Reservation(Outcome.MISMATCH)
        if status_code is None:
            return Reservation(Outcome.IN_PROGRESS)
        stored = StoredResponse(
            status_code, [(name, value) for name, value in headers], bytes(body)
        )
        return Reservation(Outcome.COMPLETED, stored)

    async def complete(
        self, scope: str, key: str, response: StoredResponse, ttl_seconds: int
    ) -> None:
        params = {
            "scope": scope,
            "key": key,
            "status_code": response.status_code,
            "headers": Jsonb(json.loads(json.dumps(response.headers))),
            "body": response.body,
            "seconds": ttl_seconds,
        }
        async with self._pool.connection() as connection:
            await connection.execute(_COMPLETE, params)

    async def release(self, scope: str, key: str) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(_RELEASE, {"scope": scope, "key": key})
