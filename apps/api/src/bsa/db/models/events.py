"""Normalized baseball event data.

These tables hold measurements, not conclusions. Every numeric column is already
in its canonical unit (see `bsa.core.units`) and says so in its name. Derived
values live in `metric_observations`, never here.

All columns except the identity/ordering ones are nullable: TrackMan does not
report every field for every pitch, and a missing measurement must be
distinguishable from a zero.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bsa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from bsa.domain.enums import SourceStatus


class PitchEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One tracked pitch."""

    __tablename__ = "pitch_events"
    __table_args__ = (
        # Idempotency: re-ingesting a session upserts on this key rather than
        # appending a second copy of every pitch.
        UniqueConstraint("session_id", "external_event_id", name="uq_pitch_events_session_event"),
        Index("ix_pitch_events_player_event_at", "player_id", "event_at"),
        Index("ix_pitch_events_org_event_at", "organization_id", "event_at"),
        Index("ix_pitch_events_player_pitch_type", "player_id", "pitch_type"),
        Index("ix_pitch_events_training_context", "training_context", postgresql_using="gin"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The pitcher.
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )

    external_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    pitch_number: Mapped[int | None] = mapped_column(nullable=True)
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: What the pitcher/coach called it. Normalized to our vocabulary
    #: (FASTBALL, SLIDER, ...) by the adapter, and the value metric filters
    #: match on.
    pitch_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: What the vendor's classifier called it. Kept separate because tagged and
    #: auto-detected types disagree, and a coach's intent is the one that
    #: matters for "fastball velocity".
    auto_pitch_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    velocity_mph: Mapped[float | None] = mapped_column(nullable=True)
    spin_rate_rpm: Mapped[float | None] = mapped_column(nullable=True)
    spin_axis_deg: Mapped[float | None] = mapped_column(nullable=True)
    horizontal_break_in: Mapped[float | None] = mapped_column(nullable=True)
    vertical_break_in: Mapped[float | None] = mapped_column(nullable=True)
    release_height_ft: Mapped[float | None] = mapped_column(nullable=True)
    release_side_ft: Mapped[float | None] = mapped_column(nullable=True)
    extension_ft: Mapped[float | None] = mapped_column(nullable=True)
    plate_location_height_ft: Mapped[float | None] = mapped_column(nullable=True)
    plate_location_side_ft: Mapped[float | None] = mapped_column(nullable=True)
    vertical_approach_angle_deg: Mapped[float | None] = mapped_column(nullable=True)
    horizontal_approach_angle_deg: Mapped[float | None] = mapped_column(nullable=True)

    #: Umpire/system call, normalized: STRIKE_CALLED, STRIKE_SWINGING, BALL,
    #: FOUL, IN_PLAY, HIT_BY_PITCH. Feeds strike-percentage style metrics.
    pitch_call: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_strike: Mapped[bool | None] = mapped_column(nullable=True)

    #: Training context: drill, grip, intent, ball type/weight, training block,
    #: coach tags. Schema-free on purpose -- the interesting dimensions are not
    #: known yet, and a GIN index keeps them queryable. Keys that prove
    #: load-bearing get promoted to real columns in a later migration.
    training_context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    source_status: Mapped[SourceStatus] = mapped_column(
        enum_column(SourceStatus, "source_status"),
        nullable=False,
        default=SourceStatus.PRELIMINARY,
    )
    #: The import this row's current values came from.
    raw_import_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("raw_imports.id", ondelete="SET NULL"), nullable=True
    )


class HitEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One tracked batted ball."""

    __tablename__ = "hit_events"
    __table_args__ = (
        UniqueConstraint("session_id", "external_event_id", name="uq_hit_events_session_event"),
        Index("ix_hit_events_player_event_at", "player_id", "event_at"),
        Index("ix_hit_events_org_event_at", "organization_id", "event_at"),
        Index("ix_hit_events_training_context", "training_context", postgresql_using="gin"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The batter.
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Set when the batted ball came from a tracked pitch in the same session.
    pitch_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pitch_events.id", ondelete="SET NULL"), nullable=True
    )

    external_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    swing_number: Mapped[int | None] = mapped_column(nullable=True)
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    exit_velocity_mph: Mapped[float | None] = mapped_column(nullable=True)
    launch_angle_deg: Mapped[float | None] = mapped_column(nullable=True)
    launch_direction_deg: Mapped[float | None] = mapped_column(nullable=True)
    distance_ft: Mapped[float | None] = mapped_column(nullable=True)
    hang_time_s: Mapped[float | None] = mapped_column(nullable=True)
    hit_spin_rate_rpm: Mapped[float | None] = mapped_column(nullable=True)
    contact_position_x_ft: Mapped[float | None] = mapped_column(nullable=True)
    contact_position_y_ft: Mapped[float | None] = mapped_column(nullable=True)
    contact_position_z_ft: Mapped[float | None] = mapped_column(nullable=True)

    #: Normalized: GROUND_BALL, LINE_DRIVE, FLY_BALL, POPUP.
    batted_ball_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    training_context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    source_status: Mapped[SourceStatus] = mapped_column(
        enum_column(SourceStatus, "source_status"),
        nullable=False,
        default=SourceStatus.PRELIMINARY,
    )
    raw_import_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("raw_imports.id", ondelete="SET NULL"), nullable=True
    )
