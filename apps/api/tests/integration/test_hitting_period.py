"""The period view, end to end through the API.

The unit tests in `test_progress.py` decide the arithmetic. These check that a
real athlete's sessions land in the right window, that the endpoint answers
rather than 404s when a window is empty, and that the athlete boundary still
holds on a route that takes a date range.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bsa.api.app import create_app
from bsa.db.models import HitEvent, Organization, PitchEvent, Player, TrainingSession
from bsa.db.session import get_db
from bsa.domain.enums import Role, SourceStatus, SwingResult
from tests.conftest import make_player, make_user

pytestmark = pytest.mark.integration

COACH = {"Authorization": "Bearer dev|coach"}
PLAYER = {"Authorization": "Bearer dev|player"}

#: Anchored to the real today, because the endpoint computes its window from
#: the facility's current date. A fixed anchor would stop overlapping the
#: window the moment the calendar moved past it.
TODAY = date.today()


@pytest.fixture
def client(db: Session):  # type: ignore[no-untyped-def]
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def bat(
    db: Session,
    organization: Organization,
    player: Player,
    day: date,
    exit_velocities: list[float],
) -> None:
    """One session on `day` where the athlete put every pitch in play."""
    session = TrainingSession(
        organization_id=organization.id,
        provider="trackman",
        external_session_id=f"s-{day}-{uuid.uuid4().hex[:6]}",
        session_date=day,
        imported_at=datetime.now(UTC),
        source_status=SourceStatus.VERIFIED,
    )
    db.add(session)
    db.flush()

    for index, velocity in enumerate(exit_velocities):
        event_id = f"{session.external_session_id}-{index}"
        db.add(
            PitchEvent(
                organization_id=organization.id,
                session_id=session.id,
                batter_id=player.id,
                external_event_id=event_id,
                pitch_number=index + 1,
                swing_result=SwingResult.IN_PLAY,
                source_status=SourceStatus.VERIFIED,
            )
        )
        db.add(
            HitEvent(
                organization_id=organization.id,
                session_id=session.id,
                player_id=player.id,
                external_event_id=event_id,
                exit_velocity_mph=velocity,
                launch_angle_deg=18.0,
                source_status=SourceStatus.VERIFIED,
            )
        )
    db.flush()


@pytest.fixture
def athlete(db: Session, organization: Organization) -> Player:
    player = make_player(
        db, organization, first_name="Jordan", last_name="Avery", external_id="TM-PERIOD-1"
    )
    make_user(db, organization, subject="dev|coach", role=Role.COACH)
    make_user(db, organization, subject="dev|player", role=Role.PLAYER, player=player)
    db.flush()
    return player


def summary(client: TestClient, player: Player, range_: str = "30d"):  # type: ignore[no-untyped-def]
    response = client.get(
        f"/api/v1/players/{player.id}/hitting/summary?range={range_}", headers=COACH
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestWindowing:
    def test_it_totals_every_session_in_the_window(
        self, client: TestClient, db: Session, organization: Organization, athlete: Player
    ) -> None:
        bat(db, organization, athlete, TODAY - timedelta(days=20), [90.0, 88.0])
        bat(db, organization, athlete, TODAY - timedelta(days=3), [95.0])

        body = summary(client, athlete, "30d")

        assert body["sessions"] == 2
        assert body["batted_balls"] == 3
        assert body["best_exit_velocity_mph"] == 95.0
        assert body["has_data"] is True
        assert body["has_trend"] is True

    def test_a_session_outside_the_window_is_excluded(
        self, client: TestClient, db: Session, organization: Organization, athlete: Player
    ) -> None:
        bat(db, organization, athlete, TODAY - timedelta(days=3), [90.0])
        bat(db, organization, athlete, TODAY - timedelta(days=60), [110.0])

        body = summary(client, athlete, "30d")

        assert body["sessions"] == 1
        assert body["best_exit_velocity_mph"] == 90.0

    def test_a_wider_window_includes_it(
        self, client: TestClient, db: Session, organization: Organization, athlete: Player
    ) -> None:
        bat(db, organization, athlete, TODAY - timedelta(days=3), [90.0])
        bat(db, organization, athlete, TODAY - timedelta(days=60), [110.0])

        body = summary(client, athlete, "90d")

        assert body["sessions"] == 2
        assert body["best_exit_velocity_mph"] == 110.0

    def test_all_time_starts_at_the_first_session(
        self, client: TestClient, db: Session, organization: Organization, athlete: Player
    ) -> None:
        """Not at an epoch, which would open the trend with years of blanks."""
        first = TODAY - timedelta(days=200)
        bat(db, organization, athlete, first, [90.0])

        body = summary(client, athlete, "all")

        assert body["start"] == first.isoformat()
        assert body["grain"] == "month"

    @pytest.mark.parametrize(
        ("range_", "grain"),
        [("7d", "day"), ("30d", "week"), ("90d", "week"), ("1y", "month")],
    )
    def test_the_grain_follows_the_window(
        self,
        client: TestClient,
        db: Session,
        organization: Organization,
        athlete: Player,
        range_: str,
        grain: str,
    ) -> None:
        bat(db, organization, athlete, TODAY, [90.0])
        assert summary(client, athlete, range_)["grain"] == grain


class TestNothingToShow:
    """The common case while a facility is still collecting data."""

    def test_an_empty_window_answers_rather_than_404s(
        self, client: TestClient, athlete: Player
    ) -> None:
        """ "How did this month go?" has an answer: you did not bat."""
        body = summary(client, athlete, "30d")

        assert body["has_data"] is False
        assert body["sessions"] == 0
        assert body["first_session"] is None

    def test_an_empty_window_sends_nulls_not_zeros(
        self, client: TestClient, athlete: Player
    ) -> None:
        body = summary(client, athlete, "30d")

        assert body["best_exit_velocity_mph"] is None
        assert body["average_exit_velocity_mph"] is None
        assert body["sweet_spot_rate"] is None

    def test_one_session_is_data_but_not_a_trend(
        self, client: TestClient, db: Session, organization: Organization, athlete: Player
    ) -> None:
        bat(db, organization, athlete, TODAY - timedelta(days=2), [91.0])

        body = summary(client, athlete, "30d")

        assert body["has_data"] is True
        assert body["has_trend"] is False
        assert body["best_exit_velocity_mph"] == 91.0

    def test_empty_buckets_are_sent_as_gaps(
        self, client: TestClient, db: Session, organization: Organization, athlete: Player
    ) -> None:
        """The client must be able to draw a gap. Dropping the bucket would
        redraw the axis; a zero would be a measurement that never happened."""
        bat(db, organization, athlete, TODAY, [90.0])

        buckets = summary(client, athlete, "30d")["buckets"]

        blanks = [b for b in buckets if b["sessions"] == 0]
        assert blanks, "a month with one session must contain empty buckets"
        assert all(b["best_exit_velocity_mph"] is None for b in blanks)
        assert all(b["batted_balls"] == 0 for b in blanks)


class TestComparison:
    def test_it_compares_with_the_preceding_equal_window(
        self, client: TestClient, db: Session, organization: Organization, athlete: Player
    ) -> None:
        bat(db, organization, athlete, TODAY - timedelta(days=5), [95.0])
        bat(db, organization, athlete, TODAY - timedelta(days=40), [90.0])

        change = summary(client, athlete, "30d")["best_exit_velocity_change"]

        assert change["current"] == 95.0
        assert change["previous"] == 90.0
        assert change["delta"] == 5.0

    def test_a_first_window_has_no_delta_rather_than_a_zero(
        self, client: TestClient, db: Session, organization: Organization, athlete: Player
    ) -> None:
        bat(db, organization, athlete, TODAY - timedelta(days=5), [95.0])

        change = summary(client, athlete, "30d")["best_exit_velocity_change"]

        assert change["previous"] is None
        assert change["delta"] is None
        assert change["percent_change"] is None

    def test_sample_sizes_are_sent_with_the_change(
        self, client: TestClient, db: Session, organization: Organization, athlete: Player
    ) -> None:
        bat(db, organization, athlete, TODAY - timedelta(days=5), [95.0, 80.0])
        bat(db, organization, athlete, TODAY - timedelta(days=40), [90.0])

        change = summary(client, athlete, "30d")["best_exit_velocity_change"]

        assert change["current_sample"] == 2
        assert change["previous_sample"] == 1


class TestAuthorization:
    def test_an_athlete_reads_their_own_period_without_sending_an_id(
        self, client: TestClient, db: Session, organization: Organization, athlete: Player
    ) -> None:
        bat(db, organization, athlete, TODAY, [90.0])

        response = client.get("/api/v1/me/hitting/summary?range=30d", headers=PLAYER)

        assert response.status_code == 200
        assert response.json()["sessions"] == 1

    def test_an_athlete_cannot_read_another_athletes_period(
        self, client: TestClient, db: Session, organization: Organization, athlete: Player
    ) -> None:
        other = make_player(
            db, organization, first_name="Riley", last_name="Chen", external_id="TM-PERIOD-2"
        )
        db.flush()

        response = client.get(
            f"/api/v1/players/{other.id}/hitting/summary?range=30d", headers=PLAYER
        )

        # 404, not 403: the difference would confirm the athlete is enrolled.
        assert response.status_code == 404

    def test_an_unknown_range_is_rejected(self, client: TestClient, athlete: Player) -> None:
        response = client.get(
            f"/api/v1/players/{athlete.id}/hitting/summary?range=forever", headers=COACH
        )
        assert response.status_code == 422
