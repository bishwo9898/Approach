"""Application-level exceptions.

These are translated into HTTP responses by a single handler in `bsa.api.app`,
so services and domain code never import FastAPI or raise HTTPException.
"""

from __future__ import annotations

from typing import Any


class BsaError(Exception):
    """Base class for expected, handled application errors."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(BsaError):
    status_code = 404
    code = "not_found"


class ValidationError(BsaError):
    status_code = 422
    code = "validation_error"


class ConflictError(BsaError):
    status_code = 409
    code = "conflict"


class AuthenticationError(BsaError):
    status_code = 401
    code = "unauthenticated"


class AuthorizationError(BsaError):
    """Raised whenever a principal reaches for data outside its scope.

    Deliberately does not distinguish "does not exist" from "not yours" in its
    public message -- that difference leaks the existence of other athletes.
    """

    status_code = 403
    code = "forbidden"


class IntegrationNotConfiguredError(BsaError):
    """A vendor integration was requested that we do not yet have access to."""

    status_code = 501
    code = "integration_not_configured"
