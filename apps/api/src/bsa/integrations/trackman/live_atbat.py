"""Parser for TrackMan "live at-bat" exports.

A different report from the same vendor, not merely different column names, so
it gets its own parser rather than another set of knobs on `ColumnMap`.

Two things make it different from a session export, and both are worth stating
plainly because they bend rules stated elsewhere:

1. **It carries no athlete ids, only names.** Our rule is that athletes are
   never identified by name -- so the name is treated as the *vendor's*
   identity string (`name:mateo-rivera`) and still goes through the
   identity-resolution queue for a human to map once, exactly like a numeric
   vendor id. Nothing auto-matches. The uniqueness constraint still makes it
   impossible for one string to point at two athletes.

2. **It carries no session id and no year.** The session id is composed from
   the fields that identify the at-bat (athlete, opponent, date, time) so that
   re-importing the same export is idempotent. The missing year is inferred and
   the assumption is recorded on the session.

The subject of the report is the batter. The pitcher is usually an opponent we
do not roster, which is why `ParsedPitch.external_player_id` is optional.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime
from typing import Any

from bsa.core.logging import get_logger
from bsa.core.units import Unit, convert
from bsa.domain.enums import ImportIssueCode, SourceStatus, SwingResult
from bsa.integrations.trackman.schema import (
    ParsedHit,
    ParsedPitch,
    ParsedSession,
    ParseResult,
    RowIssue,
)

log = get_logger(__name__)

SCHEMA_VERSION = "trackman.live_atbat.v1"

#: Columns that must all be present for this to be a live at-bat export.
REQUIRED = frozenset(
    {
        "player_name",
        "opponent_name",
        "session_date_display",
        "event_number",
        "marker_shape",
        "pitch_speed_mph",
    }
)

#: Marker shape -> what the batter did.
#:
#: Read off the source export and confirmed against it: across 66 pitches,
#: `circle` never carried a batted ball (0/32), `crossed_circle` almost never
#: (1/13, a measured foul), and `square` usually did (15/21). The shapes encode
#: the batter's response, which is the single most useful thing in the file.
SWING_RESULTS: dict[str, SwingResult] = {
    "square": SwingResult.IN_PLAY,
    "crossed_circle": SwingResult.SWING_MISS,
    "circle": SwingResult.TAKEN,
}

_NULLISH = {"", "-", "na", "n/a", "null", "none", "nan"}


def matches(headers: list[str]) -> bool:
    return {h.strip() for h in headers} >= REQUIRED


def _clean(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    return None if value.lower() in _NULLISH else value


def _number(raw: str | None) -> float | None:
    text = _clean(raw)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def vendor_identity(name: str) -> str:
    """The vendor's identity string for an athlete it names but does not id.

    Prefixed so it is never mistaken for a real vendor id, and normalized so
    trivial spacing differences between exports do not create a second queue
    entry for the same person.
    """
    return f"name:{_slug(name)}"


def _parse_day(raw: str | None, *, today: date) -> tuple[date | None, bool]:
    """Parse a year-less display date such as "Sep 22".

    Returns the date and whether the year had to be inferred. A date that would
    land in the future is taken as last year's, which is the only reading that
    makes sense for a session that has already happened.
    """
    text = _clean(raw)
    if text is None:
        return None, False

    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date(), False
        except ValueError:
            continue

    for fmt in ("%b %d", "%B %d", "%b %d %Y", "%B %d %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.year != 1900:
            return parsed.date(), False
        candidate = date(today.year, parsed.month, parsed.day)
        if candidate > today:
            candidate = date(today.year - 1, parsed.month, parsed.day)
        return candidate, True

    return None, False


def _tilt_to_degrees(raw: str | None) -> float | None:
    """Convert a clock-face tilt ("1:15") to a spin axis in degrees.

    12:00 is 0 degrees and each hour is 30, which is the standard reading.
    """
    text = _clean(raw)
    if text is None or ":" not in text:
        return None
    hours, _, minutes = text.partition(":")
    try:
        h, m = int(hours), int(minutes)
    except ValueError:
        return None
    if not (0 <= h <= 12 and 0 <= m < 60):
        return None
    return ((h % 12) * 30.0) + (m * 0.5)


def _session_id(player: str, opponent: str, day: date, time_display: str | None) -> str:
    """Compose a stable session id from the fields that identify the at-bat.

    The export has none of its own, so re-importing the same file has to arrive
    at the same id or every import would create a duplicate session. Hashed to
    keep it short and free of punctuation.
    """
    parts = [_slug(player), _slug(opponent), day.isoformat(), _slug(time_display or "")]
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    return f"lab-{day.isoformat()}-{digest}"


def parse(text: str, *, today: date) -> ParseResult:
    """Parse a live at-bat export into vendor-neutral objects."""
    result = ParseResult()
    reader = csv.DictReader(io.StringIO(text))
    sessions: dict[str, ParsedSession] = {}

    for row_number, row in enumerate(reader, start=2):
        result.rows_total += 1

        player = _clean(row.get("player_name"))
        opponent = _clean(row.get("opponent_name")) or "Unknown"
        event = _clean(row.get("event_number"))

        if not player or not event:
            result.issues.append(
                RowIssue(
                    row_number,
                    ImportIssueCode.MISSING_REQUIRED_FIELD,
                    "row has no athlete name or no event number",
                    field="player_name" if not player else "event_number",
                )
            )
            continue

        day, inferred_year = _parse_day(row.get("session_date_display"), today=today)
        if day is None:
            result.issues.append(
                RowIssue(
                    row_number,
                    ImportIssueCode.INVALID_VALUE,
                    f"unreadable session date {row.get('session_date_display')!r}",
                    field="session_date_display",
                )
            )
            continue

        time_display = _clean(row.get("session_time_display"))
        session_uid = _session_id(player, opponent, day, time_display)

        session = sessions.get(session_uid)
        if session is None:
            session = ParsedSession(
                external_session_id=session_uid,
                session_date=day,
                # A live at-bat is not republished as verified, so it is what
                # it is. Labelled preliminary rather than claiming otherwise.
                source_status=SourceStatus.PRELIMINARY,
                session_type="LIVE_AT_BAT",
                metadata={
                    "schema_version": SCHEMA_VERSION,
                    "opponent_name": opponent,
                    "session_time_display": time_display,
                    "competition": _clean(row.get("competition")),
                    "pitch_set": _clean(row.get("pitch_set")),
                    "year_inferred": inferred_year,
                },
            )
            sessions[session_uid] = session

        marker = (_clean(row.get("marker_shape")) or "").lower()
        swing = SWING_RESULTS.get(marker)
        if marker and swing is None:
            result.issues.append(
                RowIssue(
                    row_number,
                    ImportIssueCode.INVALID_VALUE,
                    f"unrecognized marker shape {marker!r}; swing result not recorded",
                    field="marker_shape",
                )
            )

        velocity = _number(row.get("pitch_speed_mph"))
        session.pitches.append(
            ParsedPitch(
                external_event_id=event,
                # The opposing pitcher is named but not rostered, so no identity
                # is asserted for them. Naming them would put an opponent into
                # the athlete-mapping queue on every import.
                external_player_id=None,
                external_batter_id=vendor_identity(player),
                external_batter_name=player,
                swing_result=swing.value if swing else None,
                pitch_number=int(_number(event) or 0) or None,
                pitch_type=_clean(row.get("pitch_type")),
                velocity_mph=convert(velocity, "mph", Unit.MPH) if velocity else None,
                spin_rate_rpm=_number(row.get("total_spin_rpm")),
                spin_axis_deg=_tilt_to_degrees(row.get("tilt_clock")),
                release_height_ft=_number(row.get("release_height_ft")),
                vertical_break_in=_number(row.get("induced_vertical_movement_in")),
                horizontal_break_in=_number(row.get("horizontal_movement_in")),
                training_context=_training_context(row, opponent),
                source_row_number=row_number,
            )
        )

        exit_velocity = _number(row.get("exit_speed_mph"))
        if exit_velocity is not None:
            session.hits.append(
                ParsedHit(
                    external_event_id=event,
                    external_player_id=vendor_identity(player),
                    external_player_name=player,
                    linked_pitch_external_id=event,
                    exit_velocity_mph=exit_velocity,
                    launch_angle_deg=_number(row.get("launch_angle_deg")),
                    hit_spin_rate_rpm=_number(row.get("hit_spin_rate_rpm")),
                    batted_ball_type=_clean(row.get("hit_type")),
                    training_context=_training_context(row, opponent),
                    source_row_number=row_number,
                )
            )

        result.rows_accepted += 1

    result.sessions = list(sessions.values())
    log.info(
        "trackman.live_atbat.parsed",
        schema=SCHEMA_VERSION,
        sessions=len(result.sessions),
        rows_total=result.rows_total,
        rows_rejected=result.rows_rejected,
    )
    return result


def _training_context(row: dict[str, str], opponent: str) -> dict[str, Any]:
    context: dict[str, Any] = {"opponent": opponent}
    for source, key in (("competition", "competition"), ("pitch_set", "pitch_set")):
        value = _clean(row.get(source))
        if value:
            context[key] = value
    return context
