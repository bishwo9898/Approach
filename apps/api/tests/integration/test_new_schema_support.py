"""Adding support for a real TrackMan schema must be a one-file change.

This is the claim the whole mapping layer rests on, and the step that has to
work the day a real export arrives. So it is tested with a schema that shares
nothing with ours: different column names, different ordering, and velocities
reported in metres per second rather than mph.

If this test passes, supporting a real export is adding a `ColumnMap` and
nothing else.
"""

from __future__ import annotations

import csv
import io
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bsa.core.units import Unit
from bsa.db.models import (
    MetricObservation,
    Organization,
    PersonalRecord,
    PitchEvent,
    Player,
)
from bsa.domain.enums import ImportStatus
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.mapping import COLUMN_MAPS, ColumnMap, NumericColumn
from bsa.integrations.trackman.schema import SourcePayload
from bsa.services.ingestion import IngestionService
from tests.conftest import make_player

pytestmark = pytest.mark.integration

SESSION_DATE = date(2026, 9, 12)

#: A plausible foreign export: nothing in common with `synthetic.v1`.
VENDOR_B = ColumnMap(
    version="vendor_b.v1",
    session_id="GameUID",
    session_date="LocalDate",
    pitch_id="PlayID",
    pitcher_id="PitcherGUID",
    pitcher_name="PitcherName",
    batter_id="BatterGUID",
    tagged_pitch_type="PitchKind",
    pitch_call="Result",
    required=frozenset({"GameUID", "LocalDate", "PlayID", "PitcherGUID"}),
    pitch_numeric={
        # Reported in metres per second, converted once at this boundary.
        "velocity_mph": NumericColumn("ReleaseVelocity", Unit.MPH, 20.0, 110.0),
        "spin_rate_rpm": NumericColumn("Spin", Unit.RPM, 0.0, 4000.0),
    },
    hit_numeric={
        "exit_velocity_mph": NumericColumn("ContactVelocity", Unit.MPH, 10.0, 130.0),
    },
    training_context={"DrillName": "drill"},
)


@pytest.fixture
def registered() -> object:
    """Register the foreign schema for the duration of one test."""
    COLUMN_MAPS[VENDOR_B.version] = VENDOR_B
    yield VENDOR_B
    COLUMN_MAPS.pop(VENDOR_B.version, None)


def vendor_b_csv(external_id: str, velocities: list[float]) -> bytes:
    fields = [
        "GameUID",
        "LocalDate",
        "PlayID",
        "PitcherGUID",
        "PitcherName",
        "BatterGUID",
        "PitchKind",
        "Result",
        "ReleaseVelocity",
        "Spin",
        "ContactVelocity",
        "DrillName",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for index, velocity in enumerate(velocities, start=1):
        writer.writerow(
            {
                "GameUID": "VB-SESSION-1",
                "LocalDate": SESSION_DATE.isoformat(),
                "PlayID": f"VB-{index:03d}",
                "PitcherGUID": external_id,
                "PitcherName": "Foreign, Athlete",
                "BatterGUID": "",
                "PitchKind": "Four-Seam",
                "Result": "StrikeCalled",
                "ReleaseVelocity": f"{velocity:.1f}",
                "Spin": "2200",
                "ContactVelocity": "",
                "DrillName": "Bullpen",
            }
        )
    return buffer.getvalue().encode()


def count(db: Session, model) -> int:  # type: ignore[no-untyped-def]
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_a_foreign_schema_ingests_once_its_columns_are_registered(
    db: Session, organization: Organization, metrics, object_store, registered
) -> None:
    player: Player = make_player(
        db,
        organization,
        first_name="Foreign",
        last_name="Athlete",
        external_id="VB-ATHLETE-1",
    )
    db.flush()

    service = IngestionService(db, organization, TrackmanCsvProvider(), object_store)
    outcome = service.ingest(
        SourcePayload(
            data=vendor_b_csv("VB-ATHLETE-1", [88.0, 89.4, 90.1, 87.6, 88.8]),
            filename="vendor_b.csv",
        )
    )

    assert outcome.status is ImportStatus.SUCCESS
    assert outcome.pitch_events == 5
    assert outcome.unresolved_players == []

    # Events landed, attributed, with our own field names.
    pitches = list(db.scalars(select(PitchEvent)))
    assert len(pitches) == 5
    assert {p.player_id for p in pitches} == {player.id}
    # The vendor's "Four-Seam" became our vocabulary, so metric filters match.
    assert {p.pitch_type for p in pitches} == {"FASTBALL"}
    assert pitches[0].training_context["drill"] == "Bullpen"

    # And the derived layers ran, which is the whole point.
    assert count(db, MetricObservation) > 0
    record = db.scalars(
        select(PersonalRecord).where(
            PersonalRecord.metric_definition_id == metrics["pitch.fastball.max_velocity"].id
        )
    ).one()
    assert record.value == pytest.approx(90.1)


def test_the_foreign_schema_is_only_readable_while_registered(
    db: Session, organization: Organization, metrics, object_store
) -> None:
    """Without its ColumnMap the same bytes are refused, not guessed at."""
    service = IngestionService(db, organization, TrackmanCsvProvider(), object_store)

    outcome = service.ingest(
        SourcePayload(data=vendor_b_csv("VB-ATHLETE-1", [88.0]), filename="vb.csv")
    )

    assert outcome.status is ImportStatus.FAILED
    assert "No registered TrackMan schema" in (outcome.error_message or "")
    # The message names every column, so it is actionable on its own.
    assert "ReleaseVelocity" in (outcome.error_message or "")
    assert count(db, PitchEvent) == 0


def test_a_vendor_reporting_metres_per_second_is_converted_not_mislabelled(
    db: Session, organization: Organization, metrics, object_store
) -> None:
    """The most dangerous mapping mistake there is, proved end to end.

    A velocity read as mph when the vendor reports metres per second is out by
    a factor of 2.24, and every resulting number -- session values, averages,
    personal records -- still looks plausible. Nothing downstream could catch
    it, so the conversion has to be right here.
    """
    metric_units = ColumnMap(
        **{
            **{f: getattr(VENDOR_B, f) for f in VENDOR_B.__dataclass_fields__},
            "version": "vendor_b_ms.v1",
            "pitch_numeric": {
                "velocity_mph": NumericColumn(
                    "ReleaseVelocity", Unit.MPH, 20.0, 110.0, source_unit="m/s"
                ),
            },
        }
    )
    COLUMN_MAPS[metric_units.version] = metric_units
    try:
        make_player(
            db,
            organization,
            first_name="Foreign",
            last_name="Athlete",
            external_id="VB-ATHLETE-1",
        )
        db.flush()

        # 39.8 m/s is an 89 mph fastball. Read as mph it would be 39.8 -- and
        # the range guard would not catch it either, because 39.8 is a
        # perfectly possible mph reading for an off-speed pitch.
        service = IngestionService(db, organization, TrackmanCsvProvider(), object_store)
        outcome = service.ingest(
            SourcePayload(
                data=vendor_b_csv("VB-ATHLETE-1", [39.8, 39.5, 40.1, 39.2, 39.9]),
                filename="vendor_b_ms.csv",
            )
        )

        assert outcome.status is ImportStatus.SUCCESS
        velocities = [p.velocity_mph for p in db.scalars(select(PitchEvent))]
        assert all(v is not None and 85.0 < v < 92.0 for v in velocities), velocities

        record = db.scalars(
            select(PersonalRecord).where(
                PersonalRecord.metric_definition_id == metrics["pitch.fastball.max_velocity"].id
            )
        ).one()
        # 40.1 m/s == 89.7 mph, stored and recorded in mph.
        assert record.value == pytest.approx(89.7, abs=0.1)
    finally:
        COLUMN_MAPS.pop(metric_units.version, None)


def test_the_default_reported_unit_is_the_canonical_one() -> None:
    """The common case stays a two-argument declaration."""
    assert NumericColumn("RelSpeed", Unit.MPH).reported_unit == "mph"
    assert NumericColumn("ReleaseVelocity", Unit.MPH, source_unit="m/s").reported_unit == "m/s"
