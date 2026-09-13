"""Raw import provenance and normalized training sessions."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bsa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from bsa.domain.enums import ImportIssueCode, ImportStatus, SourceStatus


class RawImport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One ingestion attempt, and the pointer to the bytes it was built from.

    Source data is never discarded. If the parser changes -- and it will, once a
    real TrackMan export replaces our synthetic schema -- we reprocess from the
    stored original rather than asking the facility to re-export.

    `checksum` is the idempotency key: the same bytes ingested twice is a no-op.
    """

    __tablename__ = "raw_imports"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider", "checksum", name="uq_raw_imports_checksum"),
        Index("ix_raw_imports_org_created_at", "organization_id", "created_at"),
        Index("ix_raw_imports_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    #: How the bytes reached us: "csv_upload", "ftp", "api", "feed".
    import_type: Mapped[str] = mapped_column(String(32), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #: SHA-256 of the exact bytes received.
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(nullable=False, default=0)

    #: Opaque key into the ObjectStore, not a filesystem path or bucket URL, so
    #: the storage backend can change without rewriting rows.
    object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    status: Mapped[ImportStatus] = mapped_column(
        enum_column(ImportStatus, "import_status"), nullable=False, default=ImportStatus.RECEIVED
    )
    #: Confidence of the payload, as declared by the source.
    source_status: Mapped[SourceStatus] = mapped_column(
        enum_column(SourceStatus, "source_status"),
        nullable=False,
        default=SourceStatus.PRELIMINARY,
    )

    #: Shared by every log line for this import so a failure can be traced end
    #: to end in Cloud Logging.
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rows_total: Mapped[int] = mapped_column(nullable=False, default=0)
    rows_accepted: Mapped[int] = mapped_column(nullable=False, default=0)
    rows_rejected: Mapped[int] = mapped_column(nullable=False, default=0)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Counts of created/updated entities, provider hints, reprocess pointers.
    import_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", nullable=False, default=dict
    )

    issues: Mapped[list[ImportIssue]] = relationship(
        back_populates="raw_import", cascade="all, delete-orphan"
    )


class ImportIssue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single rejected or flagged source row.

    One bad row must not fail an otherwise good file, and it must not vanish
    either -- it lands here, countable and reviewable.
    """

    __tablename__ = "import_issues"
    __table_args__ = (Index("ix_import_issues_import_code", "raw_import_id", "code"),)

    raw_import_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("raw_imports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: 1-based row number in the source file, as an operator would count it.
    row_number: Mapped[int | None] = mapped_column(nullable=True)
    code: Mapped[ImportIssueCode] = mapped_column(
        enum_column(ImportIssueCode, "import_issue_code"), nullable=False
    )
    field: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    #: Echo of the offending values only -- never the whole row, which could
    #: carry fields we have no reason to duplicate.
    context: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)

    raw_import: Mapped[RawImport] = relationship(back_populates="issues")


class TrainingSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A normalized training session.

    Named `TrainingSession` rather than `Session` to avoid colliding with
    SQLAlchemy's Session in every module that touches both. The table is
    `sessions`, which is what the domain calls it.

    A verified republish updates this row in place; it never creates a second
    session, which is what `(organization_id, provider, external_session_id)`
    guarantees.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "external_session_id",
            name="uq_sessions_provider_external_id",
        ),
        Index("ix_sessions_org_date", "organization_id", "session_date"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_session_id: Mapped[str] = mapped_column(String(128), nullable=False)

    #: Facility-local calendar date. This is what "today" means to a coach, and
    #: what day/week/month rollups group on.
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: e.g. "BULLPEN", "LIVE_BP", "CAGE". Vendor-agnostic and open-ended.
    session_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(120), nullable=True)

    source_status: Mapped[SourceStatus] = mapped_column(
        enum_column(SourceStatus, "source_status"),
        nullable=False,
        default=SourceStatus.PRELIMINARY,
    )
    #: When the verified republish landed. NULL while still preliminary.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: The import that most recently wrote this session.
    raw_import_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("raw_imports.id", ondelete="SET NULL"), nullable=True
    )

    session_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", nullable=False, default=dict
    )
