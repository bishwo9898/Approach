"""Credentials and sessions for accounts the facility provisions itself.

Why this exists at all: `bsa.integrations.auth` delegates identity to a
provider, and the intent is still that Clerk (or similar) takes this over. But
there is no provider today, and the facility's athletes are minors who will
never have a corporate SSO identity -- a coach adds them from a TrackMan roster
export. So the interim is a local account, and a local account needs somewhere
to keep a password hash.

Two deliberate separations:

* Credential material lives in its own table, not on `users`. Every
  authenticated request loads a `User`; none of them should be carrying a
  password hash around in memory or into a log line.
* Sessions are rows, not signed tokens. A row can be revoked -- on sign-out, on
  a password change, or by a coach -- and a signed token cannot. For a system
  holding minors' data, being able to end a session now matters more than
  avoiding one indexed lookup per request.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bsa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from bsa.db.models.org import User


class UserCredential(TimestampMixin, Base):
    """One row per account, created when the account is provisioned.

    It exists *before* a password does. That is the whole point of the
    activation flow: the facility creates the account from its roster, and the
    athlete later proves they are the person that account was made for and
    chooses their own password. `password_hash` being NULL is therefore a
    normal, expected state meaning "provisioned, never claimed".
    """

    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    #: Encoded Argon2id hash, parameters included. NULL until activation.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Argon2id hash of the one-time code a coach hands the athlete, when the
    #: deployment requires one. Hashed rather than stored plainly because it is
    #: a credential: it is the only thing proving the person claiming
    #: `first.last@...` is that person. The plaintext is shown once, at
    #: provisioning, and never recoverable from here afterwards.
    activation_code_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Consecutive failures, reset by any success. Drives `locked_until`.
    failed_attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    #: Set when too many failures accumulate. Counted in the database rather
    #: than in process memory so a restart -- or a second instance -- does not
    #: hand an attacker a fresh budget.
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship()

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None


class UserSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A signed-in browser.

    The token itself is never stored. We keep its SHA-256, so a reader of this
    table cannot sign in as anyone: the only way to produce the stored value is
    to already hold the token. A plain hash is correct here (unlike for
    passwords) precisely because the token is 256 bits of randomness -- there is
    no dictionary to run against it.
    """

    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_user_id_expires_at", "user_id", "expires_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Hex SHA-256 of the bearer token the client holds.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Set on sign-out or when every session is dropped after a password change.
    #: Kept rather than deleted so "this token was already revoked" stays
    #: distinguishable from "this token never existed".
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship()
