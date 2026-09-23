"""Live at-bat ingestion and the hitting report, end to end.

The fixture below mirrors the shape of a real export but every athlete in it is
invented. Real exports are gitignored and never used in tests.
"""

from __future__ import annotations

import csv
import io
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bsa.api.app import create_app
from bsa.api.deps import get_object_store_dep
from bsa.db.models import (
    ExternalPlayerIdentity,
    HitEvent,
    IdentityResolutionItem,
    Organization,
    PitchEvent,
    SessionVideo,
    TrainingSession,
)
from bsa.db.session import get_db
from bsa.domain.enums import ImportStatus, Role, SwingResult
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.live_atbat import vendor_identity
from bsa.integrations.trackman.schema import SourcePayload
from bsa.services.ingestion import IngestionService
from tests.conftest import make_player, make_user

pytestmark = pytest.mark.integration

HITTER = "Rivera, Mateo"
PITCHER = "Nolan, Pete"
TODAY = date(2026, 9, 23)
ADMIN = {"Authorization": "Bearer dev|admin"}
COACH = {"Authorization": "Bearer dev|coach"}

FIELDS = [
    "player_name",
    "opponent_name",
    "session_date_display",
    "session_time_display",
    "competition",
    "pitch_set",
    "event_number",
    "marker_shape",
    "pitch_speed_mph",
    "total_spin_rpm",
    "tilt_clock",
    "release_height_ft",
    "induced_vertical_movement_in",
    "horizontal_movement_in",
    "exit_speed_mph",
    "hit_spin_rate_rpm",
    "launch_angle_deg",
    "pitch_type",
    "hit_type",
    "source_image",
]


def live_atbat_csv(events: list[dict[str, object]], *, day: str = "Sep 22") -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for index, event in enumerate(events, start=1):
        writer.writerow(
            {
                "player_name": HITTER,
                "opponent_name": PITCHER,
                "session_date_display": day,
                "session_time_display": "7:05 PM",
                "competition": "Live ABs",
                "pitch_set": "R",
                "event_number": index,
                "source_image": "image.png",
                **event,
            }
        )
    return buffer.getvalue().encode()


def fastball(marker: str, **extra: object) -> dict[str, object]:
    return {
        "marker_shape": marker,
        "pitch_speed_mph": 78.5,
        "total_spin_rpm": 1800,
        "tilt_clock": "1:00",
        "release_height_ft": 5.1,
        "induced_vertical_movement_in": 15.0,
        "horizontal_movement_in": 9.0,
        **extra,
    }


def breaking(marker: str, **extra: object) -> dict[str, object]:
    return {
        "marker_shape": marker,
        "pitch_speed_mph": 68.0,
        "total_spin_rpm": 2200,
        "tilt_clock": "7:45",
        "release_height_ft": 5.3,
        "induced_vertical_movement_in": -6.0,
        "horizontal_movement_in": -11.0,
        **extra,
    }


SESSION = [
    fastball("square", exit_speed_mph=92.0, launch_angle_deg=14.0),
    fastball("square", exit_speed_mph=71.0, launch_angle_deg=2.0),
    fastball("crossed_circle"),
    fastball("circle"),
    fastball("circle"),
    breaking("crossed_circle"),
    breaking("circle"),
    breaking("square", exit_speed_mph=80.0, launch_angle_deg=20.0),
]


@pytest.fixture
def client(db: Session, object_store):  # type: ignore[no-untyped-def]
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_object_store_dep] = lambda: object_store
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def service(db: Session, organization: Organization, object_store) -> IngestionService:  # type: ignore[no-untyped-def]
    return IngestionService(db, organization, TrackmanCsvProvider(today=TODAY), object_store)


def count(db: Session, model) -> int:  # type: ignore[no-untyped-def]
    return db.scalar(select(func.count()).select_from(model)) or 0


def ingest(service: IngestionService, data: bytes, name: str = "ab.csv"):  # type: ignore[no-untyped-def]
    return service.ingest(SourcePayload(data=data, filename=name))


# -- ingestion ---------------------------------------------------------------


def test_the_hitter_is_held_until_a_human_maps_them(
    db: Session, service: IngestionService, metrics
) -> None:
    """The export names athletes but gives no ids. A name still maps nothing."""
    outcome = ingest(service, live_atbat_csv(SESSION))

    assert outcome.status is ImportStatus.PARTIAL
    assert outcome.unresolved_players == [vendor_identity(HITTER)]
    assert count(db, PitchEvent) == 0
    assert count(db, HitEvent) == 0

    queued = db.scalars(select(IdentityResolutionItem)).one()
    assert queued.external_display_name == HITTER


def test_a_same_named_player_is_still_not_matched(
    db: Session, organization: Organization, service: IngestionService, metrics
) -> None:
    make_player(db, organization, first_name="Mateo", last_name="Rivera")
    db.flush()

    outcome = ingest(service, live_atbat_csv(SESSION))

    assert outcome.unresolved_players == [vendor_identity(HITTER)]
    assert count(db, PitchEvent) == 0


def test_once_mapped_every_pitch_faced_is_attributed(
    db: Session, organization: Organization, service: IngestionService, metrics
) -> None:
    hitter = make_player(
        db,
        organization,
        first_name="Mateo",
        last_name="Rivera",
        external_id=vendor_identity(HITTER),
        position="OF",
    )
    db.flush()

    outcome = ingest(service, live_atbat_csv(SESSION))

    assert outcome.status is ImportStatus.SUCCESS
    assert count(db, PitchEvent) == len(SESSION)
    assert count(db, HitEvent) == 3

    pitches = list(db.scalars(select(PitchEvent)))
    assert {p.batter_id for p in pitches} == {hitter.id}
    # The opposing pitcher is named but never rostered, so no identity is
    # asserted for them and they do not enter the mapping queue.
    assert {p.player_id for p in pitches} == {None}
    assert count(db, IdentityResolutionItem) == 0

    results = {p.external_event_id: p.swing_result for p in pitches}
    assert results["1"] is SwingResult.IN_PLAY
    assert results["3"] is SwingResult.SWING_MISS
    assert results["4"] is SwingResult.TAKEN


def test_the_session_records_the_opponent_and_the_inferred_year(
    db: Session, organization: Organization, service: IngestionService, metrics
) -> None:
    make_player(
        db,
        organization,
        first_name="Mateo",
        last_name="Rivera",
        external_id=vendor_identity(HITTER),
    )
    db.flush()

    ingest(service, live_atbat_csv(SESSION))

    session = db.scalars(select(TrainingSession)).one()
    assert session.session_type == "LIVE_AT_BAT"
    assert session.session_date == date(2026, 9, 22)
    assert session.session_metadata["opponent_name"] == PITCHER
    # The export has no year. The assumption is recorded rather than hidden.
    assert session.session_metadata["year_inferred"] is True


def test_a_year_less_date_never_lands_in_the_future(
    db: Session, organization: Organization, service: IngestionService, metrics
) -> None:
    """ "Dec 20" imported in September is last December, not next."""
    make_player(
        db,
        organization,
        first_name="Mateo",
        last_name="Rivera",
        external_id=vendor_identity(HITTER),
    )
    db.flush()

    ingest(service, live_atbat_csv(SESSION, day="Dec 20"), "dec.csv")

    session = db.scalars(select(TrainingSession)).one()
    assert session.session_date == date(2025, 12, 20)


def test_reimporting_the_same_at_bat_creates_no_duplicates(
    db: Session, organization: Organization, service: IngestionService, metrics
) -> None:
    """The export carries no session id, so the composed one has to be stable."""
    make_player(
        db,
        organization,
        first_name="Mateo",
        last_name="Rivera",
        external_id=vendor_identity(HITTER),
    )
    db.flush()

    ingest(service, live_atbat_csv(SESSION))
    before = (count(db, TrainingSession), count(db, PitchEvent), count(db, HitEvent))

    service.ingest(
        SourcePayload(data=live_atbat_csv(SESSION), filename="ab.csv"),
        force_reprocess=True,
    )

    db.expire_all()
    assert (count(db, TrainingSession), count(db, PitchEvent), count(db, HitEvent)) == before


# -- the report --------------------------------------------------------------


@pytest.fixture
def batted(db: Session, organization: Organization, service: IngestionService, metrics):  # type: ignore[no-untyped-def]
    hitter = make_player(
        db,
        organization,
        first_name="Mateo",
        last_name="Rivera",
        external_id=vendor_identity(HITTER),
        position="OF",
    )
    other = make_player(db, organization, first_name="Other", last_name="Athlete")
    make_user(db, organization, subject="dev|admin", role=Role.ADMIN)
    make_user(db, organization, subject="dev|coach", role=Role.COACH)
    make_user(db, organization, subject="dev|hitter", role=Role.PLAYER, player=hitter)
    make_user(db, organization, subject="dev|other", role=Role.PLAYER, player=other)
    ingest(service, live_atbat_csv(SESSION))
    db.flush()
    return {"hitter": hitter, "other": other}


def test_the_report_counts_what_actually_happened(client, db: Session, batted) -> None:
    body = client.get(
        "/api/v1/me/hitting/latest", headers={"Authorization": "Bearer dev|hitter"}
    ).json()

    assert body["pitches_faced"] == 8
    assert body["taken"] == 3
    assert body["swings"] == 5
    assert body["whiffs"] == 2
    assert body["batted_balls"] == 3
    assert body["best_exit_velocity_mph"] == 92.0
    assert body["opponent_name"] == PITCHER


def test_batted_balls_are_listed_hardest_first(client, db: Session, batted) -> None:
    body = client.get(
        "/api/v1/me/hitting/latest", headers={"Authorization": "Bearer dev|hitter"}
    ).json()

    velocities = [c["exit_velocity_mph"] for c in body["contact"]]
    assert velocities == sorted(velocities, reverse=True)
    assert body["contact"][0]["in_sweet_spot"] is True


def test_thin_pitch_groups_are_marked_not_judgeable(client, db: Session, batted) -> None:
    """Three swings against breaking balls must not read as a weakness."""
    body = client.get(
        "/api/v1/me/hitting/latest", headers={"Authorization": "Bearer dev|hitter"}
    ).json()

    offspeed = next(g for g in body["groups"] if g["group"] == "OFFSPEED")
    assert offspeed["enough_to_judge"] is False


def test_a_player_cannot_read_another_athletes_report(client, db: Session, batted) -> None:
    """A player reaching another athlete gets "not found", not "forbidden".

    Saying "forbidden" would confirm that athlete exists, letting a player
    enumerate the roster by trying ids.
    """
    own = client.get("/api/v1/me/hitting/latest", headers={"Authorization": "Bearer dev|other"})
    assert own.status_code == 404  # they have no sessions of their own

    for path in (
        f"/api/v1/players/{batted['hitter'].id}/hitting/latest",
        f"/api/v1/players/{batted['hitter'].id}/hitting/sessions",
    ):
        response = client.get(path, headers={"Authorization": "Bearer dev|other"})
        assert response.status_code == 404, path
        assert batted["hitter"].last_name not in response.text


def test_a_coach_can_read_the_report(client, db: Session, batted) -> None:
    response = client.get(f"/api/v1/players/{batted['hitter'].id}/hitting/latest", headers=COACH)

    assert response.status_code == 200
    assert response.json()["pitches_faced"] == 8


# -- video -------------------------------------------------------------------


def test_a_coach_can_attach_a_video_and_the_athlete_sees_it(client, db: Session, batted) -> None:
    session = db.scalars(select(TrainingSession)).one()

    created = client.post(
        f"/api/v1/players/{batted['hitter'].id}/hitting/sessions/{session.id}/videos",
        headers=ADMIN,
        json={
            "title": "Hardest ball of the day",
            "url": "https://example.com/clip.mp4",
            "external_event_id": "1",
        },
    )
    assert created.status_code == 201

    body = client.get(
        "/api/v1/me/hitting/latest", headers={"Authorization": "Bearer dev|hitter"}
    ).json()
    assert len(body["videos"]) == 1
    assert body["videos"][0]["external_event_id"] == "1"


def test_a_video_link_must_be_a_web_url(client, db: Session, batted) -> None:
    """This renders as a link on a page shown to a minor."""
    session = db.scalars(select(TrainingSession)).one()

    for bad in ("javascript:alert(1)", "data:text/html,<script>", "/etc/passwd"):
        response = client.post(
            f"/api/v1/players/{batted['hitter'].id}/hitting/sessions/{session.id}/videos",
            headers=ADMIN,
            json={"title": "bad", "url": bad},
        )
        assert response.status_code == 422, bad

    assert count(db, SessionVideo) == 0


def test_a_player_cannot_attach_a_video(client, db: Session, batted) -> None:
    session = db.scalars(select(TrainingSession)).one()

    response = client.post(
        f"/api/v1/players/{batted['hitter'].id}/hitting/sessions/{session.id}/videos",
        headers={"Authorization": "Bearer dev|hitter"},
        json={"title": "mine", "url": "https://example.com/x.mp4"},
    )

    assert response.status_code == 403
    assert count(db, SessionVideo) == 0


def test_identity_is_normalized_so_spacing_does_not_split_an_athlete(
    db: Session, organization: Organization, service: IngestionService, metrics
) -> None:
    make_player(
        db,
        organization,
        first_name="Mateo",
        last_name="Rivera",
        external_id=vendor_identity(HITTER),
    )
    db.flush()

    spaced = live_atbat_csv(SESSION).replace(b"Rivera, Mateo", b"Rivera,  Mateo ")
    outcome = service.ingest(SourcePayload(data=spaced, filename="spaced.csv"))

    assert outcome.unresolved_players == []
    assert count(db, ExternalPlayerIdentity) == 1
