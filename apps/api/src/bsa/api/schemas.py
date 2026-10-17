"""API response and request models.

These are the public contract. They are deliberately separate from the ORM so a
column rename is not an API break, and so internal fields are never exposed by
accident.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from bsa.domain.analytics import TimeRange
from bsa.domain.enums import (
    Aggregation,
    Handedness,
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


class CreatePlayerIn(BaseModel):
    """Add an athlete to the roster.

    Only the name is required. Everything else is a coaching label that can be
    filled in later, and demanding it up front would make adding a roster of
    thirty athletes needlessly slow.
    """

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    preferred_name: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=32)
    graduation_year: int | None = Field(default=None, ge=1900, le=2100)
    bats: Handedness | None = None
    throws: Handedness | None = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def _require_a_real_name(cls, value: object) -> object:
        """Strip before length checking, so "   " is rejected rather than stored.

        `min_length` alone accepts whitespace, which would create an athlete
        with a blank surname that no search would ever find.
        """
        return value.strip() if isinstance(value, str) else value

    @field_validator("preferred_name", "position", mode="before")
    @classmethod
    def _blank_optional_is_none(cls, value: object) -> object:
        """Treat an empty optional field as absent rather than as an empty string."""
        if isinstance(value, str):
            return value.strip() or None
        return value


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
    #: A window is preliminary when any contributing session is preliminary.
    current_source_status: SourceStatus | None = None
    previous_source_status: SourceStatus | None = None


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


# -- hitting session report -------------------------------------------------


class InsightOut(ApiModel):
    kind: str
    headline: str
    detail: str


class BattedBallOut(ApiModel):
    """One measured batted ball. Every field here was measured, not derived."""

    event_number: int | None
    exit_velocity_mph: float
    launch_angle_deg: float | None
    pitch_velocity_mph: float | None
    #: Whether the measured launch angle falls in the 8-32 degree band.
    in_sweet_spot: bool


class SessionVideoOut(ApiModel):
    id: uuid.UUID
    title: str
    url: str
    external_event_id: str | None
    note: str | None


class AddSessionVideoIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    external_event_id: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("url")
    @classmethod
    def _must_be_a_web_link(cls, value: str) -> str:
        """Only http(s).

        A `javascript:` or `data:` URL rendered as a link on an athlete's page
        would be a stored cross-site scripting hole, and the page is shown to
        minors.
        """
        cleaned = value.strip()
        if not cleaned.lower().startswith(("http://", "https://")):
            raise ValueError("video links must start with http:// or https://")
        return cleaned


class HittingSessionReportOut(ApiModel):
    player: PlayerSummary
    session_id: uuid.UUID
    session_date: date
    session_type: str | None
    opponent_name: str | None

    #: Pitches TrackMan recorded for this hitter. NOT a count of swings: this
    #: export does not report swings, and a pitch with no measured batted ball
    #: may have been taken, fouled, missed, or simply not read by the radar.
    pitches_faced: int
    #: Pitches that produced a measured batted ball.
    batted_balls: int
    #: Share of recorded pitches with a measurement. Data coverage, not a
    #: contact rate -- see `pitches_faced`.
    measured_rate: float | None

    best_exit_velocity_mph: float | None
    average_exit_velocity_mph: float | None
    average_launch_angle_deg: float | None
    hardest_ball_launch_angle_deg: float | None
    sweet_spot_count: int
    #: Denominated in measured batted balls, never in pitches.
    sweet_spot_rate: float | None
    average_pitch_velocity_mph: float | None

    # Required rather than defaulted: a report always carries all three lists,
    # empty when there is nothing in them. Defaulting them would make each one
    # optional in the OpenAPI document, and every consumer would have to guard
    # against an absence that never happens.
    contact: list[BattedBallOut]
    insights: list[InsightOut]
    videos: list[SessionVideoOut]


class HittingSessionSummaryOut(ApiModel):
    """One line per session, for choosing which report to open."""

    session_id: uuid.UUID
    session_date: date
    session_type: str | None
    opponent_name: str | None
    pitches_faced: int
    batted_balls: int
    best_exit_velocity_mph: float | None


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
    #: Which database this process is actually talking to, as host:port/name.
    #: Never includes credentials. Present so that when two stacks are running
    #: -- a container and a local process, say -- you can tell in one request
    #: which one answered, instead of debugging a stale dashboard.
    database_target: str


# -- account setup and sign-in ----------------------------------------------
#
# Accounts are provisioned by the facility from a TrackMan roster export, so
# there is no "register" request: an athlete proves which provisioned account
# is theirs, then chooses a password for it.


class EmailIn(BaseModel):
    """Shared email field.

    Validated for shape only. Whether the address exists is a database
    question, answered by the endpoint -- and the answer is deliberately
    different for setup ("email does not match") and for sign-in (which says
    nothing).
    """

    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def _looks_like_an_address(cls, value: str) -> str:
        candidate = value.strip().lower()
        local, _, domain = candidate.partition("@")
        if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("that is not an email address")
        return candidate


class ActivationLookupIn(EmailIn):
    #: Required only when the deployment's signup gate is "code".
    code: str | None = Field(default=None, max_length=64)


class ActivationTargetOut(ApiModel):
    """What the password screen is told. Nothing the address did not imply."""

    email: str
    first_name: str
    requires_code: bool
    #: The server's password rules, in the server's words, so the form cannot
    #: show requirements that disagree with the ones actually enforced.
    password_rules: list[str]


class ActivationCompleteIn(ActivationLookupIn):
    # Capped above the policy maximum rather than at it, so an over-long
    # password gets the policy's explanation instead of a schema rejection.
    password: str = Field(min_length=1, max_length=256)
    password_confirmation: str = Field(min_length=1, max_length=256)


class LoginIn(EmailIn):
    password: str = Field(min_length=1, max_length=256)


class SignInOut(ApiModel):
    """A new session. The token is the only copy -- it is not stored anywhere."""

    token: str
    expires_at: datetime
    role: Role
    display_name: str


# -- performance over a period ----------------------------------------------


class TrendBucketOut(ApiModel):
    """One point on the trend.

    Every measurement is nullable and `sessions` says why. A bucket with no
    session is kept rather than dropped, and the client must render it as a gap:
    the athlete did not hit zero, they did not bat.
    """

    start: date
    end: date
    label: str
    sessions: int
    pitches_faced: int
    batted_balls: int
    best_exit_velocity_mph: float | None
    average_exit_velocity_mph: float | None
    sweet_spot_rate: float | None


class PeriodComparisonOut(ApiModel):
    """A headline number against the equally-long window before it."""

    current: float | None
    previous: float | None
    delta: float | None
    percent_change: float | None
    current_sample: int
    previous_sample: int


class HittingPeriodSummaryOut(ApiModel):
    """How an athlete has hit over a window of time."""

    player: PlayerSummary
    range: TimeRange
    start: date
    end: date
    #: "day" | "week" | "month" -- how the window was cut up, derived from its
    #: length so the client never has to choose a combination that makes no sense.
    grain: str
    grain_label: str

    sessions: int
    first_session: date | None
    last_session: date | None
    #: False when nothing was recorded in this window. The client shows that
    #: rather than a page of dashes.
    has_data: bool
    #: False when there is one session: a measurement, not a trend.
    has_trend: bool

    pitches_faced: int
    batted_balls: int
    measured_rate: float | None
    best_exit_velocity_mph: float | None
    average_exit_velocity_mph: float | None
    average_launch_angle_deg: float | None
    sweet_spot_count: int
    sweet_spot_rate: float | None
    average_pitch_velocity_mph: float | None

    best_exit_velocity_change: PeriodComparisonOut
    average_exit_velocity_change: PeriodComparisonOut

    buckets: list[TrendBucketOut]


# -- screenshot conversion ---------------------------------------------------


class ConversionProblemOut(ApiModel):
    """Something the reader would not accept, and where."""

    event_number: int | None
    column: str | None
    message: str
    #: False for things worth knowing that change no value -- chiefly a dash
    #: OCR did not emit, which reads as "no measurement" either way.
    blocking: bool


class ScreenshotConversionOut(ApiModel):
    """The result of turning screenshots into a CSV."""

    pitches: int
    batted_balls: int
    first_pitch: int | None
    last_pitch: int | None
    #: The athlete named in the table's own Batter row, when it was on screen.
    #: Advisory: the account the pitches are filed under comes from the form.
    batter_name_in_image: str | None
    #: True when every pitch read cleanly. False means rows were withheld.
    ok: bool
    problems: list[ConversionProblemOut]
    #: Where the CSV and the screenshots were archived.
    csv_key: str | None
    image_keys: list[str]
    #: The CSV itself, so a coach can check it before anything is imported.
    csv_text: str
    #: Set when the CSV was also run through ingestion.
    imported: ImportResultOut | None = None
