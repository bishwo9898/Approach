"""Player and vendor-identity queries.

Every function takes `organization_id` and filters on it. That is not
defensive decoration: it is the mechanism that makes cross-organization access
impossible at the data layer, independent of whatever the API layer checked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from bsa.db.models import ExternalPlayerIdentity, IdentityResolutionItem, Player
from bsa.domain.enums import IdentityResolutionStatus


def get(db: Session, organization_id: uuid.UUID, player_id: uuid.UUID) -> Player | None:
    return db.scalars(
        select(Player).where(Player.id == player_id, Player.organization_id == organization_id)
    ).first()


def _search_filter(query: str) -> Select[tuple[Player]]:
    term = f"%{query.strip().lower()}%"
    return select(Player).where(
        or_(
            func.lower(Player.first_name).like(term),
            func.lower(Player.last_name).like(term),
            func.lower(func.coalesce(Player.preferred_name, "")).like(term),
            func.lower(Player.first_name + " " + Player.last_name).like(term),
        )
    )


def search(
    db: Session,
    organization_id: uuid.UUID,
    query: str | None = None,
    *,
    active_only: bool = True,
    limit: int = 50,
) -> list[Player]:
    """Search by first, last or preferred name.

    Name search is a convenience for humans only. It never establishes identity:
    matching a name grants nothing and maps nothing.
    """
    stmt = _search_filter(query) if query and query.strip() else select(Player)
    stmt = stmt.where(Player.organization_id == organization_id)
    if active_only:
        stmt = stmt.where(Player.active.is_(True))
    stmt = stmt.order_by(Player.last_name, Player.first_name).limit(limit)
    return list(db.scalars(stmt))


def count_active(db: Session, organization_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count(Player.id)).where(
                Player.organization_id == organization_id, Player.active.is_(True)
            )
        )
        or 0
    )


def find_by_external_identity(
    db: Session, organization_id: uuid.UUID, provider: str, external_id: str
) -> Player | None:
    """The only supported way to resolve a vendor athlete to one of ours."""
    return db.scalars(
        select(Player)
        .join(ExternalPlayerIdentity, ExternalPlayerIdentity.player_id == Player.id)
        .where(
            ExternalPlayerIdentity.organization_id == organization_id,
            ExternalPlayerIdentity.provider == provider,
            ExternalPlayerIdentity.external_id == external_id,
        )
    ).first()


def get_identity(
    db: Session, organization_id: uuid.UUID, provider: str, external_id: str
) -> ExternalPlayerIdentity | None:
    return db.scalars(
        select(ExternalPlayerIdentity).where(
            ExternalPlayerIdentity.organization_id == organization_id,
            ExternalPlayerIdentity.provider == provider,
            ExternalPlayerIdentity.external_id == external_id,
        )
    ).first()


def external_id_for(db: Session, player_id: uuid.UUID, provider: str) -> str | None:
    return db.scalar(
        select(ExternalPlayerIdentity.external_id).where(
            ExternalPlayerIdentity.player_id == player_id,
            ExternalPlayerIdentity.provider == provider,
        )
    )


def record_unresolved(
    db: Session,
    organization_id: uuid.UUID,
    provider: str,
    external_id: str,
    *,
    display_name: str | None,
    occurrences: int,
    import_id: uuid.UUID | None,
) -> IdentityResolutionItem:
    """Park an unknown vendor athlete for a human decision.

    Re-running an import accumulates occurrence counts on the existing row
    rather than creating a second queue entry for the same athlete.
    """
    item = db.scalars(
        select(IdentityResolutionItem).where(
            IdentityResolutionItem.organization_id == organization_id,
            IdentityResolutionItem.provider == provider,
            IdentityResolutionItem.external_id == external_id,
        )
    ).first()

    now = datetime.now(UTC)
    if item is None:
        item = IdentityResolutionItem(
            organization_id=organization_id,
            provider=provider,
            external_id=external_id,
            external_display_name=display_name,
            status=IdentityResolutionStatus.UNRESOLVED,
            occurrence_count=occurrences,
            first_seen_import_id=import_id,
            last_seen_at=now,
        )
        db.add(item)
    else:
        item.occurrence_count += occurrences
        item.last_seen_at = now
        if display_name and not item.external_display_name:
            item.external_display_name = display_name
    return item


def list_unresolved(
    db: Session, organization_id: uuid.UUID, *, limit: int = 100
) -> list[IdentityResolutionItem]:
    return list(
        db.scalars(
            select(IdentityResolutionItem)
            .where(
                IdentityResolutionItem.organization_id == organization_id,
                IdentityResolutionItem.status == IdentityResolutionStatus.UNRESOLVED,
            )
            .order_by(IdentityResolutionItem.occurrence_count.desc())
            .limit(limit)
        )
    )


def count_unresolved(db: Session, organization_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count(IdentityResolutionItem.id)).where(
                IdentityResolutionItem.organization_id == organization_id,
                IdentityResolutionItem.status == IdentityResolutionStatus.UNRESOLVED,
            )
        )
        or 0
    )
