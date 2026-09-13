"""End-to-end ingestion against a real PostgreSQL database.

These cover the Phase 1 acceptance criteria: import, idempotency, identity
safety, and preliminary/verified reconciliation.
"""

from __future__ import annotations

import csv
import io
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bsa.db.models import (
    HitEvent,
    IdentityResolutionItem,
    ImportIssue,
    MetricObservation,
    Organization,
    PersonalRecord,
    PersonalRecordEvent,
    PitchEvent,
    Player,
    RawImport,
    SyncJob,
    TrainingSession,
)
from bsa.domain.enums import ImportIssueCode, ImportStatus, SourceStatus
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.schema import SourcePayload
from bsa.scripts.synthetic import ATHLETES, build_day_csv
from bsa.services.ingestion import IngestionService
from tests.conftest import make_player

pytestmark = pytest.mark.integration

SESSION_DATE = date(2026, 9, 12)
HISTORY_START = date(2026, 6, 1)
PITCHER = ATHLETES[0]
HITTER = next(a for a in ATHLETES if a.hits)


@pytest.fixture
def service(db: Session, organization: Organization, object_store) -> IngestionService:  # type: ignore[no-untyped-def]
    return IngestionService(db, organization, TrackmanCsvProvider(), object_store)


@pytest.fixture
def mapped_pitcher(db: Session, organization: Organization) -> Player:
    return make_player(
        db,
        organization,
        first_name=PITCHER.first_name,
        last_name=PITCHER.last_name,
        external_id=PITCHER.external_id,
    )


def payload(data: bytes, filename: str = "trackman.csv") -> SourcePayload:
    return SourcePayload(data=data, filename=filename, import_type="csv_upload")


def day_csv(*athletes, **kwargs) -> bytes:  # type: ignore[no-untyped-def]
    return build_day_csv(list(athletes), SESSION_DATE, history_start=HISTORY_START, **kwargs)


def count(db: Session, model) -> int:  # type: ignore[no-untyped-def]
    return db.scalar(select(func.count()).select_from(model)) or 0


# -- happy path --------------------------------------------------------------


def test_valid_csv_creates_session_events_metrics_and_records(
    db: Session, service: IngestionService, mapped_pitcher: Player, metrics
) -> None:
    outcome = service.ingest(payload(day_csv(PITCHER)))

    assert outcome.status is ImportStatus.SUCCESS
    assert outcome.sessions_created == 1
    assert outcome.pitch_events > 0
    assert outcome.metric_observations > 0
    assert outcome.new_personal_records > 0
    assert outcome.unresolved_players == []

    session = db.scalars(select(TrainingSession)).one()
    assert session.session_date == SESSION_DATE
    assert session.source_status is SourceStatus.PRELIMINARY
    assert session.verified_at is None

    # Every pitch is attributed to the mapped athlete, never to a name.
    assert {p.player_id for p in db.scalars(select(PitchEvent))} == {mapped_pitcher.id}

    # A max-velocity record exists and is backed by real evidence.
    record = db.scalars(
        select(PersonalRecord).where(
            PersonalRecord.metric_definition_id == metrics["pitch.fastball.max_velocity"].id
        )
    ).one()
    assert record.value > 0
    assert record.sample_size >= metrics["pitch.fastball.max_velocity"].min_sample_size
    assert record.achieved_on == SESSION_DATE


def test_raw_payload_is_archived_before_parsing(
    db: Session, service: IngestionService, mapped_pitcher: Player, metrics, object_store
) -> None:
    """Source data is never discarded -- reprocessing must stay possible."""
    data = day_csv(PITCHER)
    outcome = service.ingest(payload(data))

    stored = db.get(RawImport, outcome.raw_import_id)
    assert stored is not None and stored.object_key is not None
    assert object_store.get(stored.object_key) == data
    assert stored.checksum in stored.object_key


def test_hitting_session_ingests_without_a_pitcher(
    db: Session, organization: Organization, service: IngestionService, metrics
) -> None:
    """Machine-fed cage work has a batter and no pitcher."""
    make_player(
        db,
        organization,
        first_name=HITTER.first_name,
        last_name=HITTER.last_name,
        external_id=HITTER.external_id,
        position="OF",
    )

    outcome = service.ingest(payload(day_csv(HITTER)))

    assert outcome.status is ImportStatus.SUCCESS
    assert outcome.hit_events > 0
    assert outcome.pitch_events == 0
    assert count(db, HitEvent) == outcome.hit_events


# -- idempotency -------------------------------------------------------------


def test_identical_bytes_are_skipped_as_duplicate(
    db: Session, service: IngestionService, mapped_pitcher: Player, metrics
) -> None:
    data = day_csv(PITCHER)
    first = service.ingest(payload(data))
    second = service.ingest(payload(data))

    assert second.is_duplicate
    assert second.raw_import_id == first.raw_import_id
    assert count(db, TrainingSession) == 1


def test_reimporting_the_same_session_creates_no_duplicates(
    db: Session, service: IngestionService, mapped_pitcher: Player, metrics
) -> None:
    """The acceptance criterion: same session, different file bytes.

    Forcing a reprocess exercises the full pipeline again rather than
    short-circuiting on the checksum, which is the case that would actually
    duplicate rows if the upserts were wrong.
    """
    data = day_csv(PITCHER)
    first = service.ingest(payload(data))

    sessions = count(db, TrainingSession)
    pitches = count(db, PitchEvent)
    observations = count(db, MetricObservation)
    record_events = count(db, PersonalRecordEvent)

    second = service.ingest(payload(data), force_reprocess=True)

    assert not second.is_duplicate
    assert second.raw_import_id == first.raw_import_id
    assert count(db, TrainingSession) == sessions
    assert count(db, PitchEvent) == pitches
    assert count(db, MetricObservation) == observations
    # The critical one: no second announcement of the same achievement.
    assert count(db, PersonalRecordEvent) == record_events
    assert second.new_personal_records == 0


def test_reprocessing_does_not_duplicate_futures_sync_jobs(
    db: Session, service: IngestionService, mapped_pitcher: Player, metrics
) -> None:
    """A coach must not be told to enter the same value twice."""
    data = day_csv(PITCHER)
    service.ingest(payload(data))
    jobs = count(db, SyncJob)
    assert jobs > 0

    service.ingest(payload(data), force_reprocess=True)

    assert count(db, SyncJob) == jobs


# -- identity safety ---------------------------------------------------------


def test_unknown_athlete_is_queued_and_no_data_is_attributed(
    db: Session, service: IngestionService, metrics
) -> None:
    """Never guess. Attributing one athlete's data to another is the worst
    failure this system can produce."""
    outcome = service.ingest(payload(day_csv(PITCHER)))

    assert outcome.status is ImportStatus.PARTIAL
    assert outcome.unresolved_players == [PITCHER.external_id]
    assert count(db, PitchEvent) == 0
    assert count(db, PersonalRecordEvent) == 0

    queued = db.scalars(select(IdentityResolutionItem)).one()
    assert queued.external_id == PITCHER.external_id
    assert queued.occurrence_count > 0
    # The vendor's display name is kept for operator recognition only.
    assert queued.external_display_name == f"{PITCHER.last_name}, {PITCHER.first_name}"


def test_name_match_alone_never_resolves_an_athlete(
    db: Session, organization: Organization, service: IngestionService, metrics
) -> None:
    """A player with the same name but no mapping gets nothing attached."""
    unmapped = make_player(
        db,
        organization,
        first_name=PITCHER.first_name,
        last_name=PITCHER.last_name,
        external_id=None,
    )

    outcome = service.ingest(payload(day_csv(PITCHER)))

    assert outcome.unresolved_players == [PITCHER.external_id]
    assert (
        db.scalar(select(func.count(PitchEvent.id)).where(PitchEvent.player_id == unmapped.id)) == 0
    )


def test_unresolved_athletes_are_recorded_as_import_issues(
    db: Session, service: IngestionService, metrics
) -> None:
    outcome = service.ingest(payload(day_csv(PITCHER)))

    issues = db.scalars(
        select(ImportIssue).where(ImportIssue.raw_import_id == outcome.raw_import_id)
    ).all()
    assert any(i.code is ImportIssueCode.PLAYER_UNRESOLVED for i in issues)


def test_duplicate_external_identity_is_blocked_by_the_database(
    db: Session, organization: Organization
) -> None:
    """One vendor id can map to exactly one athlete, enforced in Postgres."""
    from sqlalchemy.exc import IntegrityError

    make_player(db, organization, first_name="A", last_name="One", external_id="TM-DUP")
    db.flush()

    # Inside a savepoint: the violation aborts the nested transaction only,
    # leaving the outer test transaction usable for the fixture rollback.
    savepoint = db.begin_nested()
    with pytest.raises(IntegrityError):
        make_player(db, organization, first_name="B", last_name="Two", external_id="TM-DUP")
        db.flush()
    savepoint.rollback()

    assert db.scalar(select(func.count(Player.id))) == 1


# -- malformed input ---------------------------------------------------------


def test_one_bad_row_does_not_fail_the_file(
    db: Session, service: IngestionService, mapped_pitcher: Player, metrics
) -> None:
    data = day_csv(PITCHER)
    reader = csv.DictReader(io.StringIO(data.decode()))
    fieldnames = list(reader.fieldnames or [])
    rows = [dict(r) for r in reader]
    rows[0]["SessionDate"] = "not-a-date"
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    outcome = service.ingest(payload(buffer.getvalue().encode()))

    assert outcome.status is ImportStatus.PARTIAL
    assert outcome.rows_rejected == 1
    assert outcome.rows_accepted == len(rows) - 1
    assert count(db, PitchEvent) == len(rows) - 1


def test_unknown_schema_fails_the_import_cleanly(
    db: Session, service: IngestionService, metrics
) -> None:
    outcome = service.ingest(payload(b"Alpha,Beta\n1,2\n", filename="mystery.csv"))

    assert outcome.status is ImportStatus.FAILED
    assert outcome.error_message is not None
    assert count(db, TrainingSession) == 0

    issues = db.scalars(select(ImportIssue)).all()
    assert any(i.code is ImportIssueCode.SCHEMA_UNKNOWN for i in issues)


# -- preliminary / verified reconciliation -----------------------------------


def test_verified_republish_supersedes_preliminary_without_duplicating(
    db: Session, service: IngestionService, mapped_pitcher: Player, metrics
) -> None:
    """Section 12's requirement, end to end.

    The verified file corrects every velocity downward. The session must be
    updated in place, its metrics recalculated, and the record it claimed
    revoked -- with the earlier record restored.
    """
    service.ingest(payload(day_csv(PITCHER), "preliminary.csv"))

    session = db.scalars(select(TrainingSession)).one()
    assert session.source_status is SourceStatus.PRELIMINARY
    pitches_before = count(db, PitchEvent)

    definition = metrics["pitch.fastball.max_velocity"]
    preliminary_value = (
        db.scalars(
            select(MetricObservation).where(MetricObservation.metric_definition_id == definition.id)
        )
        .one()
        .value
    )

    verified = build_day_csv(
        [PITCHER],
        SESSION_DATE,
        history_start=HISTORY_START,
        verified=True,
        velocity_bonus={PITCHER.external_id: -3.0},
    )
    outcome = service.ingest(payload(verified, "verified.csv"))

    assert outcome.sessions_created == 0
    assert outcome.sessions_updated == 1

    db.expire_all()
    # Exactly one session, still. No duplicate events.
    assert count(db, TrainingSession) == 1
    assert count(db, PitchEvent) == pitches_before

    session = db.scalars(select(TrainingSession)).one()
    assert session.source_status is SourceStatus.VERIFIED
    assert session.verified_at is not None

    observation = db.scalars(
        select(MetricObservation).where(MetricObservation.metric_definition_id == definition.id)
    ).one()
    assert observation.value < preliminary_value
    assert observation.source_status is SourceStatus.VERIFIED


def test_verified_correction_revokes_a_record_it_no_longer_supports(
    db: Session, service: IngestionService, mapped_pitcher: Player, metrics
) -> None:
    earlier = date(2026, 9, 5)
    definition = metrics["pitch.fastball.max_velocity"]

    # A solid earlier session establishes the baseline record.
    service.ingest(
        payload(
            build_day_csv([PITCHER], earlier, history_start=HISTORY_START),
            "day1.csv",
        )
    )
    baseline = (
        db.scalars(
            select(PersonalRecord).where(PersonalRecord.metric_definition_id == definition.id)
        )
        .one()
        .value
    )

    # A preliminary breakout day claims a new record.
    service.ingest(
        payload(
            build_day_csv(
                [PITCHER],
                SESSION_DATE,
                history_start=HISTORY_START,
                velocity_bonus={PITCHER.external_id: 6.0},
            ),
            "day2-preliminary.csv",
        )
    )
    db.expire_all()
    claimed = db.scalars(
        select(PersonalRecord).where(PersonalRecord.metric_definition_id == definition.id)
    ).one()
    assert claimed.value > baseline
    assert claimed.achieved_on == SESSION_DATE

    # The verified republish shows the breakout was a tracking artifact.
    service.ingest(
        payload(
            build_day_csv(
                [PITCHER],
                SESSION_DATE,
                history_start=HISTORY_START,
                verified=True,
                velocity_bonus={PITCHER.external_id: -8.0},
            ),
            "day2-verified.csv",
        )
    )
    db.expire_all()

    restored = db.scalars(
        select(PersonalRecord).where(PersonalRecord.metric_definition_id == definition.id)
    ).one()
    assert restored.value == baseline
    assert restored.achieved_on == earlier

    # The revoked claim is preserved, not deleted: the audit trail must show
    # what the coach was told at the time.
    superseded = db.scalars(
        select(PersonalRecordEvent).where(
            PersonalRecordEvent.metric_definition_id == definition.id,
            PersonalRecordEvent.superseded_at.is_not(None),
        )
    ).all()
    assert len(superseded) == 1
    assert superseded[0].achieved_on == SESSION_DATE
    assert "no longer a record" in (superseded[0].superseded_reason or "")


def test_verified_session_is_never_downgraded_to_preliminary(
    db: Session, service: IngestionService, mapped_pitcher: Player, metrics
) -> None:
    """A late preliminary file must not undo a verification."""
    service.ingest(payload(day_csv(PITCHER, verified=True), "verified.csv"))
    service.ingest(payload(day_csv(PITCHER), "late-preliminary.csv"))

    db.expire_all()
    session = db.scalars(select(TrainingSession)).one()
    assert session.source_status is SourceStatus.VERIFIED


def test_corrected_data_drops_events_the_republish_omits(
    db: Session, service: IngestionService, mapped_pitcher: Player, metrics
) -> None:
    """Stale readings must not keep feeding metrics after a correction."""
    service.ingest(payload(day_csv(PITCHER), "preliminary.csv"))
    before = count(db, PitchEvent)

    data = day_csv(PITCHER, verified=True)
    reader = csv.DictReader(io.StringIO(data.decode()))
    fieldnames = list(reader.fieldnames or [])
    rows = [dict(r) for r in reader][:-3]  # the republish drops three pitches
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    service.ingest(payload(buffer.getvalue().encode(), "verified-short.csv"))

    db.expire_all()
    assert count(db, PitchEvent) == before - 3


def test_a_file_with_rejected_rows_never_deletes_existing_events(
    db: Session, service: IngestionService, mapped_pitcher: Player, metrics
) -> None:
    """Ambiguity must not destroy measurements.

    A partial or partly-unreadable file omits events because *we* could not read
    them, not because the source removed them. Treating it as authoritative
    would silently delete real athlete data -- the failure mode most likely to
    go unnoticed, because the dashboard still renders happily afterwards.
    """
    service.ingest(payload(day_csv(PITCHER), "full.csv"))
    full_count = count(db, PitchEvent)
    assert full_count > 6

    # A truncated file for the same session, with one unreadable row.
    data = day_csv(PITCHER)
    reader = csv.DictReader(io.StringIO(data.decode()))
    fieldnames = list(reader.fieldnames or [])
    rows = [dict(r) for r in reader][:6]
    rows[0]["SessionDate"] = "not-a-date"
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    outcome = service.ingest(payload(buffer.getvalue().encode(), "truncated.csv"))

    assert outcome.status is ImportStatus.PARTIAL
    assert outcome.rows_rejected == 1
    assert outcome.events_pruned == 0
    db.expire_all()
    assert count(db, PitchEvent) == full_count


def test_a_file_with_unresolved_athletes_never_deletes_existing_events(
    db: Session,
    organization: Organization,
    service: IngestionService,
    mapped_pitcher: Player,
    metrics,
) -> None:
    service.ingest(payload(day_csv(PITCHER), "full.csv"))
    full_count = count(db, PitchEvent)

    # Same session, but now also containing an athlete we cannot map.
    second = ATHLETES[1]
    outcome = service.ingest(
        payload(
            build_day_csv([PITCHER, second], SESSION_DATE, history_start=HISTORY_START),
            "with-unknown.csv",
        )
    )

    assert outcome.unresolved_players == [second.external_id]
    assert outcome.events_pruned == 0
    db.expire_all()
    assert count(db, PitchEvent) == full_count
