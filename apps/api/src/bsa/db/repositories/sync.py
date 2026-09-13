"""Outbound synchronization queue."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bsa.db.models import (
    ExternalMetricMapping,
    MetricDefinition,
    PersonalRecordEvent,
    Player,
    SyncJob,
)
from bsa.domain.enums import SyncStatus


def mapping_for_metric(
    db: Session, organization_id: uuid.UUID, metric_definition_id: uuid.UUID, destination: str
) -> ExternalMetricMapping | None:
    return db.scalars(
        select(ExternalMetricMapping).where(
            ExternalMetricMapping.organization_id == organization_id,
            ExternalMetricMapping.metric_definition_id == metric_definition_id,
            ExternalMetricMapping.destination == destination,
            ExternalMetricMapping.enabled.is_(True),
        )
    ).first()


def upsert_job(
    db: Session,
    *,
    organization_id: uuid.UUID,
    player_id: uuid.UUID,
    metric_definition_id: uuid.UUID,
    personal_record_event_id: uuid.UUID | None,
    destination: str,
    destination_field: str,
    value: float,
    unit: str,
) -> SyncJob:
    """Queue one value for a destination, without creating duplicates.

    Keyed on the PR event that triggered it, so re-running ingestion refreshes
    the pending instruction instead of giving the coach the same item twice.
    """
    existing = db.scalars(
        select(SyncJob).where(
            SyncJob.player_id == player_id,
            SyncJob.metric_definition_id == metric_definition_id,
            SyncJob.destination == destination,
            SyncJob.personal_record_event_id == personal_record_event_id,
        )
    ).first()

    if existing is not None:
        # A completed job is never reopened by a recalculation: the coach
        # already entered that value, and re-queueing it would send them back
        # to do work they have done.
        if existing.status is not SyncStatus.SYNCED:
            existing.value = value
            existing.unit = unit
            existing.destination_field = destination_field
        return existing

    job = SyncJob(
        organization_id=organization_id,
        player_id=player_id,
        metric_definition_id=metric_definition_id,
        personal_record_event_id=personal_record_event_id,
        destination=destination,
        destination_field=destination_field,
        value=value,
        unit=unit,
        status=SyncStatus.PENDING,
    )
    db.add(job)
    db.flush()
    return job


def list_pending(
    db: Session, organization_id: uuid.UUID, *, destination: str = "futures", limit: int = 100
) -> list[tuple[SyncJob, Player, MetricDefinition]]:
    stmt = (
        select(SyncJob, Player, MetricDefinition)
        .join(Player, Player.id == SyncJob.player_id)
        .join(MetricDefinition, MetricDefinition.id == SyncJob.metric_definition_id)
        .where(
            SyncJob.organization_id == organization_id,
            SyncJob.destination == destination,
            SyncJob.status.in_([SyncStatus.PENDING, SyncStatus.MANUAL_REQUIRED, SyncStatus.FAILED]),
        )
        .order_by(SyncJob.created_at.desc())
        .limit(limit)
    )
    return [(j, p, m) for j, p, m in db.execute(stmt)]


def count_pending(db: Session, organization_id: uuid.UUID, *, destination: str = "futures") -> int:
    return (
        db.scalar(
            select(func.count(SyncJob.id)).where(
                SyncJob.organization_id == organization_id,
                SyncJob.destination == destination,
                SyncJob.status.in_(
                    [SyncStatus.PENDING, SyncStatus.MANUAL_REQUIRED, SyncStatus.FAILED]
                ),
            )
        )
        or 0
    )


def get_job(db: Session, organization_id: uuid.UUID, job_id: uuid.UUID) -> SyncJob | None:
    return db.scalars(
        select(SyncJob).where(SyncJob.id == job_id, SyncJob.organization_id == organization_id)
    ).first()


def mark_complete(db: Session, job: SyncJob, *, user_id: uuid.UUID | None) -> SyncJob:
    job.status = SyncStatus.SYNCED
    job.completed_at = datetime.now(UTC)
    job.completed_by_user_id = user_id
    job.attempt_count += 1
    job.last_error = None
    db.flush()
    return job


def source_record_event(db: Session, job: SyncJob) -> PersonalRecordEvent | None:
    if job.personal_record_event_id is None:
        return None
    return db.get(PersonalRecordEvent, job.personal_record_event_id)
