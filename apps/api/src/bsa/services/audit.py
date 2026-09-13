"""Audit trail writer."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from bsa.db.models import AuditLog, User
from bsa.domain.enums import AuditAction

#: Keys that must never appear in audit metadata, regardless of caller.
#: Audit rows are the most widely-read table during an incident.
_FORBIDDEN_KEYS = {"password", "token", "secret", "authorization", "api_key", "credential"}


def _scrub(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v for k, v in metadata.items() if not any(bad in k.lower() for bad in _FORBIDDEN_KEYS)
    }


def record(
    db: Session,
    *,
    organization_id: uuid.UUID,
    action: AuditAction,
    target_type: str,
    target_id: uuid.UUID | None = None,
    actor: User | None = None,
    actor_label: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Append one audit entry.

    `actor_label` is stored alongside the user id so the log stays readable
    after a user row is deactivated or renamed.
    """
    entry = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor.id if actor else None,
        actor_label=actor_label or (actor.display_name if actor else "system"),
        action=action,
        target_type=target_type,
        target_id=target_id,
        audit_metadata=_scrub(metadata or {}),
    )
    db.add(entry)
    return entry
