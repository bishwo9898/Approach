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


class EmailNotRecognizedError(BsaError):
    """The email given at account setup is not on the roster.

    Deliberately explicit, and deliberately different from a failed sign-in.
    Setting up an account is the one place a person needs to be told *which*
    field is wrong -- they cannot correct a typo in an address they were given
    verbally if the only feedback is "something was wrong". The roster this
    reveals is the facility's own class list, which every athlete in it already
    knows; the credential that actually protects the account is the activation
    code, not the secrecy of the address.
    """

    status_code = 404
    code = "email_not_recognized"


class ActivationCodeError(BsaError):
    """The activation code did not match the account being claimed."""

    status_code = 403
    code = "activation_code_invalid"


class AlreadyActivatedError(BsaError):
    """This account already has a password, so it cannot be set up again.

    Resetting a forgotten password is a coach action, not a self-service one --
    self-service reset would need a mail channel we do not have, and without
    one it would reduce to "anyone who knows the address can take the account".
    """

    status_code = 409
    code = "already_activated"


class PasswordNotSetError(BsaError):
    """A sign-in attempt against a provisioned but unclaimed account."""

    status_code = 401
    code = "password_not_set"


class AccountLockedError(BsaError):
    """Too many consecutive failures. Rate limiting, not a permanent state."""

    status_code = 429
    code = "account_locked"
