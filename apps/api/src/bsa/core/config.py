"""Runtime configuration.

Every setting comes from the environment. In production the environment is
populated from Google Secret Manager; nothing sensitive is ever read from a file
that could be committed.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BSA_",
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    api_port: int = 8000

    database_url: str = "postgresql+psycopg://bsa:bsa@localhost:5433/bsa"
    test_database_url: str = "postgresql+psycopg://bsa:bsa@localhost:5433/bsa_test"
    db_echo: bool = False

    object_store_backend: str = "local"
    object_store_local_root: Path = Path("./var/objectstore")
    gcs_bucket: str | None = None

    auth_provider: str = "dev"
    clerk_jwks_url: str | None = None
    clerk_issuer: str | None = None
    clerk_audience: str | None = None

    trackman_provider: str = "csv"
    futures_provider: str = "manual"

    #: Browser origins allowed to call the API.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _guard_production(self) -> Settings:
        """Fail fast rather than run production on development shortcuts."""
        if self.env is Environment.PRODUCTION:
            if self.auth_provider == "dev":
                raise ValueError(
                    "BSA_AUTH_PROVIDER=dev is refused in production: "
                    "dev auth trusts static seeded tokens."
                )
            if self.object_store_backend == "local":
                raise ValueError(
                    "BSA_OBJECT_STORE_BACKEND=local is refused in production: "
                    "Cloud Run instances have ephemeral disks, raw imports would be lost."
                )
            if self.object_store_backend == "gcs" and not self.gcs_bucket:
                raise ValueError("BSA_GCS_BUCKET is required when object store backend is gcs")
        return self

    @property
    def is_development(self) -> bool:
        return self.env is Environment.DEVELOPMENT


@lru_cache
def get_settings() -> Settings:
    return Settings()
