"""Reads for the hitting session report."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from bsa.db.models import HitEvent, PitchEvent, SessionVideo, TrainingSession
from bsa.domain.hitting_report import FacedPitch


def sessions_batted_in(
    db: Session, player_id: uuid.UUID, *, limit: int = 50
) -> list[TrainingSession]:
    """Sessions where this athlete faced pitches, most recent first."""
    faced = select(PitchEvent.session_id).where(PitchEvent.batter_id == player_id)
    return list(
        db.scalars(
            select(TrainingSession)
            .where(TrainingSession.id.in_(faced))
            .order_by(TrainingSession.session_date.desc())
            .limit(limit)
        )
    )


def faced_pitches(db: Session, player_id: uuid.UUID, session_id: uuid.UUID) -> list[FacedPitch]:
    """Every pitch the athlete saw in a session, with what they did with it.

    Batted-ball measurements are joined on the event id rather than stored
    twice, so a correction to a hit event shows up here without a second write.
    """
    hits = {
        h.external_event_id: h
        for h in db.scalars(
            select(HitEvent).where(
                HitEvent.session_id == session_id, HitEvent.player_id == player_id
            )
        )
    }

    pitches = db.scalars(
        select(PitchEvent)
        .where(PitchEvent.session_id == session_id, PitchEvent.batter_id == player_id)
        .order_by(PitchEvent.pitch_number, PitchEvent.external_event_id)
    )

    out: list[FacedPitch] = []
    for pitch in pitches:
        hit = hits.get(pitch.external_event_id)
        out.append(
            FacedPitch(
                event_number=pitch.pitch_number,
                swing_result=pitch.swing_result,
                pitch_velocity_mph=pitch.velocity_mph,
                induced_vertical_break_in=pitch.vertical_break_in,
                exit_velocity_mph=hit.exit_velocity_mph if hit else None,
                launch_angle_deg=hit.launch_angle_deg if hit else None,
            )
        )
    return out


def videos_for(db: Session, player_id: uuid.UUID, session_id: uuid.UUID) -> list[SessionVideo]:
    return list(
        db.scalars(
            select(SessionVideo)
            .where(
                SessionVideo.session_id == session_id,
                SessionVideo.player_id == player_id,
            )
            .order_by(SessionVideo.created_at)
        )
    )
