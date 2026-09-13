"""TrackMan CSV parsing.

Exercised against the same synthetic generator the seed and samples use, so a
change to the documented schema breaks these tests rather than production.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from bsa.domain.enums import ImportIssueCode, SourceStatus
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.mapping import (
    UnknownSchemaError,
    detect_schema,
    normalize_pitch_type,
)
from bsa.integrations.trackman.schema import SourcePayload
from bsa.scripts.synthetic import ATHLETES, build_day_csv

SESSION_DATE = date(2026, 9, 12)
HISTORY_START = date(2026, 6, 1)


def parse(data: bytes):  # type: ignore[no-untyped-def]
    return TrackmanCsvProvider().parse(SourcePayload(data=data, filename="test.csv"))


def edit_rows(data: bytes, mutate) -> bytes:  # type: ignore[no-untyped-def]
    """Rewrite rows through the csv module.

    Splitting a TrackMan row on "," by hand misaligns every column after
    PitcherName, which is quoted because it contains a comma ("Jones, Ryan").
    """
    reader = csv.DictReader(io.StringIO(data.decode()))
    fieldnames = list(reader.fieldnames or [])
    rows = [dict(r) for r in reader]
    mutate(rows)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def test_parses_a_well_formed_export() -> None:
    pitcher = ATHLETES[0]
    result = parse(build_day_csv([pitcher], SESSION_DATE, history_start=HISTORY_START))

    assert len(result.sessions) == 1
    session = result.sessions[0]
    assert session.session_date == SESSION_DATE
    assert session.source_status is SourceStatus.PRELIMINARY
    assert len(session.pitches) == result.rows_total
    assert result.rows_rejected == 0
    assert not result.issues

    pitch = session.pitches[0]
    assert pitch.external_player_id == pitcher.external_id
    assert pitch.velocity_mph is not None and 40 < pitch.velocity_mph < 110
    assert pitch.training_context["drill"]
    assert pitch.training_context["tags"] == ["bullpen", "tracked"]


def test_session_start_and_end_derive_from_event_timestamps() -> None:
    result = parse(build_day_csv([ATHLETES[0]], SESSION_DATE, history_start=HISTORY_START))
    session = result.sessions[0]

    assert session.started_at is not None and session.ended_at is not None
    assert session.started_at <= session.ended_at


def test_verified_flag_is_read_from_the_source() -> None:
    result = parse(
        build_day_csv([ATHLETES[0]], SESSION_DATE, history_start=HISTORY_START, verified=True)
    )

    assert result.sessions[0].source_status is SourceStatus.VERIFIED


def test_missing_status_defaults_to_preliminary() -> None:
    """Conservative direction: never label unverified data as verified."""

    def blank_status(rows):  # type: ignore[no-untyped-def]
        for row in rows:
            row["SourceStatus"] = ""

    data = edit_rows(
        build_day_csv([ATHLETES[0]], SESSION_DATE, history_start=HISTORY_START),
        blank_status,
    )

    assert parse(data).sessions[0].source_status is SourceStatus.PRELIMINARY


def test_machine_fed_cage_rows_produce_hits_without_a_pitcher() -> None:
    """A pitching machine is not an athlete and must not be invented as one."""
    hitter = next(a for a in ATHLETES if a.hits)
    result = parse(build_day_csv([hitter], SESSION_DATE, history_start=HISTORY_START))

    session = result.sessions[0]
    assert session.pitches == []
    assert len(session.hits) == result.rows_total
    assert all(h.external_player_id == hitter.external_id for h in session.hits)
    assert result.rows_rejected == 0


def test_rows_missing_required_ids_are_rejected_individually() -> None:
    """One bad row must not cost the facility the rest of the file."""

    def drop_session_id(rows):  # type: ignore[no-untyped-def]
        rows[0]["SessionUID"] = ""

    original = build_day_csv([ATHLETES[0]], SESSION_DATE, history_start=HISTORY_START)
    total_rows = len(original.decode().splitlines()) - 1

    result = parse(edit_rows(original, drop_session_id))

    assert result.rows_rejected == 1
    assert result.rows_accepted == total_rows - 1
    assert result.issues[0].code is ImportIssueCode.MISSING_REQUIRED_FIELD
    # The good rows still landed.
    assert len(result.sessions[0].pitches) == result.rows_accepted


def test_unparseable_date_rejects_only_that_row() -> None:
    def break_date(rows):  # type: ignore[no-untyped-def]
        rows[0]["SessionDate"] = "not-a-date"

    result = parse(
        edit_rows(
            build_day_csv([ATHLETES[0]], SESSION_DATE, history_start=HISTORY_START),
            break_date,
        )
    )

    assert result.rows_rejected == 1
    assert result.issues[0].code is ImportIssueCode.INVALID_VALUE


def test_impossible_velocity_is_discarded_with_an_issue() -> None:
    """The row survives; the implausible measurement does not."""

    def implausible_velocity(rows):  # type: ignore[no-untyped-def]
        rows[0]["RelSpeed"] = "268.0"

    result = parse(
        edit_rows(
            build_day_csv([ATHLETES[0]], SESSION_DATE, history_start=HISTORY_START),
            implausible_velocity,
        )
    )

    assert result.rows_rejected == 0
    assert any(i.code is ImportIssueCode.INVALID_VALUE for i in result.issues)
    assert result.sessions[0].pitches[0].velocity_mph is None


def test_unknown_header_fails_the_whole_file() -> None:
    """A misread column is worse than a rejected file."""
    result = parse(b"Alpha,Beta\n1,2\n")

    assert result.sessions == []
    assert result.issues[0].code is ImportIssueCode.SCHEMA_UNKNOWN


def test_empty_file_is_reported_not_crashed() -> None:
    result = parse(b"")

    assert result.sessions == []
    assert result.issues[0].code is ImportIssueCode.SCHEMA_UNKNOWN


def test_pitch_type_aliases_normalize_to_our_vocabulary() -> None:
    for alias in ("Fastball", "FourSeamFastBall", "four-seam", "FF", "fb"):
        assert normalize_pitch_type(alias) == "FASTBALL"


def test_unknown_pitch_label_is_preserved_not_bucketed() -> None:
    """Forcing it into OTHER would hide a mapping we still owe."""
    assert normalize_pitch_type("Screwball") == "SCREWBALL"
    assert normalize_pitch_type("") is None


def test_schema_detection_requires_every_required_column() -> None:
    assert (
        detect_schema(["SessionUID", "SessionDate", "PitchUID", "PitcherId", "Extra"]).version
        == "synthetic.v1"
    )

    try:
        detect_schema(["SessionUID", "SessionDate"])
    except UnknownSchemaError as exc:
        assert "no registered TrackMan schema" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected UnknownSchemaError")
