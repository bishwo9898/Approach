"""Filing screenshots under the athlete a coach picked.

The reason this exists: screenshots carry a name, not a vendor id, so
ingestion matches on a normalized name. On a roster with 63 shared names that
match is the thing that must not be guessed. Picking the athlete up front turns
it into a statement instead.
"""

from __future__ import annotations

import csv
import io
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bsa.db.models import ExternalPlayerIdentity, Organization
from bsa.domain.screenshot_table import MergedTable, TableRow
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.live_atbat import vendor_identity
from bsa.integrations.trackman.schema import SourcePayload
from bsa.services import screenshots
from bsa.services.ingestion import IngestionService
from tests.conftest import make_player

pytestmark = pytest.mark.integration


def table() -> MergedTable:
    return MergedTable(
        rows=[
            TableRow(
                event_number=number,
                values={
                    "pitch_speed_mph": 78.0,
                    "exit_speed_mph": 90.0 if number == 1 else None,
                    "launch_angle_deg": 14.0 if number == 1 else None,
                },
            )
            for number in (1, 2)
        ],
        source_of={1: "a.png", 2: "a.png"},
    )


def test_the_identity_registered_is_the_one_the_csv_will_carry(
    db: Session, organization: Organization
) -> None:
    """These two are derived in different places and must agree exactly, or
    every screenshot import lands in the mapping queue."""
    player = make_player(db, organization, first_name="Jordan", last_name="Avery")
    db.flush()

    assert screenshots.ensure_name_identity(db, organization.id, player) is True

    identity = db.scalars(select(ExternalPlayerIdentity)).one()
    text = screenshots.to_csv(
        table(), player_name=player.display_name, session_date=date(2026, 9, 22)
    )
    row = next(csv.DictReader(io.StringIO(text)))

    assert identity.external_id == vendor_identity(row["player_name"])


def test_registering_twice_is_a_no_op(db: Session, organization: Organization) -> None:
    player = make_player(db, organization, first_name="Jordan", last_name="Avery")
    db.flush()

    assert screenshots.ensure_name_identity(db, organization.id, player) is True
    assert screenshots.ensure_name_identity(db, organization.id, player) is False
    assert len(db.scalars(select(ExternalPlayerIdentity)).all()) == 1


def test_converted_pitches_attach_to_the_chosen_athlete(
    db: Session, organization: Organization, metrics, object_store
) -> None:
    """End to end: pick an athlete, convert, ingest, and the pitches are
    theirs -- not held in the identity queue."""
    player = make_player(db, organization, first_name="Jordan", last_name="Avery")
    db.flush()
    screenshots.ensure_name_identity(db, organization.id, player)
    db.flush()

    text = screenshots.to_csv(
        table(), player_name=player.display_name, session_date=date(2026, 9, 22)
    )
    outcome = IngestionService(
        db, organization, TrackmanCsvProvider(today=date(2026, 9, 22)), object_store
    ).ingest(SourcePayload(data=text.encode(), filename="s.csv", import_type="screenshot"))

    assert outcome.unresolved_players == []
    assert outcome.pitch_events == 2
    assert outcome.hit_events == 1


def test_without_the_identity_the_pitches_are_held(
    db: Session, organization: Organization, metrics, object_store
) -> None:
    """The behaviour picking an athlete avoids. Nothing is attributed to a
    name-similar athlete; it waits for a human."""
    make_player(db, organization, first_name="Jordan", last_name="Avery")
    db.flush()

    text = screenshots.to_csv(table(), player_name="Jordan Avery", session_date=date(2026, 9, 22))
    outcome = IngestionService(
        db, organization, TrackmanCsvProvider(today=date(2026, 9, 22)), object_store
    ).ingest(SourcePayload(data=text.encode(), filename="s.csv", import_type="screenshot"))

    assert outcome.unresolved_players == [vendor_identity("Jordan Avery")]
    assert outcome.pitch_events == 0
