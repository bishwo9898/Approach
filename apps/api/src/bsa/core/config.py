"""Runtime configuration.

Every setting comes from the environment. In production the environment is
populated from Google Secret Manager; nothing sensitive is ever read from a file
that could be committed.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class SignupGate(StrEnum):
    """What an athlete must prove to claim the account provisioned for them.

    Login emails are derived from names (`first.last@...`), so they are
    guessable by anyone holding a team sheet. `OPEN` therefore means "whoever
    types the address first owns the account", which is acceptable while the
    app is being demonstrated on synthetic data and is not acceptable once real
    athletes' sessions are in it. `CODE` closes that by requiring the one-time
    code a coach hands out.
    """

    #: Email match alone is enough. Development and demos only.
    OPEN = "open"
    #: Email match plus the account's activation code.
    CODE = "code"


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

    auth_provider: str = "local"
    #: Domain of the login addresses the roster provisioner mints.
    account_email_domain: str = "approach.com"
    signup_gate: SignupGate = SignupGate.OPEN
    #: How long a sign-in lasts before the browser must sign in again.
    session_ttl_hours: int = 12
    #: Consecutive failures before an account is locked, and for how long.
    #: Low enough to stop online guessing, high enough to survive real typos.
    login_max_attempts: int = 7
    login_lockout_minutes: int = 15
    #: Shared passcodes, one per role. Development defaults only -- production
    #: refuses to start while they are still these values.
    coach_passcode: str = "coach"
    player_passcode: str = "player"
    clerk_jwks_url: str | None = None
    clerk_issuer: str | None = None
    clerk_audience: str | None = None

    #: Which OCR engine converts screenshots. "vision" is macOS-only and is
    #: the one measured against real TrackMan screenshots; "tesseract" runs in
    #: the container. There is no automatic fallback between them.
    ocr_engine: str = "vision"

    trackman_provider: str = "csv"
    futures_provider: str = "manual"

    #: Browser origins allowed to call the API.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _guard_production(self) -> Settings:
        """Fail fast rather than run production on development shortcuts."""
        deployed = self.env in (Environment.STAGING, Environment.PRODUCTION)

        # A deployed app is reachable by anyone with the link, so the signup
        # gate must be a decision somebody made rather than a default they
        # inherited. Staging is included because staging is the public demo.
        chose_gate = "signup_gate" in self.model_fields_set
        if deployed and self.auth_provider == "local" and not chose_gate:
            raise ValueError(
                f"BSA_SIGNUP_GATE must be set explicitly when BSA_ENV={self.env.value}. "
                "Use 'code' to require the activation code a coach hands out, or "
                "'open' to accept a matching email alone -- which lets anyone who "
                "can guess first.last@domain claim that athlete's account."
            )

        if self.env is Environment.PRODUCTION:
            if self.auth_provider == "dev":
                raise ValueError(
                    "BSA_AUTH_PROVIDER=dev is refused in production: "
                    "dev auth trusts static seeded tokens."
                )
            if self.auth_provider == "passcode":
                # A deployment must never inherit the development passcodes.
                weak = {
                    name
                    for name, value in (
                        ("BSA_COACH_PASSCODE", self.coach_passcode),
                        ("BSA_PLAYER_PASSCODE", self.player_passcode),
                    )
                    if value in ("coach", "player") or len(value) < 8
                }
                if weak:
                    raise ValueError(
                        f"{', '.join(sorted(weak))} must be set to a value of at "
                        "least 8 characters in production."
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
    def session_ttl_seconds(self) -> int:
        return self.session_ttl_hours * 3600

    @property
    def is_development(self) -> bool:
        return self.env is Environment.DEVELOPMENT

    @property
    def database_target(self) -> str:
        """`host:port/name` for the configured database, without credentials.

        Used by /health so it is obvious which database a process is attached
        to. Deliberately reconstructed field by field rather than by trimming
        the URL string, so a password cannot survive a parsing mistake.
        """
        try:
            parsed = urlsplit(self.database_url)
            host, port = parsed.hostname, parsed.port
        except ValueError:
            return "unknown"

        # No host means the URL did not parse as one. Returning any part of the
        # raw string here could echo back a malformed URL that still contains a
        # password, so report nothing instead.
        if not host:
            return "unknown"

        name = (parsed.path or "").lstrip("/") or "unknown"
        return f"{host}{':' + str(port) if port else ''}/{name}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
