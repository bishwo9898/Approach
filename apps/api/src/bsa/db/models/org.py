"""Organization and user records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bsa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from bsa.domain.enums import Role


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A baseball facility.

    There is exactly one today. Every tenant-owned table still carries
    `organization_id` because retrofitting multi-tenancy onto a live analytics
    database is far more expensive than carrying the column from day one.
    """

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    #: IANA timezone. Session dates are facility-local, so "what did Jake do
    #: today" needs the facility's idea of today, not UTC's.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/New_York")

    users: Mapped[list[User]] = relationship(back_populates="organization")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Someone allowed to sign in.

    Password security is delegated to the auth provider; we store only the
    provider's subject id. No credential material is ever persisted here.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("auth_provider", "auth_subject", name="uq_users_auth_identity"),
        Index("ix_users_organization_id_role", "organization_id", "role"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    auth_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    auth_subject: Mapped[str] = mapped_column(String(255), nullable=False)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[Role] = mapped_column(enum_column(Role, "role"), nullable=False)

    #: Set only for role=PLAYER. This single column is the entire basis of
    #: player self-access; it is checked server-side on every player-scoped read.
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True, index=True
    )

    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="users")
