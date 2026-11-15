"""Configuration, read from environment variables only.

There is no settings file and no .env loading: secrets come from the
platform's secret manager as environment variables and never live in the
repository.
"""

from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SAJAO_", extra="ignore")

    environment: Literal["dev", "staging", "production"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Postgres connection string. Required outside dev so the service stays stateless.
    database_url: SecretStr | None = None

    # Apps older than this are told to update. "0.0.0" allows every version.
    min_app_version: str = Field(default="0.0.0", pattern=r"^\d+\.\d+\.\d+$")

    # How long a finished write can be replayed for the same idempotency key.
    idempotency_ttl_seconds: int = Field(default=24 * 60 * 60, gt=0)
    # How long an unfinished write blocks retries before it can be taken over.
    idempotency_in_progress_seconds: int = Field(default=60, gt=0)

    @model_validator(mode="after")
    def _require_database_outside_dev(self) -> Self:
        if self.environment != "dev" and self.database_url is None:
            raise ValueError("SAJAO_DATABASE_URL is required in staging and production")
        return self
