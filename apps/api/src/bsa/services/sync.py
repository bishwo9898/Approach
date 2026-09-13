"""Outbound synchronization to external systems.

Today this only queues work for a human, because no Futures ingestion method is
confirmed. The queue is still the useful half: it tells the coach exactly which
numbers changed and what to type, which is the part they currently do by hand.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from bsa.core.logging import get_logger
from bsa.core.units import Unit, UnitConversionError, convert
from bsa.db.models import PersonalRecordEvent, SyncJob, User
from bsa.db.repositories import metrics as metrics_repo
from bsa.db.repositories import sync as sync_repo
from bsa.domain.enums import AuditAction, SyncStatus
from bsa.integrations.futures.base import FuturesProvider, MetricPush
from bsa.services import audit

log = get_logger(__name__)

DESTINATION_FUTURES = "futures"


def queue_for_record_events(
    db: Session,
    *,
    organization_id: uuid.UUID,
    events: list[PersonalRecordEvent],
    destination: str = DESTINATION_FUTURES,
) -> list[SyncJob]:
    """Queue a push for each new record that has a destination mapping.

    Metrics with no mapping are skipped silently: not every metric we track is
    one the facility records externally.
    """
    jobs: list[SyncJob] = []

    for event in events:
        mapping = sync_repo.mapping_for_metric(
            db, organization_id, event.metric_definition_id, destination
        )
        if mapping is None:
            continue

        definition = metrics_repo.get_definition(db, organization_id, event.metric_definition_id)
        if definition is None:  # pragma: no cover -- FK makes this unreachable
            continue

        value, unit = _convert_for_destination(
            event.new_value, definition.unit, mapping.destination_unit
        )
        if value is None:
            log.error(
                "sync.unit_conversion_failed",
                metric=definition.key,
                from_unit=definition.unit,
                to_unit=mapping.destination_unit,
            )
            continue

        jobs.append(
            sync_repo.upsert_job(
                db,
                organization_id=organization_id,
                player_id=event.player_id,
                metric_definition_id=event.metric_definition_id,
                personal_record_event_id=event.id,
                destination=destination,
                destination_field=mapping.destination_field,
                value=round(value, mapping.destination_precision),
                unit=unit,
            )
        )

    db.flush()
    return jobs


def _convert_for_destination(
    value: float, source_unit: str, destination_unit: str | None
) -> tuple[float | None, str]:
    """Convert into the destination's unit, or fail loudly.

    A silently unconverted value is how a 137 km/h fastball becomes "137 mph" in
    someone else's system.
    """
    if not destination_unit or destination_unit == source_unit:
        return value, source_unit
    try:
        target = Unit(destination_unit)
    except ValueError:
        return None, source_unit
    try:
        return convert(value, source_unit, target), destination_unit
    except UnitConversionError:
        return None, source_unit


def attempt_push(
    db: Session, job: SyncJob, provider: FuturesProvider, external_player_id: str
) -> SyncJob:
    """Try to deliver one queued value.

    With the manual provider this always lands on MANUAL_REQUIRED, which is the
    honest outcome rather than a failure.
    """
    definition = metrics_repo.get_definition(db, job.organization_id, job.metric_definition_id)
    job.attempt_count += 1
    job.last_attempted_at = datetime.now(UTC)

    result = provider.update_player_metric(
        MetricPush(
            external_player_id=external_player_id,
            destination_field=job.destination_field,
            value=job.value,
            unit=job.unit,
            metric_key=definition.key if definition else "",
        )
    )

    if result.accepted:
        job.status = SyncStatus.SYNCED
        job.completed_at = datetime.now(UTC)
        job.last_error = None
    elif result.requires_manual_entry:
        job.status = SyncStatus.MANUAL_REQUIRED
        job.last_error = result.message
    else:
        job.status = SyncStatus.FAILED
        job.last_error = result.message

    db.flush()
    return job


def mark_manually_updated(
    db: Session, *, organization_id: uuid.UUID, job: SyncJob, actor: User
) -> SyncJob:
    """Record that a coach entered the value by hand.

    Audited: this is a human asserting that an external system now matches ours,
    and it is the only evidence we will ever have that it happened.
    """
    sync_repo.mark_complete(db, job, user_id=actor.id)
    audit.record(
        db,
        organization_id=organization_id,
        action=AuditAction.FUTURES_SYNC_MANUALLY_CONFIRMED,
        target_type="sync_job",
        target_id=job.id,
        actor=actor,
        metadata={
            "destination": job.destination,
            "destination_field": job.destination_field,
            "value": job.value,
            "unit": job.unit,
            "player_id": str(job.player_id),
        },
    )
    return job
