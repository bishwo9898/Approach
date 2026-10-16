"""Hitting session report service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from bsa.core.clock import today_in
from bsa.core.errors import NotFoundError
from bsa.db.models import Player, SessionVideo, TrainingSession
from bsa.db.repositories import hitting as hitting_repo
from bsa.db.repositories import sessions as sessions_repo
from bsa.domain.analytics import TimeRange, preceding_window, window_for
from bsa.domain.hitting_report import FacedPitch, HittingReport, build_report
from bsa.domain.progress import PeriodSummary, summarize_period


@dataclass(slots=True)
class SessionReport:
    player: Player
    session: TrainingSession
    report: HittingReport
    videos: list[SessionVideo]
    #: Every pitch the athlete faced, kept so the API can list the individual
    #: batted balls without recomputing them.
    faced: list[FacedPitch]

    @property
    def contact_pitches(self) -> list[FacedPitch]:
        return [p for p in self.faced if p.is_batted_ball]

    @property
    def opponent_name(self) -> str | None:
        value = self.session.session_metadata.get("opponent_name")
        return str(value) if value else None


def session_report(
    db: Session, organization_id: uuid.UUID, player: Player, session_id: uuid.UUID
) -> SessionReport:
    """Build one athlete's report for one session.

    The session is loaded organization-scoped, and the report is built only
    from pitches this athlete actually faced -- so a session containing several
    hitters yields a different report for each of them.
    """
    session = sessions_repo.get(db, organization_id, session_id)
    if session is None:
        raise NotFoundError("session not found")

    pitches = hitting_repo.faced_pitches(db, player.id, session.id)
    if not pitches:
        raise NotFoundError("this athlete did not bat in that session")

    return SessionReport(
        player=player,
        session=session,
        report=build_report(pitches),
        videos=hitting_repo.videos_for(db, player.id, session.id),
        faced=pitches,
    )


def latest_session_report(
    db: Session, organization_id: uuid.UUID, player: Player
) -> SessionReport | None:
    """The athlete's most recent batting session, or None if they have none."""
    recent = hitting_repo.sessions_batted_in(db, player.id, limit=1)
    if not recent:
        return None
    return session_report(db, organization_id, player, recent[0].id)


def period_summary(
    db: Session,
    organization_id: uuid.UUID,
    player: Player,
    *,
    time_range: TimeRange,
    timezone_name: str | None = None,
    today: date | None = None,
) -> PeriodSummary:
    """How the athlete has hit over a window of time.

    "Today" is the facility's today, not UTC's -- an evening session in New
    York is already tomorrow in UTC, and a window that silently excludes the
    session a coach just ran is worse than no window at all.

    All-time starts at the athlete's first session rather than at an arbitrary
    epoch, so the trend does not open with years of empty buckets.
    """
    anchor = today or today_in(timezone_name)

    earliest: date | None = None
    if time_range is TimeRange.ALL_TIME:
        known = hitting_repo.sessions_batted_in(db, player.id, limit=500)
        earliest = min((s.session_date for s in known), default=anchor)

    window = window_for(time_range, anchor, earliest)
    previous = preceding_window(window)

    return summarize_period(
        hitting_repo.sessions_with_pitches(db, player.id, start=window.start, end=window.end),
        hitting_repo.sessions_with_pitches(db, player.id, start=previous.start, end=previous.end),
        time_range=time_range,
        window=window,
    )
