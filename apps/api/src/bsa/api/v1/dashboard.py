"""Coach dashboard endpoints: today's activity, the PR feed, data health."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Query

from bsa.api import mappers, schemas
from bsa.api.deps import DbSession, StaffPrincipal
from bsa.core.clock import today_in
from bsa.db.repositories import records as records_repo
from bsa.db.repositories import sessions as sessions_repo
from bsa.services import analytics

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/today", response_model=schemas.TodaySnapshotOut)
def today(
    db: DbSession,
    principal: StaffPrincipal,
    on_date: date | None = Query(default=None, alias="date"),
) -> schemas.TodaySnapshotOut:
    snapshot = analytics.today_snapshot(
        db,
        principal.organization_id,
        on_date=on_date,
        timezone_name=principal.organization.timezone,
    )
    return schemas.TodaySnapshotOut(
        on_date=snapshot.on_date,
        athletes_trained=snapshot.athletes_trained,
        sessions=snapshot.sessions,
        tracked_events=snapshot.tracked_events,
        new_personal_records=snapshot.new_personal_records,
    )


@router.get("/prs/recent", response_model=list[schemas.PersonalRecordEventOut])
def recent_records(
    db: DbSession,
    principal: StaffPrincipal,
    days: int = Query(default=14, ge=1, le=365),
    limit: int = Query(default=25, le=100),
) -> list[schemas.PersonalRecordEventOut]:
    """Newest records across the organization -- the feed a coach scans first."""
    since = today_in(principal.organization.timezone) - timedelta(days=days)
    return [
        mappers.record_event(event, player, definition)
        for event, player, definition in records_repo.recent_events(
            db, principal.organization_id, since=since, limit=limit
        )
    ]


@router.get("/sessions", response_model=list[schemas.SessionOut])
def list_sessions(
    db: DbSession,
    principal: StaffPrincipal,
    on_date: date | None = Query(default=None, alias="date"),
    limit: int = Query(default=50, le=200),
) -> list[schemas.SessionOut]:
    found = sessions_repo.list_for_org(db, principal.organization_id, on_date=on_date, limit=limit)
    counts = sessions_repo.event_counts(db, [s.id for s in found])
    return [
        mappers.session_out(
            s, pitch_count=counts.get(s.id, (0, 0))[0], hit_count=counts.get(s.id, (0, 0))[1]
        )
        for s in found
    ]


@router.get("/integrations/status", response_model=schemas.IntegrationHealthOut)
def integration_status(db: DbSession, principal: StaffPrincipal) -> schemas.IntegrationHealthOut:
    """Operational health. Broken automation is shown, never hidden."""
    health = analytics.integration_health(db, principal.organization_id)
    return schemas.IntegrationHealthOut(
        provider=health.provider,
        last_successful_import_at=health.last_successful_import_at,
        last_import_status=health.last_import_status,
        failed_imports_7d=health.failed_imports_7d,
        sessions_awaiting_verification=health.sessions_awaiting_verification,
        unresolved_players=health.unresolved_players,
        futures_updates_pending=health.futures_updates_pending,
    )
