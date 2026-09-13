"""API response and request models.

These are the public contract. They are deliberately separate from the ORM so a
column rename is not an API break, and so internal fields are never exposed by
accident.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bsa.domain.enums import (
    Aggregation,
    ImportIssueCode,
    ImportStatus,
    MetricCategory,
    RecordDirection,
    Role,
    SourceStatus,
    SyncStatus,
)


class ApiModel(BaseModel):
    """Base for response models.

    Enum-typed fields are declared with their domain enum rather than `str`, so
    the OpenAPI document carries the real value set. The frontend's types are
    generated from that document, which is what turns a status into a checked
    union in the UI instead of an unconstrained string.
    """

    model_config = ConfigDict(from_attributes=True)


# -- identity ---------------------------------------------------------------


class PlayerSummary(ApiModel):
    id: uuid.UUID
    display_name: str
    full_name: str
    first_name: str
    last_name: str
    preferred_name: str | None = None
    position: str | None = None
    graduation_year: int | None = None
    bats: str | None = None
    throws: str | None = None
    active: bool


class CurrentUser(ApiModel):
    id: uuid.UUID
    display_name: str
    email: str
    role: Role
    organization_id: uuid.UUID
    organization_name: str
    #: Set only for PLAYER accounts.
    player_id: uuid.UUID | None = None


# -- metrics ----------------------------------------------------------------


class MetricDefinitionOut(ApiModel):
    id: uuid.UUID
    key: str
    display_name: str
    description: str | None = None
    category: MetricCategory
    unit: str
    aggregation: Aggregation
    record_direction: RecordDirection
    display_precision: int
    min_sample_size: int
    is_headline: bool
    calculation_version: int


class MetricValue(ApiModel):
    """A number that always travels with its unit and its evidence."""

    value: float | None
    unit: str
    sample_size: int = 0
    #: PRELIMINARY values can change when TrackMan republishes the session.
    source_status: SourceStatus | None = None
    observed_on: date | None = None


class MetricComparison(ApiModel):
    current: float | None
    previous: float | None
    delta: float | None
    percent_change: float | None
    current_sample: int
    previous_sample: int


class PersonalRecordOut(ApiModel):
    metric_key: str
    metric_display_name: str
    unit: str
    display_precision: int
    value: float
    sample_size: int
    achieved_on: date
    session_id: uuid.UUID | None
    source_status: SourceStatus
    is_manual_override: bool = False


class MetricSummaryOut(ApiModel):
    definition: MetricDefinitionOut
    latest: MetricValue
    window: MetricComparison
    record: PersonalRecordOut | None


class MetricSeriesPointOut(ApiModel):
    session_id: uuid.UUID | None
    observed_on: date
    value: float
    sample_size: int
    source_status: SourceStatus


class MetricSeriesOut(ApiModel):
    definition: MetricDefinitionOut
    time_range: str
    points: list[MetricSeriesPointOut]


# -- sessions ---------------------------------------------------------------


class SessionOut(ApiModel):
    id: uuid.UUID
    session_date: date
    session_type: str | None = None
    venue: str | None = None
    source_status: SourceStatus
    verified_at: datetime | None = None
    started_at: datetime | None = None
    pitch_count: int = 0
    hit_count: int = 0


class PlayerOverviewOut(ApiModel):
    player: PlayerSummary
    time_range: str
    last_session: SessionOut | None
    sessions_in_window: int
    metrics: list[MetricSummaryOut]


# -- personal record feed ---------------------------------------------------


class PersonalRecordEventOut(ApiModel):
    id: uuid.UUID
    player_id: uuid.UUID
    player_display_name: str
    metric_key: str
    metric_display_name: str
    unit: str
    display_precision: int
    previous_value: float | None
    new_value: float
    delta: float | None
    sample_size: int
    achieved_on: date
    source_status: SourceStatus


# -- coach dashboard --------------------------------------------------------


class TodaySnapshotOut(ApiModel):
    on_date: date
    athletes_trained: int
    sessions: int
    tracked_events: int
    new_personal_records: int


class IntegrationHealthOut(ApiModel):
    provider: str
    last_successful_import_at: datetime | None
    last_import_status: str | None
    failed_imports_7d: int
    sessions_awaiting_verification: int
    unresolved_players: int
    futures_updates_pending: int


class UnresolvedIdentityOut(ApiModel):
    id: uuid.UUID
    provider: str
    external_id: str
    external_display_name: str | None
    occurrence_count: int
    last_seen_at: datetime | None


class ResolveIdentityIn(BaseModel):
    """Attach an unknown vendor athlete to one of our players.

    `player_id` is required and explicit: there is no "match by name" option,
    by design.
    """

    player_id: uuid.UUID
    note: str | None = Field(default=None, max_length=500)
    #: Re-run the imports whose events were held for this athlete, so their data
    #: is actually recovered. Defaults on -- mapping an athlete and leaving their
    #: sessions stranded is almost never what an admin meant.
    reprocess: bool = True


class ResolveIdentityOut(ApiModel):
    """What a mapping actually recovered."""

    player: PlayerSummary
    imports_reprocessed: int
    new_personal_records: int


# -- imports ----------------------------------------------------------------


class ImportIssueOut(ApiModel):
    row_number: int | None
    code: ImportIssueCode
    field: str | None
    message: str


class ImportOut(ApiModel):
    id: uuid.UUID
    provider: str
    import_type: str
    filename: str | None
    status: ImportStatus
    source_status: SourceStatus
    rows_total: int
    rows_accepted: int
    rows_rejected: int
    created_at: datetime
    completed_at: datetime | None
    error_message: str | None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="import_metadata")


class ImportDetailOut(ImportOut):
    issues: list[ImportIssueOut] = Field(default_factory=list)


class ImportResultOut(ApiModel):
    raw_import_id: uuid.UUID
    status: str
    is_duplicate: bool
    sessions_created: int
    sessions_updated: int
    pitch_events: int
    hit_events: int
    metric_observations: int
    new_personal_records: int
    sync_jobs_queued: int
    rows_total: int
    rows_accepted: int
    rows_rejected: int
    unresolved_players: list[str]
    error_message: str | None = None


# -- futures sync -----------------------------------------------------------


class SyncJobOut(ApiModel):
    id: uuid.UUID
    player_id: uuid.UUID
    player_display_name: str
    metric_key: str
    metric_display_name: str
    destination: str
    destination_field: str
    value: float
    unit: str
    status: SyncStatus
    attempt_count: int
    last_error: str | None
    created_at: datetime


class HealthOut(BaseModel):
    status: str
    version: str
    environment: str
    database: str
