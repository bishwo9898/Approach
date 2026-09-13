"""Clerk JWT verification.

Verifies the session token's signature against Clerk's published JWKS and checks
issuer, audience and expiry. What it deliberately does NOT do is read any role
or organization claim: those come from our `users` table, keyed on the verified
subject.

Left unconfigured until a Clerk application exists -- `verify` refuses rather
than falling back to a weaker check.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from bsa.core.errors import AuthenticationError, IntegrationNotConfiguredError
from bsa.integrations.auth.base import VerifiedSubject


@lru_cache(maxsize=4)
def _jwk_client(jwks_url: str) -> PyJWKClient:
    # Cached: the JWKS is fetched over the network and rotates rarely.
    return PyJWKClient(jwks_url, cache_keys=True)


class ClerkAuthProvider:
    name = "clerk"

    def __init__(self, jwks_url: str | None, issuer: str | None, audience: str | None) -> None:
        if not jwks_url or not issuer:
            raise IntegrationNotConfiguredError(
                "Clerk is not configured. Set BSA_CLERK_JWKS_URL and BSA_CLERK_ISSUER "
                "(from Secret Manager in production)."
            )
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience

    def verify(self, credential: str) -> VerifiedSubject:
        try:
            signing_key = _jwk_client(self._jwks_url).get_signing_key_from_jwt(credential)
            claims: dict[str, Any] = jwt.decode(
                credential,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": ["exp", "iss", "sub"],
                    "verify_aud": bool(self._audience),
                },
            )
        except jwt.PyJWTError as exc:
            # The reason is logged, not returned: telling a caller precisely why
            # a token failed helps forge the next one.
            raise AuthenticationError("token verification failed") from exc

        subject = claims.get("sub")
        if not subject:
            raise AuthenticationError("token has no subject")
        return VerifiedSubject(provider=self.name, subject=str(subject), email=claims.get("email"))
