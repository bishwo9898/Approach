"""Futures synchronization.

Covers the part we can honestly build today: queueing the right values, never
queueing them twice, converting units at the boundary, and recording that a
human entered them.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bsa.core.units import Unit
from bsa.db.models import AuditLog, ExternalMetricMapping, Organization, SyncJob
from bsa.db.repositories import sync as sync_repo
from bsa.domain.enums import AuditAction, Role, SyncStatus
from bsa.integrations.futures.base import MetricPush
from bsa.integrations.futures.manual import ManualFuturesProvider
from bsa.integrations.futures.mock import MockFuturesProvider
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.schema import SourcePayload
from bsa.scripts.synthetic import ATHLETES, build_day_csv
from bsa.services import sync as sync_service
from bsa.services.ingestion import IngestionService
from tests.conftest import make_player, make_user

pytestmark = pytest.mark.integration

PITCHER = ATHLETES[0]
SESSION_DATE = date(2026, 9, 12)
HISTORY_START = date(2026, 7, 1)


@pytest.fixture
def ingested(db: Session, organization: Organization, metrics, object_store):  # type: ignore[no-untyped-def]
    player = make_player(
        db,
        organization,
        first_name=PITCHER.first_name,
        last_name=PITCHER.last_name,
        external_id=PITCHER.external_id,
    )
    service = IngestionService(db, organization, TrackmanCsvProvider(), object_store)
    service.ingest(
        SourcePayload(
            data=build_day_csv([PITCHER], SESSION_DATE, history_start=HISTORY_START),
            filename="day.csv",
        )
    )
    db.flush()
    return player


def test_new_records_queue_only_mapped_metrics(
    db: Session, organization: Organization, ingested, metrics
) -> None:
    """Not every metric we track is one the facility records externally."""
    jobs = db.scalars(select(SyncJob)).all()

    assert jobs
    mapped_ids = {m.metric_definition_id for m in db.scalars(select(ExternalMetricMapping)).all()}
    assert {j.metric_definition_id for j in jobs} <= mapped_ids
    assert all(j.status is SyncStatus.PENDING for j in jobs)
    assert all(j.destination == "futures" for j in jobs)
    # The value is frozen with its unit at queue time.
    assert all(j.unit for j in jobs)


def test_queue_carries_the_destination_field_label(
    db: Session, organization: Organization, ingested, metrics
) -> None:
    job = db.scalars(
        select(SyncJob).where(
            SyncJob.metric_definition_id == metrics["pitch.fastball.max_velocity"].id
        )
    ).one()

    assert job.destination_field == "Fastball Velocity"
    assert job.unit == "mph"


def test_unit_conversion_happens_at_the_destination_boundary() -> None:
    """A value must never reach another system in the wrong unit."""
    # Same unit: passed through untouched.
    same, same_unit = sync_service._convert_for_destination(88.0, "mph", "mph")
    assert same == 88.0 and same_unit == "mph"

    # Supported conversion: applied once, here, and nowhere else.
    converted, converted_unit = sync_service._convert_for_destination(1.5, "ft", "in")
    assert converted == 18.0 and converted_unit == "in"

    # Unsupported destination unit: a None value is the failure signal the
    # caller acts on. Queueing 88 labelled "km/h" would be far worse than
    # queueing nothing.
    value, _unit = sync_service._convert_for_destination(88.0, Unit.MPH.value, "km/h")
    assert value is None

    value, _unit = sync_service._convert_for_destination(88.0, "mph", "furlongs")
    assert value is None


def test_manual_provider_reports_that_a_human_must_enter_the_value() -> None:
    """The honest outcome today -- not an error."""
    result = ManualFuturesProvider().update_player_metric(
        MetricPush("TM-1", "Fastball Velocity", 87.3, "mph", "pitch.fastball.max_velocity")
    )

    assert result.accepted is False
    assert result.requires_manual_entry is True
    assert "87.3" in (result.message or "")


def test_attempt_push_moves_a_job_to_manual_required(
    db: Session, organization: Organization, ingested, metrics
) -> None:
    job = db.scalars(select(SyncJob)).first()
    assert job is not None

    sync_service.attempt_push(db, job, ManualFuturesProvider(), "TM-100241")

    assert job.status is SyncStatus.MANUAL_REQUIRED
    assert job.attempt_count == 1
    assert job.last_error is not None


def test_mock_provider_completes_a_push(
    db: Session, organization: Organization, ingested, metrics
) -> None:
    job = db.scalars(select(SyncJob)).first()
    assert job is not None
    provider = MockFuturesProvider()

    sync_service.attempt_push(db, job, provider, "TM-100241")

    assert job.status is SyncStatus.SYNCED
    assert job.completed_at is not None
    assert provider.pushed[0].destination_field == job.destination_field


def test_marking_updated_is_audited(
    db: Session, organization: Organization, ingested, metrics
) -> None:
    """The only evidence we will have that Futures was actually updated."""
    coach = make_user(db, organization, subject="dev|coach", role=Role.COACH)
    job = db.scalars(select(SyncJob)).first()
    assert job is not None

    sync_service.mark_manually_updated(db, organization_id=organization.id, job=job, actor=coach)

    assert job.status is SyncStatus.SYNCED
    assert job.completed_by_user_id == coach.id

    entry = db.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.FUTURES_SYNC_MANUALLY_CONFIRMED)
    ).one()
    assert entry.actor_user_id == coach.id
    assert entry.audit_metadata["destination_field"] == job.destination_field


def test_audit_metadata_never_stores_credentials(
    db: Session, organization: Organization, metrics
) -> None:
    from bsa.services import audit

    entry = audit.record(
        db,
        organization_id=organization.id,
        action=AuditAction.METRIC_CHANGED,
        target_type="metric_definition",
        metadata={"metric": "x", "api_key": "leaked", "password": "leaked"},
    )

    assert entry.audit_metadata == {"metric": "x"}


def test_completed_jobs_are_not_reopened_by_recalculation(
    db: Session, organization: Organization, ingested, metrics
) -> None:
    """A coach who already typed the value must not be sent back to redo it."""
    job = db.scalars(select(SyncJob)).first()
    assert job is not None
    job.status = SyncStatus.SYNCED
    db.flush()

    sync_repo.upsert_job(
        db,
        organization_id=organization.id,
        player_id=job.player_id,
        metric_definition_id=job.metric_definition_id,
        personal_record_event_id=job.personal_record_event_id,
        destination=job.destination,
        destination_field=job.destination_field,
        value=999.0,
        unit="mph",
    )

    assert job.status is SyncStatus.SYNCED
    assert job.value != 999.0
