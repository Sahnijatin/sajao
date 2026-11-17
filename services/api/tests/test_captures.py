import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from psycopg_pool import AsyncConnectionPool

from sajao_api.captures import CaptureStore, InMemoryCaptureStore, PostgresCaptureStore
from sajao_api.idempotency import InMemoryIdempotencyStore
from sajao_api.main import create_app
from sajao_api.settings import Settings
from sajao_api.storage import InMemoryObjectStorage

from .test_auth import VERIFIER, bearer, token

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
CAPTURE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"
TEST_DATABASE_URL = os.environ.get("SAJAO_TEST_DATABASE_URL") or None
_keys = iter(range(1, 10_000))


@pytest.fixture(params=["memory", "postgres"])
async def captures(request: pytest.FixtureRequest) -> AsyncIterator[CaptureStore]:
    """Every capture test runs against both stores."""
    if request.param == "memory":
        yield InMemoryCaptureStore()
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
            for migration in sorted(MIGRATIONS.glob("*.sql")):
                table = (
                    "private.idempotency_keys"
                    if "idempotency" in migration.name
                    else "public.captures"
                )
                row = await (
                    await connection.execute("select to_regclass(%s)", (table,))
                ).fetchone()
                if row is None or row[0] is None:
                    await connection.execute(migration.read_bytes())
            await connection.execute("truncate public.captures cascade")
        yield PostgresCaptureStore(pool)
    finally:
        await pool.close()


def client(store: CaptureStore) -> httpx.AsyncClient:
    app = create_app(
        Settings(), InMemoryIdempotencyStore(), VERIFIER, InMemoryObjectStorage(), store
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://api.test")


def headers(user: str = USER_A) -> dict[str, str]:
    return {**bearer(token(sub=user)), "Idempotency-Key": f"capture-key-{next(_keys):05d}"}


def key(user: str, number: int, extension: str) -> str:
    return f"{user}/{number:032x}.{extension}"


def capture(user: str = USER_A, capture_id: str = CAPTURE_ID) -> dict[str, Any]:
    pose = {
        "position": {"x_m": 0.1, "y_m": 1.4, "z_m": -0.2},
        "rotation": [0.0, 0.0, 0.0, 1.0],
    }
    intrinsics = {
        "fx": 1400.0,
        "fy": 1400.0,
        "cx": 960.0,
        "cy": 540.0,
        "width_px": 1920,
        "height_px": 1080,
    }
    return {
        "id": capture_id,
        "device": {"platform": "android", "tier": "low", "has_ar": True},
        "media": [
            {
                "id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                "kind": "video",
                "origin": "camera",
                "storage_key": key(user, 9, "mp4"),
                "width_px": 1920,
                "height_px": 1080,
                "duration_s": 42.0,
                "has_ar_pose": True,
            }
        ],
        "package": {
            "ar": {"tracking": "arcore", "lidar": False, "depth": True},
            "video": key(user, 9, "mp4"),
            "keyframes": [
                {
                    "id": "k1",
                    "image": key(user, 1, "jpg"),
                    "captured_at_ms": 1200,
                    "sharpness": 31.5,
                    "pose": pose,
                    "intrinsics": intrinsics,
                },
                # Taken while tracking was lost: kept without a pose.
                {
                    "id": "k2",
                    "image": key(user, 2, "jpg"),
                    "captured_at_ms": 2700,
                    "sharpness": 20.0,
                },
            ],
            "detections": [],
            "sensor_log": key(user, 3, "jsonl"),
            "planes": key(user, 4, "json"),
            "depth": key(user, 5, "bin"),
        },
    }


async def test_a_capture_registers_and_reads_back_as_a_valid_capture(
    captures: CaptureStore,
) -> None:
    async with client(captures) as api:
        created = await api.post("/v1/captures", json=capture(), headers=headers())
        assert created.status_code == 201, created.text
        stored = created.json()
        assert stored["id"] == CAPTURE_ID
        assert stored["user_id"] == USER_A
        assert stored["schema_version"] == "1.0"
        assert stored["package"]["keyframes"][0]["pose"]["rotation"] == [0.0, 0.0, 0.0, 1.0]
        assert "pose" not in stored["package"]["keyframes"][1]
        assert stored["package"]["sensor_log"].endswith(".jsonl")

        read = await api.get(f"/v1/captures/{CAPTURE_ID}", headers=bearer(token(sub=USER_A)))
        assert read.status_code == 200
        assert read.json() == stored


async def test_registering_the_same_capture_again_returns_the_first_one(
    captures: CaptureStore,
) -> None:
    async with client(captures) as api:
        first = await api.post("/v1/captures", json=capture(), headers=headers())
        # A retry with a new idempotency key, as after an app restart.
        again = await api.post("/v1/captures", json=capture(), headers=headers())
        assert (first.status_code, again.status_code) == (201, 200)
        assert again.json() == first.json()


async def test_a_capture_cannot_point_at_another_users_files(captures: CaptureStore) -> None:
    async with client(captures) as api:
        body = capture()
        body["package"]["keyframes"][0]["image"] = key(USER_B, 1, "jpg")
        refused = await api.post("/v1/captures", json=body, headers=headers())
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "unknown_storage_key"

        body = capture()
        body["media"][0]["storage_key"] = "https://example.com/video.mp4"
        refused = await api.post("/v1/captures", json=body, headers=headers())
        assert refused.status_code == 422


async def test_an_invalid_package_is_refused(captures: CaptureStore) -> None:
    async with client(captures) as api:
        body = capture()
        body["package"]["keyframes"] = []
        assert (await api.post("/v1/captures", json=body, headers=headers())).status_code == 422
        body = capture()
        body["package"]["price_inr"] = 100
        assert (await api.post("/v1/captures", json=body, headers=headers())).status_code == 422


async def test_captures_are_private_to_their_owner(captures: CaptureStore) -> None:
    async with client(captures) as api:
        await api.post("/v1/captures", json=capture(), headers=headers())
        other = await api.get(f"/v1/captures/{CAPTURE_ID}", headers=bearer(token(sub=USER_B)))
        assert other.status_code == 404
        # Someone else cannot take over the id either.
        taken = await api.post("/v1/captures", json=capture(USER_B), headers=headers(USER_B))
        assert taken.status_code == 409
        mine = await api.get(f"/v1/captures/{CAPTURE_ID}", headers=bearer(token(sub=USER_A)))
        assert mine.json()["user_id"] == USER_A


async def test_registering_needs_a_signed_in_caller(captures: CaptureStore) -> None:
    async with client(captures) as api:
        refused = await api.post(
            "/v1/captures", json=capture(), headers={"Idempotency-Key": "capture-key-anon1"}
        )
        assert refused.status_code == 401
