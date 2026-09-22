"""Athlete endpoints.

Every path here runs through `authorize_player`, which is what stops a PLAYER
from reading another athlete by editing the URL.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from bsa.api import mappers, schemas
from bsa.api.deps import (
    AdminPrincipal,
    CurrentPrincipal,
    DbSession,
    StaffPrincipal,
    authorize_player,
)
from bsa.core.errors import NotFoundError
from bsa.db.models import Player
from bsa.db.repositories import metrics as metrics_repo
from bsa.db.repositories import players as players_repo
from bsa.db.repositories import records as records_repo
from bsa.db.repositories import sessions as sessions_repo
from bsa.domain.analytics import TimeRange
from bsa.domain.enums import AuditAction
from bsa.services import analytics, audit

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=list[schemas.PlayerSummary])
def list_players(
    db: DbSession,
    principal: StaffPrincipal,
    q: str | None = Query(default=None, description="name search: first, last or preferred"),
    active_only: bool = True,
    limit: int = Query(default=50, le=200),
) -> list[schemas.PlayerSummary]:
    """Search the roster. Staff only -- a player has no roster."""
    found = players_repo.search(
        db, principal.organization_id, q, active_only=active_only, limit=limit
    )
    return [mappers.player_summary(p) for p in found]


@router.post("", response_model=schemas.PlayerSummary, status_code=201)
def create_player(
    payload: schemas.CreatePlayerIn, db: DbSession, principal: AdminPrincipal
) -> schemas.PlayerSummary:
    """Add an athlete to the roster.

    Creating an athlete deliberately does NOT map them to any vendor identity.
    That is a separate, explicit step, so a new roster entry can never silently
    adopt somebody else's TrackMan data.

    Duplicate names are allowed and not warned about: two athletes really can
    share a name, and blocking that would be worse than having two rows a coach
    can tell apart.
    """
    player = Player(
        organization_id=principal.organization_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        preferred_name=payload.preferred_name,
        position=payload.position,
        graduation_year=payload.graduation_year,
        bats=payload.bats,
        throws=payload.throws,
        active=True,
    )
    db.add(player)
    db.flush()

    audit.record(
        db,
        organization_id=principal.organization_id,
        action=AuditAction.PLAYER_CREATED,
        target_type="player",
        target_id=player.id,
        actor=principal.user,
        metadata={"display_name": player.display_name},
    )
    db.commit()
    return mappers.player_summary(player)


@router.get("/{player_id}", response_model=schemas.PlayerSummary)
def get_player(
    player_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal
) -> schemas.PlayerSummary:
    return mappers.player_summary(authorize_player(db, principal, player_id))


@router.get("/{player_id}/overview", response_model=schemas.PlayerOverviewOut)
def get_overview(
    player_id: uuid.UUID,
    db: DbSession,
    principal: CurrentPrincipal,
    time_range: TimeRange = Query(default=TimeRange.LAST_30, alias="range"),
    headline_only: bool = True,
) -> schemas.PlayerOverviewOut:
    """Headline metrics, their movement over the window, and current records."""
    player = authorize_player(db, principal, player_id)
    overview = analytics.player_overview(
        db,
        principal.organization_id,
        player,
        time_range=time_range,
        timezone_name=principal.organization.timezone,
        headline_only=headline_only,
    )
    counts = (0, 0)
    if overview.last_session:
        counts = sessions_repo.event_counts(db, [overview.last_session.id]).get(
            overview.last_session.id, (0, 0)
        )
    return mappers.player_overview(overview, time_range.value, last_session_counts=counts)


@router.get("/{player_id}/metrics/{metric_key}/series", response_model=schemas.MetricSeriesOut)
def get_metric_series(
    player_id: uuid.UUID,
    metric_key: str,
    db: DbSession,
    principal: CurrentPrincipal,
    time_range: TimeRange = Query(default=TimeRange.LAST_90, alias="range"),
) -> schemas.MetricSeriesOut:
    """Session-by-session progression for one metric."""
    player = authorize_player(db, principal, player_id)
    definition = metrics_repo.get_definition_by_key(db, principal.organization_id, metric_key)
    if definition is None:
        raise NotFoundError(f"no metric with key {metric_key!r}")

    points = analytics.metric_series(
        db,
        player.id,
        definition,
        time_range=time_range,
        timezone_name=principal.organization.timezone,
    )
    return schemas.MetricSeriesOut(
        definition=mappers.metric_definition(definition),
        time_range=time_range.value,
        points=[
            schemas.MetricSeriesPointOut(
                session_id=p.session_id,
                observed_on=p.observed_on,
                value=p.value,
                sample_size=p.sample_size,
                source_status=p.source_status,
            )
            for p in points
        ],
    )


@router.get("/{player_id}/prs", response_model=list[schemas.PersonalRecordOut])
def get_personal_records(
    player_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal
) -> list[schemas.PersonalRecordOut]:
    player = authorize_player(db, principal, player_id)
    out: list[schemas.PersonalRecordOut] = []
    for record in records_repo.list_current_for_player(db, player.id):
        definition = metrics_repo.get_definition(
            db, principal.organization_id, record.metric_definition_id
        )
        if definition is not None:
            out.append(mappers.personal_record(record, definition))
    return out


@router.get(
    "/{player_id}/prs/{metric_key}/history",
    response_model=list[schemas.PersonalRecordEventOut],
)
def get_record_history(
    player_id: uuid.UUID, metric_key: str, db: DbSession, principal: CurrentPrincipal
) -> list[schemas.PersonalRecordEventOut]:
    """The full progression -- when each record was set, and by how much."""
    player = authorize_player(db, principal, player_id)
    definition = metrics_repo.get_definition_by_key(db, principal.organization_id, metric_key)
    if definition is None:
        raise NotFoundError(f"no metric with key {metric_key!r}")
    return [
        mappers.record_event(event, player, definition)
        for event in records_repo.history_for_player_metric(db, player.id, definition.id)
    ]


@router.get("/{player_id}/sessions", response_model=list[schemas.SessionOut])
def get_sessions(
    player_id: uuid.UUID,
    db: DbSession,
    principal: CurrentPrincipal,
    limit: int = Query(default=20, le=100),
) -> list[schemas.SessionOut]:
    player = authorize_player(db, principal, player_id)
    found = sessions_repo.list_for_player(db, player.id, limit=limit)
    counts = sessions_repo.event_counts(db, [s.id for s in found])
    return [
        mappers.session_out(
            s, pitch_count=counts.get(s.id, (0, 0))[0], hit_count=counts.get(s.id, (0, 0))[1]
        )
        for s in found
    ]
