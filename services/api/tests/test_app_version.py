import pytest

from sajao_api.middleware.app_version import parse_version
from sajao_api.settings import Settings

from .conftest import ClientFactory


def test_versions_compare_numerically_not_as_text() -> None:
    older, newer = parse_version("1.9.0"), parse_version("1.10.0")
    assert older is not None and newer is not None
    assert older < newer
    assert parse_version("1.2") is None
    assert parse_version("v1.2.3") is None


@pytest.mark.parametrize(
    ("sent", "status"),
    [("1.4.0", 200), ("1.10.0", 200), ("2.0.0", 200), ("1.3.9", 426), ("0.9.0", 426)],
)
async def test_old_apps_are_told_to_update(
    make_client: ClientFactory, sent: str, status: int
) -> None:
    async with make_client(Settings(min_app_version="1.4.0")) as client:
        response = await client.get("/v1/health", headers={"X-App-Version": sent})
    assert response.status_code == status
    if status == 426:
        assert response.json() == {
            "error": {
                "code": "app_update_required",
                "message": "Please update the app to continue.",
                "min_version": "1.4.0",
            }
        }
        assert response.headers["x-request-id"]


async def test_clients_without_the_header_are_allowed(make_client: ClientFactory) -> None:
    async with make_client(Settings(min_app_version="1.4.0")) as client:
        assert (await client.get("/v1/health")).status_code == 200


async def test_a_malformed_version_is_rejected(make_client: ClientFactory) -> None:
    async with make_client() as client:
        response = await client.get("/v1/health", headers={"X-App-Version": "latest"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_app_version"
