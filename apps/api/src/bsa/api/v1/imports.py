"""Import endpoints: upload, history, and the identity-resolution queue."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from bsa.api import mappers, schemas
from bsa.api.deps import (
    CurrentObjectStore,
    CurrentTrackmanProvider,
    DbSession,
    StaffPrincipal,
)
from bsa.core.config import Settings, get_settings
from bsa.core.errors import ConflictError, NotFoundError, ValidationError
from bsa.core.logging import get_logger
from bsa.db.models import ExternalPlayerIdentity
from bsa.db.repositories import imports as imports_repo
from bsa.db.repositories import players as players_repo
from bsa.domain.enums import AuditAction, IdentityResolutionStatus
from bsa.integrations.ocr import get_ocr_engine
from bsa.integrations.trackman.schema import SourcePayload
from bsa.services import audit, screenshots
from bsa.services.ingestion import IngestionService

router = APIRouter(tags=["imports"])

log = get_logger(__name__)

#: Upload ceiling. A TrackMan day export is well under this; anything larger is
#: more likely a mistake than a session.
MAX_UPLOAD_BYTES = 32 * 1024 * 1024


@router.post("/imports/trackman/csv", response_model=schemas.ImportResultOut)
async def upload_trackman_csv(
    db: DbSession,
    principal: StaffPrincipal,
    provider: CurrentTrackmanProvider,
    object_store: CurrentObjectStore,
    file: UploadFile = File(...),
    force: bool = False,
) -> schemas.ImportResultOut:
    """Ingest a TrackMan CSV export.

    Re-uploading the same file is safe and explicitly reported as a duplicate
    rather than silently creating a second copy of the session.
    """
    data = await file.read()
    if not data:
        raise ValidationError("uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationError(f"file is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES} bytes")

    service = IngestionService(db, principal.organization, provider, object_store)
    outcome = service.ingest(
        SourcePayload(data=data, filename=file.filename, import_type="csv_upload"),
        force_reprocess=force,
    )
    if force and not outcome.is_duplicate:
        audit.record(
            db,
            organization_id=principal.organization_id,
            action=AuditAction.IMPORT_REPROCESSED,
            target_type="raw_import",
            target_id=outcome.raw_import_id,
            actor=principal.user,
            metadata={"filename": file.filename},
        )
    db.commit()
    return mappers.import_result(outcome)


@router.get("/imports", response_model=list[schemas.ImportOut])
def list_imports(
    db: DbSession, principal: StaffPrincipal, limit: int = 25
) -> list[schemas.ImportOut]:
    return [
        mappers.import_out(i)
        for i in imports_repo.list_recent(db, principal.organization_id, limit=limit)
    ]


@router.get("/imports/{import_id}", response_model=schemas.ImportDetailOut)
def get_import(
    import_id: uuid.UUID, db: DbSession, principal: StaffPrincipal
) -> schemas.ImportDetailOut:
    """One import with its rejected rows, so nothing is silently discarded."""
    raw_import = imports_repo.get(db, principal.organization_id, import_id)
    if raw_import is None:
        raise NotFoundError("import not found")
    return mappers.import_detail(raw_import, imports_repo.list_issues(db, raw_import.id))


@router.post("/imports/{import_id}/reprocess", response_model=schemas.ImportResultOut)
def reprocess_import(
    import_id: uuid.UUID,
    db: DbSession,
    principal: StaffPrincipal,
    provider: CurrentTrackmanProvider,
    object_store: CurrentObjectStore,
) -> schemas.ImportResultOut:
    """Re-run a stored import from its archived source bytes.

    Used after mapping a previously-unknown athlete, and after a parser or
    metric change. Audited, because it rewrites athlete-facing numbers.
    """
    raw_import = imports_repo.get(db, principal.organization_id, import_id)
    if raw_import is None:
        raise NotFoundError("import not found")

    service = IngestionService(db, principal.organization, provider, object_store)
    outcome = service.reprocess(raw_import)

    audit.record(
        db,
        organization_id=principal.organization_id,
        action=AuditAction.IMPORT_REPROCESSED,
        target_type="raw_import",
        target_id=raw_import.id,
        actor=principal.user,
        metadata={
            "filename": raw_import.filename,
            "status": outcome.status.value,
            "new_personal_records": outcome.new_personal_records,
        },
    )
    db.commit()
    return mappers.import_result(outcome)


@router.get("/identity/unresolved", response_model=list[schemas.UnresolvedIdentityOut])
def list_unresolved(
    db: DbSession, principal: StaffPrincipal, limit: int = 100
) -> list[schemas.UnresolvedIdentityOut]:
    """Vendor athletes awaiting a human decision."""
    return [
        schemas.UnresolvedIdentityOut(
            id=item.id,
            provider=item.provider,
            external_id=item.external_id,
            external_display_name=item.external_display_name,
            occurrence_count=item.occurrence_count,
            last_seen_at=item.last_seen_at,
        )
        for item in players_repo.list_unresolved(db, principal.organization_id, limit=limit)
    ]


@router.post("/identity/unresolved/{item_id}/resolve", response_model=schemas.ResolveIdentityOut)
def resolve_identity(
    item_id: uuid.UUID,
    payload: schemas.ResolveIdentityIn,
    db: DbSession,
    # Staff, not admin. The facility runs on two roles, coach and player, so an
    # admin-only control on the coach's own Data Health page is a control
    # nobody can use -- and mapping a vendor athlete to one of ours is exactly
    # the judgement a coach is there to make. It stays audited either way.
    principal: StaffPrincipal,
    provider: CurrentTrackmanProvider,
    object_store: CurrentObjectStore,
) -> schemas.ResolveIdentityOut:
    """Map a vendor athlete to one of our players, and recover their held data.

    Admin-only and audited: this decision determines whose data is whose, and it
    is the one place a mistake would attribute one athlete's numbers to another.

    Events held back for this athlete are recovered by **reprocessing** the
    affected imports from their archived source bytes -- never by back-filling
    rows by hand. The recovered data therefore goes through exactly the same
    validated pipeline as a first ingest, and stays idempotent.
    """
    items = players_repo.list_unresolved(db, principal.organization_id, limit=1000)
    item = next((i for i in items if i.id == item_id), None)
    if item is None:
        raise NotFoundError("unresolved identity not found")

    player = players_repo.get(db, principal.organization_id, payload.player_id)
    if player is None:
        raise NotFoundError("player not found")

    existing = players_repo.get_identity(
        db, principal.organization_id, item.provider, item.external_id
    )
    if existing is not None:
        raise ConflictError(
            f"{item.provider} id {item.external_id!r} is already mapped to another athlete"
        )

    now = datetime.now(UTC)
    db.add(
        ExternalPlayerIdentity(
            organization_id=principal.organization_id,
            player_id=player.id,
            provider=item.provider,
            external_id=item.external_id,
            external_display_name=item.external_display_name,
            verified_at=now,
            player_metadata={"resolved_from_queue": True},
        )
    )
    item.status = IdentityResolutionStatus.RESOLVED
    item.resolved_player_id = player.id
    item.resolved_at = now
    item.resolved_by_user_id = principal.user.id
    item.notes = payload.note

    audit.record(
        db,
        organization_id=principal.organization_id,
        action=AuditAction.PLAYER_MAPPING_CREATED,
        target_type="external_player_identity",
        target_id=player.id,
        actor=principal.user,
        metadata={
            "provider": item.provider,
            "external_id": item.external_id,
            "external_display_name": item.external_display_name,
        },
    )
    db.flush()

    reprocessed: list[uuid.UUID] = []
    recovered_records = 0
    if payload.reprocess:
        service = IngestionService(db, principal.organization, provider, object_store)
        for blocked in imports_repo.find_blocked_by_external_id(
            db, principal.organization_id, item.provider, item.external_id
        ):
            # One unreadable archive must not abandon the rest of the recovery.
            try:
                outcome = service.reprocess(blocked)
            except ValidationError as exc:
                log.warning(
                    "identity.reprocess_skipped",
                    raw_import_id=str(blocked.id),
                    reason=str(exc),
                )
                continue
            reprocessed.append(blocked.id)
            recovered_records += outcome.new_personal_records
            audit.record(
                db,
                organization_id=principal.organization_id,
                action=AuditAction.IMPORT_REPROCESSED,
                target_type="raw_import",
                target_id=blocked.id,
                actor=principal.user,
                metadata={
                    "reason": "athlete mapping resolved",
                    "external_id": item.external_id,
                },
            )

    db.commit()
    return schemas.ResolveIdentityOut(
        player=mappers.player_summary(player),
        imports_reprocessed=len(reprocessed),
        new_personal_records=recovered_records,
    )


@router.post("/imports/trackman/screenshots", response_model=schemas.ScreenshotConversionOut)
def convert_screenshots(
    db: DbSession,
    principal: StaffPrincipal,
    object_store: CurrentObjectStore,
    settings: Annotated[Settings, Depends(get_settings)],
    provider: CurrentTrackmanProvider,
    files: Annotated[list[UploadFile], File(description="TrackMan pitch-table screenshots")],
    player_name: Annotated[str, Form()],
    session_date: Annotated[date, Form()],
    opponent_name: Annotated[str, Form()] = "",
    session_time: Annotated[str, Form()] = "",
    competition: Annotated[str, Form()] = "",
    ingest: Annotated[bool, Form()] = True,
) -> schemas.ScreenshotConversionOut:
    """Read a set of screenshots into a CSV, and optionally import it.

    Screenshots are converted, archived alongside the CSV they produced, and
    only then imported -- and **only if every pitch read cleanly.** A single
    unreadable value stops the import and comes back named, because a number
    nobody checked is worse than a number nobody has.

    Pass `ingest=false` to convert and archive without importing, which is how
    to inspect the CSV first.
    """
    images = [
        screenshots.UploadedImage(filename=f.filename or "screenshot.png", data=f.file.read())
        for f in files
    ]
    if not images:
        raise ValidationError("attach at least one screenshot")

    result = screenshots.convert(
        get_ocr_engine(settings),
        object_store,
        images,
        player_name=player_name.strip(),
        session_date=session_date,
        opponent_name=opponent_name.strip(),
        session_time=session_time.strip(),
        competition=competition.strip(),
    )

    imported = None
    if ingest and result.ok:
        service = IngestionService(db, principal.organization, provider, object_store)
        outcome = service.ingest(
            SourcePayload(
                data=result.csv_text.encode("utf-8"),
                filename=f"screenshots-{session_date.isoformat()}.csv",
                import_type="screenshot",
            )
        )
        db.commit()
        imported = mappers.import_result(outcome)

    return schemas.ScreenshotConversionOut(
        pitches=result.pitches,
        batted_balls=result.batted_balls,
        first_pitch=result.first_pitch,
        last_pitch=result.last_pitch,
        batter_name_in_image=result.batter_name,
        ok=result.ok,
        problems=[
            schemas.ConversionProblemOut(
                event_number=p.event_number,
                column=p.column,
                message=p.message,
                blocking=p.blocking,
            )
            for p in result.problems
        ],
        csv_key=result.csv_key,
        image_keys=result.image_keys,
        csv_text=result.csv_text,
        imported=imported,
    )
