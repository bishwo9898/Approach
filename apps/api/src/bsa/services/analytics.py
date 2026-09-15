"""Read-side analytics for the dashboards.

Answers the questions the product exists to answer -- what is it now, how has it
moved, is it a record -- and nothing more. No interpretation, no prediction, no
risk language.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from bsa.core.clock import today_in
from bsa.db.models import (
    MetricDefinition,
    MetricObservation,
    PersonalRecord,
    Player,
    TrainingSession,
)
from bsa.db.repositories import imports as imports_repo
from bsa.db.repositories import metrics as metrics_repo
from bsa.db.repositories import players as players_repo
from bsa.db.repositories import records as records_repo
from bsa.db.repositories import sessions as sessions_repo
from bsa.db.repositories import sync as sync_repo
from bsa.domain.analytics import (
    Comparison,
    DateWindow,
    TimeRange,
    preceding_window,
    window_for,
)
from bsa.domain.enums import Aggregation, SourceStatus


@dataclass(slots=True)
class MetricSummary:
    """One headline metric with its movement and record."""

    definition: MetricDefinition
    latest: MetricObservation | None
    comparison: Comparison
    record: PersonalRecord | None


@dataclass(slots=True)
class PlayerOverview:
    player: Player
    last_session: TrainingSession | None
    sessions_in_window: int
    metrics: list[MetricSummary] = field(default_factory=list)


def _aggregate(values: list[tuple[float, int]], aggregation: Aggregation) -> float | None:
    """Roll session values up to a window using the metric's own aggregation.

    A window maximum is the max of its sessions; a window average is the mean of
    all qualifying events represented by its sessions. Session averages and
    rates must be weighted by sample size: a bullpen with 40 pitches is more
    evidence than one with 5. Using the metric's declared aggregation keeps the
    30-day number the same *kind* of number as the session number.
    """
    if not values:
        return None
    measurements = [value for value, _sample_size in values]
    match aggregation:
        case Aggregation.MAX:
            return max(measurements)
        case Aggregation.MIN:
            return min(measurements)
        case Aggregation.COUNT | Aggregation.SUM:
            return sum(measurements)
        case Aggregation.AVG | Aggregation.RATE:
            weighted = [(value, sample_size) for value, sample_size in values if sample_size > 0]
            total_sample = sum(sample_size for _value, sample_size in weighted)
            if total_sample == 0:
                return None
            return sum(value * sample_size for value, sample_size in weighted) / total_sample


def _window_source_status(observations: list[MetricObservation]) -> SourceStatus | None:
    """Conservatively label a rollup preliminary if any input is preliminary."""
    if not observations:
        return None
    if any(o.source_status is SourceStatus.PRELIMINARY for o in observations):
        return SourceStatus.PRELIMINARY
    return SourceStatus.VERIFIED


def _window_value(
    db: Session,
    player_id: uuid.UUID,
    definition: MetricDefinition,
    window: DateWindow,
) -> tuple[float | None, int, SourceStatus | None]:
    observations = metrics_repo.observations_in_window(
        db, player_id, definition.id, window.start, window.end
    )
    value = _aggregate([(o.value, o.sample_size) for o in observations], definition.aggregation)
    return (
        value,
        sum(o.sample_size for o in observations),
        _window_source_status(observations),
    )


def player_overview(
    db: Session,
    organization_id: uuid.UUID,
    player: Player,
    *,
    time_range: TimeRange = TimeRange.LAST_30,
    today: date | None = None,
    timezone_name: str | None = None,
    headline_only: bool = True,
) -> PlayerOverview:
    today = today or today_in(timezone_name)
    window = window_for(time_range, today)
    prior = preceding_window(window)

    definitions = metrics_repo.list_definitions(db, organization_id)
    if headline_only:
        definitions = [d for d in definitions if d.is_headline]

    latest_by_metric = metrics_repo.latest_observations(db, player.id, [d.id for d in definitions])
    sessions = sessions_repo.list_for_player(db, player.id, limit=200, since=window.start)

    summaries: list[MetricSummary] = []
    for definition in definitions:
        current, current_sample, current_status = _window_value(db, player.id, definition, window)
        previous, previous_sample, previous_status = _window_value(db, player.id, definition, prior)
        latest = latest_by_metric.get(definition.id)
        record = records_repo.get_current(db, player.id, definition.id)

        # A pitcher has no exit velocity and a hitter has no spin rate. Showing
        # every headline metric to every athlete fills the page with dashes and
        # buries the numbers that do apply, so metrics this athlete has never
        # produced any data for are omitted entirely.
        if latest is None and record is None and current is None:
            continue

        summaries.append(
            MetricSummary(
                definition=definition,
                latest=latest,
                comparison=Comparison(
                    current,
                    previous,
                    current_sample,
                    previous_sample,
                    current_status.value if current_status else None,
                    previous_status.value if previous_status else None,
                ),
                record=record,
            )
        )

    all_sessions = sessions_repo.list_for_player(db, player.id, limit=1)
    return PlayerOverview(
        player=player,
        last_session=all_sessions[0] if all_sessions else None,
        sessions_in_window=len(sessions),
        metrics=summaries,
    )


@dataclass(slots=True)
class MetricSeriesPoint:
    session_id: uuid.UUID | None
    observed_on: date
    value: float
    sample_size: int
    source_status: str


def metric_series(
    db: Session,
    player_id: uuid.UUID,
    definition: MetricDefinition,
    *,
    time_range: TimeRange = TimeRange.LAST_90,
    today: date | None = None,
    timezone_name: str | None = None,
) -> list[MetricSeriesPoint]:
    """Session-by-session progression for a chart."""
    today = today or today_in(timezone_name)
    window = window_for(time_range, today)
    observations = metrics_repo.session_observations_for_player(
        db,
        player_id,
        definition.id,
        since=None if time_range is TimeRange.ALL_TIME else window.start,
        until=window.end,
    )
    return [
        MetricSeriesPoint(
            session_id=o.session_id,
            observed_on=o.period_start,
            value=o.value,
            sample_size=o.sample_size,
            source_status=o.source_status.value,
        )
        for o in observations
    ]


@dataclass(slots=True)
class TodaySnapshot:
    on_date: date
    athletes_trained: int
    sessions: int
    tracked_events: int
    new_personal_records: int


def today_snapshot(
    db: Session,
    organization_id: uuid.UUID,
    *,
    on_date: date | None = None,
    timezone_name: str | None = None,
) -> TodaySnapshot:
    on_date = on_date or today_in(timezone_name)
    sessions = sessions_repo.list_for_org(db, organization_id, on_date=on_date, limit=200)
    session_ids = [s.id for s in sessions]

    athletes: set[uuid.UUID] = set()
    for session_id in session_ids:
        athletes |= sessions_repo.player_ids_in_session(db, session_id)

    counts = sessions_repo.event_counts(db, session_ids)
    return TodaySnapshot(
        on_date=on_date,
        athletes_trained=len(athletes),
        sessions=len(sessions),
        tracked_events=sum(p + h for p, h in counts.values()),
        new_personal_records=records_repo.count_events_on(db, organization_id, on_date),
    )


@dataclass(slots=True)
class IntegrationHealth:
    """Operational visibility. Broken automation must be visible, not hidden."""

    provider: str
    last_successful_import_at: datetime | None
    last_import_status: str | None
    failed_imports_7d: int
    sessions_awaiting_verification: int
    unresolved_players: int
    futures_updates_pending: int


def integration_health(
    db: Session, organization_id: uuid.UUID, *, provider: str = "trackman"
) -> IntegrationHealth:
    recent = imports_repo.list_recent(db, organization_id, limit=1)
    last_success = imports_repo.last_successful(db, organization_id, provider)
    week_ago = datetime.now(UTC) - timedelta(days=7)

    awaiting = sum(
        1
        for s in sessions_repo.list_for_org(db, organization_id, limit=500)
        if s.verified_at is None
    )
    return IntegrationHealth(
        provider=provider,
        last_successful_import_at=last_success.completed_at if last_success else None,
        last_import_status=recent[0].status.value if recent else None,
        failed_imports_7d=imports_repo.count_failed_since(db, organization_id, week_ago),
        sessions_awaiting_verification=awaiting,
        unresolved_players=players_repo.count_unresolved(db, organization_id),
        futures_updates_pending=sync_repo.count_pending(db, organization_id),
    )
