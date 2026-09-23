"""Server-side authorization.

The rule under test: a player must never reach another athlete's data, and no
user may reach another organization's data, regardless of what the client sends.
Hiding a route in the frontend is not a control.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bsa.api.app import create_app
from bsa.db.models import Organization, Player
from bsa.db.session import get_db
from bsa.domain.enums import Role
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.schema import SourcePayload
from bsa.scripts.synthetic import ATHLETES, build_day_csv
from bsa.services.ingestion import IngestionService
from tests.conftest import make_player, make_user

pytestmark = pytest.mark.integration

SESSION_DATE = date(2026, 9, 12)
HISTORY_START = date(2026, 6, 1)
PITCHER = ATHLETES[0]
SECOND = ATHLETES[1]


@pytest.fixture
def client(db: Session):  # type: ignore[no-untyped-def]
    """App wired to the test transaction, with real auth dependencies intact.

    Only the database dependency is overridden -- `get_principal` is deliberately
    NOT stubbed, because it is the thing under test.
    """
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def roster(db: Session, organization: Organization, metrics, object_store):  # type: ignore[no-untyped-def]
    """Two athletes with data, plus one user per role."""
    first = make_player(
        db,
        organization,
        first_name=PITCHER.first_name,
        last_name=PITCHER.last_name,
        external_id=PITCHER.external_id,
    )
    second = make_player(
        db,
        organization,
        first_name=SECOND.first_name,
        last_name=SECOND.last_name,
        external_id=SECOND.external_id,
    )

    service = IngestionService(db, organization, TrackmanCsvProvider(), object_store)
    service.ingest(
        SourcePayload(
            data=build_day_csv([PITCHER, SECOND], SESSION_DATE, history_start=HISTORY_START),
            filename="roster.csv",
        )
    )

    make_user(db, organization, subject="dev|coach", role=Role.COACH)
    make_user(db, organization, subject="dev|admin", role=Role.ADMIN)
    make_user(db, organization, subject="dev|p1", role=Role.PLAYER, player=first)
    make_user(db, organization, subject="dev|p2", role=Role.PLAYER, player=second)
    db.flush()
    return {"first": first, "second": second}


def auth(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {subject}"}


# -- authentication ----------------------------------------------------------


def test_protected_endpoints_reject_anonymous_callers(client, roster) -> None:  # type: ignore[no-untyped-def]
    for path in ("/api/v1/me", "/api/v1/players", "/api/v1/dashboard/today"):
        assert client.get(path).status_code == 401, path


def test_malformed_and_unknown_credentials_are_rejected(client, roster) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/v1/me", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/api/v1/me", headers=auth("garbage")).status_code == 401
    # Well-formed but belonging to nobody.
    assert client.get("/api/v1/me", headers=auth("dev|nobody")).status_code == 401


def test_health_is_public(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/health").status_code == 200


# -- coach / admin access ----------------------------------------------------


def test_coach_can_read_any_athlete_in_their_organization(client, roster) -> None:  # type: ignore[no-untyped-def]
    for player in (roster["first"], roster["second"]):
        response = client.get(f"/api/v1/players/{player.id}", headers=auth("dev|coach"))
        assert response.status_code == 200
        assert response.json()["id"] == str(player.id)


def test_coach_can_search_the_roster(client, roster) -> None:  # type: ignore[no-untyped-def]
    response = client.get(f"/api/v1/players?q={PITCHER.last_name}", headers=auth("dev|coach"))

    assert response.status_code == 200
    assert [p["last_name"] for p in response.json()] == [PITCHER.last_name]


# -- player self-access ------------------------------------------------------


def test_player_can_read_their_own_profile(client, roster) -> None:  # type: ignore[no-untyped-def]
    player = roster["first"]

    assert client.get("/api/v1/me", headers=auth("dev|p1")).status_code == 200
    assert client.get(f"/api/v1/players/{player.id}", headers=auth("dev|p1")).status_code == 200
    assert client.get("/api/v1/me/overview", headers=auth("dev|p1")).status_code == 200
    assert client.get("/api/v1/me/prs", headers=auth("dev|p1")).status_code == 200


def test_player_cannot_read_another_athlete_by_changing_the_url(client, roster) -> None:  # type: ignore[no-untyped-def]
    """The central authorization requirement."""
    other = roster["second"]

    for path in (
        f"/api/v1/players/{other.id}",
        f"/api/v1/players/{other.id}/overview",
        f"/api/v1/players/{other.id}/prs",
        f"/api/v1/players/{other.id}/sessions",
        f"/api/v1/players/{other.id}/metrics/pitch.fastball.max_velocity/series",
        f"/api/v1/players/{other.id}/prs/pitch.fastball.max_velocity/history",
        f"/api/v1/players/{other.id}/hitting/latest",
        f"/api/v1/players/{other.id}/hitting/sessions",
    ):
        assert client.get(path, headers=auth("dev|p1")).status_code == 404, path


def test_player_cannot_list_the_roster_or_see_the_coach_dashboard(client, roster) -> None:  # type: ignore[no-untyped-def]
    for path in (
        "/api/v1/players",
        "/api/v1/dashboard/today",
        "/api/v1/prs/recent",
        "/api/v1/integrations/status",
        "/api/v1/identity/unresolved",
        "/api/v1/sync/futures/pending",
    ):
        assert client.get(path, headers=auth("dev|p1")).status_code == 403, path


def test_coach_cannot_perform_admin_only_identity_mapping(client, roster) -> None:  # type: ignore[no-untyped-def]
    """Deciding whose data is whose is an admin action."""
    response = client.post(
        f"/api/v1/identity/unresolved/{uuid.uuid4()}/resolve",
        headers=auth("dev|coach"),
        json={"player_id": str(roster["first"].id)},
    )

    assert response.status_code == 403


# -- cross-organization isolation -------------------------------------------


def test_user_cannot_reach_another_organizations_athlete(
    client, db: Session, roster, organization: Organization
) -> None:
    """Existence is not leaked: a foreign athlete is simply not found."""
    other_org = Organization(name="Rival Facility", slug="rival", timezone="UTC")
    db.add(other_org)
    db.flush()
    foreign: Player = make_player(
        db, other_org, first_name="Foreign", last_name="Athlete", external_id="TM-FOREIGN"
    )
    db.flush()

    response = client.get(f"/api/v1/players/{foreign.id}", headers=auth("dev|coach"))

    assert response.status_code == 404
    assert "Foreign" not in response.text


def test_roster_search_never_crosses_organizations(
    client, db: Session, roster, organization: Organization
) -> None:
    other_org = Organization(name="Rival Facility", slug="rival2", timezone="UTC")
    db.add(other_org)
    db.flush()
    make_player(db, other_org, first_name="Foreign", last_name="Athlete")
    db.flush()

    response = client.get("/api/v1/players?q=Athlete", headers=auth("dev|coach"))

    assert response.status_code == 200
    assert response.json() == []
