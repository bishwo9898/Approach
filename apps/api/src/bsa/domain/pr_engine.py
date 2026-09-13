"""The personal-record engine.

Design decision that everything else rests on: a PR progression is *derived*,
never incremented.

`compute_progression` is a pure function from the player's full ordered
observation series to the complete list of moments the record was broken. It is
not "compare the new value to the stored PR and maybe write a row".

That choice buys three properties that the incremental version cannot have:

  * **Idempotency.** Re-importing a session yields a byte-identical
    progression, so no duplicate PR is ever announced.
  * **Correct reconciliation.** When TrackMan republishes a session as VERIFIED
    with a lower velocity, the record that session claimed disappears and the
    earlier record is restored -- automatically, because the whole series is
    recomputed rather than patched.
  * **Testability.** The hardest logic in the system has no database in it.

A PR *rule* is not a separate configurable object: it is a metric definition
plus a direction. Splitting them would let the two drift, and a rule whose
filters disagree with its metric's filters compares values that were never
comparable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from bsa.domain.enums import RecordDirection, SourceStatus


@dataclass(frozen=True, slots=True)
class ObservationPoint:
    """One session-scope metric value, as evidence for a record."""

    session_id: uuid.UUID
    session_date: date
    value: float
    sample_size: int
    source_status: SourceStatus
    achieved_at: datetime | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RecordRule:
    """When an observation is allowed to set a record."""

    direction: RecordDirection
    #: Observations backed by fewer events than this cannot set a record, even
    #: though they are still stored and charted. One freak reading should not
    #: become a number the athlete is measured against for a year.
    min_sample_size: int = 1

    @property
    def tracks_records(self) -> bool:
        return self.direction is not RecordDirection.NONE


@dataclass(frozen=True, slots=True)
class RecordBreak:
    """A moment the record was broken."""

    session_id: uuid.UUID
    previous_value: float | None
    new_value: float
    achieved_on: date
    achieved_at: datetime | None
    sample_size: int
    source_status: SourceStatus
    context: dict[str, Any]

    @property
    def delta(self) -> float | None:
        """Signed change. Negative is an improvement for LOWER_IS_BETTER."""
        if self.previous_value is None:
            return None
        return round(self.new_value - self.previous_value, 4)


def _sort_key(point: ObservationPoint) -> tuple[date, str, str]:
    """Chronological, with a deterministic tiebreak.

    Two sessions on the same date with no timestamps must still order the same
    way on every run, or the progression would depend on row order. The session
    UUID is arbitrary but stable, which is all that is required.
    """
    timestamp = point.achieved_at.isoformat() if point.achieved_at else ""
    return (point.session_date, timestamp, str(point.session_id))


def _is_improvement(direction: RecordDirection, candidate: float, incumbent: float) -> bool:
    """Strictly better. Equalling a record does not break it."""
    if direction is RecordDirection.HIGHER_IS_BETTER:
        return candidate > incumbent
    if direction is RecordDirection.LOWER_IS_BETTER:
        return candidate < incumbent
    return False


def compute_progression(
    rule: RecordRule, observations: list[ObservationPoint]
) -> list[RecordBreak]:
    """Return every record break in the series, oldest first.

    Deterministic: the same observations always produce the same list,
    regardless of how many times ingestion has run.
    """
    if not rule.tracks_records:
        return []

    eligible = [o for o in observations if o.sample_size >= rule.min_sample_size]
    breaks: list[RecordBreak] = []
    incumbent: float | None = None

    for point in sorted(eligible, key=_sort_key):
        if incumbent is not None and not _is_improvement(rule.direction, point.value, incumbent):
            continue
        breaks.append(
            RecordBreak(
                session_id=point.session_id,
                previous_value=incumbent,
                new_value=point.value,
                achieved_on=point.session_date,
                achieved_at=point.achieved_at,
                sample_size=point.sample_size,
                source_status=point.source_status,
                context=dict(point.context),
            )
        )
        incumbent = point.value

    return breaks


def current_record(breaks: list[RecordBreak]) -> RecordBreak | None:
    """The standing record: the last break in the progression."""
    return breaks[-1] if breaks else None
