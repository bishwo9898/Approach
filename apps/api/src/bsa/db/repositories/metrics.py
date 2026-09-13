"""Metric definition and observation persistence."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from bsa.db.models import MetricDefinition, MetricObservation
from bsa.domain.enums import EventSource, Period, SourceStatus


def list_definitions(
    db: Session, organization_id: uuid.UUID, *, enabled_only: bool = True
) -> list[MetricDefinition]:
    stmt = select(MetricDefinition).where(MetricDefinition.organization_id == organization_id)
    if enabled_only:
        stmt = stmt.where(MetricDefinition.enabled.is_(True))
    return list(db.scalars(stmt.order_by(MetricDefinition.sort_order, MetricDefinition.key)))


def get_definition(
    db: Session, organization_id: uuid.UUID, definition_id: uuid.UUID
) -> MetricDefinition | None:
    return db.scalars(
        select(MetricDefinition).where(
            MetricDefinition.id == definition_id,
            MetricDefinition.organization_id == organization_id,
        )
    ).first()


def get_definition_by_key(
    db: Session, organization_id: uuid.UUID, key: str
) -> MetricDefinition | None:
    return db.scalars(
        select(MetricDefinition).where(
            MetricDefinition.organization_id == organization_id, MetricDefinition.key == key
        )
    ).first()


def definitions_for_source(
    db: Session, organization_id: uuid.UUID, source: EventSource
) -> list[MetricDefinition]:
    return [d for d in list_definitions(db, organization_id) if d.event_source is source]


def upsert_session_observation(
    db: Session,
    *,
    organization_id: uuid.UUID,
    player_id: uuid.UUID,
    metric_definition_id: uuid.UUID,
    session_id: uuid.UUID,
    period_start: date,
    value: float,
    sample_size: int,
    source_status: SourceStatus,
    calculation_version: int,
    context: dict[str, Any],
) -> None:
    """Write one session-scope observation, replacing any previous value.

    Recalculating a session overwrites rather than accumulates -- which is what
    makes a reprocessed import produce the same database state as the first run.
    """
    stmt = insert(MetricObservation).values(
        id=uuid.uuid4(),
        organization_id=organization_id,
        player_id=player_id,
        metric_definition_id=metric_definition_id,
        session_id=session_id,
        period=Period.SESSION.value,
        period_start=period_start,
        value=value,
        sample_size=sample_size,
        source_status=source_status.value,
        calculation_version=calculation_version,
        calculated_at=datetime.now(UTC),
        context=context,
    )
    db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_metric_observations_scope",
            set_={
                "value": stmt.excluded.value,
                "sample_size": stmt.excluded.sample_size,
                "source_status": stmt.excluded.source_status,
                "calculated_at": stmt.excluded.calculated_at,
                "context": stmt.excluded.context,
                "updated_at": datetime.now(UTC),
            },
        )
    )


def delete_session_observations(
    db: Session, session_id: uuid.UUID, *, keep_metric_ids: Sequence[uuid.UUID] | None = None
) -> int:
    """Drop observations a recalculation no longer produces.

    If corrected data drops a player below a metric's minimum sample size, the
    old value must disappear rather than linger as a number nothing supports.
    """
    stmt = delete(MetricObservation).where(MetricObservation.session_id == session_id)
    if keep_metric_ids:
        stmt = stmt.where(MetricObservation.metric_definition_id.not_in(list(keep_metric_ids)))
    return cast("CursorResult[Any]", db.execute(stmt)).rowcount or 0


def delete_player_session_observations(
    db: Session,
    session_id: uuid.UUID,
    player_id: uuid.UUID,
    keep_metric_ids: Sequence[uuid.UUID],
) -> int:
    stmt = delete(MetricObservation).where(
        MetricObservation.session_id == session_id,
        MetricObservation.player_id == player_id,
    )
    if keep_metric_ids:
        stmt = stmt.where(MetricObservation.metric_definition_id.not_in(list(keep_metric_ids)))
    return cast("CursorResult[Any]", db.execute(stmt)).rowcount or 0


def session_observations_for_player(
    db: Session,
    player_id: uuid.UUID,
    metric_definition_id: uuid.UUID,
    *,
    since: date | None = None,
    until: date | None = None,
) -> list[MetricObservation]:
    """The full ordered series behind a metric -- the PR engine's only input."""
    stmt = select(MetricObservation).where(
        MetricObservation.player_id == player_id,
        MetricObservation.metric_definition_id == metric_definition_id,
        MetricObservation.period == Period.SESSION,
    )
    if since:
        stmt = stmt.where(MetricObservation.period_start >= since)
    if until:
        stmt = stmt.where(MetricObservation.period_start <= until)
    return list(db.scalars(stmt.order_by(MetricObservation.period_start)))


def latest_observations(
    db: Session, player_id: uuid.UUID, metric_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, MetricObservation]:
    """Most recent session value per metric."""
    if not metric_ids:
        return {}
    rows = db.scalars(
        select(MetricObservation)
        .where(
            MetricObservation.player_id == player_id,
            MetricObservation.metric_definition_id.in_(list(metric_ids)),
            MetricObservation.period == Period.SESSION,
        )
        .order_by(MetricObservation.period_start.desc())
    )
    latest: dict[uuid.UUID, MetricObservation] = {}
    for row in rows:
        latest.setdefault(row.metric_definition_id, row)
    return latest


def observations_in_window(
    db: Session,
    player_id: uuid.UUID,
    metric_definition_id: uuid.UUID,
    start: date,
    end: date,
) -> list[MetricObservation]:
    return list(
        db.scalars(
            select(MetricObservation).where(
                MetricObservation.player_id == player_id,
                MetricObservation.metric_definition_id == metric_definition_id,
                MetricObservation.period == Period.SESSION,
                MetricObservation.period_start >= start,
                MetricObservation.period_start <= end,
            )
        )
    )


def session_observation_points(
    db: Session, player_id: uuid.UUID, metric_definition_id: uuid.UUID
) -> list[tuple[MetricObservation, Any]]:
    """Observations joined to their session.

    The PR engine orders by session date and start time, so both travel
    together rather than being fetched per row.
    """
    from bsa.db.models import TrainingSession

    stmt = (
        select(MetricObservation, TrainingSession)
        .join(TrainingSession, TrainingSession.id == MetricObservation.session_id)
        .where(
            MetricObservation.player_id == player_id,
            MetricObservation.metric_definition_id == metric_definition_id,
            MetricObservation.period == Period.SESSION,
        )
        .order_by(MetricObservation.period_start)
    )
    return [(o, s) for o, s in db.execute(stmt)]
