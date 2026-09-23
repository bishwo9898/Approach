"""Video attached to a session.

Videos live somewhere else -- a phone, Hudl, YouTube, a shared drive -- so this
stores a link rather than bytes. Hosting video is a real piece of infrastructure
(transcoding, storage cost, access control on minors' footage) and is not worth
building before anyone has actually attached one.

A video may point at a specific event, which is what makes it useful: "this is
the swing that produced your hardest ball" beats a forty-minute session file.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bsa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SessionVideo(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "session_videos"
    __table_args__ = (Index("ix_session_videos_session_player", "session_id", "player_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The athlete the video is of. Required: a video of nobody in particular
    #: cannot be shown on anyone's page, and footage of minors should never be
    #: attached without saying who it is.
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Where the video actually lives. Validated as http(s) before it is stored.
    url: Mapped[str] = mapped_column(Text, nullable=False)
    #: The event this is footage of, when it is one swing rather than a session.
    #: Matches `pitch_events.external_event_id` within the session.
    external_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
