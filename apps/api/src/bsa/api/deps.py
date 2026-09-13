"""Request-scoped dependencies: authentication, organization scope, authorization.

The rule this module exists to enforce: **authorization is decided on the
server, from our database, on every protected request.** The auth provider is
only asked "who is this?". What they may see is answered here.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from bsa.core.config import Settings, get_settings
from bsa.core.errors import AuthenticationError, AuthorizationError, NotFoundError
from bsa.db.models import Organization, Player, User
from bsa.db.repositories import players as players_repo
from bsa.db.session import get_db
from bsa.domain.enums import Role
from bsa.integrations.auth import get_auth_provider
from bsa.integrations.storage import ObjectStore, get_object_store
from bsa.integrations.trackman import TrackmanProvider, get_trackman_provider


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller, with the scope they are confined to."""

    user: User
    organization: Organization

    @property
    def role(self) -> Role:
        return self.user.role

    @property
    def organization_id(self) -> uuid.UUID:
        return self.organization.id

    @property
    def is_staff(self) -> bool:
        """Staff see the whole organization. Players see only themselves."""
        return self.role in (Role.ADMIN, Role.COACH)


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("missing bearer token")
    return token.strip()


def get_principal(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    """Verify the credential and load the caller's own record.

    Roles and organization membership come from our `users` table, never from a
    token claim: an auth provider must not be able to grant itself access to an
    athlete's data.
    """
    subject = get_auth_provider(settings).verify(_bearer_token(request))

    user = db.scalars(
        select(User).where(
            User.auth_provider == subject.provider,
            User.auth_subject == subject.subject,
            User.active.is_(True),
        )
    ).first()
    if user is None:
        # The credential was valid but nobody has granted it access here.
        raise AuthenticationError("no active user for this credential")

    organization = db.get(Organization, user.organization_id)
    if organization is None:  # pragma: no cover -- FK makes this unreachable
        raise AuthenticationError("user is not attached to an organization")

    return Principal(user=user, organization=organization)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
DbSession = Annotated[Session, Depends(get_db)]


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    """Dependency factory restricting an endpoint to specific roles."""
    allowed = set(roles)

    def _dependency(principal: CurrentPrincipal) -> Principal:
        if principal.role not in allowed:
            raise AuthorizationError("your role does not permit this operation")
        return principal

    return _dependency


require_staff = require_roles(Role.ADMIN, Role.COACH)
require_admin = require_roles(Role.ADMIN)

StaffPrincipal = Annotated[Principal, Depends(require_staff)]
AdminPrincipal = Annotated[Principal, Depends(require_admin)]


def authorize_player(db: Session, principal: Principal, player_id: uuid.UUID) -> Player:
    """Resolve a player the caller is actually allowed to read.

    The single choke point for athlete access. Two checks, both server-side:

      1. The player must belong to the caller's organization.
      2. A PLAYER may read only the athlete their own user row points at.

    A player reaching for someone else's id gets the same response as one
    reaching for an id that does not exist -- distinguishing them would confirm
    which athletes are enrolled at the facility.
    """
    player = players_repo.get(db, principal.organization_id, player_id)
    if player is None:
        raise NotFoundError("player not found")

    if not principal.is_staff and principal.user.player_id != player.id:
        raise AuthorizationError("you do not have access to this athlete")

    return player


def current_player(db: Session, principal: Principal) -> Player:
    """The athlete behind a PLAYER login."""
    if principal.user.player_id is None:
        raise NotFoundError("this account is not linked to an athlete profile")
    return authorize_player(db, principal, principal.user.player_id)


def db_session() -> Iterator[Session]:
    yield from get_db()


# -- integration adapters ----------------------------------------------------
#
# Exposed as FastAPI dependencies rather than constructed inside route bodies so
# the composition is explicit and a test can substitute a temp-directory object
# store or a stub provider without monkeypatching module globals.


def get_object_store_dep(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ObjectStore:
    return get_object_store(settings)


def get_trackman_provider_dep(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TrackmanProvider:
    return get_trackman_provider(settings)


CurrentObjectStore = Annotated[ObjectStore, Depends(get_object_store_dep)]
CurrentTrackmanProvider = Annotated[TrackmanProvider, Depends(get_trackman_provider_dep)]
