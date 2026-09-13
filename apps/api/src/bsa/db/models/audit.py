"""Audit trail for actions that change records a coach relies on."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from bsa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from bsa.domain.enums import AuditAction


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only record of manual interventions.

    Scope is deliberately narrow: administrative actions that override or
    reshape athlete-facing data. It is not a request log.

    `metadata` must never carry credentials, tokens or raw vendor payloads --
    audit rows are the most widely-read table in an incident.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_created", "organization_id", "created_at"),
        Index("ix_audit_logs_target", "target_type", "target_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: NULL for actions taken by an automated job rather than a person.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_label: Mapped[str] = mapped_column(String(200), nullable=False)

    action: Mapped[AuditAction] = mapped_column(
        enum_column(AuditAction, "audit_action"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    audit_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", nullable=False, default=dict)
