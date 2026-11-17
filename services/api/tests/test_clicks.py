"""Buy taps: each one is logged with its click id, then the phone opens the retailer."""

import copy
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from psycopg_pool import AsyncConnectionPool

from sajao_api.captures import CaptureStore, InMemoryCaptureStore, PostgresCaptureStore
from sajao_api.clicks import ClickStore, InMemoryClickStore, PostgresClickStore
from sajao_api.idempotency import InMemoryIdempotencyStore
from sajao_api.main import create_app
from sajao_api.pipeline import RecordingLauncher
from sajao_api.rooms import InMemoryRoomStore, PostgresRoomStore
from sajao_api.settings import Settings
from sajao_api.storage import InMemoryObjectStorage

from .test_auth import VERIFIER
from .test_captures import USER_A, USER_B
from .test_rooms import MIGRATIONS, REQUEST_ID, TEST_DATABASE_URL, fixture, headers, room_for

CLICK_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


@dataclass
class Backend:
    captures: CaptureStore
    rooms: InMemoryRoomStore | PostgresRoomStore
    clicks: ClickStore

    def client(self) -> httpx.AsyncClient:
        app = create_app(
            Settings(),
            InMemoryIdempotencyStore(),
            VERIFIER,
            InMemoryObjectStorage(),
            self.captures,
            self.rooms,
            RecordingLauncher(),
            self.clicks,
        )
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url="http://api.test")


@pytest.fixture(params=["memory", "postgres"])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    """Every click test runs against both stores."""
    if request.param == "memory":
        yield Backend(InMemoryCaptureStore(), InMemoryRoomStore(), InMemoryClickStore())
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
                "captures.sql": "public.captures",
                "rooms": "public.rooms",
                "clicks": "public.clicks",
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
        yield Backend(PostgresCaptureStore(pool), PostgresRoomStore(pool), PostgresClickStore(pool))
    finally:
        await pool.close()


def design() -> dict[str, Any]:
    return fixture("design")


async def designs_ready(backend: Backend, api: httpx.AsyncClient, designs: list[Any]) -> str:
    room = await room_for(api)
    await backend.rooms.set_space_twin(room["id"], fixture("space-twin"))
    asked = await api.post(
        f"/v1/rooms/{room['id']}/designs",
        json={"id": REQUEST_ID, "brief": fixture("brief")},
        headers=headers(),
    )
    assert asked.status_code == 201, asked.text
    await backend.rooms.set_designs(REQUEST_ID, designs)
    return REQUEST_ID


def tap(d: dict[str, Any], item: int = 0, **extra: Any) -> dict[str, Any]:
    return {
        "id": CLICK_ID,
        "design_request_id": REQUEST_ID,
        "design_id": d["id"],
        "product_id": d["items"][item]["product"]["id"],
        "position": item,
        **extra,
    }


async def test_a_buy_tap_is_logged_and_returns_the_retailer_link_with_its_click_id(
    backend: Backend,
) -> None:
    d = design()
    async with backend.client() as api:
        await designs_ready(backend, api, [d])
        made = await api.post("/v1/clicks", json=tap(d), headers=headers())

    assert made.status_code == 201, made.text
    body = made.json()
    route = next(r for r in d["items"][0]["product"]["routes"] if r["kind"] == "buy")
    assert body["id"] == CLICK_ID
    assert body["retailer"] == route["retailer"]
    assert body["price"] == route["price"]
    url = urlsplit(body["url"])
    assert body["url"].startswith(route["url"].split("?")[0])
    assert url.scheme == "https"
    assert route["retailer"] == "flipkart"
    assert parse_qs(url.query)["affExtParam1"] == [CLICK_ID]  # the network reports it back

    logged = await backend.clicks.get(CLICK_ID)
    assert logged is not None
    assert (logged.user_id, logged.design_id, logged.product_id, logged.position) == (
        USER_A,
        d["id"],
        d["items"][0]["product"]["id"],
        0,
    )


async def test_tapping_again_with_the_same_click_id_logs_it_once(backend: Backend) -> None:
    d = design()
    async with backend.client() as api:
        await designs_ready(backend, api, [d])
        first = await api.post("/v1/clicks", json=tap(d), headers=headers())
        again = await api.post("/v1/clicks", json=tap(d), headers=headers())

    assert first.status_code == 201 and again.status_code == 200
    assert again.json() == first.json()
    assert len(await backend.clicks.for_user(USER_A)) == 1


async def test_a_rent_tap_opens_the_rent_route(backend: Backend) -> None:
    d = design()
    async with backend.client() as api:
        await designs_ready(backend, api, [d])
        made = await api.post("/v1/clicks", json=tap(d, kind="rent"), headers=headers())

    rent = next(r for r in d["items"][0]["product"]["routes"] if r["kind"] == "rent")
    assert made.status_code == 201
    assert made.json()["retailer"] == rent["retailer"]
    assert made.json()["url"] == rent["url"]  # no known click parameter for this retailer


async def test_only_products_in_the_callers_own_design_can_be_tapped(backend: Backend) -> None:
    d = design()
    async with backend.client() as api:
        await designs_ready(backend, api, [d])
        other_user = await api.post("/v1/clicks", json=tap(d), headers=headers(USER_B))
        no_route = await api.post("/v1/clicks", json=tap(d, item=1, kind="rent"), headers=headers())
        not_in_design = await api.post(
            "/v1/clicks",
            json=tap(d, product_id="00000000-0000-4000-8000-0000000000ff"),
            headers=headers(),
        )

    assert other_user.status_code == 404
    assert other_user.json()["error"]["code"] == "design_not_found"
    assert no_route.status_code == 404
    assert no_route.json()["error"]["code"] == "route_not_found"
    assert not_in_design.status_code == 404
    assert not_in_design.json()["error"]["code"] == "product_not_in_design"
    assert await backend.clicks.for_user(USER_A) == []
    assert await backend.clicks.for_user(USER_B) == []


async def test_an_out_of_stock_product_is_not_opened(backend: Backend) -> None:
    d = design()
    gone = copy.deepcopy(d)
    gone["items"][0]["product"]["in_stock"] = False
    async with backend.client() as api:
        await designs_ready(backend, api, [gone])
        made = await api.post("/v1/clicks", json=tap(gone), headers=headers())

    assert made.status_code == 409
    assert made.json()["error"]["code"] == "product_unavailable"


async def test_a_click_id_used_for_another_tap_is_refused(backend: Backend) -> None:
    d = design()
    async with backend.client() as api:
        await designs_ready(backend, api, [d])
        await api.post("/v1/clicks", json=tap(d), headers=headers())
        moved = await api.post("/v1/clicks", json=tap(d, position=3), headers=headers())

    assert moved.status_code == 409
    assert moved.json()["error"]["code"] == "click_id_taken"
