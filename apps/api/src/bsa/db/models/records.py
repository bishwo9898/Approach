"""Personal records and their immutable progression history."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from bsa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from bsa.domain.enums import SourceStatus


class PersonalRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The player's current best for one metric.

    A cached projection of the last row of `personal_record_events`. It exists
    so the dashboard can read a PR without walking history; it is always
    rebuilt from the event series, never incremented in place.
    """

    __tablename__ = "personal_records"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "metric_definition_id", name="uq_personal_records_player_metric"
        ),
        Index("ix_personal_records_org_achieved", "organization_id", "achieved_on"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("metric_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    value: Mapped[float] = mapped_column(nullable=False)
    sample_size: Mapped[int] = mapped_column(nullable=False, default=0)

    #: Session in which the record was set.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    achieved_on: Mapped[date] = mapped_column(Date, nullable=False)
    achieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: A PR standing on PRELIMINARY data is shown as provisional, because a
    #: verified republish can take it away.
    source_status: Mapped[SourceStatus] = mapped_column(
        enum_column(SourceStatus, "source_status"),
        nullable=False,
        default=SourceStatus.PRELIMINARY,
    )
    calculation_version: Mapped[int] = mapped_column(nullable=False, default=1)
    context: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)

    #: Set when an admin pins a value by hand; the engine then leaves it alone.
    is_manual_override: Mapped[bool] = mapped_column(nullable=False, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PersonalRecordEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One moment a record was broken.

    The progression, not just the number: "when did Jake hit that PR" and "how
    much has he gained this year" are both answered from this table.

    Uniqueness on (player, metric, session) is what makes the PR engine
    idempotent -- re-importing a session rewrites its row rather than announcing
    the same achievement twice.
    """

    __tablename__ = "personal_record_events"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "metric_definition_id",
            "session_id",
            name="uq_pr_events_player_metric_session",
        ),
        Index("ix_pr_events_org_achieved", "organization_id", "achieved_on"),
        Index("ix_pr_events_player_metric", "player_id", "metric_definition_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("metric_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: NULL for the first record of a metric -- there was nothing to beat.
    previous_value: Mapped[float | None] = mapped_column(nullable=True)
    new_value: Mapped[float] = mapped_column(nullable=False)
    #: new - previous, sign preserved. For LOWER_IS_BETTER metrics an
    #: improvement is negative, which is the honest representation.
    delta: Mapped[float | None] = mapped_column(nullable=True)

    sample_size: Mapped[int] = mapped_column(nullable=False, default=0)
    achieved_on: Mapped[date] = mapped_column(Date, nullable=False)
    achieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_status: Mapped[SourceStatus] = mapped_column(
        enum_column(SourceStatus, "source_status"),
        nullable=False,
        default=SourceStatus.PRELIMINARY,
    )
    calculation_version: Mapped[int] = mapped_column(nullable=False, default=1)
    context: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)

    #: Set when a verified republish invalidated a record this row had claimed.
    #: The row stays -- the audit trail must show what we told the coach at the
    #: time -- but it no longer counts toward the progression.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
