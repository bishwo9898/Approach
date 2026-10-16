"""Auth provider selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bsa.core.config import Settings
from bsa.core.errors import IntegrationNotConfiguredError
from bsa.integrations.auth.base import AuthProvider, VerifiedSubject
from bsa.integrations.auth.dev import DevAuthProvider

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

__all__ = ["AuthProvider", "DevAuthProvider", "VerifiedSubject", "get_auth_provider"]


def get_auth_provider(settings: Settings, db: Session | None = None) -> AuthProvider:
    """The configured provider.

    `db` is required only by the `local` provider, whose credentials are rows in
    our own database rather than something it can verify offline. It is passed
    by the request dependency and omitted by tests that exercise the stateless
    providers.
    """
    kind = settings.auth_provider.lower()
    if kind == "dev":
        return DevAuthProvider()
    if kind == "local":
        from bsa.integrations.auth.local import LocalAuthProvider

        if db is None:
            raise IntegrationNotConfiguredError(
                "the local auth provider needs a database session to verify a token"
            )
        return LocalAuthProvider(db)
    if kind == "passcode":
        from bsa.integrations.auth.passcode import PasscodeAuthProvider

        return PasscodeAuthProvider(
            {"coach": settings.coach_passcode, "player": settings.player_passcode}
        )
    if kind == "clerk":
        from bsa.integrations.auth.clerk import ClerkAuthProvider

        return ClerkAuthProvider(
            settings.clerk_jwks_url, settings.clerk_issuer, settings.clerk_audience
        )
    raise IntegrationNotConfiguredError(f"unknown auth provider {kind!r}")
