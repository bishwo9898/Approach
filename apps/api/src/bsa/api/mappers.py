"""ORM/domain objects -> API schemas.

Kept in one place so every endpoint renders a metric the same way -- with its
unit, its sample size and its source status attached.
"""

from __future__ import annotations

from bsa.api import schemas
from bsa.db.models import (
    ImportIssue,
    MetricDefinition,
    PersonalRecord,
    PersonalRecordEvent,
    Player,
    RawImport,
    SyncJob,
    TrainingSession,
)
from bsa.db.models import (
    PersonalRecordEvent as PrEvent,
)
from bsa.services.analytics import MetricSummary, PlayerOverview
from bsa.services.hitting import SessionReport
from bsa.services.ingestion import ImportOutcome


def player_summary(player: Player) -> schemas.PlayerSummary:
    return schemas.PlayerSummary(
        id=player.id,
        display_name=player.display_name,
        full_name=player.full_name,
        first_name=player.first_name,
        last_name=player.last_name,
        preferred_name=player.preferred_name,
        position=player.position,
        graduation_year=player.graduation_year,
        bats=player.bats.value if player.bats else None,
        throws=player.throws.value if player.throws else None,
        active=player.active,
    )


def metric_definition(definition: MetricDefinition) -> schemas.MetricDefinitionOut:
    return schemas.MetricDefinitionOut(
        id=definition.id,
        key=definition.key,
        display_name=definition.display_name,
        description=definition.description,
        category=definition.category.value,
        unit=definition.unit,
        aggregation=definition.aggregation.value,
        record_direction=definition.record_direction.value,
        display_precision=definition.display_precision,
        min_sample_size=definition.min_sample_size,
        is_headline=definition.is_headline,
        calculation_version=definition.calculation_version,
    )


def personal_record(
    record: PersonalRecord, definition: MetricDefinition
) -> schemas.PersonalRecordOut:
    return schemas.PersonalRecordOut(
        metric_key=definition.key,
        metric_display_name=definition.display_name,
        unit=definition.unit,
        display_precision=definition.display_precision,
        value=record.value,
        sample_size=record.sample_size,
        achieved_on=record.achieved_on,
        session_id=record.session_id,
        source_status=record.source_status.value,
        is_manual_override=record.is_manual_override,
    )


def metric_summary(summary: MetricSummary) -> schemas.MetricSummaryOut:
    comparison = summary.comparison
    return schemas.MetricSummaryOut(
        definition=metric_definition(summary.definition),
        latest=schemas.MetricValue(
            value=summary.latest.value if summary.latest else None,
            unit=summary.definition.unit,
            sample_size=summary.latest.sample_size if summary.latest else 0,
            source_status=summary.latest.source_status.value if summary.latest else None,
            observed_on=summary.latest.period_start if summary.latest else None,
        ),
        window=schemas.MetricComparison(
            current=comparison.current,
            previous=comparison.previous,
            delta=comparison.delta,
            percent_change=comparison.percent_change,
            current_sample=comparison.current_sample,
            previous_sample=comparison.previous_sample,
            current_source_status=comparison.current_source_status,
            previous_source_status=comparison.previous_source_status,
        ),
        record=(personal_record(summary.record, summary.definition) if summary.record else None),
    )


def session_out(
    session: TrainingSession, *, pitch_count: int = 0, hit_count: int = 0
) -> schemas.SessionOut:
    return schemas.SessionOut(
        id=session.id,
        session_date=session.session_date,
        session_type=session.session_type,
        venue=session.venue,
        source_status=session.source_status.value,
        verified_at=session.verified_at,
        started_at=session.started_at,
        pitch_count=pitch_count,
        hit_count=hit_count,
    )


def player_overview(
    overview: PlayerOverview,
    time_range: str,
    *,
    last_session_counts: tuple[int, int] = (0, 0),
) -> schemas.PlayerOverviewOut:
    return schemas.PlayerOverviewOut(
        player=player_summary(overview.player),
        time_range=time_range,
        last_session=(
            session_out(
                overview.last_session,
                pitch_count=last_session_counts[0],
                hit_count=last_session_counts[1],
            )
            if overview.last_session
            else None
        ),
        sessions_in_window=overview.sessions_in_window,
        metrics=[metric_summary(m) for m in overview.metrics],
    )


def record_event(
    event: PrEvent, player: Player, definition: MetricDefinition
) -> schemas.PersonalRecordEventOut:
    return schemas.PersonalRecordEventOut(
        id=event.id,
        player_id=player.id,
        player_display_name=player.display_name,
        metric_key=definition.key,
        metric_display_name=definition.display_name,
        unit=definition.unit,
        display_precision=definition.display_precision,
        previous_value=event.previous_value,
        new_value=event.new_value,
        delta=event.delta,
        sample_size=event.sample_size,
        achieved_on=event.achieved_on,
        source_status=event.source_status.value,
    )


def import_out(raw_import: RawImport) -> schemas.ImportOut:
    return schemas.ImportOut(
        id=raw_import.id,
        provider=raw_import.provider,
        import_type=raw_import.import_type,
        filename=raw_import.filename,
        status=raw_import.status.value,
        source_status=raw_import.source_status.value,
        rows_total=raw_import.rows_total,
        rows_accepted=raw_import.rows_accepted,
        rows_rejected=raw_import.rows_rejected,
        created_at=raw_import.created_at,
        completed_at=raw_import.completed_at,
        error_message=raw_import.error_message,
        import_metadata=raw_import.import_metadata,
    )


def import_detail(raw_import: RawImport, issues: list[ImportIssue]) -> schemas.ImportDetailOut:
    base = import_out(raw_import)
    return schemas.ImportDetailOut(
        **base.model_dump(by_alias=True),
        issues=[
            schemas.ImportIssueOut(
                row_number=i.row_number,
                code=i.code.value,
                field=i.field,
                message=i.message,
            )
            for i in issues
        ],
    )


def import_result(outcome: ImportOutcome) -> schemas.ImportResultOut:
    return schemas.ImportResultOut(
        raw_import_id=outcome.raw_import_id,
        status=outcome.status.value,
        is_duplicate=outcome.is_duplicate,
        sessions_created=outcome.sessions_created,
        sessions_updated=outcome.sessions_updated,
        pitch_events=outcome.pitch_events,
        hit_events=outcome.hit_events,
        metric_observations=outcome.metric_observations,
        new_personal_records=outcome.new_personal_records,
        sync_jobs_queued=outcome.sync_jobs_queued,
        rows_total=outcome.rows_total,
        rows_accepted=outcome.rows_accepted,
        rows_rejected=outcome.rows_rejected,
        unresolved_players=outcome.unresolved_players,
        error_message=outcome.error_message,
    )


def sync_job(job: SyncJob, player: Player, definition: MetricDefinition) -> schemas.SyncJobOut:
    return schemas.SyncJobOut(
        id=job.id,
        player_id=player.id,
        player_display_name=player.display_name,
        metric_key=definition.key,
        metric_display_name=definition.display_name,
        destination=job.destination,
        destination_field=job.destination_field,
        value=job.value,
        unit=job.unit,
        status=job.status.value,
        attempt_count=job.attempt_count,
        last_error=job.last_error,
        created_at=job.created_at,
    )


def hitting_report(result: SessionReport) -> schemas.HittingSessionReportOut:
    """Render a session report, keeping every sample size attached to its number."""
    report = result.report
    contact = [
        schemas.BattedBallOut(
            event_number=p.event_number,
            exit_velocity_mph=p.exit_velocity_mph,
            launch_angle_deg=p.launch_angle_deg,
            in_sweet_spot=p.in_sweet_spot,
        )
        for p in sorted(
            result.contact_pitches,
            key=lambda p: p.exit_velocity_mph or 0,
            reverse=True,
        )
        if p.exit_velocity_mph is not None
    ]

    return schemas.HittingSessionReportOut(
        player=player_summary(result.player),
        session_id=result.session.id,
        session_date=result.session.session_date,
        session_type=result.session.session_type,
        opponent_name=result.opponent_name,
        pitches_faced=report.pitches_faced,
        taken=report.taken,
        swings=report.swings,
        whiffs=report.whiffs,
        whiff_rate=report.whiff_rate,
        swing_rate=report.swing_rate,
        batted_balls=report.batted_balls,
        best_exit_velocity_mph=report.best_exit_velocity_mph,
        average_exit_velocity_mph=report.average_exit_velocity_mph,
        average_launch_angle_deg=report.average_launch_angle_deg,
        sweet_spot_count=report.sweet_spot_count,
        sweet_spot_rate=report.sweet_spot_rate,
        groups=[
            schemas.PitchGroupSplitOut(
                group=g.group.value,
                label=g.group.label,
                seen=g.seen,
                swings=g.swings,
                whiffs=g.whiffs,
                whiff_rate=g.whiff_rate,
                batted_balls=g.batted_balls,
                average_pitch_velocity_mph=g.average_pitch_velocity_mph,
                average_exit_velocity_mph=g.average_exit_velocity_mph,
                best_exit_velocity_mph=g.best_exit_velocity_mph,
                enough_to_judge=g.has_enough_swings_to_judge,
            )
            for g in report.groups
        ],
        contact=contact,
        insights=[
            schemas.InsightOut(kind=i.kind.value, headline=i.headline, detail=i.detail)
            for i in report.insights
        ],
        videos=[
            schemas.SessionVideoOut(
                id=v.id,
                title=v.title,
                url=v.url,
                external_event_id=v.external_event_id,
                note=v.note,
            )
            for v in result.videos
        ],
    )


__all__ = [
    "hitting_report",
    "import_detail",
    "import_out",
    "import_result",
    "metric_definition",
    "metric_summary",
    "personal_record",
    "player_overview",
    "player_summary",
    "record_event",
    "session_out",
    "sync_job",
]

# Re-exported for callers that only need the event type.
PersonalRecordEventModel = PersonalRecordEvent
