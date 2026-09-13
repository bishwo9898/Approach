"""Outbound synchronization to The Futures App.

No Futures integration method is confirmed yet, so this models the *intent* to
push a value and its outcome. That is useful immediately: even with zero
automation, it drives a "these records still need entering" worklist, which is
the coach's actual current pain.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from bsa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from bsa.domain.enums import SyncStatus


class ExternalMetricMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Maps one of our metrics to a destination system's field."""

    __tablename__ = "external_metric_mappings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "destination",
            "metric_definition_id",
            name="uq_metric_mapping_destination_metric",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    metric_definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("metric_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: e.g. "futures". A string rather than an enum so a second destination
    #: needs no migration.
    destination: Mapped[str] = mapped_column(String(32), nullable=False)
    #: The label the coach sees in the destination system.
    destination_field: Mapped[str] = mapped_column(String(160), nullable=False)
    #: Unit the destination expects. If it differs from the metric's canonical
    #: unit, conversion happens once, in bsa.core.units, at push time.
    destination_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    destination_precision: Mapped[int] = mapped_column(nullable=False, default=1)

    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    mapping_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", nullable=False, default=dict
    )


class SyncJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One pending or completed push of one value to one destination."""

    __tablename__ = "sync_jobs"
    __table_args__ = (
        # At most one open job per (player, metric, destination). Re-running the
        # PR engine refreshes the pending value rather than queueing a second
        # copy of the same instruction.
        UniqueConstraint(
            "player_id",
            "metric_definition_id",
            "destination",
            "personal_record_event_id",
            name="uq_sync_jobs_target",
        ),
        Index("ix_sync_jobs_org_status", "organization_id", "status"),
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
    #: What triggered the push. NULL would mean a manual/ad-hoc request.
    personal_record_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("personal_record_events.id", ondelete="CASCADE"), nullable=True
    )

    destination: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Value and unit frozen at queue time, so the worklist shows what was
    #: intended even if the metric is later recalculated.
    value: Mapped[float] = mapped_column(nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    destination_field: Mapped[str] = mapped_column(String(160), nullable=False)

    status: Mapped[SyncStatus] = mapped_column(
        enum_column(SyncStatus, "sync_status"), nullable=False, default=SyncStatus.PENDING
    )
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Who clicked "Mark Updated", when the destination has no API.
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
