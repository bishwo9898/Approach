"""Auth provider selection."""

from __future__ import annotations

from bsa.core.config import Settings
from bsa.core.errors import IntegrationNotConfiguredError
from bsa.integrations.auth.base import AuthProvider, VerifiedSubject
from bsa.integrations.auth.dev import DevAuthProvider

__all__ = ["AuthProvider", "DevAuthProvider", "VerifiedSubject", "get_auth_provider"]


def get_auth_provider(settings: Settings) -> AuthProvider:
    kind = settings.auth_provider.lower()
    if kind == "dev":
        return DevAuthProvider()
    if kind == "clerk":
        from bsa.integrations.auth.clerk import ClerkAuthProvider

        return ClerkAuthProvider(
            settings.clerk_jwks_url, settings.clerk_issuer, settings.clerk_audience
        )
    raise IntegrationNotConfiguredError(f"unknown auth provider {kind!r}")
