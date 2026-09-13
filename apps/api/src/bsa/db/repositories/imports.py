"""Raw import provenance queries."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bsa.db.models import ImportIssue, RawImport
from bsa.domain.enums import ImportIssueCode, ImportStatus
from bsa.integrations.trackman.schema import RowIssue


def find_by_checksum(
    db: Session, organization_id: uuid.UUID, provider: str, checksum: str
) -> RawImport | None:
    """The duplicate check. Identical bytes have already been ingested."""
    return db.scalars(
        select(RawImport).where(
            RawImport.organization_id == organization_id,
            RawImport.provider == provider,
            RawImport.checksum == checksum,
        )
    ).first()


def get(db: Session, organization_id: uuid.UUID, import_id: uuid.UUID) -> RawImport | None:
    return db.scalars(
        select(RawImport).where(
            RawImport.id == import_id, RawImport.organization_id == organization_id
        )
    ).first()


def list_recent(db: Session, organization_id: uuid.UUID, *, limit: int = 25) -> list[RawImport]:
    return list(
        db.scalars(
            select(RawImport)
            .where(RawImport.organization_id == organization_id)
            .order_by(RawImport.created_at.desc())
            .limit(limit)
        )
    )


def last_successful(db: Session, organization_id: uuid.UUID, provider: str) -> RawImport | None:
    return db.scalars(
        select(RawImport)
        .where(
            RawImport.organization_id == organization_id,
            RawImport.provider == provider,
            RawImport.status.in_([ImportStatus.SUCCESS, ImportStatus.PARTIAL]),
        )
        .order_by(RawImport.completed_at.desc())
        .limit(1)
    ).first()


def count_failed_since(db: Session, organization_id: uuid.UUID, since: datetime) -> int:
    return (
        db.scalar(
            select(func.count(RawImport.id)).where(
                RawImport.organization_id == organization_id,
                RawImport.status == ImportStatus.FAILED,
                RawImport.created_at >= since,
            )
        )
        or 0
    )


def add_issues(db: Session, raw_import_id: uuid.UUID, issues: Sequence[RowIssue]) -> None:
    """Persist row-level rejections so nothing is silently discarded."""
    for issue in issues:
        db.add(
            ImportIssue(
                raw_import_id=raw_import_id,
                row_number=issue.row_number or None,
                code=issue.code,
                field=issue.field,
                message=issue.message,
                context=issue.context,
            )
        )


def list_issues(db: Session, raw_import_id: uuid.UUID, *, limit: int = 200) -> list[ImportIssue]:
    return list(
        db.scalars(
            select(ImportIssue)
            .where(ImportIssue.raw_import_id == raw_import_id)
            .order_by(ImportIssue.row_number)
            .limit(limit)
        )
    )


def find_blocked_by_external_id(
    db: Session, organization_id: uuid.UUID, provider: str, external_id: str
) -> list[RawImport]:
    """Imports that held events back because this athlete was unmapped.

    Found via the `PLAYER_UNRESOLVED` issues those imports recorded, which is
    why unresolved athletes are written as import issues and not only to the
    resolution queue -- it is what makes the held data recoverable later.
    """
    return list(
        db.scalars(
            select(RawImport)
            .join(ImportIssue, ImportIssue.raw_import_id == RawImport.id)
            .where(
                RawImport.organization_id == organization_id,
                RawImport.provider == provider,
                ImportIssue.code == ImportIssueCode.PLAYER_UNRESOLVED,
                ImportIssue.context["external_id"].astext == external_id,
            )
            .order_by(RawImport.created_at)
            .distinct()
        )
    )
