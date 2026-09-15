"""The data contract the dashboards depend on.

Guards the properties a chart can be misleading without: every value carries its
unit, its sample size and its source status.
"""

from __future__ import annotations

import itertools
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bsa.api.app import create_app
from bsa.api.deps import get_object_store_dep
from bsa.db.models import Organization
from bsa.db.session import get_db
from bsa.domain.enums import Role
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.schema import SourcePayload
from bsa.scripts.synthetic import ATHLETES, build_day_csv
from bsa.services.ingestion import IngestionService
from tests.conftest import make_player, make_user

pytestmark = pytest.mark.integration

PITCHER = ATHLETES[0]
HITTER = next(a for a in ATHLETES if a.hits)
TODAY = date(2026, 9, 12)
HISTORY_START = date(2026, 7, 1)
COACH = {"Authorization": "Bearer dev|coach"}


@pytest.fixture
def client(db: Session, object_store):  # type: ignore[no-untyped-def]
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_object_store_dep] = lambda: object_store
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(db: Session, organization: Organization, metrics, object_store):  # type: ignore[no-untyped-def]
    """Several training days so window comparisons have something to compare."""
    pitcher = make_player(
        db,
        organization,
        first_name=PITCHER.first_name,
        last_name=PITCHER.last_name,
        external_id=PITCHER.external_id,
    )
    hitter = make_player(
        db,
        organization,
        first_name=HITTER.first_name,
        last_name=HITTER.last_name,
        external_id=HITTER.external_id,
        position="OF",
    )
    make_user(db, organization, subject="dev|coach", role=Role.COACH)

    service = IngestionService(db, organization, TrackmanCsvProvider(), object_store)
    for day in (date(2026, 8, 8), date(2026, 8, 22), date(2026, 9, 5), TODAY):
        service.ingest(
            SourcePayload(
                data=build_day_csv([PITCHER, HITTER], day, history_start=HISTORY_START),
                filename=f"{day}.csv",
            )
        )
    db.flush()
    return {"pitcher": pitcher, "hitter": hitter}


def test_overview_reports_units_samples_and_source_status(client, seeded) -> None:  # type: ignore[no-untyped-def]
    response = client.get(
        f"/api/v1/players/{seeded['pitcher'].id}/overview?range=30d", headers=COACH
    )

    assert response.status_code == 200
    body = response.json()
    assert body["time_range"] == "30d"
    assert body["player"]["display_name"]
    assert body["metrics"], "a pitcher with four sessions must have metrics"

    for metric in body["metrics"]:
        assert metric["definition"]["unit"], "a value without a unit is unusable"
        assert metric["latest"]["unit"] == metric["definition"]["unit"]
        # Sample size travels with the number: 96 mph off two pitches is not the
        # same claim as off forty.
        assert metric["latest"]["sample_size"] > 0
        assert metric["latest"]["source_status"] in ("PRELIMINARY", "VERIFIED")


def test_overview_hides_metrics_the_athlete_has_no_data_for(client, seeded) -> None:  # type: ignore[no-untyped-def]
    """A pitcher has no exit velocity; showing dashes buries what matters."""
    pitcher = client.get(f"/api/v1/players/{seeded['pitcher'].id}/overview", headers=COACH).json()
    hitter = client.get(f"/api/v1/players/{seeded['hitter'].id}/overview", headers=COACH).json()

    pitcher_keys = {m["definition"]["key"] for m in pitcher["metrics"]}
    hitter_keys = {m["definition"]["key"] for m in hitter["metrics"]}

    assert all(k.startswith("pitch.") for k in pitcher_keys)
    assert all(k.startswith("hit.") for k in hitter_keys)


def test_window_comparison_uses_an_equal_length_prior_window(client, seeded) -> None:  # type: ignore[no-untyped-def]
    body = client.get(
        f"/api/v1/players/{seeded['pitcher'].id}/overview?range=30d", headers=COACH
    ).json()

    window = body["metrics"][0]["window"]
    assert window["current"] is not None
    assert set(window) == {
        "current",
        "previous",
        "delta",
        "percent_change",
        "current_sample",
        "previous_sample",
        "current_source_status",
        "previous_source_status",
    }
    assert window["current_source_status"] == "PRELIMINARY"
    if window["previous"] is not None:
        assert window["delta"] == pytest.approx(window["current"] - window["previous"], abs=1e-4)


def test_metric_series_is_chronological_and_labelled(client, seeded) -> None:  # type: ignore[no-untyped-def]
    response = client.get(
        f"/api/v1/players/{seeded['pitcher'].id}"
        "/metrics/pitch.fastball.max_velocity/series?range=90d",
        headers=COACH,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["definition"]["unit"] == "mph"
    dates = [p["observed_on"] for p in body["points"]]
    assert dates == sorted(dates)
    assert len(dates) == 4
    assert all(p["sample_size"] > 0 for p in body["points"])


def test_unknown_metric_key_is_a_clean_404(client, seeded) -> None:  # type: ignore[no-untyped-def]
    response = client.get(
        f"/api/v1/players/{seeded['pitcher'].id}/metrics/does.not.exist/series",
        headers=COACH,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_record_history_returns_the_full_progression(client, seeded) -> None:  # type: ignore[no-untyped-def]
    response = client.get(
        f"/api/v1/players/{seeded['pitcher'].id}/prs/pitch.fastball.max_velocity/history",
        headers=COACH,
    )

    assert response.status_code == 200
    events = response.json()
    assert events, "an improving athlete must have a progression"
    assert events[0]["previous_value"] is None
    for previous, current in itertools.pairwise(events):
        assert current["previous_value"] == previous["new_value"]
        assert current["new_value"] > previous["new_value"]
        assert current["achieved_on"] >= previous["achieved_on"]


def test_sessions_endpoint_reports_event_counts(client, seeded) -> None:  # type: ignore[no-untyped-def]
    response = client.get(f"/api/v1/players/{seeded['pitcher'].id}/sessions", headers=COACH)

    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 4
    assert all(s["pitch_count"] > 0 for s in sessions)
    # Most recent first -- what a coach wants at the top of the page.
    assert [s["session_date"] for s in sessions] == sorted(
        (s["session_date"] for s in sessions), reverse=True
    )


def test_today_snapshot_counts_only_that_day(client, seeded) -> None:  # type: ignore[no-untyped-def]
    body = client.get(f"/api/v1/dashboard/today?date={TODAY}", headers=COACH).json()

    assert body["on_date"] == TODAY.isoformat()
    assert body["athletes_trained"] == 2
    assert body["sessions"] == 2
    assert body["tracked_events"] > 0


def test_integration_status_surfaces_operational_health(client, seeded) -> None:  # type: ignore[no-untyped-def]
    """Broken automation must be visible, not hidden."""
    body = client.get("/api/v1/integrations/status", headers=COACH).json()

    assert body["provider"] == "trackman"
    assert body["last_import_status"] == "SUCCESS"
    assert body["last_successful_import_at"] is not None
    assert body["failed_imports_7d"] == 0
    assert body["unresolved_players"] == 0
    # Everything ingested is still preliminary until TrackMan republishes it.
    assert body["sessions_awaiting_verification"] == 8


def test_metric_catalog_is_served_as_data(client, seeded) -> None:  # type: ignore[no-untyped-def]
    """The dashboard reads the catalog rather than hardcoding metric names."""
    body = client.get("/api/v1/metrics", headers=COACH).json()

    keys = {m["key"] for m in body}
    assert "pitch.fastball.max_velocity" in keys
    assert "pitch.fastball.min_velocity" in keys
    assert "hit.min_exit_velocity" in keys
    assert all(m["unit"] for m in body)
    assert all(
        m["record_direction"] in ("HIGHER_IS_BETTER", "LOWER_IS_BETTER", "NONE") for m in body
    )


def test_csv_upload_endpoint_ingests_and_reports_duplicates(client, seeded) -> None:  # type: ignore[no-untyped-def]
    data = build_day_csv([PITCHER], date(2026, 9, 10), history_start=HISTORY_START)
    files = {"file": ("upload.csv", data, "text/csv")}

    first = client.post("/api/v1/imports/trackman/csv", headers=COACH, files=files)
    assert first.status_code == 200
    assert first.json()["sessions_created"] == 1
    assert first.json()["is_duplicate"] is False

    second = client.post(
        "/api/v1/imports/trackman/csv",
        headers=COACH,
        files={"file": ("upload.csv", data, "text/csv")},
    )
    assert second.status_code == 200
    assert second.json()["is_duplicate"] is True


def test_empty_upload_is_rejected(client, seeded) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/imports/trackman/csv",
        headers=COACH,
        files={"file": ("empty.csv", b"", "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
