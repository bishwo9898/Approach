"""Personal record engine.

The highest-value tests in the repository: PR detection is the feature coaches
will trust most and the one where a silent bug is least likely to be noticed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from bsa.domain.enums import RecordDirection, SourceStatus
from bsa.domain.pr_engine import (
    ObservationPoint,
    RecordRule,
    compute_progression,
    current_record,
)

HIGHER = RecordRule(RecordDirection.HIGHER_IS_BETTER)
LOWER = RecordRule(RecordDirection.LOWER_IS_BETTER)


def point(
    value: float,
    day: str,
    *,
    sample: int = 10,
    session_id: uuid.UUID | None = None,
    status: SourceStatus = SourceStatus.PRELIMINARY,
    at: datetime | None = None,
) -> ObservationPoint:
    return ObservationPoint(
        session_id=session_id or uuid.uuid4(),
        session_date=date.fromisoformat(day),
        value=value,
        sample_size=sample,
        source_status=status,
        achieved_at=at,
    )


def test_first_observation_creates_a_record() -> None:
    breaks = compute_progression(HIGHER, [point(86.6, "2026-01-10")])

    assert len(breaks) == 1
    assert breaks[0].previous_value is None
    assert breaks[0].new_value == 86.6
    # No delta on a first record: there was nothing to improve on, and
    # reporting +86.6 would be nonsense.
    assert breaks[0].delta is None


def test_higher_value_breaks_the_record() -> None:
    breaks = compute_progression(HIGHER, [point(86.6, "2026-01-10"), point(87.3, "2026-01-17")])

    assert [b.new_value for b in breaks] == [86.6, 87.3]
    assert breaks[1].previous_value == 86.6
    assert breaks[1].delta == pytest.approx(0.7)
    assert current_record(breaks) is not None
    assert current_record(breaks).new_value == 87.3  # type: ignore[union-attr]


def test_lower_value_does_not_break_the_record() -> None:
    breaks = compute_progression(
        HIGHER,
        [point(87.3, "2026-01-10"), point(85.1, "2026-01-17"), point(86.9, "2026-01-24")],
    )

    assert [b.new_value for b in breaks] == [87.3]
    assert current_record(breaks).new_value == 87.3  # type: ignore[union-attr]


def test_equalling_a_record_does_not_break_it() -> None:
    """A tie is not an achievement. It must not produce a second announcement."""
    breaks = compute_progression(HIGHER, [point(87.3, "2026-01-10"), point(87.3, "2026-01-17")])

    assert len(breaks) == 1
    assert breaks[0].achieved_on == date(2026, 1, 10)


def test_lower_is_better_metric() -> None:
    breaks = compute_progression(
        LOWER, [point(7.2, "2026-01-10"), point(6.8, "2026-01-17"), point(7.0, "2026-01-24")]
    )

    assert [b.new_value for b in breaks] == [7.2, 6.8]
    # An improvement on a lower-is-better metric is a negative delta. Reporting
    # it as positive would misrepresent the direction of the change.
    assert breaks[1].delta == pytest.approx(-0.4)


def test_direction_none_produces_no_records() -> None:
    """Volume metrics are tracked but are not achievements."""
    rule = RecordRule(RecordDirection.NONE)

    assert compute_progression(rule, [point(40, "2026-01-10"), point(55, "2026-01-17")]) == []


def test_minimum_sample_size_is_enforced() -> None:
    """A freak reading off two pitches must not become the standing record."""
    rule = RecordRule(RecordDirection.HIGHER_IS_BETTER, min_sample_size=5)
    breaks = compute_progression(
        rule, [point(99.0, "2026-01-10", sample=2), point(88.0, "2026-01-17", sample=20)]
    )

    assert [b.new_value for b in breaks] == [88.0]


def test_progression_is_chronological_regardless_of_input_order() -> None:
    unordered = [
        point(88.0, "2026-03-01"),
        point(86.0, "2026-01-01"),
        point(87.0, "2026-02-01"),
    ]

    breaks = compute_progression(HIGHER, unordered)

    assert [b.achieved_on.isoformat() for b in breaks] == [
        "2026-01-01",
        "2026-02-01",
        "2026-03-01",
    ]
    assert [b.new_value for b in breaks] == [86.0, 87.0, 88.0]


def test_same_day_sessions_order_by_timestamp() -> None:
    morning = point(86.0, "2026-01-10", at=datetime(2026, 1, 10, 9, tzinfo=UTC))
    evening = point(87.5, "2026-01-10", at=datetime(2026, 1, 10, 18, tzinfo=UTC))

    breaks = compute_progression(HIGHER, [evening, morning])

    assert [b.new_value for b in breaks] == [86.0, 87.5]


def test_progression_is_deterministic_across_runs() -> None:
    """The idempotency guarantee, at the engine level.

    Recomputing from the same observations must give byte-identical results, or
    re-importing a session would announce records the coach has already seen.
    """
    points = [point(86.6, "2026-01-10"), point(87.3, "2026-01-17"), point(87.1, "2026-01-24")]

    first = compute_progression(HIGHER, points)
    second = compute_progression(HIGHER, list(reversed(points)))

    assert first == second


def test_verified_correction_revokes_a_record() -> None:
    """Section 12's hard requirement, at the engine level.

    A preliminary session claimed a record at 88.0. The verified republish
    corrects it to 86.9, which no longer beats the standing 87.3. The record
    must disappear from the progression, not linger.
    """
    session_id = uuid.uuid4()
    preliminary = [
        point(87.3, "2026-01-10"),
        point(88.0, "2026-01-17", session_id=session_id),
    ]
    assert [b.new_value for b in compute_progression(HIGHER, preliminary)] == [87.3, 88.0]

    verified = [
        point(87.3, "2026-01-10"),
        point(86.9, "2026-01-17", session_id=session_id, status=SourceStatus.VERIFIED),
    ]

    breaks = compute_progression(HIGHER, verified)

    assert [b.new_value for b in breaks] == [87.3]
    assert current_record(breaks).new_value == 87.3  # type: ignore[union-attr]


def test_empty_series_has_no_record() -> None:
    assert compute_progression(HIGHER, []) == []
    assert current_record([]) is None
