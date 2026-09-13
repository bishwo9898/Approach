"""Session and event persistence.

The upserts here are what make ingestion safe to re-run. Nothing in this module
appends blindly: every write targets a natural key that identifies the same
real-world thing across imports.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from bsa.db.models import HitEvent, PitchEvent, TrainingSession
from bsa.domain.enums import SourceStatus


def get_by_external(
    db: Session, organization_id: uuid.UUID, provider: str, external_session_id: str
) -> TrainingSession | None:
    return db.scalars(
        select(TrainingSession).where(
            TrainingSession.organization_id == organization_id,
            TrainingSession.provider == provider,
            TrainingSession.external_session_id == external_session_id,
        )
    ).first()


def get(db: Session, organization_id: uuid.UUID, session_id: uuid.UUID) -> TrainingSession | None:
    return db.scalars(
        select(TrainingSession).where(
            TrainingSession.id == session_id,
            TrainingSession.organization_id == organization_id,
        )
    ).first()


def upsert(
    db: Session,
    organization_id: uuid.UUID,
    provider: str,
    external_session_id: str,
    *,
    session_date: date,
    source_status: SourceStatus,
    started_at: datetime | None,
    ended_at: datetime | None,
    session_type: str | None,
    venue: str | None,
    raw_import_id: uuid.UUID | None,
    metadata: dict[str, Any],
) -> tuple[TrainingSession, bool]:
    """Create or update a session. Returns (session, created).

    A verified republish updates the existing row in place -- there is exactly
    one row per real session, ever.

    A VERIFIED session is never downgraded back to PRELIMINARY: if a late
    preliminary file arrives after verification, the verified values stand.
    """
    existing = get_by_external(db, organization_id, provider, external_session_id)
    now = datetime.now(UTC)

    if existing is None:
        session = TrainingSession(
            organization_id=organization_id,
            provider=provider,
            external_session_id=external_session_id,
            session_date=session_date,
            source_status=source_status,
            started_at=started_at,
            ended_at=ended_at,
            session_type=session_type,
            venue=venue,
            imported_at=now,
            verified_at=now if source_status is SourceStatus.VERIFIED else None,
            raw_import_id=raw_import_id,
            session_metadata=metadata,
        )
        db.add(session)
        db.flush()
        return session, True

    promoting = (
        source_status is SourceStatus.VERIFIED
        and existing.source_status is not SourceStatus.VERIFIED
    )
    if existing.source_status is not SourceStatus.VERIFIED:
        existing.source_status = source_status
    if promoting:
        existing.verified_at = now

    existing.session_date = session_date
    existing.started_at = started_at or existing.started_at
    existing.ended_at = ended_at or existing.ended_at
    existing.session_type = session_type or existing.session_type
    existing.venue = venue or existing.venue
    existing.imported_at = now
    existing.raw_import_id = raw_import_id
    existing.session_metadata = {**existing.session_metadata, **metadata}
    db.flush()
    return existing, False


def upsert_pitch_events(db: Session, rows: Sequence[dict[str, Any]]) -> int:
    """Bulk upsert on (session_id, external_event_id)."""
    if not rows:
        return 0
    stmt = insert(PitchEvent).values(list(rows))
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in PitchEvent.__table__.columns
        if c.name not in ("id", "session_id", "external_event_id", "created_at")
    }
    stmt = stmt.on_conflict_do_update(constraint="uq_pitch_events_session_event", set_=update_cols)
    db.execute(stmt)
    return len(rows)


def upsert_hit_events(db: Session, rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    stmt = insert(HitEvent).values(list(rows))
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in HitEvent.__table__.columns
        if c.name not in ("id", "session_id", "external_event_id", "created_at")
    }
    stmt = stmt.on_conflict_do_update(constraint="uq_hit_events_session_event", set_=update_cols)
    db.execute(stmt)
    return len(rows)


def prune_events_not_in(
    db: Session, session_id: uuid.UUID, pitch_ids: set[str], hit_ids: set[str]
) -> int:
    """Remove events the authoritative payload no longer contains.

    Only called when the payload describes a whole session. A verified
    republish that drops three mis-tracked pitches must actually drop them,
    otherwise the stale readings keep feeding metrics and can hold a personal
    record that the corrected data does not support.
    """
    removed = 0
    pitch_stmt = delete(PitchEvent).where(PitchEvent.session_id == session_id)
    if pitch_ids:
        pitch_stmt = pitch_stmt.where(PitchEvent.external_event_id.not_in(pitch_ids))
    removed += cast("CursorResult[Any]", db.execute(pitch_stmt)).rowcount or 0

    hit_stmt = delete(HitEvent).where(HitEvent.session_id == session_id)
    if hit_ids:
        hit_stmt = hit_stmt.where(HitEvent.external_event_id.not_in(hit_ids))
    removed += cast("CursorResult[Any]", db.execute(hit_stmt)).rowcount or 0
    return removed


def link_hits_to_pitches(db: Session, session_id: uuid.UUID) -> None:
    """Attach batted balls to the pitch they came off, where ids line up."""
    pitch_ids = {
        external_id: pid
        for pid, external_id in db.execute(
            select(PitchEvent.id, PitchEvent.external_event_id).where(
                PitchEvent.session_id == session_id
            )
        )
    }
    if not pitch_ids:
        return
    for hit in db.scalars(select(HitEvent).where(HitEvent.session_id == session_id)):
        match = pitch_ids.get(hit.external_event_id)
        if match and hit.pitch_event_id != match:
            hit.pitch_event_id = match


def player_ids_in_session(db: Session, session_id: uuid.UUID) -> set[uuid.UUID]:
    """Every athlete with at least one event in the session."""
    pitchers = db.scalars(
        select(PitchEvent.player_id).where(PitchEvent.session_id == session_id).distinct()
    )
    batters = db.scalars(
        select(HitEvent.player_id).where(HitEvent.session_id == session_id).distinct()
    )
    return set(pitchers) | set(batters)


def _event_dicts(
    rows: Sequence[Any], numeric_fields: Sequence[str], text_fields: Sequence[str]
) -> list[dict[str, Any]]:
    """Flatten ORM events into the plain dicts the metric engine consumes.

    Training-context keys are exposed as `ctx.<key>` so a metric can filter on
    drill or intent without the engine knowing anything about JSONB.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {f: getattr(row, f) for f in numeric_fields}
        item.update({f: getattr(row, f) for f in text_fields})
        for key, value in (row.training_context or {}).items():
            item[f"ctx.{key}"] = value
        out.append(item)
    return out


PITCH_NUMERIC_FIELDS = (
    "velocity_mph",
    "spin_rate_rpm",
    "spin_axis_deg",
    "horizontal_break_in",
    "vertical_break_in",
    "release_height_ft",
    "release_side_ft",
    "extension_ft",
    "plate_location_height_ft",
    "plate_location_side_ft",
    "vertical_approach_angle_deg",
    "horizontal_approach_angle_deg",
)
PITCH_TEXT_FIELDS = ("pitch_type", "auto_pitch_type", "pitch_call", "is_strike")

HIT_NUMERIC_FIELDS = (
    "exit_velocity_mph",
    "launch_angle_deg",
    "launch_direction_deg",
    "distance_ft",
    "hang_time_s",
    "hit_spin_rate_rpm",
)
HIT_TEXT_FIELDS = ("batted_ball_type",)


def pitch_events_for(
    db: Session, player_id: uuid.UUID, session_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(PitchEvent).where(
                PitchEvent.player_id == player_id, PitchEvent.session_id == session_id
            )
        )
    )
    return _event_dicts(rows, PITCH_NUMERIC_FIELDS, PITCH_TEXT_FIELDS)


def hit_events_for(
    db: Session, player_id: uuid.UUID, session_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(HitEvent).where(
                HitEvent.player_id == player_id, HitEvent.session_id == session_id
            )
        )
    )
    return _event_dicts(rows, HIT_NUMERIC_FIELDS, HIT_TEXT_FIELDS)


def list_for_player(
    db: Session, player_id: uuid.UUID, *, limit: int = 20, since: date | None = None
) -> list[TrainingSession]:
    """Sessions an athlete actually appears in, most recent first."""
    subquery = (
        select(PitchEvent.session_id)
        .where(PitchEvent.player_id == player_id)
        .union(select(HitEvent.session_id).where(HitEvent.player_id == player_id))
    )
    stmt = select(TrainingSession).where(TrainingSession.id.in_(subquery))
    if since:
        stmt = stmt.where(TrainingSession.session_date >= since)
    return list(db.scalars(stmt.order_by(TrainingSession.session_date.desc()).limit(limit)))


def list_for_org(
    db: Session,
    organization_id: uuid.UUID,
    *,
    on_date: date | None = None,
    since: date | None = None,
    limit: int = 50,
) -> list[TrainingSession]:
    stmt = select(TrainingSession).where(TrainingSession.organization_id == organization_id)
    if on_date:
        stmt = stmt.where(TrainingSession.session_date == on_date)
    if since:
        stmt = stmt.where(TrainingSession.session_date >= since)
    return list(db.scalars(stmt.order_by(TrainingSession.session_date.desc()).limit(limit)))


def event_counts(db: Session, session_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    """(pitch count, hit count) per session, in two queries rather than 2N."""
    if not session_ids:
        return {}
    counts: dict[uuid.UUID, tuple[int, int]] = dict.fromkeys(session_ids, (0, 0))
    for sid, n in db.execute(
        select(PitchEvent.session_id, func.count(PitchEvent.id))
        .where(PitchEvent.session_id.in_(session_ids))
        .group_by(PitchEvent.session_id)
    ):
        counts[sid] = (n, counts[sid][1])
    for sid, n in db.execute(
        select(HitEvent.session_id, func.count(HitEvent.id))
        .where(HitEvent.session_id.in_(session_ids))
        .group_by(HitEvent.session_id)
    ):
        counts[sid] = (counts[sid][0], n)
    return counts
