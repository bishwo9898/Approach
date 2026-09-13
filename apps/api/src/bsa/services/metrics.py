"""Metric calculation service.

Bridges the pure engine to the database: load events, evaluate every enabled
metric, persist the results, and remove any stale value the new data no longer
supports.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from bsa.core.logging import get_logger
from bsa.db.models import MetricDefinition, TrainingSession
from bsa.db.repositories import metrics as metrics_repo
from bsa.db.repositories import sessions as sessions_repo
from bsa.domain.enums import EventSource
from bsa.domain.metrics_engine import MetricConfig, calculate

log = get_logger(__name__)


@dataclass(slots=True)
class SessionMetricOutcome:
    """What a recalculation produced, per player."""

    calculated: dict[uuid.UUID, list[uuid.UUID]]
    removed: int = 0

    @property
    def observation_count(self) -> int:
        return sum(len(v) for v in self.calculated.values())


def recalculate_session(
    db: Session,
    organization_id: uuid.UUID,
    session: TrainingSession,
    *,
    definitions: list[MetricDefinition] | None = None,
) -> SessionMetricOutcome:
    """Recompute every enabled metric for every athlete in a session.

    Idempotent: observations are upserted on their natural key and anything the
    current data no longer produces is deleted, so running this twice leaves
    the database in the same state as running it once.
    """
    definitions = definitions or metrics_repo.list_definitions(db, organization_id)
    player_ids = sessions_repo.player_ids_in_session(db, session.id)
    outcome = SessionMetricOutcome(calculated={})

    for player_id in player_ids:
        events = {
            EventSource.PITCH: sessions_repo.pitch_events_for(db, player_id, session.id),
            EventSource.HIT: sessions_repo.hit_events_for(db, player_id, session.id),
        }
        produced: list[uuid.UUID] = []

        for definition in definitions:
            result = calculate(
                MetricConfig.from_definition(definition), events[definition.event_source]
            )
            if result is None:
                continue
            metrics_repo.upsert_session_observation(
                db,
                organization_id=organization_id,
                player_id=player_id,
                metric_definition_id=definition.id,
                session_id=session.id,
                period_start=session.session_date,
                value=result.value,
                sample_size=result.sample_size,
                source_status=session.source_status,
                calculation_version=definition.calculation_version,
                context=result.context,
            )
            produced.append(definition.id)

        # Whatever this player no longer qualifies for must not linger.
        outcome.removed += metrics_repo.delete_player_session_observations(
            db, session.id, player_id, produced
        )
        outcome.calculated[player_id] = produced

    db.flush()
    log.info(
        "metrics.session.recalculated",
        session_id=str(session.id),
        players=len(player_ids),
        observations=outcome.observation_count,
        removed=outcome.removed,
    )
    return outcome
