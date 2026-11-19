import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from psycopg_pool import AsyncConnectionPool

from sajao_api.captures import CaptureStore, InMemoryCaptureStore, PostgresCaptureStore
from sajao_api.idempotency import InMemoryIdempotencyStore
from sajao_api.main import create_app
from sajao_api.pipeline import RecordingLauncher
from sajao_api.rooms import InMemoryRoomStore, PostgresRoomStore
from sajao_api.settings import Settings
from sajao_api.storage import InMemoryObjectStorage

from .test_auth import VERIFIER, bearer, token
from .test_captures import CAPTURE_ID, USER_A, USER_B, capture

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "supabase" / "migrations"
FIXTURES = ROOT / "packages" / "schemas" / "fixtures" / "v1" / "valid"
TEST_DATABASE_URL = os.environ.get("SAJAO_TEST_DATABASE_URL") or None
REQUEST_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
OTHER_CAPTURE = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
_keys = iter(range(1, 10_000))


def fixture(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text())
    return loaded


@dataclass
class Backend:
    captures: CaptureStore
    rooms: InMemoryRoomStore | PostgresRoomStore
    launcher: RecordingLauncher

    def client(self) -> httpx.AsyncClient:
        app = create_app(
            Settings(),
            InMemoryIdempotencyStore(),
            VERIFIER,
            InMemoryObjectStorage(),
            self.captures,
            self.rooms,
            self.launcher,
        )
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url="http://api.test")


@pytest.fixture(params=["memory", "postgres"])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    """Every room test runs against both stores."""
    if request.param == "memory":
        yield Backend(InMemoryCaptureStore(), InMemoryRoomStore(), RecordingLauncher())
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
            tables = {
                "idempotency": "private.idempotency_keys",
                "rooms": "public.rooms",
                "captures.sql": "public.captures",
            }
            for migration in sorted(MIGRATIONS.glob("*.sql")):
                table = next((t for part, t in tables.items() if part in migration.name), None)
                if table is None:
                    continue  # storage buckets: not part of a plain Postgres
                row = await (
                    await connection.execute("select to_regclass(%s)", (table,))
                ).fetchone()
                if row is None or row[0] is None:
                    await connection.execute(migration.read_bytes())
            await connection.execute("truncate public.captures cascade")
        yield Backend(PostgresCaptureStore(pool), PostgresRoomStore(pool), RecordingLauncher())
    finally:
        await pool.close()


def headers(user: str = USER_A) -> dict[str, str]:
    return {**bearer(token(sub=user)), "Idempotency-Key": f"room-key-{next(_keys):05d}"}


async def room_for(
    api: httpx.AsyncClient, user: str = USER_A, capture_id: str = CAPTURE_ID
) -> dict[str, Any]:
    registered = await api.post(
        "/v1/captures", json=capture(user, capture_id), headers=headers(user)
    )
    assert registered.status_code in (200, 201), registered.text
    # Registering made the room; asking for it returns that room.
    created = await api.post("/v1/rooms", json={"capture_id": capture_id}, headers=headers(user))
    assert created.status_code == 200, created.text
    room: dict[str, Any] = created.json()
    return room


async def test_registering_a_capture_makes_its_room_and_starts_it(backend: Backend) -> None:
    async with backend.client() as api:
        registered = await api.post("/v1/captures", json=capture(), headers=headers())
        assert registered.status_code == 201, registered.text
        # The job started on the upload's completion, before any room call.
        assert len(backend.launcher.rooms) == 1
        listed = (await api.get("/v1/rooms", headers=headers())).json()["rooms"]
        assert [r["id"] for r in listed] == backend.launcher.rooms

        room = await room_for(api)
        assert room["id"] == backend.launcher.rooms[0]
        assert room["capture_id"] == CAPTURE_ID
        assert room["stage"] == "uploaded"
        assert "failure" not in room and "confidence_level" not in room
        assert room["items"] == []
        assert room["status"] == "working"
        assert [(s["stage"], s["status"]) for s in room["stages"]] == [
            ("measure", "queued"),
            ("inventory", "queued"),
        ]

        read = await api.get(f"/v1/rooms/{room['id']}", headers=headers())
        assert read.status_code == 200
        assert read.json() == room


async def test_creating_a_room_again_returns_the_same_room_and_starts_it_again(
    backend: Backend,
) -> None:
    async with backend.client() as api:
        room = await room_for(api)
        again = await api.post("/v1/rooms", json={"capture_id": CAPTURE_ID}, headers=headers())
        assert again.status_code == 200
        assert again.json()["id"] == room["id"]
        # Registered, asked for, asked again: started each time, one room.
        assert backend.launcher.rooms == [room["id"]] * 3
        registered_again = await api.post("/v1/captures", json=capture(), headers=headers())
        assert registered_again.status_code == 200
        assert backend.launcher.rooms == [room["id"]] * 4

        listed = await api.get("/v1/rooms", headers=headers())
        assert [r["id"] for r in listed.json()["rooms"]] == [room["id"]]


async def test_a_room_needs_a_capture_the_caller_owns(backend: Backend) -> None:
    async with backend.client() as api:
        unknown = await api.post("/v1/rooms", json={"capture_id": CAPTURE_ID}, headers=headers())
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "capture_not_found"

        await room_for(api)
        other = await api.post(
            "/v1/rooms", json={"capture_id": CAPTURE_ID}, headers=headers(USER_B)
        )
        assert other.status_code == 404
        assert len(set(backend.launcher.rooms)) == 1


async def test_another_user_cannot_read_a_room(backend: Backend) -> None:
    async with backend.client() as api:
        room = await room_for(api)
        for path in ("", "/twin", "/designs"):
            read = await api.get(f"/v1/rooms/{room['id']}{path}", headers=headers(USER_B))
            assert read.status_code == 404, path
            assert read.json()["error"]["code"] == "room_not_found"
        listed = await api.get("/v1/rooms", headers=headers(USER_B))
        assert listed.json() == {"rooms": []}


async def test_rooms_list_newest_first(backend: Backend) -> None:
    async with backend.client() as api:
        first = await room_for(api)
        second = await room_for(api, capture_id=OTHER_CAPTURE)
        listed = await api.get("/v1/rooms", headers=headers())
        assert [r["id"] for r in listed.json()["rooms"]] == [second["id"], first["id"]]


async def test_job_status_follows_the_stages_and_the_twin_appears_when_ready(
    backend: Backend,
) -> None:
    async with backend.client() as api:
        room = await room_for(api)
        early = await api.get(f"/v1/rooms/{room['id']}/twin", headers=headers())
        assert early.status_code == 409
        assert early.json()["error"]["code"] == "room_not_ready"

        await backend.rooms.set_stage(room["id"], "measure", "running")
        reading = (await api.get(f"/v1/rooms/{room['id']}", headers=headers())).json()
        assert reading["stage"] == "reading"
        await backend.rooms.set_stage(room["id"], "measure", "done")
        working = (await api.get(f"/v1/rooms/{room['id']}", headers=headers())).json()
        assert working["stage"] == "reading"
        assert working["status"] == "working"
        assert [s["status"] for s in working["stages"]] == ["done", "queued"]

        twin = fixture("space-twin")
        await backend.rooms.set_space_twin(room["id"], twin)
        await backend.rooms.set_stage(room["id"], "inventory", "done")
        ready = (await api.get(f"/v1/rooms/{room['id']}", headers=headers())).json()
        assert ready["status"] == "ready"
        # Read, with no brief yet: designing waits on the app's request.
        assert ready["stage"] == "designing"
        assert ready["awaiting_brief"] is True
        assert ready["confidence_level"] == "ar_measured"
        read = await api.get(f"/v1/rooms/{room['id']}/twin", headers=headers())
        assert read.status_code == 200
        assert read.json() == twin


async def test_a_failed_stage_shows_as_failed_with_its_reason(backend: Backend) -> None:
    async with backend.client() as api:
        room = await room_for(api)
        await backend.rooms.set_stage(room["id"], "measure", "failed", "no_walls")
        failed = (await api.get(f"/v1/rooms/{room['id']}", headers=headers())).json()
        assert failed["stage"] == "failed"
        assert failed["failure"] == {"reason": "no_walls", "stage": "reading", "retryable": False}
        assert failed["status"] == "failed"
        assert failed["stages"][0]["detail"] == "no_walls"


async def test_a_reason_the_contract_does_not_know_is_reported_as_internal(
    backend: Backend,
) -> None:
    async with backend.client() as api:
        room = await room_for(api)
        await backend.rooms.set_stage(room["id"], "measure", "failed", "input_missing")
        failed = (await api.get(f"/v1/rooms/{room['id']}", headers=headers())).json()
        assert failed["failure"] == {"reason": "internal", "stage": "reading", "retryable": True}


async def test_a_photo_smaller_than_the_render_needs_is_refused(backend: Backend) -> None:
    async with backend.client() as api:
        small = capture()
        small["media"].append(
            {**small["media"][0], "kind": "photo", "width_px": 960, "height_px": 720}
        )
        refused = await api.post("/v1/captures", json=small, headers=headers())
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "photo_too_small"
        assert backend.launcher.rooms == []


async def test_designs_may_be_asked_for_before_the_room_is_read_and_start_once_it_is(
    backend: Backend,
) -> None:
    async with backend.client() as api:
        room = await room_for(api)
        body = {"id": REQUEST_ID, "brief": fixture("brief")}
        path = f"/v1/rooms/{room['id']}/designs"

        none_yet = await api.get(path, headers=headers())
        assert none_yet.status_code == 404
        assert none_yet.json()["error"]["code"] == "designs_not_requested"

        # Asked early: stored, not started; the room job starts it when reading ends.
        early = await api.post(path, json=body, headers=headers())
        assert early.status_code == 201, early.text
        request = early.json()
        assert request["id"] == REQUEST_ID
        assert request["status"] == "working"
        assert [s["stage"] for s in request["stages"]] == ["spec", "placement"]
        assert request["designs"] is None
        assert backend.launcher.designs == []
        status = (await api.get(f"/v1/rooms/{room['id']}", headers=headers())).json()
        assert status["stage"] == "uploaded"
        assert status["design_request_id"] == REQUEST_ID

        for stage in ("measure", "inventory"):
            await backend.rooms.set_stage(room["id"], stage, "done")
        await backend.rooms.set_space_twin(room["id"], fixture("space-twin"))
        again = await api.post(path, json=body, headers=headers())
        assert again.status_code == 200
        assert again.json()["id"] == REQUEST_ID
        assert backend.launcher.designs == [(room["id"], REQUEST_ID)]
        designing = (await api.get(f"/v1/rooms/{room['id']}", headers=headers())).json()
        assert designing["stage"] == "designing"
        assert designing["awaiting_brief"] is False

        designs = [fixture("design")] * 3
        for stage in ("spec", "placement"):
            await backend.rooms.set_stage(room["id"], stage, "done", request_id=REQUEST_ID)
        await backend.rooms.set_designs(REQUEST_ID, designs)
        ready = await api.get(path, headers=headers())
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"
        assert ready.json()["designs"] == designs
        room_now = (await api.get(f"/v1/rooms/{room['id']}", headers=headers())).json()
        assert room_now["stage"] == "ready"
        # The design fixture was placed on a taped room: each item's fit was checked.
        assert len(room_now["items"]) == 3 * len(designs[0]["items"])
        assert all(item["fit_checked"] for item in room_now["items"])


async def test_on_an_estimated_room_no_item_carries_a_fit_check(backend: Backend) -> None:
    async with backend.client() as api:
        room = await room_for(api)
        twin = {**fixture("space-twin"), "confidence": {"level": "estimated", "basis": "photos"}}
        for stage in ("measure", "inventory"):
            await backend.rooms.set_stage(room["id"], stage, "done")
        await backend.rooms.set_space_twin(room["id"], twin)
        path = f"/v1/rooms/{room['id']}/designs"
        await api.post(path, json={"id": REQUEST_ID, "brief": fixture("brief")}, headers=headers())
        design = {**fixture("design"), "measurement_level": "estimated"}
        for stage in ("spec", "placement"):
            await backend.rooms.set_stage(room["id"], stage, "done", request_id=REQUEST_ID)
        await backend.rooms.set_designs(REQUEST_ID, [design])
        status = (await api.get(f"/v1/rooms/{room['id']}", headers=headers())).json()
        assert status["stage"] == "ready"
        assert status["confidence_level"] == "estimated"
        assert status["items"] and not any(i["fit_checked"] for i in status["items"])


async def test_a_design_request_id_cannot_be_reused_for_another_room(backend: Backend) -> None:
    async with backend.client() as api:
        first = await room_for(api)
        second = await room_for(api, capture_id=OTHER_CAPTURE)
        for room in (first, second):
            await backend.rooms.set_space_twin(room["id"], fixture("space-twin"))
        body = {"id": REQUEST_ID, "brief": fixture("brief")}
        assert (
            await api.post(f"/v1/rooms/{first['id']}/designs", json=body, headers=headers())
        ).status_code == 201
        taken = await api.post(f"/v1/rooms/{second['id']}/designs", json=body, headers=headers())
        assert taken.status_code == 409
        assert taken.json()["error"]["code"] == "design_request_id_taken"


async def test_a_brief_that_breaks_the_contract_is_refused(backend: Backend) -> None:
    async with backend.client() as api:
        room = await room_for(api)
        await backend.rooms.set_space_twin(room["id"], fixture("space-twin"))
        brief = {**fixture("brief"), "budget": "a lot"}
        refused = await api.post(
            f"/v1/rooms/{room['id']}/designs",
            json={"id": REQUEST_ID, "brief": brief},
            headers=headers(),
        )
        assert refused.status_code == 422
