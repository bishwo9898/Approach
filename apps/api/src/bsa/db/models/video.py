"""Video of an athlete.

This row is a *reference*, never the bytes. The file itself lives with a media
provider -- Cloudinary in a deployment, the local object store in development --
which is where transcoding, delivery and access control belong. What is kept
here is enough to find it again, show it, and take it down.

A video belongs to an athlete. It may also belong to one of their sessions, and
may point at a single event within it, which is what makes it useful: "this is
the swing that produced your hardest ball" beats a forty-minute session file.
Neither is required, because a coach often has a clip before they have anywhere
to file it.
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
    #: The session this is footage of, when it is of one. Nullable: a coach
    #: uploading a clip should not have to invent a session to file it under,
    #: and an untied video still belongs on the athlete's page.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True, index=True
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

    #: Which media provider holds the file: "cloudinary", "local", or "link"
    #: for a URL somebody pasted in. Stored so a video uploaded under one
    #: provider is still findable after the deployment moves to another.
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="link")
    #: The provider's own id for the asset -- Cloudinary's public_id, or the
    #: object-store key. This is what a delete needs; `url` is only for playing.
    external_asset_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    byte_size: Mapped[int | None] = mapped_column(nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
