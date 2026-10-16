"""Account setup and sign-in.

The only unauthenticated endpoints in the API. Each one is rate limited per
client, on top of the per-account lockout in `services.accounts`, because these
are the endpoints an attacker can reach without a credential.

The flow is three screens and matches what a coach can actually support:

    1. POST /auth/activation/lookup    "is this my email?"   -> yes / no match
    2. POST /auth/activation/complete  choose a password
    3. POST /auth/login                sign in with it

Step 2 does not trust step 1. It repeats every check itself, because step 1
hands back nothing that could serve as proof it succeeded.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from bsa.api import schemas
from bsa.api.deps import CurrentPrincipal, DbSession, bearer_token
from bsa.core.config import Settings, get_settings
from bsa.core.password import policy_summary
from bsa.core.throttle import SlidingWindowLimiter
from bsa.services import accounts

router = APIRouter(prefix="/auth", tags=["auth"])

CurrentSettings = Annotated[Settings, Depends(get_settings)]

#: Separate budgets. A person mistyping their password should not use up the
#: allowance that stops someone walking the roster, and vice versa.
_LOOKUP_LIMIT = SlidingWindowLimiter(limit=20, window_seconds=300)
_LOGIN_LIMIT = SlidingWindowLimiter(limit=15, window_seconds=300)


def _client(request: Request) -> str:
    """A key to rate limit by.

    Behind Render and Vercel the socket address is a proxy, so the forwarded
    header is the only thing that distinguishes callers. It is caller-supplied
    and therefore spoofable -- which is exactly why this limiter is defence in
    depth and the per-account lockout is the control that has to hold.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/activation/lookup", response_model=schemas.ActivationTargetOut)
def lookup(
    payload: schemas.ActivationLookupIn,
    request: Request,
    db: DbSession,
    settings: CurrentSettings,
) -> schemas.ActivationTargetOut:
    """Check an email against the roster, before asking for a password.

    Returns 404 `email_not_recognized` when it does not match, which is the one
    place the API confirms whether an address is enrolled. See
    `EmailNotRecognizedError` for why that is deliberate.
    """
    _LOOKUP_LIMIT.check(_client(request))
    target = accounts.begin_activation(db, settings, email=payload.email, code=payload.code)
    return schemas.ActivationTargetOut(
        email=target.email,
        first_name=target.first_name,
        requires_code=target.requires_code,
        password_rules=policy_summary(),
    )


@router.post("/activation/complete", status_code=204)
def complete(
    payload: schemas.ActivationCompleteIn,
    request: Request,
    db: DbSession,
    settings: CurrentSettings,
) -> Response:
    """Set the account's first password.

    Deliberately does not return a session. The athlete goes to the sign-in
    screen and uses the password they just chose, which is the only way they
    find out straight away that they can reproduce it.
    """
    _LOOKUP_LIMIT.check(_client(request))
    accounts.complete_activation(
        db,
        settings,
        email=payload.email,
        code=payload.code,
        password=payload.password,
        confirmation=payload.password_confirmation,
    )
    return Response(status_code=204)


@router.post("/login", response_model=schemas.SignInOut)
def login(
    payload: schemas.LoginIn,
    request: Request,
    db: DbSession,
    settings: CurrentSettings,
) -> schemas.SignInOut:
    _LOGIN_LIMIT.check(_client(request))
    issued = accounts.authenticate(db, settings, email=payload.email, password=payload.password)
    return schemas.SignInOut(
        token=issued.token,
        expires_at=issued.expires_at,
        role=issued.user.role,
        display_name=issued.user.display_name,
    )


@router.post("/logout", status_code=204)
def logout(request: Request, db: DbSession, principal: CurrentPrincipal) -> Response:
    """End this session only, leaving the person's other devices signed in.

    Requires a valid credential so an unauthenticated caller cannot revoke a
    token they happen to have seen in a log.
    """
    accounts.revoke_session(db, bearer_token(request))
    return Response(status_code=204)
