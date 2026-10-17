"""Hitting session reports.

The athlete-facing surface. Every route resolves the athlete through
`authorize_player`, so a player reaches only their own report and a coach
reaches anyone in their organization -- decided on the server, as everywhere
else.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from bsa.api import mappers, schemas
from bsa.api.deps import (
    CurrentPrincipal,
    DbSession,
    StaffPrincipal,
    authorize_player,
    current_player,
)
from bsa.core.config import Settings, get_settings
from bsa.core.errors import NotFoundError
from bsa.db.models import SessionVideo
from bsa.db.repositories import hitting as hitting_repo
from bsa.domain.analytics import TimeRange
from bsa.integrations.media import get_media_store
from bsa.services import hitting

router = APIRouter(tags=["hitting"])

CurrentSettings = Annotated[Settings, Depends(get_settings)]


def _summaries(
    db: DbSession, principal: CurrentPrincipal, player_id: uuid.UUID
) -> list[schemas.HittingSessionSummaryOut]:
    out: list[schemas.HittingSessionSummaryOut] = []
    for session in hitting_repo.sessions_batted_in(db, player_id):
        faced = hitting_repo.faced_pitches(db, player_id, session.id)
        exit_velocities = [p.exit_velocity_mph for p in faced if p.exit_velocity_mph is not None]
        out.append(
            schemas.HittingSessionSummaryOut(
                session_id=session.id,
                session_date=session.session_date,
                session_type=session.session_type,
                opponent_name=session.session_metadata.get("opponent_name"),
                pitches_faced=len(faced),
                batted_balls=len(exit_velocities),
                best_exit_velocity_mph=(
                    round(max(exit_velocities), 1) if exit_velocities else None
                ),
            )
        )
    return out


# -- the athlete's own view --------------------------------------------------


@router.get("/me/hitting/sessions", response_model=list[schemas.HittingSessionSummaryOut])
def my_hitting_sessions(
    db: DbSession, principal: CurrentPrincipal
) -> list[schemas.HittingSessionSummaryOut]:
    return _summaries(db, principal, current_player(db, principal).id)


@router.get("/me/hitting/latest", response_model=schemas.HittingSessionReportOut)
def my_latest_session(
    db: DbSession, principal: CurrentPrincipal, settings: CurrentSettings
) -> schemas.HittingSessionReportOut:
    """The athlete's most recent batting session.

    The player dashboard opens straight to this -- there is nothing to choose
    from until they have batted more than once.
    """
    player = current_player(db, principal)
    result = hitting.latest_session_report(
        db, principal.organization_id, player, media_store=get_media_store(settings)
    )
    if result is None:
        raise NotFoundError("no batting sessions have been imported for you yet")
    return mappers.hitting_report(result)


@router.get("/me/hitting/sessions/{session_id}", response_model=schemas.HittingSessionReportOut)
def my_session(
    session_id: uuid.UUID,
    db: DbSession,
    principal: CurrentPrincipal,
    settings: CurrentSettings,
) -> schemas.HittingSessionReportOut:
    player = current_player(db, principal)
    return mappers.hitting_report(
        hitting.session_report(
            db,
            principal.organization_id,
            player,
            session_id,
            media_store=get_media_store(settings),
        )
    )


@router.get("/me/hitting/summary", response_model=schemas.HittingPeriodSummaryOut)
def my_period_summary(
    db: DbSession,
    principal: CurrentPrincipal,
    time_range: TimeRange = Query(default=TimeRange.LAST_30, alias="range"),
) -> schemas.HittingPeriodSummaryOut:
    """How the athlete has hit over a window, rather than in one session.

    Always answers, including when the window holds nothing. An athlete who has
    not batted this month gets `has_data=false` and null measurements, not a
    404 -- the question "how did this month go?" has an answer, and the answer
    is "you did not bat".
    """
    player = current_player(db, principal)
    return mappers.hitting_period(
        player,
        hitting.period_summary(
            db,
            principal.organization_id,
            player,
            time_range=time_range,
            timezone_name=principal.organization.timezone,
        ),
    )


# -- the coach's view of an athlete ------------------------------------------


@router.get(
    "/players/{player_id}/hitting/sessions",
    response_model=list[schemas.HittingSessionSummaryOut],
)
def hitting_sessions(
    player_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal
) -> list[schemas.HittingSessionSummaryOut]:
    player = authorize_player(db, principal, player_id)
    return _summaries(db, principal, player.id)


@router.get(
    "/players/{player_id}/hitting/latest",
    response_model=schemas.HittingSessionReportOut,
)
def latest_hitting_session(
    player_id: uuid.UUID,
    db: DbSession,
    principal: CurrentPrincipal,
    settings: CurrentSettings,
) -> schemas.HittingSessionReportOut:
    player = authorize_player(db, principal, player_id)
    result = hitting.latest_session_report(
        db, principal.organization_id, player, media_store=get_media_store(settings)
    )
    if result is None:
        raise NotFoundError("no batting sessions have been imported for this athlete")
    return mappers.hitting_report(result)


@router.get(
    "/players/{player_id}/hitting/sessions/{session_id}",
    response_model=schemas.HittingSessionReportOut,
)
def hitting_session(
    player_id: uuid.UUID,
    session_id: uuid.UUID,
    db: DbSession,
    principal: CurrentPrincipal,
    settings: CurrentSettings,
) -> schemas.HittingSessionReportOut:
    player = authorize_player(db, principal, player_id)
    return mappers.hitting_report(
        hitting.session_report(
            db,
            principal.organization_id,
            player,
            session_id,
            media_store=get_media_store(settings),
        )
    )


@router.get(
    "/players/{player_id}/hitting/summary",
    response_model=schemas.HittingPeriodSummaryOut,
)
def hitting_period_summary(
    player_id: uuid.UUID,
    db: DbSession,
    principal: CurrentPrincipal,
    time_range: TimeRange = Query(default=TimeRange.LAST_30, alias="range"),
) -> schemas.HittingPeriodSummaryOut:
    player = authorize_player(db, principal, player_id)
    return mappers.hitting_period(
        player,
        hitting.period_summary(
            db,
            principal.organization_id,
            player,
            time_range=time_range,
            timezone_name=principal.organization.timezone,
        ),
    )


# -- video -------------------------------------------------------------------


@router.post(
    "/players/{player_id}/hitting/sessions/{session_id}/videos",
    response_model=schemas.SessionVideoOut,
    status_code=201,
)
def add_video(
    player_id: uuid.UUID,
    session_id: uuid.UUID,
    payload: schemas.AddSessionVideoIn,
    db: DbSession,
    principal: StaffPrincipal,
) -> schemas.SessionVideoOut:
    """Attach a video of this athlete's session.

    Staff only, and the link must be http(s) -- this is rendered on a page shown
    to a minor, so an unchecked URL would be a stored scripting hole.
    """
    player = authorize_player(db, principal, player_id)
    # Reuses the report loader purely for its checks: the session exists, is in
    # this organization, and this athlete actually batted in it. No media store
    # is needed -- the existing videos are not being read here.
    hitting.session_report(db, principal.organization_id, player, session_id)

    video = SessionVideo(
        organization_id=principal.organization_id,
        session_id=session_id,
        player_id=player.id,
        title=payload.title.strip(),
        url=payload.url,
        external_event_id=payload.external_event_id,
        note=payload.note,
        created_by_user_id=principal.user.id,
    )
    db.add(video)
    db.commit()
    return schemas.SessionVideoOut(
        id=video.id,
        title=video.title,
        url=video.url,
        external_event_id=video.external_event_id,
        note=video.note,
    )
