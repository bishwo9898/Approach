"""Domain vocabulary.

These names are ours, not a vendor's. TrackMan/Futures terminology is translated
at the adapter boundary so a vendor rename never ripples through the codebase.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Platform roles. PARENT is deliberately not implemented yet."""

    ADMIN = "ADMIN"
    COACH = "COACH"
    PLAYER = "PLAYER"


class Handedness(StrEnum):
    LEFT = "L"
    RIGHT = "R"
    SWITCH = "S"


class SourceStatus(StrEnum):
    """Confidence level of vendor-supplied data.

    TrackMan can publish a session as PRELIMINARY and later republish it as
    VERIFIED with corrected values. Everything derived from an event carries the
    status of the data it was derived from so the UI can label it honestly.
    """

    PRELIMINARY = "PRELIMINARY"
    VERIFIED = "VERIFIED"


class ImportStatus(StrEnum):
    """Lifecycle of a single ingestion attempt."""

    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"


class ImportIssueCode(StrEnum):
    """Machine-readable reasons a row or file was rejected or flagged."""

    SCHEMA_UNKNOWN = "SCHEMA_UNKNOWN"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_VALUE = "INVALID_VALUE"
    INVALID_UNIT = "INVALID_UNIT"
    PLAYER_UNRESOLVED = "PLAYER_UNRESOLVED"
    AMBIGUOUS_SESSION = "AMBIGUOUS_SESSION"


class MetricCategory(StrEnum):
    PITCHING = "PITCHING"
    HITTING = "HITTING"
    THROWING = "THROWING"
    TRAINING = "TRAINING"


class EventSource(StrEnum):
    """Which normalized event table a metric reads from."""

    PITCH = "PITCH"
    HIT = "HIT"


class Aggregation(StrEnum):
    MAX = "MAX"
    MIN = "MIN"
    AVG = "AVG"
    COUNT = "COUNT"
    SUM = "SUM"
    RATE = "RATE"
    """RATE = fraction of sampled events whose filter predicate holds, 0..100."""


class RecordDirection(StrEnum):
    """Which direction of change counts as a personal record."""

    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"
    NONE = "NONE"
    """NONE = tracked as a metric but never produces a personal record
    (e.g. pitch count -- throwing more pitches is not an achievement)."""


class MetricDataType(StrEnum):
    FLOAT = "FLOAT"
    INTEGER = "INTEGER"


class Period(StrEnum):
    """Time scope a metric observation summarizes."""

    SESSION = "SESSION"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    ALL_TIME = "ALL_TIME"


class SyncStatus(StrEnum):
    PENDING = "PENDING"
    SYNCED = "SYNCED"
    FAILED = "FAILED"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"


class IdentityResolutionStatus(StrEnum):
    UNRESOLVED = "UNRESOLVED"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


class AuditAction(StrEnum):
    PLAYER_MAPPING_CREATED = "PLAYER_MAPPING_CREATED"
    PLAYER_MAPPING_CHANGED = "PLAYER_MAPPING_CHANGED"
    METRIC_CREATED = "METRIC_CREATED"
    METRIC_CHANGED = "METRIC_CHANGED"
    PR_OVERRIDDEN = "PR_OVERRIDDEN"
    FUTURES_SYNC_MANUALLY_CONFIRMED = "FUTURES_SYNC_MANUALLY_CONFIRMED"
    IMPORT_REPROCESSED = "IMPORT_REPROCESSED"
