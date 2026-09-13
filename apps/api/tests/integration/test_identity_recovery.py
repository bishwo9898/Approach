"""Resolving an unknown athlete must actually recover their held data.

Mapping an athlete and leaving their sessions stranded would make the
identity-resolution queue a dead end -- the data would be safe, and useless.
Recovery works by reprocessing the archived source bytes through the ordinary
pipeline, never by back-filling rows.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bsa.api.app import create_app
from bsa.api.deps import get_object_store_dep
from bsa.db.models import (
    AuditLog,
    ExternalPlayerIdentity,
    IdentityResolutionItem,
    Organization,
    PersonalRecord,
    PitchEvent,
    Player,
    RawImport,
)
from bsa.db.session import get_db
from bsa.domain.enums import AuditAction, IdentityResolutionStatus, Role
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.schema import SourcePayload
from bsa.scripts.synthetic import ATHLETES, build_day_csv
from bsa.services.ingestion import IngestionService
from tests.conftest import make_player, make_user

pytestmark = pytest.mark.integration

PITCHER = ATHLETES[0]
SESSION_DATE = date(2026, 9, 12)
HISTORY_START = date(2026, 7, 1)
ADMIN = {"Authorization": "Bearer dev|admin"}
COACH = {"Authorization": "Bearer dev|coach"}


@pytest.fixture
def client(db: Session, object_store):  # type: ignore[no-untyped-def]
    """App wired to the test transaction and the test's temp object store.

    The object store matters here: reprocessing reads the archived source bytes
    back, so the API must see the same store the fixture ingested through.
    """
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_object_store_dep] = lambda: object_store
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def held_import(db: Session, organization: Organization, metrics, object_store):  # type: ignore[no-untyped-def]
    """An import whose events were held because the athlete was unmapped."""
    make_user(db, organization, subject="dev|admin", role=Role.ADMIN)
    make_user(db, organization, subject="dev|coach", role=Role.COACH)

    service = IngestionService(db, organization, TrackmanCsvProvider(), object_store)
    outcome = service.ingest(
        SourcePayload(
            data=build_day_csv([PITCHER], SESSION_DATE, history_start=HISTORY_START),
            filename="held.csv",
        )
    )
    db.flush()

    assert outcome.unresolved_players == [PITCHER.external_id]
    assert db.scalar(select(func.count(PitchEvent.id))) == 0
    return outcome


def count(db: Session, model) -> int:  # type: ignore[no-untyped-def]
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_mapping_an_athlete_recovers_their_held_events(
    client, db: Session, organization: Organization, held_import, metrics
) -> None:
    player: Player = make_player(db, organization, first_name="Jake", last_name="Williams")
    db.flush()
    item = db.scalars(select(IdentityResolutionItem)).one()

    response = client.post(
        f"/api/v1/identity/unresolved/{item.id}/resolve",
        headers=ADMIN,
        json={"player_id": str(player.id), "note": "confirmed with coach"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["player"]["id"] == str(player.id)
    assert body["imports_reprocessed"] == 1

    db.expire_all()
    # The events that were held are now attributed -- to this athlete, and only
    # because a human said so.
    assert count(db, PitchEvent) > 0
    assert {p.player_id for p in db.scalars(select(PitchEvent))} == {player.id}

    # And the derived layers ran: metrics and records exist for them now.
    assert body["new_personal_records"] > 0
    assert count(db, PersonalRecord) > 0


def test_resolution_marks_the_queue_item_and_creates_the_mapping(
    client, db: Session, organization: Organization, held_import, metrics
) -> None:
    player = make_player(db, organization, first_name="Jake", last_name="Williams")
    db.flush()
    item = db.scalars(select(IdentityResolutionItem)).one()

    client.post(
        f"/api/v1/identity/unresolved/{item.id}/resolve",
        headers=ADMIN,
        json={"player_id": str(player.id)},
    )

    db.expire_all()
    item = db.scalars(select(IdentityResolutionItem)).one()
    assert item.status is IdentityResolutionStatus.RESOLVED
    assert item.resolved_player_id == player.id
    assert item.resolved_at is not None

    identity = db.scalars(select(ExternalPlayerIdentity)).one()
    assert identity.external_id == PITCHER.external_id
    assert identity.player_id == player.id
    # Human-confirmed, not machine-asserted.
    assert identity.verified_at is not None


def test_resolution_is_audited(
    client, db: Session, organization: Organization, held_import, metrics
) -> None:
    player = make_player(db, organization, first_name="Jake", last_name="Williams")
    db.flush()
    item = db.scalars(select(IdentityResolutionItem)).one()

    client.post(
        f"/api/v1/identity/unresolved/{item.id}/resolve",
        headers=ADMIN,
        json={"player_id": str(player.id)},
    )

    db.expire_all()
    actions = {entry.action for entry in db.scalars(select(AuditLog))}
    assert AuditAction.PLAYER_MAPPING_CREATED in actions
    assert AuditAction.IMPORT_REPROCESSED in actions


def test_recovery_can_be_declined(
    client, db: Session, organization: Organization, held_import, metrics
) -> None:
    """An admin fixing a mis-mapping may not want an immediate re-run."""
    player = make_player(db, organization, first_name="Jake", last_name="Williams")
    db.flush()
    item = db.scalars(select(IdentityResolutionItem)).one()

    response = client.post(
        f"/api/v1/identity/unresolved/{item.id}/resolve",
        headers=ADMIN,
        json={"player_id": str(player.id), "reprocess": False},
    )

    assert response.json()["imports_reprocessed"] == 0
    db.expire_all()
    assert count(db, PitchEvent) == 0


def test_a_vendor_id_cannot_be_mapped_to_a_second_athlete(
    client, db: Session, organization: Organization, held_import, metrics
) -> None:
    first = make_player(db, organization, first_name="Jake", last_name="Williams")
    second = make_player(db, organization, first_name="Other", last_name="Athlete")
    db.flush()
    item = db.scalars(select(IdentityResolutionItem)).one()

    ok = client.post(
        f"/api/v1/identity/unresolved/{item.id}/resolve",
        headers=ADMIN,
        json={"player_id": str(first.id)},
    )
    assert ok.status_code == 200

    # The queue item is resolved, so a second attempt cannot even find it --
    # and the uniqueness constraint stands behind that.
    again = client.post(
        f"/api/v1/identity/unresolved/{item.id}/resolve",
        headers=ADMIN,
        json={"player_id": str(second.id)},
    )
    assert again.status_code in (404, 409)

    db.expire_all()
    assert count(db, ExternalPlayerIdentity) == 1


def test_reprocessing_an_import_is_idempotent(
    client, db: Session, organization: Organization, metrics, object_store
) -> None:
    """The archive exists so a re-run is safe, not so it can be run once."""
    player = make_player(
        db,
        organization,
        first_name=PITCHER.first_name,
        last_name=PITCHER.last_name,
        external_id=PITCHER.external_id,
    )
    make_user(db, organization, subject="dev|coach", role=Role.COACH)
    service = IngestionService(db, organization, TrackmanCsvProvider(), object_store)
    outcome = service.ingest(
        SourcePayload(
            data=build_day_csv([PITCHER], SESSION_DATE, history_start=HISTORY_START),
            filename="clean.csv",
        )
    )
    db.flush()
    assert player is not None

    before = (count(db, PitchEvent), count(db, PersonalRecord))

    response = client.post(f"/api/v1/imports/{outcome.raw_import_id}/reprocess", headers=COACH)

    assert response.status_code == 200
    assert response.json()["new_personal_records"] == 0
    db.expire_all()
    assert (count(db, PitchEvent), count(db, PersonalRecord)) == before


def test_reprocess_reports_a_missing_archive_rather_than_crashing(
    client, db: Session, organization: Organization, held_import, metrics
) -> None:
    raw_import = db.scalars(select(RawImport)).one()
    raw_import.object_key = None
    db.flush()

    response = client.post(f"/api/v1/imports/{raw_import.id}/reprocess", headers=COACH)

    assert response.status_code == 422
    assert "archived payload" in response.json()["error"]["message"]


def test_a_coach_cannot_map_an_athlete(
    client, db: Session, organization: Organization, held_import, metrics
) -> None:
    player = make_player(db, organization, first_name="Jake", last_name="Williams")
    db.flush()
    item = db.scalars(select(IdentityResolutionItem)).one()

    response = client.post(
        f"/api/v1/identity/unresolved/{item.id}/resolve",
        headers=COACH,
        json={"player_id": str(player.id)},
    )

    assert response.status_code == 403
    db.expire_all()
    assert count(db, ExternalPlayerIdentity) == 0
