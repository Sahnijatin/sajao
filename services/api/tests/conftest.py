import asyncio
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool

from sajao_api.idempotency import (
    IdempotencyStore,
    InMemoryIdempotencyStore,
    PostgresIdempotencyStore,
)
from sajao_api.main import create_app
from sajao_api.settings import Settings

MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"
TEST_DATABASE_URL = os.environ.get("SAJAO_TEST_DATABASE_URL") or None


@pytest.fixture(params=["memory", "postgres"])
async def store(request: pytest.FixtureRequest) -> AsyncIterator[IdempotencyStore]:
    """Every idempotency test runs against both stores."""
    if request.param == "memory":
        yield InMemoryIdempotencyStore()
        return
    if TEST_DATABASE_URL is None:
        pytest.skip("SAJAO_TEST_DATABASE_URL is not set")
    pool = AsyncConnectionPool(
        TEST_DATABASE_URL,
        open=False,
        min_size=1,
        max_size=5,
        kwargs={"prepare_threshold": None, "autocommit": True},
    )
    await pool.open()
    try:
        async with pool.connection() as connection:
            row = await (
                await connection.execute("select to_regclass('private.idempotency_keys')")
            ).fetchone()
            if row is None or row[0] is None:
                for migration in sorted(MIGRATIONS.glob("*.sql")):
                    await connection.execute(migration.read_bytes())
            await connection.execute("truncate private.idempotency_keys")
        yield PostgresIdempotencyStore(pool)
    finally:
        await pool.close()


class Calls:
    """Counts how many times the test handlers really ran."""

    def __init__(self) -> None:
        self.created = 0
        self.failed = 0
        self.slow_started = asyncio.Event()
        self.release_slow = asyncio.Event()


def add_test_routes(app: FastAPI, calls: Calls) -> None:
    @app.post("/v1/test/things", status_code=201)
    async def create_thing(payload: dict[str, str]) -> dict[str, object]:
        calls.created += 1
        return {"number": calls.created, "name": payload["name"]}

    @app.post("/v1/test/flaky")
    async def flaky() -> dict[str, str]:
        calls.failed += 1
        if calls.failed == 1:
            raise RuntimeError("first attempt fails")
        return {"status": "ok"}

    @app.post("/v1/test/slow", status_code=201)
    async def slow() -> dict[str, int]:
        calls.created += 1
        calls.slow_started.set()
        await calls.release_slow.wait()
        return {"number": calls.created}


ClientFactory = Callable[..., httpx.AsyncClient]


@pytest.fixture
def calls() -> Calls:
    return Calls()


@pytest.fixture
def make_client(calls: Calls) -> ClientFactory:
    def build(
        settings: Settings | None = None, store: IdempotencyStore | None = None
    ) -> httpx.AsyncClient:
        app = create_app(settings or Settings(), store or InMemoryIdempotencyStore())
        add_test_routes(app, calls)
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url="http://api.test")

    return build
