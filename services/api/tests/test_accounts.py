import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from psycopg_pool import AsyncConnectionPool

from sajao_api.accounts import (
    AccountStore,
    InMemoryAccountStore,
    PostgresAccountStore,
    erase_account,
)
from sajao_api.captures import InMemoryCaptureStore, PostgresCaptureStore
from sajao_api.idempotency import InMemoryIdempotencyStore
from sajao_api.main import create_app
from sajao_api.pipeline import RecordingLauncher
from sajao_api.rooms import InMemoryRoomStore, PostgresRoomStore
from sajao_api.settings import Settings
from sajao_api.storage import InMemoryObjectStorage

from .test_auth import VERIFIER, bearer, token
from .test_captures import CAPTURE_ID, USER_A, USER_B, capture

MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"
TEST_DATABASE_URL = os.environ.get("SAJAO_TEST_DATABASE_URL") or None
OTHER_CAPTURE = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


class Files:
    def __init__(self, fail: bool = False) -> None:
        self.erased: list[str] = []
        self.fail = fail

    def erase(self, user_id: str) -> int:
        if self.fail:
            raise RuntimeError("storage is down")
        self.erased.append(user_id)
        return 3


class SignIn:
    def __init__(self) -> None:
        self.erased: list[str] = []

    async def erase(self, user_id: str) -> None:
        self.erased.append(user_id)


def client(accounts: AccountStore, launcher: RecordingLauncher) -> httpx.AsyncClient:
    app = create_app(
        Settings(),
        InMemoryIdempotencyStore(),
        VERIFIER,
        InMemoryObjectStorage(),
        InMemoryCaptureStore(),
        InMemoryRoomStore(),
        launcher,
        accounts,
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://api.test")


def headers(key: str, user: str = USER_A) -> dict[str, str]:
    return {**bearer(token(sub=user)), "Idempotency-Key": f"delete-key-{key}-0001"}


async def test_deleting_an_account_records_the_request_and_starts_the_erasure() -> None:
    accounts, launcher = InMemoryAccountStore(), RecordingLauncher()
    async with client(accounts, launcher) as api:
        asked = await api.request("DELETE", "/v1/me", headers=headers("a"))
        assert asked.status_code == 202, asked.text
        assert asked.json() == {"status": "deleting"}
        assert launcher.deletions == [USER_A]
        assert await accounts.deletion_finished(USER_A) is False
        assert await accounts.deletion_finished(USER_B) is None

        # A repeat starts the erasure again and says the same.
        again = await api.request("DELETE", "/v1/me", headers=headers("b"))
        assert again.status_code == 202
        assert launcher.deletions == [USER_A, USER_A]

        await erase_account(USER_A, accounts, Files(), SignIn())
        done = await api.request("DELETE", "/v1/me", headers=headers("c"))
        assert done.json() == {"status": "deleted"}


async def test_deleting_needs_a_signed_in_caller() -> None:
    launcher = RecordingLauncher()
    async with client(InMemoryAccountStore(), launcher) as api:
        refused = await api.request(
            "DELETE", "/v1/me", headers={"Idempotency-Key": "delete-key-anon-0001"}
        )
        assert refused.status_code == 401
        assert launcher.deletions == []


async def test_erasing_removes_files_then_rows_then_the_sign_in_account() -> None:
    accounts, files, sign_in = InMemoryAccountStore(), Files(), SignIn()
    await accounts.request_deletion(USER_A)
    assert await erase_account(USER_A, accounts, files, sign_in) == 3
    assert files.erased == [USER_A]
    assert accounts.erased == [USER_A]
    assert sign_in.erased == [USER_A]
    assert await accounts.deletion_finished(USER_A) is True


async def test_a_failed_erasure_keeps_the_account_so_it_can_run_again() -> None:
    accounts, sign_in = InMemoryAccountStore(), SignIn()
    await accounts.request_deletion(USER_A)
    with pytest.raises(RuntimeError):
        await erase_account(USER_A, accounts, Files(fail=True), sign_in)
    assert sign_in.erased == []
    assert await accounts.deletion_finished(USER_A) is False
    assert await accounts.unfinished_deletions() == [USER_A]

    await erase_account(USER_A, accounts, Files(), sign_in)
    assert await accounts.deletion_finished(USER_A) is True


@pytest.fixture
async def pool() -> AsyncIterator[AsyncConnectionPool]:
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
            tables = {
                "idempotency": "private.idempotency_keys",
                "rooms": "public.rooms",
                "captures.sql": "public.captures",
                "account_deletions": "private.account_deletions",
            }
            for migration in sorted(MIGRATIONS.glob("*.sql")):
                table = next((t for part, t in tables.items() if part in migration.name), None)
                if table is None:
                    continue
                row = await (
                    await connection.execute("select to_regclass(%s)", (table,))
                ).fetchone()
                if row is None or row[0] is None:
                    await connection.execute(migration.read_bytes())
            await connection.execute("truncate public.captures, private.account_deletions cascade")
        yield pool
    finally:
        await pool.close()


async def test_postgres_erases_only_the_users_own_rows(pool: AsyncConnectionPool) -> None:
    captures, rooms, accounts = (
        PostgresCaptureStore(pool),
        PostgresRoomStore(pool),
        PostgresAccountStore(pool),
    )
    await captures.register(CAPTURE_ID, USER_A, capture(USER_A, CAPTURE_ID))
    await captures.register(OTHER_CAPTURE, USER_B, capture(USER_B, OTHER_CAPTURE))
    mine, _ = await rooms.create_room("11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa", USER_A, CAPTURE_ID)
    theirs, _ = await rooms.create_room(
        "22222222-aaaa-4aaa-8aaa-aaaaaaaaaaaa", USER_B, OTHER_CAPTURE
    )

    assert await accounts.request_deletion(USER_A) is True
    assert await accounts.request_deletion(USER_A) is False
    assert await accounts.unfinished_deletions() == [USER_A]
    await erase_account(USER_A, accounts, Files(), SignIn())
    await erase_account(USER_A, accounts, Files(), SignIn())  # safe to repeat

    assert await rooms.get_room(mine.room_id, USER_A) is None
    assert await captures.get(CAPTURE_ID, USER_A) is None
    assert await rooms.list_rooms(USER_A) == []
    assert await rooms.get_room(theirs.room_id, USER_B) is not None
    assert await captures.get(OTHER_CAPTURE, USER_B) is not None
    assert await accounts.deletion_finished(USER_A) is True
    assert await accounts.unfinished_deletions() == []
    async with pool.connection() as connection:
        left = await (
            await connection.execute(
                "select count(*) from public.pipeline_stages where user_id = %s", (USER_A,)
            )
        ).fetchone()
    assert left == (0,)
