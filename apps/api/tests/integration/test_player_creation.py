"""Adding an athlete to the roster.

Without this, a real TrackMan export is a dead end: every athlete in it is
unknown, and the resolution queue can only map to players that already exist.
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
)
from bsa.db.session import get_db
from bsa.domain.enums import AuditAction, Role
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.schema import SourcePayload
from bsa.scripts.synthetic import ATHLETES, build_day_csv
from bsa.services.ingestion import IngestionService
from tests.conftest import make_user

pytestmark = pytest.mark.integration

ADMIN = {"Authorization": "Bearer dev|admin"}
COACH = {"Authorization": "Bearer dev|coach"}
PITCHER = ATHLETES[0]
SESSION_DATE = date(2026, 9, 12)
HISTORY_START = date(2026, 7, 1)


@pytest.fixture
def client(db: Session, object_store):  # type: ignore[no-untyped-def]
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_object_store_dep] = lambda: object_store
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def users(db: Session, organization: Organization):  # type: ignore[no-untyped-def]
    make_user(db, organization, subject="dev|admin", role=Role.ADMIN)
    make_user(db, organization, subject="dev|coach", role=Role.COACH)
    db.flush()


def count(db: Session, model) -> int:  # type: ignore[no-untyped-def]
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_an_admin_can_add_an_athlete(client, db: Session, users) -> None:
    response = client.post(
        "/api/v1/players",
        headers=ADMIN,
        json={
            "first_name": "Daniel",
            "last_name": "Okafor",
            "position": "RHP",
            "graduation_year": 2029,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["display_name"] == "Daniel Okafor"
    assert body["position"] == "RHP"
    assert body["active"] is True


def test_only_a_name_is_required(client, db: Session, users) -> None:
    """Onboarding a thirty-athlete roster must not demand optional labels."""
    response = client.post(
        "/api/v1/players",
        headers=ADMIN,
        json={"first_name": "Sam", "last_name": "Reyes"},
    )

    assert response.status_code == 201
    assert response.json()["position"] is None
    assert response.json()["graduation_year"] is None


def test_a_blank_name_is_rejected(client, db: Session, users) -> None:
    for payload in (
        {"first_name": "", "last_name": "Reyes"},
        {"first_name": "Sam", "last_name": "   "},
        {"first_name": "Sam"},
    ):
        response = client.post("/api/v1/players", headers=ADMIN, json=payload)
        assert response.status_code == 422, payload


def test_a_new_athlete_is_mapped_to_nothing(client, db: Session, users) -> None:
    """Creating an athlete must never adopt somebody else's vendor data."""
    client.post(
        "/api/v1/players",
        headers=ADMIN,
        json={"first_name": "Daniel", "last_name": "Okafor"},
    )

    assert count(db, ExternalPlayerIdentity) == 0


def test_creation_is_audited(client, db: Session, users) -> None:
    client.post(
        "/api/v1/players",
        headers=ADMIN,
        json={"first_name": "Daniel", "last_name": "Okafor"},
    )

    entry = db.scalars(select(AuditLog).where(AuditLog.action == AuditAction.PLAYER_CREATED)).one()
    assert entry.audit_metadata["display_name"] == "Daniel Okafor"


def test_a_coach_cannot_add_an_athlete(client, db: Session, users) -> None:
    response = client.post(
        "/api/v1/players",
        headers=COACH,
        json={"first_name": "Daniel", "last_name": "Okafor"},
    )

    assert response.status_code == 403
    assert count(db, Player) == 0


def test_the_athlete_belongs_to_the_callers_organization(
    client, db: Session, organization: Organization, users
) -> None:
    client.post(
        "/api/v1/players",
        headers=ADMIN,
        json={"first_name": "Daniel", "last_name": "Okafor"},
    )

    player = db.scalars(select(Player)).one()
    assert player.organization_id == organization.id


def test_create_then_map_recovers_held_data(
    client, db: Session, organization: Organization, users, metrics, object_store
) -> None:
    """The whole point: a real export whose athletes we have never seen.

    Import holds the events, an admin creates the athlete and maps them, and
    the held sessions are recovered -- without anyone touching the database.
    """
    service = IngestionService(db, organization, TrackmanCsvProvider(), object_store)
    service.ingest(
        SourcePayload(
            data=build_day_csv([PITCHER], SESSION_DATE, history_start=HISTORY_START),
            filename="unknown-athletes.csv",
        )
    )
    db.flush()
    assert count(db, PitchEvent) == 0

    created = client.post(
        "/api/v1/players",
        headers=ADMIN,
        json={"first_name": PITCHER.first_name, "last_name": PITCHER.last_name},
    )
    assert created.status_code == 201

    item = db.scalars(select(IdentityResolutionItem)).one()
    resolved = client.post(
        f"/api/v1/identity/unresolved/{item.id}/resolve",
        headers=ADMIN,
        json={"player_id": created.json()["id"]},
    )

    assert resolved.status_code == 200
    assert resolved.json()["imports_reprocessed"] == 1
    assert resolved.json()["new_personal_records"] > 0

    db.expire_all()
    assert count(db, PitchEvent) > 0
    assert count(db, PersonalRecord) > 0
    assert {p.player_id for p in db.scalars(select(PitchEvent))} == {
        db.scalars(select(Player)).one().id
    }
