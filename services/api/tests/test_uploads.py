import os
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from sajao_api.idempotency import InMemoryIdempotencyStore
from sajao_api.main import create_app
from sajao_api.settings import Settings
from sajao_api.storage import InMemoryObjectStorage, ObjectStorage, S3ObjectStorage
from sajao_api.v1.uploads import MIB, PART_SIZE_BYTES

from .test_auth import VERIFIER, bearer, token

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
_keys = iter(range(1, 10_000))


def client(storage: ObjectStorage | None) -> httpx.AsyncClient:
    app = create_app(Settings(), InMemoryIdempotencyStore(), VERIFIER, storage)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://api.test")


def headers(user: str = USER_A) -> dict[str, str]:
    return {**bearer(token(sub=user)), "Idempotency-Key": f"upload-key-{next(_keys):05d}"}


def photo(size: int = 400_000) -> dict[str, Any]:
    return {"kind": "photo", "content_type": "image/jpeg", "size_bytes": size}


def video(size: int) -> dict[str, Any]:
    return {"kind": "video", "content_type": "video/mp4", "size_bytes": size}


async def test_a_photo_uploads_in_one_part_through_a_signed_url() -> None:
    storage = InMemoryObjectStorage()
    async with client(storage) as api:
        created = await api.post("/v1/uploads", json=photo(), headers=headers())
        plan = created.json()
        assert created.status_code == 201
        assert plan["key"].startswith(f"{USER_A}/") and plan["key"].endswith(".jpg")
        assert (plan["part_count"], plan["uploaded"]) == (1, [])
        assert [part["part_number"] for part in plan["parts"]] == [1]
        assert "signed=1" in plan["parts"][0]["url"]
        assert plan["url_expires_in_seconds"] == 900

        etag = storage.put_part(plan["key"], plan["upload_id"], 1, b"x" * 400_000)
        done = await api.post(
            "/v1/uploads/complete",
            json={
                "key": plan["key"],
                "upload_id": plan["upload_id"],
                "parts": [{"part_number": 1, "size_bytes": 400_000, "etag": etag}],
            },
            headers=headers(),
        )
    assert done.status_code == 200
    assert done.json() == {"key": plan["key"], "size_bytes": 400_000}
    assert storage.objects[plan["key"]] == b"x" * 400_000


async def test_a_video_is_split_into_five_megabyte_parts() -> None:
    async with client(InMemoryObjectStorage()) as api:
        plan = (await api.post("/v1/uploads", json=video(12 * MIB), headers=headers())).json()
    assert plan["part_size_bytes"] == PART_SIZE_BYTES == 5 * MIB
    assert [part["part_number"] for part in plan["parts"]] == [1, 2, 3]


async def test_after_a_dropped_connection_only_the_missing_parts_are_sent_again() -> None:
    storage = InMemoryObjectStorage()
    async with client(storage) as api:
        plan = (await api.post("/v1/uploads", json=video(12 * MIB), headers=headers())).json()
        ref = {"key": plan["key"], "upload_id": plan["upload_id"]}
        storage.put_part(plan["key"], plan["upload_id"], 1, b"a" * PART_SIZE_BYTES)
        # The connection drops here. Later the phone asks where it stood.
        resumed = await api.post(
            "/v1/uploads/resume", json={**ref, "size_bytes": 12 * MIB}, headers=headers()
        )
        state = resumed.json()
        assert resumed.status_code == 200
        assert [part["part_number"] for part in state["uploaded"]] == [1]
        assert state["uploaded"][0]["size_bytes"] == PART_SIZE_BYTES
        assert [part["part_number"] for part in state["parts"]] == [2, 3]

        storage.put_part(plan["key"], plan["upload_id"], 2, b"b" * PART_SIZE_BYTES)
        storage.put_part(plan["key"], plan["upload_id"], 3, b"c" * (2 * MIB))
        finished = (
            await api.post(
                "/v1/uploads/resume", json={**ref, "size_bytes": 12 * MIB}, headers=headers()
            )
        ).json()
        assert finished["parts"] == []
        done = await api.post(
            "/v1/uploads/complete", json={**ref, "parts": finished["uploaded"]}, headers=headers()
        )
    assert done.json()["size_bytes"] == 12 * MIB
    assert len(storage.objects[plan["key"]]) == 12 * MIB


async def test_uploads_need_a_signed_in_or_guest_caller() -> None:
    async with client(InMemoryObjectStorage()) as api:
        response = await api.post(
            "/v1/uploads", json=photo(), headers={"Idempotency-Key": "anonymous-upload-1"}
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"kind": "photo", "content_type": "application/pdf", "size_bytes": 10}, 415, None),
        ({"kind": "photo", "content_type": "video/mp4", "size_bytes": 10}, 415, None),
        ({"kind": "photo", "content_type": "image/jpeg", "size_bytes": 21 * MIB}, 413, None),
        ({"kind": "video", "content_type": "video/mp4", "size_bytes": 513 * MIB}, 413, None),
        ({"kind": "data", "content_type": "application/json", "size_bytes": 101 * MIB}, 413, None),
        ({"kind": "data", "content_type": "image/jpeg", "size_bytes": 10}, 415, None),
        ({"kind": "photo", "content_type": "image/jpeg", "size_bytes": 0}, 422, None),
        ({"kind": "document", "content_type": "image/jpeg", "size_bytes": 10}, 422, None),
    ],
    ids=[
        "pdf",
        "video-as-photo",
        "photo-too-large",
        "video-too-large",
        "data-too-large",
        "image-as-data",
        "empty",
        "unknown-kind",
    ],
)
async def test_only_room_media_within_the_size_limits_can_start_an_upload(
    body: dict[str, Any], status: int, code: None
) -> None:
    async with client(InMemoryObjectStorage()) as api:
        response = await api.post("/v1/uploads", json=body, headers=headers())
    assert response.status_code == status


async def test_the_size_limit_is_enforced_on_what_really_arrived() -> None:
    storage = InMemoryObjectStorage()
    async with client(storage) as api:
        plan = (await api.post("/v1/uploads", json=photo(1000), headers=headers())).json()
        # The phone declared 1,000 bytes and then sent far more.
        etag = storage.put_part(plan["key"], plan["upload_id"], 1, b"x" * (21 * MIB))
        done = await api.post(
            "/v1/uploads/complete",
            json={
                "key": plan["key"],
                "upload_id": plan["upload_id"],
                "parts": [{"part_number": 1, "size_bytes": 21 * MIB, "etag": etag}],
            },
            headers=headers(),
        )
    assert done.status_code == 413
    assert plan["key"] not in storage.objects


async def test_a_user_cannot_touch_another_users_upload() -> None:
    storage = InMemoryObjectStorage()
    async with client(storage) as api:
        plan = (await api.post("/v1/uploads", json=photo(), headers=headers(USER_A))).json()
        ref = {"key": plan["key"], "upload_id": plan["upload_id"]}
        etag = storage.put_part(plan["key"], plan["upload_id"], 1, b"x")
        resume = await api.post(
            "/v1/uploads/resume", json={**ref, "size_bytes": 1}, headers=headers(USER_B)
        )
        complete = await api.post(
            "/v1/uploads/complete",
            json={**ref, "parts": [{"part_number": 1, "size_bytes": 1, "etag": etag}]},
            headers=headers(USER_B),
        )
    assert resume.status_code == complete.status_code == 404
    assert resume.json()["error"]["code"] == "upload_not_found"
    assert storage.objects == {}


@pytest.mark.parametrize(
    "key",
    [
        "../other/file.jpg",
        f"{USER_A}/../../{USER_B}/a.jpg",
        f"{USER_A}/not-a-generated-name.jpg",
        f"{USER_A}/{'a' * 32}.exe",
        "",
    ],
)
async def test_keys_that_were_not_issued_by_the_api_are_rejected(key: str) -> None:
    async with client(InMemoryObjectStorage()) as api:
        response = await api.post(
            "/v1/uploads/resume",
            json={"key": key, "upload_id": "upload-1", "size_bytes": 1},
            headers=headers(),
        )
    assert response.status_code == 404


async def test_an_unknown_or_finished_upload_is_not_found() -> None:
    async with client(InMemoryObjectStorage()) as api:
        response = await api.post(
            "/v1/uploads/resume",
            json={"key": f"{USER_A}/{'a' * 32}.jpg", "upload_id": "gone", "size_bytes": 1},
            headers=headers(),
        )
    assert response.status_code == 404


async def test_uploads_answer_unavailable_when_storage_is_not_configured() -> None:
    async with client(None) as api:
        response = await api.post("/v1/uploads", json=photo(), headers=headers())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "uploads_unavailable"


def test_storage_settings_are_set_together(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAJAO_STORAGE_ENDPOINT", "https://storage.test")
    with pytest.raises(ValueError, match="must be set together"):
        Settings()
    monkeypatch.setenv("SAJAO_STORAGE_REGION", "auto")
    monkeypatch.setenv("SAJAO_STORAGE_BUCKET", "captures")
    monkeypatch.setenv("SAJAO_STORAGE_ACCESS_KEY_ID", "key-id")
    monkeypatch.setenv("SAJAO_STORAGE_SECRET_ACCESS_KEY", "hunter2")
    settings = Settings()
    assert settings.storage_secret_access_key == SecretStr("hunter2")
    assert "hunter2" not in repr(settings)


S3_URL = os.environ.get("SAJAO_TEST_S3_URL") or None


@pytest.mark.skipif(S3_URL is None, reason="SAJAO_TEST_S3_URL is not set")
async def test_a_real_multipart_upload_resumes_on_the_local_stack() -> None:
    assert S3_URL is not None
    storage = S3ObjectStorage(
        endpoint=S3_URL,
        region=os.environ["SAJAO_TEST_S3_REGION"],
        bucket="captures",
        access_key_id=os.environ["SAJAO_TEST_S3_ACCESS_KEY_ID"],
        secret_access_key=os.environ["SAJAO_TEST_S3_SECRET_ACCESS_KEY"],
    )
    size = PART_SIZE_BYTES + 1000
    async with client(storage) as api, httpx.AsyncClient(timeout=60) as phone:
        plan = (await api.post("/v1/uploads", json=video(size), headers=headers())).json()
        ref = {"key": plan["key"], "upload_id": plan["upload_id"]}
        first = await phone.put(plan["parts"][0]["url"], content=b"a" * PART_SIZE_BYTES)
        assert first.status_code == 200

        # Connection lost. Resume: part 1 is there, part 2 gets a fresh signed URL.
        state = (
            await api.post(
                "/v1/uploads/resume", json={**ref, "size_bytes": size}, headers=headers()
            )
        ).json()
        assert [part["part_number"] for part in state["uploaded"]] == [1]
        assert [part["part_number"] for part in state["parts"]] == [2]
        second = await phone.put(state["parts"][0]["url"], content=b"b" * 1000)
        assert second.status_code == 200

        parts = (
            await api.post(
                "/v1/uploads/resume", json={**ref, "size_bytes": size}, headers=headers()
            )
        ).json()["uploaded"]
        done = await api.post(
            "/v1/uploads/complete", json={**ref, "parts": parts}, headers=headers()
        )
        assert done.json() == {"key": plan["key"], "size_bytes": size}

        # Reading needs a signed URL too; the bare object URL is refused.
        signed = storage.sign_download(plan["key"], 60)
        assert (await phone.get(signed, headers={"Range": "bytes=0-0"})).status_code == 206
        assert (await phone.get(signed.split("?")[0])).status_code in (400, 401, 403)

        # A finished upload cannot be resumed.
        gone = await api.post(
            "/v1/uploads/resume", json={**ref, "size_bytes": size}, headers=headers()
        )
        assert gone.status_code == 404
    storage.delete(plan["key"])


@pytest.mark.parametrize(
    ("content_type", "extension"),
    [
        ("application/x-ndjson", "jsonl"),
        ("application/json", "json"),
        ("application/octet-stream", "bin"),
    ],
)
async def test_capture_package_data_files_upload_and_resume(
    content_type: str, extension: str
) -> None:
    storage = InMemoryObjectStorage()
    body = {"kind": "data", "content_type": content_type, "size_bytes": 2000}
    async with client(storage) as api:
        created = await api.post("/v1/uploads", json=body, headers=headers())
        plan = created.json()
        assert created.status_code == 201
        assert plan["key"].startswith(f"{USER_A}/") and plan["key"].endswith(f".{extension}")
        ref = {"key": plan["key"], "upload_id": plan["upload_id"]}
        resumed = await api.post(
            "/v1/uploads/resume", json={**ref, "size_bytes": 2000}, headers=headers()
        )
        assert resumed.status_code == 200
        etag = storage.put_part(plan["key"], plan["upload_id"], 1, b"x" * 2000)
        done = await api.post(
            "/v1/uploads/complete",
            json={**ref, "parts": [{"part_number": 1, "size_bytes": 2000, "etag": etag}]},
            headers=headers(),
        )
        assert done.json() == {"key": plan["key"], "size_bytes": 2000}


async def test_the_stores_own_limit_refuses_a_larger_file_before_any_part_is_sent() -> None:
    settings = Settings(storage_max_object_bytes=50 * MIB)
    app = create_app(settings, InMemoryIdempotencyStore(), VERIFIER, InMemoryObjectStorage())
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as api:
        too_large = await api.post("/v1/uploads", json=video(51 * MIB), headers=headers())
        assert too_large.status_code == 413
        assert too_large.json()["error"]["code"] == "file_too_large"
        fits = await api.post("/v1/uploads", json=video(49 * MIB), headers=headers())
        assert fits.status_code == 201


async def test_user_session_storage_signs_with_the_callers_own_token() -> None:
    settings = Settings(
        storage_endpoint="https://project.storage.example/storage/v1/s3",
        storage_region="ap-south-1",
        storage_bucket="captures",
        storage_access_key_id=SecretStr("project-ref"),
        storage_secret_access_key=SecretStr("public-anon-key"),
        storage_user_sessions=True,
    )
    app = create_app(settings, InMemoryIdempotencyStore(), VERIFIER)
    assert app.state.storage is None
    access_token = token(sub=USER_A)
    scoped = app.state.storage_for_session(access_token)
    assert isinstance(scoped, S3ObjectStorage)
    # Signing is local: the caller's token travels in the URL as the session token.
    url = scoped.sign_part(f"{USER_A}/{'0' * 32}.jpg", "upload-1", 1, 900)
    assert "X-Amz-Security-Token=" in url and access_token[:20] in url
    assert "public-anon-key" not in url
