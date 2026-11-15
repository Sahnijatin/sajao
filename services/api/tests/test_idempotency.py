import asyncio

from sajao_api.idempotency import IdempotencyStore, Outcome, StoredResponse
from sajao_api.settings import Settings

from .conftest import Calls, ClientFactory

KEY = {"Idempotency-Key": "key-0001"}


async def test_reads_need_no_key(make_client: ClientFactory, store: IdempotencyStore) -> None:
    async with make_client(store=store) as client:
        assert (await client.get("/v1/health")).status_code == 200


async def test_a_write_without_a_key_is_rejected_and_never_runs(
    make_client: ClientFactory, store: IdempotencyStore, calls: Calls
) -> None:
    async with make_client(store=store) as client:
        missing = await client.post("/v1/test/things", json={"name": "sofa"})
        short = await client.post(
            "/v1/test/things", json={"name": "sofa"}, headers={"Idempotency-Key": "abc"}
        )
    assert missing.status_code == short.status_code == 400
    assert missing.json()["error"]["code"] == "idempotency_key_required"
    assert calls.created == 0


async def test_a_retry_runs_once_and_replays_the_first_response(
    make_client: ClientFactory, store: IdempotencyStore, calls: Calls
) -> None:
    async with make_client(store=store) as client:
        first = await client.post("/v1/test/things", json={"name": "sofa"}, headers=KEY)
        retry = await client.post("/v1/test/things", json={"name": "sofa"}, headers=KEY)
    assert calls.created == 1
    assert first.status_code == retry.status_code == 201
    assert first.json() == retry.json() == {"number": 1, "name": "sofa"}
    assert "idempotency-replayed" not in first.headers
    assert retry.headers["idempotency-replayed"] == "true"
    assert retry.headers["content-type"] == "application/json"
    # The replay is a new request, so it gets its own request id.
    assert retry.headers["x-request-id"] != first.headers["x-request-id"]


async def test_different_keys_run_separately(
    make_client: ClientFactory, store: IdempotencyStore, calls: Calls
) -> None:
    async with make_client(store=store) as client:
        await client.post("/v1/test/things", json={"name": "sofa"}, headers=KEY)
        other = await client.post(
            "/v1/test/things", json={"name": "sofa"}, headers={"Idempotency-Key": "key-0002"}
        )
    assert calls.created == 2
    assert other.json()["number"] == 2


async def test_reusing_a_key_for_a_different_request_is_rejected(
    make_client: ClientFactory, store: IdempotencyStore, calls: Calls
) -> None:
    async with make_client(store=store) as client:
        await client.post("/v1/test/things", json={"name": "sofa"}, headers=KEY)
        different_body = await client.post("/v1/test/things", json={"name": "lamp"}, headers=KEY)
        different_path = await client.post("/v1/test/flaky", headers=KEY)
    assert different_body.status_code == different_path.status_code == 422
    assert different_body.json()["error"]["code"] == "idempotency_key_reused"
    assert calls.created == 1
    assert calls.failed == 0


async def test_a_concurrent_duplicate_does_not_run_twice(
    make_client: ClientFactory, store: IdempotencyStore, calls: Calls
) -> None:
    async with make_client(store=store) as client:
        first = asyncio.create_task(client.post("/v1/test/slow", headers=KEY))
        await calls.slow_started.wait()
        duplicate = await client.post("/v1/test/slow", headers=KEY)
        calls.release_slow.set()
        finished = await first
        retry = await client.post("/v1/test/slow", headers=KEY)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "request_in_progress"
    assert finished.status_code == 201
    assert retry.json() == finished.json()
    assert calls.created == 1


async def test_a_server_error_is_not_stored_so_a_retry_can_succeed(
    make_client: ClientFactory, store: IdempotencyStore, calls: Calls
) -> None:
    async with make_client(store=store) as client:
        failed = await client.post("/v1/test/flaky", headers=KEY)
        retry = await client.post("/v1/test/flaky", headers=KEY)
        replay = await client.post("/v1/test/flaky", headers=KEY)
    assert failed.status_code == 500
    assert retry.status_code == 200
    assert replay.headers["idempotency-replayed"] == "true"
    assert calls.failed == 2


async def test_a_client_error_is_a_final_answer_and_is_replayed(
    make_client: ClientFactory, store: IdempotencyStore, calls: Calls
) -> None:
    async with make_client(store=store) as client:
        first = await client.post("/v1/test/things", json={"name": 5}, headers=KEY)
        retry = await client.post("/v1/test/things", json={"name": 5}, headers=KEY)
    assert first.status_code == retry.status_code == 422
    assert retry.headers["idempotency-replayed"] == "true"
    assert calls.created == 0


async def test_oversized_bodies_are_rejected(
    make_client: ClientFactory, store: IdempotencyStore, calls: Calls
) -> None:
    async with make_client(store=store) as client:
        response = await client.post(
            "/v1/test/things", content=b"x" * (1024 * 1024 + 1), headers=KEY
        )
    assert response.status_code == 413
    assert calls.created == 0


async def test_keys_are_separate_per_owner(store: IdempotencyStore) -> None:
    done = StoredResponse(201, [("content-type", "application/json")], b'{"n":1}')
    assert (await store.reserve("user-a", "key-0001", "f", 60)).outcome is Outcome.STARTED
    await store.complete("user-a", "key-0001", done, 3600)

    assert (await store.reserve("user-b", "key-0001", "f", 60)).outcome is Outcome.STARTED
    replay = await store.reserve("user-a", "key-0001", "f", 60)
    assert replay.outcome is Outcome.COMPLETED
    assert replay.response == done


async def test_an_abandoned_request_can_be_taken_over_after_it_expires(
    make_client: ClientFactory, store: IdempotencyStore, calls: Calls
) -> None:
    # A request that crashed the process leaves an unfinished reservation behind.
    assert (await store.reserve("anonymous", "key-0001", "stale", 1)).outcome is Outcome.STARTED
    await asyncio.sleep(1.1)
    settings = Settings(idempotency_in_progress_seconds=1)
    async with make_client(settings, store) as client:
        response = await client.post("/v1/test/things", json={"name": "sofa"}, headers=KEY)
    assert response.status_code == 201
    assert calls.created == 1


async def test_stored_responses_expire(store: IdempotencyStore) -> None:
    done = StoredResponse(200, [], b"{}")
    await store.reserve("anonymous", "key-0001", "f", 60)
    await store.complete("anonymous", "key-0001", done, 1)
    assert (await store.reserve("anonymous", "key-0001", "f", 60)).outcome is Outcome.COMPLETED
    await asyncio.sleep(1.1)
    assert (await store.reserve("anonymous", "key-0001", "f", 60)).outcome is Outcome.STARTED
