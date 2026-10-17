"""Video of an athlete.

Uploading is staff work; watching is the athlete's own. Both go through
`authorize_player`, so a player reaches only their own footage and the check is
the same one every other athlete-scoped route uses.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from bsa.api import schemas
from bsa.api.deps import (
    CurrentObjectStore,
    CurrentPrincipal,
    DbSession,
    StaffPrincipal,
    authorize_player,
    current_player,
)
from bsa.core.config import Environment, Settings, get_settings
from bsa.core.errors import NotFoundError
from bsa.integrations.media import MediaStore, get_media_store
from bsa.services import media

router = APIRouter(tags=["media"])

CurrentSettings = Annotated[Settings, Depends(get_settings)]


def _store(settings: Settings) -> MediaStore:
    return get_media_store(settings)


def _out(playable: media.PlayableVideo) -> schemas.AthleteVideoOut:
    video = playable.video
    return schemas.AthleteVideoOut(
        id=video.id,
        title=video.title,
        playback_url=playable.playback_url,
        thumbnail_url=playable.thumbnail_url,
        note=video.note,
        session_id=video.session_id,
        external_event_id=video.external_event_id,
        duration_seconds=video.duration_seconds,
        byte_size=video.byte_size,
        provider=video.provider,
        created_at=video.created_at,
    )


@router.post(
    "/players/{player_id}/videos",
    response_model=schemas.AthleteVideoOut,
    status_code=201,
)
def upload_video(
    player_id: uuid.UUID,
    db: DbSession,
    principal: StaffPrincipal,
    settings: CurrentSettings,
    file: Annotated[UploadFile, File(description="A video of the athlete")],
    title: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
    session_id: Annotated[uuid.UUID | None, Form()] = None,
) -> schemas.AthleteVideoOut:
    """Attach a clip to an athlete, and optionally to one of their sessions.

    The session is optional on purpose: a coach usually has the clip before
    they have decided where it belongs, and an untied clip still shows on the
    athlete's page.
    """
    player = authorize_player(db, principal, player_id)
    return _out(
        media.attach_video(
            db,
            _store(settings),
            organization_id=principal.organization_id,
            player=player,
            uploaded_by=principal.user.id,
            filename=file.filename or "clip.mp4",
            content_type=file.content_type,
            data=file.file.read(),
            title=title or (file.filename or "Clip"),
            note=note.strip() or None,
            session_id=session_id,
            max_bytes=settings.max_video_megabytes * 1_000_000,
        )
    )


@router.get("/players/{player_id}/videos", response_model=list[schemas.AthleteVideoOut])
def list_player_videos(
    player_id: uuid.UUID,
    db: DbSession,
    principal: CurrentPrincipal,
    settings: CurrentSettings,
) -> list[schemas.AthleteVideoOut]:
    player = authorize_player(db, principal, player_id)
    return [
        _out(v)
        for v in media.videos_for_player(
            db,
            _store(settings),
            organization_id=principal.organization_id,
            player_id=player.id,
        )
    ]


@router.get("/me/videos", response_model=list[schemas.AthleteVideoOut])
def my_videos(
    db: DbSession, principal: CurrentPrincipal, settings: CurrentSettings
) -> list[schemas.AthleteVideoOut]:
    """The athlete's own footage. Takes no id, so there is none to tamper with."""
    player = current_player(db, principal)
    return [
        _out(v)
        for v in media.videos_for_player(
            db,
            _store(settings),
            organization_id=principal.organization_id,
            player_id=player.id,
        )
    ]


@router.delete("/videos/{video_id}", status_code=204)
def delete_video(
    video_id: uuid.UUID,
    db: DbSession,
    principal: StaffPrincipal,
    settings: CurrentSettings,
) -> Response:
    """Take a clip down here and at the provider.

    Deleting only the row would leave the file hosted and reachable by anyone
    holding a link, which for footage of a minor is the whole problem.
    """
    media.remove_video(
        db,
        _store(settings),
        organization_id=principal.organization_id,
        video_id=video_id,
    )
    return Response(status_code=204)


@router.get("/media/{key:path}", include_in_schema=False)
def serve_local_media(
    key: str, settings: CurrentSettings, object_store: CurrentObjectStore
) -> Response:
    """Serve a development-stored video.

    Unauthenticated, which is why it exists only in development: a `<video>`
    element cannot send an Authorization header, and building signed URLs for a
    provider nobody deploys is work spent on the wrong thing. A deployment uses
    Cloudinary, whose authenticated assets are reachable only through a signed
    link -- and `Settings` refuses `media_provider=local` outside development.
    """
    if settings.env is not Environment.DEVELOPMENT or settings.media_provider != "local":
        raise NotFoundError("not found")
    try:
        data = object_store.get(key)
    except Exception as exc:
        raise NotFoundError("video not found") from exc
    return Response(content=data, media_type="video/mp4")
