"""Athlete identity and the mapping to vendor identities."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bsa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from bsa.domain.enums import Handedness, IdentityResolutionStatus


class Player(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Our canonical athlete record -- the only identity the domain trusts.

    Deliberately minimal on PII: this system holds data about minors, so a field
    is added only when a feature actually requires it. `date_of_birth` is
    nullable and exists solely for age-band grouping; nothing in Phase 1 reads it.
    """

    __tablename__ = "players"
    __table_args__ = (
        Index("ix_players_organization_id_active", "organization_id", "active"),
        Index("ix_players_organization_id_last_name", "organization_id", "last_name"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    preferred_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(nullable=True)
    #: Free text (e.g. "RHP", "C/OF"). Positions are a coaching label, not a
    #: closed vocabulary worth constraining.
    position: Mapped[str | None] = mapped_column(String(32), nullable=True)

    bats: Mapped[Handedness | None] = mapped_column(enum_column(Handedness, "bats"), nullable=True)
    throws: Mapped[Handedness | None] = mapped_column(
        enum_column(Handedness, "throws"), nullable=True
    )

    active: Mapped[bool] = mapped_column(nullable=False, default=True)

    identities: Mapped[list[ExternalPlayerIdentity]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def display_name(self) -> str:
        return f"{self.preferred_name or self.first_name} {self.last_name}"


class ExternalPlayerIdentity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Maps one vendor identity to one of our players.

    The uniqueness constraint below is the load-bearing part of this table: a
    given (provider, external_id) can point at exactly one internal player, so a
    TrackMan id can never silently end up attached to two athletes.

    A player may hold several identities per provider (TrackMan has been known to
    issue a new id after a roster re-entry), which is why the constraint is on
    the external side, not on (player, provider).
    """

    __tablename__ = "external_player_identities"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "provider", "external_id", name="uq_external_identity_provider_id"
        ),
        Index("ix_external_identities_player_provider", "player_id", "provider"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    #: The name the vendor shows. Stored for operator recognition only -- it is
    #: never used to match athletes.
    external_display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    player_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", nullable=False, default=dict
    )
    #: Set when a human confirmed the mapping. NULL means machine-asserted.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    player: Mapped[Player] = relationship(back_populates="identities")


class IdentityResolutionItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An unknown vendor athlete parked for a human decision.

    We never guess. If TrackMan reports an id we have no mapping for, its rows
    are held here rather than attached to a name-similar player, because
    attributing one athlete's data to another is the single worst failure this
    system can produce.
    """

    __tablename__ = "identity_resolution_items"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "provider", "external_id", name="uq_identity_resolution_provider_id"
        ),
        Index("ix_identity_resolution_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    status: Mapped[IdentityResolutionStatus] = mapped_column(
        enum_column(IdentityResolutionStatus, "identity_resolution_status"),
        nullable=False,
        default=IdentityResolutionStatus.UNRESOLVED,
    )
    #: How many source rows are blocked on this decision -- lets the dashboard
    #: rank the queue by how much data is stuck.
    occurrence_count: Mapped[int] = mapped_column(nullable=False, default=0)
    first_seen_import_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("raw_imports.id", ondelete="SET NULL"), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    resolved_player_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
