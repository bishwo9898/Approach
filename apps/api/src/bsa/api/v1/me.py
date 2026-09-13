"""Endpoints scoped to the caller themselves.

A player's dashboard uses these rather than /players/{id}, so the client never
needs to know or send an athlete id at all.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from bsa.api import mappers, schemas
from bsa.api.deps import CurrentPrincipal, DbSession, current_player
from bsa.db.repositories import metrics as metrics_repo
from bsa.db.repositories import records as records_repo
from bsa.db.repositories import sessions as sessions_repo
from bsa.domain.analytics import TimeRange
from bsa.services import analytics

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=schemas.CurrentUser)
def get_me(db: DbSession, principal: CurrentPrincipal) -> schemas.CurrentUser:
    return schemas.CurrentUser(
        id=principal.user.id,
        display_name=principal.user.display_name,
        email=principal.user.email,
        role=principal.role.value,
        organization_id=principal.organization.id,
        organization_name=principal.organization.name,
        player_id=principal.user.player_id,
    )


@router.get("/overview", response_model=schemas.PlayerOverviewOut)
def my_overview(
    db: DbSession,
    principal: CurrentPrincipal,
    time_range: TimeRange = Query(default=TimeRange.LAST_30, alias="range"),
) -> schemas.PlayerOverviewOut:
    player = current_player(db, principal)
    overview = analytics.player_overview(
        db,
        principal.organization_id,
        player,
        time_range=time_range,
        timezone_name=principal.organization.timezone,
    )
    counts = (0, 0)
    if overview.last_session:
        counts = sessions_repo.event_counts(db, [overview.last_session.id]).get(
            overview.last_session.id, (0, 0)
        )
    return mappers.player_overview(overview, time_range.value, last_session_counts=counts)


@router.get("/prs", response_model=list[schemas.PersonalRecordOut])
def my_records(db: DbSession, principal: CurrentPrincipal) -> list[schemas.PersonalRecordOut]:
    player = current_player(db, principal)
    out: list[schemas.PersonalRecordOut] = []
    for record in records_repo.list_current_for_player(db, player.id):
        definition = metrics_repo.get_definition(
            db, principal.organization_id, record.metric_definition_id
        )
        if definition is not None:
            out.append(mappers.personal_record(record, definition))
    return out


@router.get("/sessions", response_model=list[schemas.SessionOut])
def my_sessions(
    db: DbSession, principal: CurrentPrincipal, limit: int = Query(default=20, le=100)
) -> list[schemas.SessionOut]:
    player = current_player(db, principal)
    found = sessions_repo.list_for_player(db, player.id, limit=limit)
    counts = sessions_repo.event_counts(db, [s.id for s in found])
    return [
        mappers.session_out(
            s, pitch_count=counts.get(s.id, (0, 0))[0], hit_count=counts.get(s.id, (0, 0))[1]
        )
        for s in found
    ]
