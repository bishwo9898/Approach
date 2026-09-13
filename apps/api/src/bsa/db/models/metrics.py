"""Configurable metric definitions and their calculated observations."""

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
from sqlalchemy.orm import Mapped, mapped_column

from bsa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from bsa.domain.enums import (
    Aggregation,
    EventSource,
    MetricCategory,
    MetricDataType,
    Period,
    RecordDirection,
    SourceStatus,
)


class MetricDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What a metric *is* -- data, not code.

    "Fastball max velocity" is a row, not a function. Coaches will change the
    metric set repeatedly, and the alternative (a hardcoded calculation per
    metric) makes every change a deployment.

    The `spec` column carries the selector -- which events feed the metric and
    how they are filtered -- validated against `bsa.domain.metric_spec.MetricSpec`
    before it is written.
    """

    __tablename__ = "metric_definitions"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_metric_definitions_key"),
        Index("ix_metric_definitions_org_category", "organization_id", "category"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    #: Stable dotted identifier, e.g. "pitch.fastball.max_velocity". This is what
    #: code, mappings and API callers refer to; display_name is free to change.
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[MetricCategory] = mapped_column(
        enum_column(MetricCategory, "metric_category"), nullable=False
    )
    event_source: Mapped[EventSource] = mapped_column(
        enum_column(EventSource, "event_source"), nullable=False
    )
    aggregation: Mapped[Aggregation] = mapped_column(
        enum_column(Aggregation, "aggregation"), nullable=False
    )
    record_direction: Mapped[RecordDirection] = mapped_column(
        enum_column(RecordDirection, "record_direction"),
        nullable=False,
        default=RecordDirection.NONE,
    )
    data_type: Mapped[MetricDataType] = mapped_column(
        enum_column(MetricDataType, "metric_data_type"),
        nullable=False,
        default=MetricDataType.FLOAT,
    )
    #: Canonical unit. NOT NULL: a stored measurement whose unit is unknown is
    #: unusable, and worse, is usually displayed anyway.
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Decimal places for display, so the API and UI never disagree.
    display_precision: Mapped[int] = mapped_column(nullable=False, default=1)

    #: Minimum qualifying events before the metric is calculated at all. Stops a
    #: single mis-tracked pitch from becoming a personal record.
    min_sample_size: Mapped[int] = mapped_column(nullable=False, default=1)

    #: The selector. See bsa.domain.metric_spec.MetricSpec.
    spec: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)

    #: Bumped by hand when the calculation changes meaning. Observations record
    #: the version that produced them, so historical numbers never shift
    #: silently underneath a coach.
    calculation_version: Mapped[int] = mapped_column(nullable=False, default=1)

    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    #: Shown on the player overview without being asked for.
    is_headline: Mapped[bool] = mapped_column(nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=100)

    metric_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", nullable=False, default=dict
    )


class MetricObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A metric's value for one player over one scope.

    Phase 1 materializes only SESSION-scope observations. They are the atoms
    everything else is built from: day/week/month rollups and the PR progression
    are all derived from this ordered series, so re-deriving them is cheap and
    always consistent with the events.
    """

    __tablename__ = "metric_observations"
    __table_args__ = (
        # One value per (player, metric, scope, calculation version). Recomputing
        # an import upserts onto this key instead of stacking duplicates.
        UniqueConstraint(
            "player_id",
            "metric_definition_id",
            "period",
            "period_start",
            "session_id",
            "calculation_version",
            name="uq_metric_observations_scope",
        ),
        Index(
            "ix_metric_obs_player_metric_period",
            "player_id",
            "metric_definition_id",
            "period_start",
        ),
        Index("ix_metric_obs_session", "session_id"),
        Index(
            "ix_metric_obs_org_period",
            "organization_id",
            "period_start",
        ),
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

    period: Mapped[Period] = mapped_column(enum_column(Period, "period"), nullable=False)
    #: First calendar day of the scope. For SESSION, the session's date -- which
    #: keeps the uniqueness key non-null for every period type.
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    #: Set only for SESSION-scope rows.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True
    )

    value: Mapped[float] = mapped_column(nullable=False)
    #: Number of qualifying events behind the value. Displayed with every chart:
    #: a 96 mph average off two pitches is not the same claim as off forty.
    sample_size: Mapped[int] = mapped_column(nullable=False, default=0)

    source_status: Mapped[SourceStatus] = mapped_column(
        enum_column(SourceStatus, "source_status"),
        nullable=False,
        default=SourceStatus.PRELIMINARY,
    )
    calculation_version: Mapped[int] = mapped_column(nullable=False, default=1)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: Filter dimensions the value was computed under (e.g. pitch_type).
    context: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
