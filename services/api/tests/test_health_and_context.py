import json

import pytest
from pydantic import SecretStr

from sajao_api import __version__
from sajao_api.settings import Settings

from .conftest import ClientFactory


async def test_health_is_versioned_and_reports_environment(make_client: ClientFactory) -> None:
    async with make_client() as client:
        response = await client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "environment": "dev"}


async def test_unversioned_paths_do_not_exist(make_client: ClientFactory) -> None:
    async with make_client() as client:
        assert (await client.get("/health")).status_code == 404


async def test_every_response_carries_a_request_id(make_client: ClientFactory) -> None:
    async with make_client() as client:
        generated = await client.get("/v1/health")
        echoed = await client.get("/v1/health", headers={"X-Request-ID": "abc-123"})
        unsafe = await client.get("/v1/health", headers={"X-Request-ID": "bad id\twith spaces"})
    assert len(generated.headers["x-request-id"]) == 32
    assert echoed.headers["x-request-id"] == "abc-123"
    assert unsafe.headers["x-request-id"] != "bad id\twith spaces"


async def test_requests_are_logged_as_json_with_the_request_id(
    make_client: ClientFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    async with make_client() as client:
        await client.get("/v1/health?token=do-not-log", headers={"X-Request-ID": "req-1"})
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    entry = next(line for line in lines if line["event"] == "request")
    assert entry["request_id"] == "req-1"
    assert entry["method"] == "GET"
    assert entry["path"] == "/v1/health"
    assert entry["status"] == 200
    assert entry["level"] == "info"
    assert "duration_ms" in entry
    # Query strings, headers and bodies can hold personal data and are never logged.
    assert "do-not-log" not in json.dumps(entry)


async def test_docs_are_served_only_in_dev(make_client: ClientFactory) -> None:
    async with make_client() as client:
        assert (await client.get("/v1/docs")).status_code == 200
    staging = Settings(
        environment="staging",
        database_url=SecretStr("postgresql://unused"),
        auth_jwks_url="https://auth.test/jwks.json",
        auth_issuer="https://auth.test",
    )
    async with make_client(staging) as client:
        assert (await client.get("/v1/docs")).status_code == 404
