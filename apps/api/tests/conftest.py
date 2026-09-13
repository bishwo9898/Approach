"""Shared test fixtures.

Integration tests run against a real PostgreSQL database. They are not mocked:
the guarantees this system makes -- upsert idempotency, uniqueness constraints,
JSONB storage -- are database behaviours, and a fake would only prove the fake
works.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("BSA_ENV", "development")
os.environ.setdefault("BSA_AUTH_PROVIDER", "dev")

from bsa.core.config import get_settings
from bsa.db.base import Base
from bsa.db.models import (
    ExternalMetricMapping,
    ExternalPlayerIdentity,
    MetricDefinition,
    Organization,
    Player,
    User,
)
from bsa.domain.enums import Handedness, Role
from bsa.domain.metric_catalog import (
    STARTER_FUTURES_MAPPINGS,
    STARTER_METRICS,
)
from bsa.integrations.storage.local import LocalObjectStore


@pytest.fixture(scope="session")
def database_url() -> str:
    return get_settings().test_database_url


@pytest.fixture(scope="session")
def engine(database_url: str):  # type: ignore[no-untyped-def]
    try:
        engine = create_engine(database_url, future=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover -- environment problem, not a test failure
        pytest.skip(f"test database unavailable ({exc}); set BSA_TEST_DATABASE_URL")

    # Rebuilt from the models rather than by running migrations: this keeps the
    # suite fast, and migration correctness is verified separately by applying
    # them to a real database in CI.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    """A session wrapped in a transaction that is always rolled back.

    Each test sees a clean database without paying to recreate the schema.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False, future=True)()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def organization(db: Session) -> Organization:
    org = Organization(
        name="Test Facility", slug=f"test-{uuid.uuid4().hex[:8]}", timezone="America/New_York"
    )
    db.add(org)
    db.flush()
    return org


@pytest.fixture
def metrics(db: Session, organization: Organization) -> dict[str, MetricDefinition]:
    """The real starter catalog, so tests exercise production metric configs."""
    by_key: dict[str, MetricDefinition] = {}
    for seed in STARTER_METRICS:
        definition = MetricDefinition(
            organization_id=organization.id,
            key=seed.key,
            display_name=seed.display_name,
            description=seed.description,
            category=seed.category,
            event_source=seed.event_source,
            aggregation=seed.aggregation,
            record_direction=seed.record_direction,
            data_type=seed.data_type,
            unit=seed.unit.value,
            display_precision=seed.display_precision,
            min_sample_size=seed.min_sample_size,
            spec=seed.spec,
            is_headline=seed.is_headline,
            sort_order=seed.sort_order,
        )
        db.add(definition)
        by_key[seed.key] = definition
    db.flush()

    for mapping in STARTER_FUTURES_MAPPINGS:
        definition = by_key[mapping.metric_key]
        db.add(
            ExternalMetricMapping(
                organization_id=organization.id,
                metric_definition_id=definition.id,
                destination="futures",
                destination_field=mapping.destination_field,
                destination_unit=(
                    mapping.destination_unit.value if mapping.destination_unit else None
                ),
                destination_precision=mapping.destination_precision,
            )
        )
    db.flush()
    return by_key


def make_player(
    db: Session,
    organization: Organization,
    *,
    first_name: str,
    last_name: str,
    external_id: str | None = None,
    position: str = "RHP",
) -> Player:
    player = Player(
        organization_id=organization.id,
        first_name=first_name,
        last_name=last_name,
        position=position,
        bats=Handedness.RIGHT,
        throws=Handedness.RIGHT,
        graduation_year=2028,
    )
    db.add(player)
    db.flush()
    if external_id:
        db.add(
            ExternalPlayerIdentity(
                organization_id=organization.id,
                player_id=player.id,
                provider="trackman",
                external_id=external_id,
                external_display_name=f"{last_name}, {first_name}",
            )
        )
        db.flush()
    return player


@pytest.fixture
def player(db: Session, organization: Organization) -> Player:
    return make_player(
        db, organization, first_name="Ryan", last_name="Jones", external_id="TM-TEST-1"
    )


@pytest.fixture
def object_store(tmp_path) -> LocalObjectStore:  # type: ignore[no-untyped-def]
    return LocalObjectStore(tmp_path / "objectstore")


@pytest.fixture
def today() -> date:
    """Fixed anchor date so window arithmetic is never time-of-run dependent."""
    return date(2026, 9, 12)


def make_user(
    db: Session,
    organization: Organization,
    *,
    subject: str,
    role: Role,
    player: Player | None = None,
) -> User:
    user = User(
        organization_id=organization.id,
        auth_provider="dev",
        auth_subject=subject,
        email=f"{subject.replace('|', '-')}@example.test",
        display_name=subject,
        role=role,
        player_id=player.id if player else None,
    )
    db.add(user)
    db.flush()
    return user
