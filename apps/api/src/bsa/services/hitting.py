"""Hitting session report service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from bsa.core.errors import NotFoundError
from bsa.db.models import Player, SessionVideo, TrainingSession
from bsa.db.repositories import hitting as hitting_repo
from bsa.db.repositories import sessions as sessions_repo
from bsa.domain.hitting_report import FacedPitch, HittingReport, build_report


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
