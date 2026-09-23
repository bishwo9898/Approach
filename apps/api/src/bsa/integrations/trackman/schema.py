"""Vendor-neutral parse results.

A TrackMan adapter's job ends here: it produces these objects and nothing
downstream knows whether the bytes came from a CSV, an FTP drop, the Data API or
a webhook. Values on these objects are already in canonical units.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from bsa.domain.enums import ImportIssueCode, SourceStatus


@dataclass(slots=True)
class RowIssue:
    """A source row that could not be fully accepted.

    Collected rather than raised: one unusable row must not cost the facility
    the other four hundred in the file.
    """

    row_number: int
    code: ImportIssueCode
    message: str
    #: Source column the issue relates to. Shadows `dataclasses.field` inside
    #: this class body, hence the qualified call below.
    field: str | None = None
    context: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclass(slots=True)
class ParsedPitch:
    external_event_id: str
    #: The pitcher's vendor identity. None when the export does not name a
    #: pitcher we could roster -- machine work, or an opposing pitcher.
    external_player_id: str | None
    external_player_name: str | None = None

    #: The batter who faced this pitch. A live at-bat export is about the
    #: hitter, so this is often the only rostered athlete on the row.
    external_batter_id: str | None = None
    external_batter_name: str | None = None
    #: What the batter did with it: TAKEN, SWING_MISS or IN_PLAY.
    swing_result: str | None = None
    pitch_number: int | None = None
    event_at: datetime | None = None

    pitch_type: str | None = None
    auto_pitch_type: str | None = None
    pitch_call: str | None = None
    is_strike: bool | None = None

    velocity_mph: float | None = None
    spin_rate_rpm: float | None = None
    spin_axis_deg: float | None = None
    horizontal_break_in: float | None = None
    vertical_break_in: float | None = None
    release_height_ft: float | None = None
    release_side_ft: float | None = None
    extension_ft: float | None = None
    plate_location_height_ft: float | None = None
    plate_location_side_ft: float | None = None
    vertical_approach_angle_deg: float | None = None
    horizontal_approach_angle_deg: float | None = None

    training_context: dict[str, Any] = field(default_factory=dict)
    source_row_number: int | None = None


@dataclass(slots=True)
class ParsedHit:
    external_event_id: str
    external_player_id: str
    external_player_name: str | None = None
    #: Set when the batted ball came off a pitch in the same file, so the two
    #: events can be linked after both are persisted.
    linked_pitch_external_id: str | None = None
    swing_number: int | None = None
    event_at: datetime | None = None

    exit_velocity_mph: float | None = None
    launch_angle_deg: float | None = None
    launch_direction_deg: float | None = None
    distance_ft: float | None = None
    hang_time_s: float | None = None
    hit_spin_rate_rpm: float | None = None
    contact_position_x_ft: float | None = None
    contact_position_y_ft: float | None = None
    contact_position_z_ft: float | None = None
    batted_ball_type: str | None = None

    training_context: dict[str, Any] = field(default_factory=dict)
    source_row_number: int | None = None


@dataclass(slots=True)
class ParsedSession:
    external_session_id: str
    session_date: date
    source_status: SourceStatus = SourceStatus.PRELIMINARY
    started_at: datetime | None = None
    ended_at: datetime | None = None
    session_type: str | None = None
    venue: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    pitches: list[ParsedPitch] = field(default_factory=list)
    hits: list[ParsedHit] = field(default_factory=list)


@dataclass(slots=True)
class ParseResult:
    """Everything one source payload yielded, including what it failed to yield."""

    sessions: list[ParsedSession] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)
    rows_total: int = 0
    rows_accepted: int = 0

    @property
    def rows_rejected(self) -> int:
        return self.rows_total - self.rows_accepted


@dataclass(slots=True)
class SourcePayload:
    """Raw bytes plus how they reached us, before any parsing."""

    data: bytes
    filename: str | None = None
    import_type: str = "csv_upload"
    external_session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
