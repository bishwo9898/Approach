"""Futures synchronization worklist.

Until a supported Futures ingestion method exists, this is the product: a list
of exactly which values changed and need entering, with a way to mark them done.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from bsa.api import mappers, schemas
from bsa.api.deps import DbSession, StaffPrincipal
from bsa.core.errors import ConflictError, NotFoundError
from bsa.db.repositories import metrics as metrics_repo
from bsa.db.repositories import players as players_repo
from bsa.db.repositories import sync as sync_repo
from bsa.domain.enums import SyncStatus
from bsa.services import sync as sync_service

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/futures/pending", response_model=list[schemas.SyncJobOut])
def pending_futures_updates(
    db: DbSession, principal: StaffPrincipal, limit: int = 100
) -> list[schemas.SyncJobOut]:
    return [
        mappers.sync_job(job, player, definition)
        for job, player, definition in sync_repo.list_pending(
            db, principal.organization_id, limit=limit
        )
    ]


@router.post("/futures/{job_id}/mark-updated", response_model=schemas.SyncJobOut)
def mark_updated(job_id: uuid.UUID, db: DbSession, principal: StaffPrincipal) -> schemas.SyncJobOut:
    """Confirm that a coach entered the value into Futures by hand.

    Audited: this is the only evidence we will have that the external system
    was actually updated.
    """
    job = sync_repo.get_job(db, principal.organization_id, job_id)
    if job is None:
        raise NotFoundError("sync job not found")
    if job.status is SyncStatus.SYNCED:
        raise ConflictError("this update was already marked complete")

    sync_service.mark_manually_updated(
        db, organization_id=principal.organization_id, job=job, actor=principal.user
    )
    player = players_repo.get(db, principal.organization_id, job.player_id)
    definition = metrics_repo.get_definition(
        db, principal.organization_id, job.metric_definition_id
    )
    db.commit()
    if player is None or definition is None:  # pragma: no cover -- FK enforced
        raise NotFoundError("sync job target no longer exists")
    return mappers.sync_job(job, player, definition)
