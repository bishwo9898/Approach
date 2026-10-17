"""Attaching video to an athlete.

Thin on purpose. The provider holds the file; this decides which athlete a clip
belongs to, keeps enough to find and remove it, and produces a playback URL at
read time rather than storing one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from bsa.core.errors import NotFoundError, ValidationError
from bsa.core.logging import get_logger
from bsa.db.models import Player, SessionVideo, TrainingSession
from bsa.integrations.media import MediaStore

log = get_logger(__name__)

#: Containers a browser can actually play. Checked by extension and content
#: type both, because either on its own is trivially wrong.
ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
ALLOWED_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-m4v",
    "video/webm",
}


@dataclass(frozen=True, slots=True)
class PlayableVideo:
    """A stored video, with a URL good for right now."""

    video: SessionVideo
    playback_url: str
    thumbnail_url: str | None


def _check(filename: str, content_type: str | None, data: bytes, *, max_bytes: int) -> None:
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix not in ALLOWED_SUFFIXES:
        raise ValidationError(
            f"{filename} is not a video this app can play. "
            f"Use one of {', '.join(sorted(ALLOWED_SUFFIXES))}."
        )
    if content_type and content_type.split(";")[0].strip() not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(f"{filename} does not look like a video file ({content_type}).")
    if not data:
        raise ValidationError(f"{filename} is empty.")
    if len(data) > max_bytes:
        raise ValidationError(
            f"{filename} is {len(data) / 1_000_000:.0f} MB, over the "
            f"{max_bytes / 1_000_000:.0f} MB limit."
        )


def attach_video(
    db: Session,
    store: MediaStore,
    *,
    organization_id: uuid.UUID,
    player: Player,
    uploaded_by: uuid.UUID,
    filename: str,
    content_type: str | None,
    data: bytes,
    title: str,
    note: str | None = None,
    session_id: uuid.UUID | None = None,
    max_bytes: int = 200_000_000,
) -> PlayableVideo:
    """Upload a clip and record who it is of.

    The athlete is required and the session is not: a coach usually has the
    clip before they have decided which session it belongs to, and a video with
    no athlete could not be shown on anyone's page anyway.
    """
    _check(filename, content_type, data, max_bytes=max_bytes)

    if session_id is not None:
        session = db.scalars(
            select(TrainingSession).where(
                TrainingSession.id == session_id,
                TrainingSession.organization_id == organization_id,
            )
        ).first()
        if session is None:
            raise NotFoundError("session not found")

    stored = store.upload(
        data,
        filename=filename,
        folder=f"athletes/{player.id}",
    )

    video = SessionVideo(
        organization_id=organization_id,
        session_id=session_id,
        player_id=player.id,
        title=title.strip() or filename,
        url=stored.url,
        note=note,
        provider=store.name,
        external_asset_id=stored.asset_id,
        thumbnail_url=stored.thumbnail_url,
        duration_seconds=stored.duration_seconds,
        byte_size=stored.byte_size,
        created_by_user_id=uploaded_by,
    )
    db.add(video)
    db.commit()

    log.info(
        "media.attached",
        player_id=str(player.id),
        provider=store.name,
        bytes=stored.byte_size,
        session_id=str(session_id) if session_id else None,
    )
    return _playable(store, video)


def _playable(store: MediaStore, video: SessionVideo) -> PlayableVideo:
    """Mint a URL for right now, rather than trusting the one in the row.

    A stored URL outlives whatever permission produced it; an authenticated
    Cloudinary asset is deliberately unreachable without a fresh signature.
    """
    if video.external_asset_id and video.provider == store.name:
        url = store.playback_url(video.external_asset_id, fallback=video.url)
    else:
        # Uploaded under a different provider, or a link somebody pasted in.
        url = video.url
    return PlayableVideo(video=video, playback_url=url, thumbnail_url=video.thumbnail_url)


def videos_for_player(
    db: Session, store: MediaStore, *, organization_id: uuid.UUID, player_id: uuid.UUID
) -> list[PlayableVideo]:
    """Every clip of this athlete, newest first."""
    found = db.scalars(
        select(SessionVideo)
        .where(
            SessionVideo.organization_id == organization_id,
            SessionVideo.player_id == player_id,
        )
        .order_by(SessionVideo.created_at.desc())
    )
    return [_playable(store, video) for video in found]


def videos_for_session(
    db: Session,
    store: MediaStore,
    *,
    organization_id: uuid.UUID,
    player_id: uuid.UUID,
    session_id: uuid.UUID,
) -> list[PlayableVideo]:
    """Clips to show on one session's report.

    Includes the athlete's untied clips: a coach who uploaded footage without
    filing it under a session still meant it for this athlete, and a video
    nobody can find is the same as no video.
    """
    found = db.scalars(
        select(SessionVideo)
        .where(
            SessionVideo.organization_id == organization_id,
            SessionVideo.player_id == player_id,
            (SessionVideo.session_id == session_id) | SessionVideo.session_id.is_(None),
        )
        .order_by(SessionVideo.created_at)
    )
    return [_playable(store, video) for video in found]


def remove_video(
    db: Session, store: MediaStore, *, organization_id: uuid.UUID, video_id: uuid.UUID
) -> None:
    """Take a clip down, at the provider as well as here.

    Deleting the row alone would leave the file hosted and reachable by anyone
    holding a link, which for footage of a minor is the whole problem.
    """
    video = db.scalars(
        select(SessionVideo).where(
            SessionVideo.id == video_id, SessionVideo.organization_id == organization_id
        )
    ).first()
    if video is None:
        raise NotFoundError("video not found")

    if video.external_asset_id and video.provider == store.name:
        store.delete(video.external_asset_id)
    db.delete(video)
    db.commit()
    log.info("media.removed", video_id=str(video_id), provider=video.provider)
