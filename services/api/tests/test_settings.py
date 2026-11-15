import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sajao_api.main import create_app
from sajao_api.settings import Settings

API = Path(__file__).resolve().parents[1]


def test_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAJAO_ENVIRONMENT", "staging")
    monkeypatch.setenv("SAJAO_DATABASE_URL", "postgresql://user:hunter2@db.internal/sajao")
    monkeypatch.setenv("SAJAO_MIN_APP_VERSION", "1.2.0")
    monkeypatch.setenv("SAJAO_AUTH_JWKS_URL", "https://auth.test/jwks.json")
    monkeypatch.setenv("SAJAO_AUTH_ISSUER", "https://auth.test")
    settings = Settings()
    assert settings.environment == "staging"
    assert settings.min_app_version == "1.2.0"


def test_a_settings_file_is_never_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SAJAO_ENVIRONMENT=production\nSAJAO_MIN_APP_VERSION=9.9.9\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SAJAO_ENVIRONMENT", raising=False)
    assert Settings().environment == "dev"
    assert Settings().min_app_version == "0.0.0"


def test_secrets_do_not_appear_when_settings_are_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAJAO_DATABASE_URL", "postgresql://user:hunter2@db.internal/sajao")
    settings = Settings()
    assert "hunter2" not in repr(settings)
    assert "hunter2" not in settings.model_dump_json()


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_a_database_is_required_outside_dev(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("SAJAO_ENVIRONMENT", environment)
    monkeypatch.delenv("SAJAO_DATABASE_URL", raising=False)
    monkeypatch.setenv("SAJAO_AUTH_JWKS_URL", "https://auth.test/jwks.json")
    monkeypatch.setenv("SAJAO_AUTH_ISSUER", "https://auth.test")
    with pytest.raises(ValidationError, match="SAJAO_DATABASE_URL is required"):
        Settings()


def test_bad_values_fail_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAJAO_MIN_APP_VERSION", "one")
    with pytest.raises(ValidationError):
        Settings()


def test_the_committed_openapi_document_is_current() -> None:
    committed = json.loads((API / "openapi.json").read_text())
    assert committed == create_app(Settings(environment="dev", database_url=None)).openapi()
    assert all(path.startswith("/v1/") for path in committed["paths"])
