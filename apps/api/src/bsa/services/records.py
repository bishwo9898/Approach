"""Personal record service.

Loads a player's observation series, hands it to the pure engine, and reconciles
the database to the result. Contains no record logic of its own -- that lives in
`bsa.domain.pr_engine` where it can be tested without a database.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from bsa.core.logging import get_logger
from bsa.db.models import MetricDefinition, PersonalRecordEvent
from bsa.db.repositories import metrics as metrics_repo
from bsa.db.repositories import records as records_repo
from bsa.domain.enums import RecordDirection
from bsa.domain.pr_engine import ObservationPoint, RecordRule, compute_progression

log = get_logger(__name__)


@dataclass(slots=True)
class RecordOutcome:
    new_events: list[PersonalRecordEvent] = field(default_factory=list)


def recalculate_for_player_metric(
    db: Session,
    *,
    organization_id: uuid.UUID,
    player_id: uuid.UUID,
    definition: MetricDefinition,
) -> list[PersonalRecordEvent]:
    """Recompute one player's progression for one metric from scratch.

    Recomputing the entire series rather than comparing against the stored
    record is what makes verified corrections work: if a republished session
    lowers a value, the record it claimed simply does not appear in the new
    progression, and the earlier record is restored.
    """
    if definition.record_direction is RecordDirection.NONE:
        return []

    points = [
        ObservationPoint(
            session_id=observation.session_id,
            session_date=observation.period_start,
            value=observation.value,
            sample_size=observation.sample_size,
            source_status=observation.source_status,
            achieved_at=session.started_at,
            context=observation.context,
        )
        for observation, session in metrics_repo.session_observation_points(
            db, player_id, definition.id
        )
        if observation.session_id is not None
    ]

    breaks = compute_progression(
        RecordRule(
            direction=definition.record_direction,
            min_sample_size=definition.min_sample_size,
        ),
        points,
    )
    return records_repo.replace_progression(
        db,
        organization_id=organization_id,
        player_id=player_id,
        metric_definition_id=definition.id,
        breaks=breaks,
        calculation_version=definition.calculation_version,
    )


def recalculate_for_players(
    db: Session,
    *,
    organization_id: uuid.UUID,
    player_ids: list[uuid.UUID],
    definitions: list[MetricDefinition] | None = None,
) -> RecordOutcome:
    """Recompute every record-tracking metric for the given athletes."""
    definitions = definitions or metrics_repo.list_definitions(db, organization_id)
    tracked = [d for d in definitions if d.record_direction is not RecordDirection.NONE]
    outcome = RecordOutcome()

    for player_id in player_ids:
        for definition in tracked:
            outcome.new_events.extend(
                recalculate_for_player_metric(
                    db,
                    organization_id=organization_id,
                    player_id=player_id,
                    definition=definition,
                )
            )

    db.flush()
    log.info(
        "records.recalculated",
        players=len(player_ids),
        metrics=len(tracked),
        new_records=len(outcome.new_events),
    )
    return outcome
