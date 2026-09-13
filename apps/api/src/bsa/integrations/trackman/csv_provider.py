"""CSV ingestion -- the first production TrackMan path.

Handles an event export where each row is one tracked pitch and the batted-ball
columns are populated only when the ball was put in play.

Parsing rules, in order of importance:

  * Never guess. An unrecognized header fails the file; an unparseable value
    fails its row, with a reason recorded.
  * Never silently drop. Every rejected row produces a `RowIssue`.
  * Never trust units. Every number goes through `bsa.core.units.convert`.
  * Never resolve athletes here. The parser reports the vendor's id; mapping it
    to one of our players is a database concern and happens downstream.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from bsa.core.logging import get_logger
from bsa.core.units import UnitConversionError, convert
from bsa.domain.enums import ImportIssueCode, SourceStatus
from bsa.domain.vocabulary import STRIKE_CALLS, PitchCall
from bsa.integrations.trackman.mapping import (
    ColumnMap,
    NumericColumn,
    UnknownSchemaError,
    detect_schema,
    normalize_batted_ball_type,
    normalize_pitch_call,
    normalize_pitch_type,
)
from bsa.integrations.trackman.schema import (
    ParsedHit,
    ParsedPitch,
    ParsedSession,
    ParseResult,
    RowIssue,
    SourcePayload,
)

log = get_logger(__name__)

#: Spellings a vendor may use for "no reading". Distinct from 0.
_NULLISH = {"", "na", "n/a", "null", "none", "nan", "-", "undefined"}


def _clean(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    return None if value.lower() in _NULLISH else value


def _parse_float(raw: str | None) -> float | None:
    text = _clean(raw)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(raw: str | None) -> int | None:
    value = _parse_float(raw)
    return None if value is None else int(value)


def _parse_date(raw: str | None) -> date | None:
    text = _clean(raw)
    if text is None:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_datetime(raw: str | None) -> datetime | None:
    """Parse a timestamp, assuming UTC when no offset is given.

    The assumption is explicit rather than incidental: a naive timestamp stored
    against a timezone-aware column would otherwise be interpreted by whatever
    the server's locale happens to be.
    """
    text = _clean(raw)
    if text is None:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%m/%d/%Y %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


class TrackmanCsvProvider:
    """Parses TrackMan-shaped CSV exports.

    Discovery walks a directory; in production the same class serves uploads,
    where the caller supplies the payload directly.
    """

    name = "trackman"

    def __init__(self, source_dir: Path | None = None) -> None:
        self.source_dir = Path(source_dir) if source_dir else None

    # -- discovery / retrieval ------------------------------------------------

    def discover_sessions(
        self, *, since: date | None = None, until: date | None = None
    ) -> Iterable[str]:
        if self.source_dir is None or not self.source_dir.exists():
            return []
        return sorted(str(p) for p in self.source_dir.glob("*.csv"))

    def fetch_payload(self, reference: str) -> SourcePayload:
        path = Path(reference)
        return SourcePayload(data=path.read_bytes(), filename=path.name, import_type="csv_file")

    # -- parsing --------------------------------------------------------------

    def parse(self, payload: SourcePayload) -> ParseResult:
        result = ParseResult()

        try:
            text = payload.data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            result.issues.append(
                RowIssue(0, ImportIssueCode.SCHEMA_UNKNOWN, f"file is not valid UTF-8: {exc}")
            )
            return result

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            result.issues.append(
                RowIssue(0, ImportIssueCode.SCHEMA_UNKNOWN, "file has no header row")
            )
            return result

        try:
            column_map = detect_schema(list(reader.fieldnames))
        except UnknownSchemaError as exc:
            result.issues.append(RowIssue(0, ImportIssueCode.SCHEMA_UNKNOWN, str(exc)))
            return result

        sessions: dict[str, ParsedSession] = {}

        # `start=2` -- row 1 is the header, so these numbers match what an
        # operator sees when they open the file.
        for row_number, row in enumerate(reader, start=2):
            result.rows_total += 1
            if self._parse_row(row, row_number, column_map, sessions, result):
                result.rows_accepted += 1

        result.sessions = list(sessions.values())
        for session in result.sessions:
            timestamps = [p.event_at for p in session.pitches if p.event_at]
            if timestamps:
                session.started_at = min(timestamps)
                session.ended_at = max(timestamps)

        log.info(
            "trackman.csv.parsed",
            schema=column_map.version,
            filename=payload.filename,
            sessions=len(result.sessions),
            rows_total=result.rows_total,
            rows_rejected=result.rows_rejected,
        )
        return result

    def _parse_row(
        self,
        row: dict[str, str],
        row_number: int,
        cmap: ColumnMap,
        sessions: dict[str, ParsedSession],
        result: ParseResult,
    ) -> bool:
        session_uid = _clean(row.get(cmap.session_id))
        event_uid = _clean(row.get(cmap.pitch_id))

        if not session_uid or not event_uid:
            missing = cmap.session_id if not session_uid else cmap.pitch_id
            result.issues.append(
                RowIssue(
                    row_number,
                    ImportIssueCode.MISSING_REQUIRED_FIELD,
                    f"required column {missing!r} is empty",
                    field=missing,
                )
            )
            return False

        session_date = _parse_date(row.get(cmap.session_date))
        if session_date is None:
            result.issues.append(
                RowIssue(
                    row_number,
                    ImportIssueCode.INVALID_VALUE,
                    f"unparseable session date {row.get(cmap.session_date)!r}",
                    field=cmap.session_date,
                )
            )
            return False

        session = sessions.get(session_uid)
        if session is None:
            session = ParsedSession(
                external_session_id=session_uid,
                session_date=session_date,
                source_status=self._read_source_status(row, cmap),
                session_type=_clean(row.get(cmap.session_type)) if cmap.session_type else None,
                venue=_clean(row.get(cmap.venue)) if cmap.venue else None,
                metadata={"schema_version": cmap.version},
            )
            sessions[session_uid] = session
        elif session.session_date != session_date:
            # Two different dates under one session id means the file is not
            # describing what it claims to. Better to reject the row than to
            # let a session silently span days.
            result.issues.append(
                RowIssue(
                    row_number,
                    ImportIssueCode.AMBIGUOUS_SESSION,
                    f"session {session_uid!r} already seen with date {session.session_date}, "
                    f"row reports {session_date}",
                    field=cmap.session_date,
                )
            )
            return False

        training_context = self._read_training_context(row, cmap)
        event_at = _parse_datetime(row.get(cmap.event_timestamp)) if cmap.event_timestamp else None

        emitted = self._maybe_append_pitch(
            row, row_number, cmap, session, result, training_context, event_at, event_uid
        )
        emitted |= self._maybe_append_hit(
            row, row_number, cmap, session, result, training_context, event_at, event_uid
        )

        if not emitted:
            result.issues.append(
                RowIssue(
                    row_number,
                    ImportIssueCode.MISSING_REQUIRED_FIELD,
                    "row carries neither a pitcher id nor a measured batted ball",
                    field=cmap.pitcher_id,
                )
            )
            return False
        return True

    def _maybe_append_pitch(
        self,
        row: dict[str, str],
        row_number: int,
        cmap: ColumnMap,
        session: ParsedSession,
        result: ParseResult,
        training_context: dict[str, Any],
        event_at: datetime | None,
        event_uid: str,
    ) -> bool:
        """Emit a pitch event when the row names who threw it.

        A pitcher id is NOT required of every row: machine-fed cage work has a
        batter and no pitcher, and rejecting those rows would discard real
        batted-ball data because nobody threw the pitch.
        """
        pitcher_id = _clean(row.get(cmap.pitcher_id))
        if not pitcher_id:
            return False

        values, unit_issues = self._read_numeric(row, cmap.pitch_numeric, row_number, cmap.version)
        result.issues.extend(unit_issues)

        pitch_call = normalize_pitch_call(row.get(cmap.pitch_call) if cmap.pitch_call else None)
        session.pitches.append(
            ParsedPitch(
                external_event_id=event_uid,
                external_player_id=pitcher_id,
                external_player_name=(
                    _clean(row.get(cmap.pitcher_name)) if cmap.pitcher_name else None
                ),
                pitch_number=_parse_int(row.get(cmap.pitch_number)) if cmap.pitch_number else None,
                event_at=event_at,
                pitch_type=normalize_pitch_type(
                    row.get(cmap.tagged_pitch_type) if cmap.tagged_pitch_type else None
                ),
                auto_pitch_type=normalize_pitch_type(
                    row.get(cmap.auto_pitch_type) if cmap.auto_pitch_type else None
                ),
                pitch_call=pitch_call,
                is_strike=self._is_strike(pitch_call),
                training_context=training_context,
                source_row_number=row_number,
                **values,
            )
        )
        return True

    def _maybe_append_hit(
        self,
        row: dict[str, str],
        row_number: int,
        cmap: ColumnMap,
        session: ParsedSession,
        result: ParseResult,
        training_context: dict[str, Any],
        event_at: datetime | None,
        event_uid: str,
    ) -> bool:
        """Emit a batted-ball event only when the row actually measured one."""
        values, unit_issues = self._read_numeric(row, cmap.hit_numeric, row_number, cmap.version)
        result.issues.extend(unit_issues)

        # Exit velocity is the anchor: without it there is no batted ball worth
        # recording, and a row with only a launch angle is a tracking remnant.
        if values.get("exit_velocity_mph") is None:
            return False

        batter_id = _clean(row.get(cmap.batter_id)) if cmap.batter_id else None
        if not batter_id:
            result.issues.append(
                RowIssue(
                    row_number,
                    ImportIssueCode.MISSING_REQUIRED_FIELD,
                    "row reports a batted ball but no batter id; hit not recorded",
                    field=cmap.batter_id or "BatterId",
                )
            )
            return False

        session.hits.append(
            ParsedHit(
                external_event_id=event_uid,
                external_player_id=batter_id,
                external_player_name=(
                    _clean(row.get(cmap.batter_name)) if cmap.batter_name else None
                ),
                linked_pitch_external_id=event_uid,
                event_at=event_at,
                batted_ball_type=normalize_batted_ball_type(
                    row.get(cmap.batted_ball_type) if cmap.batted_ball_type else None
                ),
                training_context=training_context,
                source_row_number=row_number,
                **values,
            )
        )
        return True

    def _read_numeric(
        self,
        row: dict[str, str],
        columns: dict[str, NumericColumn],
        row_number: int,
        schema_version: str,
    ) -> tuple[dict[str, Any], list[RowIssue]]:
        """Read, convert and range-check measured columns.

        A value outside its plausible range is discarded with an issue rather
        than stored: an impossible reading that reaches the metric engine can
        become a permanent personal record.
        """
        # Keyed by destination attribute name, so the type is necessarily dynamic.
        values: dict[str, Any] = {}
        issues: list[RowIssue] = []

        for target, column in columns.items():
            raw = _parse_float(row.get(column.source))
            if raw is None:
                values[target] = None
                continue
            try:
                converted = convert(raw, column.unit.value, column.unit)
            except UnitConversionError as exc:
                issues.append(
                    RowIssue(
                        row_number,
                        ImportIssueCode.INVALID_UNIT,
                        str(exc),
                        field=column.source,
                        context={"schema_version": schema_version},
                    )
                )
                values[target] = None
                continue

            if (column.min_value is not None and converted < column.min_value) or (
                column.max_value is not None and converted > column.max_value
            ):
                issues.append(
                    RowIssue(
                        row_number,
                        ImportIssueCode.INVALID_VALUE,
                        f"{column.source}={converted:g}{column.unit.value} is outside the "
                        f"plausible range [{column.min_value}, {column.max_value}]; discarded",
                        field=column.source,
                        context={"value": converted},
                    )
                )
                values[target] = None
                continue

            values[target] = converted

        return values, issues

    def _read_training_context(self, row: dict[str, str], cmap: ColumnMap) -> dict[str, Any]:
        """Collect coach-supplied training context.

        Only non-empty values are kept, so a JSONB payload of nulls does not
        make every pitch look annotated when it is not.
        """
        context: dict[str, Any] = {}
        for source, key in cmap.training_context.items():
            value = _clean(row.get(source))
            if value is None:
                continue
            if key == "tags":
                context[key] = [t.strip() for t in value.split("|") if t.strip()]
            elif key == "ball_weight_oz":
                weight = _parse_float(value)
                if weight is not None:
                    context[key] = weight
            else:
                context[key] = value
        return context

    def _read_source_status(self, row: dict[str, str], cmap: ColumnMap) -> SourceStatus:
        """Default to PRELIMINARY when the source says nothing.

        The conservative direction: data we later learn is verified can be
        promoted, but a preliminary value labelled verified is a lie the coach
        has no way to detect.
        """
        if not cmap.source_status:
            return SourceStatus.PRELIMINARY
        raw = (_clean(row.get(cmap.source_status)) or "").upper()
        return SourceStatus.VERIFIED if raw == "VERIFIED" else SourceStatus.PRELIMINARY

    @staticmethod
    def _is_strike(pitch_call: str | None) -> bool | None:
        if pitch_call is None:
            return None
        try:
            call = PitchCall(pitch_call)
        except ValueError:
            return None
        if call in (PitchCall.IN_PLAY, PitchCall.HIT_BY_PITCH, PitchCall.UNDEFINED):
            # Not a strike and not a ball -- returning False would understate
            # strike percentage, so the event is excluded from the metric.
            return None
        return call in STRIKE_CALLS
