"""Personal record persistence.

`replace_progression` is where the PR engine's purity is cashed in: it takes a
freshly computed progression and reconciles the database to match it, rather
than appending to whatever was there before.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bsa.db.models import MetricDefinition, PersonalRecord, PersonalRecordEvent, Player
from bsa.domain.pr_engine import RecordBreak


def replace_progression(
    db: Session,
    *,
    organization_id: uuid.UUID,
    player_id: uuid.UUID,
    metric_definition_id: uuid.UUID,
    breaks: Sequence[RecordBreak],
    calculation_version: int,
) -> list[PersonalRecordEvent]:
    """Reconcile stored PR history to `breaks`. Returns newly created events.

    Three cases, all handled by comparing against what is already stored:

      * A break we already recorded for that session -- updated in place. The
        coach is not notified twice for the same achievement, which is the
        idempotency requirement.
      * A break we had recorded that the new data no longer supports -- marked
        superseded rather than deleted, because the audit trail must show what
        we told the coach at the time.
      * A genuinely new break -- inserted and returned, so callers can queue
        downstream work such as a Futures sync job.
    """
    existing = {
        event.session_id: event
        for event in db.scalars(
            select(PersonalRecordEvent).where(
                PersonalRecordEvent.player_id == player_id,
                PersonalRecordEvent.metric_definition_id == metric_definition_id,
            )
        )
    }

    now = datetime.now(UTC)
    created: list[PersonalRecordEvent] = []
    kept: set[uuid.UUID] = set()

    for record_break in breaks:
        kept.add(record_break.session_id)
        event = existing.get(record_break.session_id)
        if event is None:
            event = PersonalRecordEvent(
                organization_id=organization_id,
                player_id=player_id,
                metric_definition_id=metric_definition_id,
                session_id=record_break.session_id,
                previous_value=record_break.previous_value,
                new_value=record_break.new_value,
                delta=record_break.delta,
                sample_size=record_break.sample_size,
                achieved_on=record_break.achieved_on,
                achieved_at=record_break.achieved_at,
                source_status=record_break.source_status,
                calculation_version=calculation_version,
                context=record_break.context,
            )
            db.add(event)
            created.append(event)
            continue

        event.previous_value = record_break.previous_value
        event.new_value = record_break.new_value
        event.delta = record_break.delta
        event.sample_size = record_break.sample_size
        event.achieved_on = record_break.achieved_on
        event.achieved_at = record_break.achieved_at
        event.source_status = record_break.source_status
        event.calculation_version = calculation_version
        event.context = record_break.context
        # A previously superseded break that the corrected data supports again
        # is reinstated rather than left tombstoned.
        event.superseded_at = None
        event.superseded_reason = None

    for session_id, event in existing.items():
        if session_id not in kept and event.superseded_at is None:
            event.superseded_at = now
            event.superseded_reason = (
                "recalculated from corrected source data; this value is no longer a record"
            )

    db.flush()
    _sync_current_record(
        db,
        organization_id=organization_id,
        player_id=player_id,
        metric_definition_id=metric_definition_id,
        breaks=breaks,
        calculation_version=calculation_version,
    )
    return created


def _sync_current_record(
    db: Session,
    *,
    organization_id: uuid.UUID,
    player_id: uuid.UUID,
    metric_definition_id: uuid.UUID,
    breaks: Sequence[RecordBreak],
    calculation_version: int,
) -> None:
    """Project the standing record from the last break in the progression."""
    current = db.scalars(
        select(PersonalRecord).where(
            PersonalRecord.player_id == player_id,
            PersonalRecord.metric_definition_id == metric_definition_id,
        )
    ).first()

    # A hand-pinned record is left alone. An admin overrode the engine on
    # purpose, and silently recomputing over that decision would be worse than
    # a stale number.
    if current is not None and current.is_manual_override:
        return

    if not breaks:
        if current is not None:
            db.delete(current)
        return

    best = breaks[-1]
    if current is None:
        current = PersonalRecord(
            organization_id=organization_id,
            player_id=player_id,
            metric_definition_id=metric_definition_id,
        )
        db.add(current)

    current.value = best.new_value
    current.sample_size = best.sample_size
    current.session_id = best.session_id
    current.achieved_on = best.achieved_on
    current.achieved_at = best.achieved_at
    current.source_status = best.source_status
    current.calculation_version = calculation_version
    current.context = best.context
    db.flush()


def get_current(
    db: Session, player_id: uuid.UUID, metric_definition_id: uuid.UUID
) -> PersonalRecord | None:
    return db.scalars(
        select(PersonalRecord).where(
            PersonalRecord.player_id == player_id,
            PersonalRecord.metric_definition_id == metric_definition_id,
        )
    ).first()


def list_current_for_player(db: Session, player_id: uuid.UUID) -> list[PersonalRecord]:
    return list(
        db.scalars(
            select(PersonalRecord)
            .where(PersonalRecord.player_id == player_id)
            .order_by(PersonalRecord.achieved_on.desc())
        )
    )


def history_for_player_metric(
    db: Session, player_id: uuid.UUID, metric_definition_id: uuid.UUID
) -> list[PersonalRecordEvent]:
    """Full progression, oldest first, excluding superseded claims."""
    return list(
        db.scalars(
            select(PersonalRecordEvent)
            .where(
                PersonalRecordEvent.player_id == player_id,
                PersonalRecordEvent.metric_definition_id == metric_definition_id,
                PersonalRecordEvent.superseded_at.is_(None),
            )
            .order_by(PersonalRecordEvent.achieved_on)
        )
    )


def recent_events(
    db: Session,
    organization_id: uuid.UUID,
    *,
    since: date | None = None,
    limit: int = 25,
) -> list[tuple[PersonalRecordEvent, Player, MetricDefinition]]:
    """The coach dashboard's PR feed, joined in one query."""
    stmt = (
        select(PersonalRecordEvent, Player, MetricDefinition)
        .join(Player, Player.id == PersonalRecordEvent.player_id)
        .join(
            MetricDefinition,
            MetricDefinition.id == PersonalRecordEvent.metric_definition_id,
        )
        .where(
            PersonalRecordEvent.organization_id == organization_id,
            PersonalRecordEvent.superseded_at.is_(None),
        )
    )
    if since:
        stmt = stmt.where(PersonalRecordEvent.achieved_on >= since)
    stmt = stmt.order_by(
        PersonalRecordEvent.achieved_on.desc(), PersonalRecordEvent.created_at.desc()
    ).limit(limit)
    return [(e, p, m) for e, p, m in db.execute(stmt)]


def count_events_on(db: Session, organization_id: uuid.UUID, on_date: date) -> int:
    return (
        db.scalar(
            select(func.count(PersonalRecordEvent.id)).where(
                PersonalRecordEvent.organization_id == organization_id,
                PersonalRecordEvent.achieved_on == on_date,
                PersonalRecordEvent.superseded_at.is_(None),
            )
        )
        or 0
    )
