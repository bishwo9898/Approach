"""Development seed.

Creates the organization, users, athletes, metric catalog and Futures mappings,
then generates a synthetic training history and ingests it **through the real
pipeline** -- the same `IngestionService` production will use.

That last point is deliberate. Inserting metrics and PRs directly would produce
a dashboard that looks right while proving nothing; running the seed through
ingestion means a broken parser, a broken metric or a broken PR engine shows up
the moment you seed.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from bsa.core.config import get_settings
from bsa.core.logging import configure_logging, get_logger
from bsa.db.models import (
    ExternalMetricMapping,
    ExternalPlayerIdentity,
    MetricDefinition,
    Organization,
    Player,
    User,
)
from bsa.db.session import session_scope
from bsa.domain.enums import Handedness, Role
from bsa.domain.metric_catalog import STARTER_FUTURES_MAPPINGS, STARTER_METRICS
from bsa.integrations.storage import get_object_store
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.schema import SourcePayload
from bsa.scripts.synthetic import ATHLETES, SyntheticAthlete, build_day_csv
from bsa.services.ingestion import IngestionService

log = get_logger(__name__)

ORG_SLUG = "approach-baseball"
ORG_NAME = "Approach Baseball Performance"

#: Development logins. Not secrets -- see bsa.integrations.auth.dev.
DEV_USERS = [
    ("dev|admin", "admin@example.test", "Dana Admin", Role.ADMIN, None),
    ("dev|coach", "coach@example.test", "Chris Coach", Role.COACH, None),
    ("dev|player", "jake@example.test", "Jake Williams", Role.PLAYER, "TM-100241"),
    ("dev|player2", "marcus@example.test", "Marcus Cole", Role.PLAYER, "TM-100482"),
]


def ensure_organization(db: Session) -> Organization:
    org = db.scalars(select(Organization).where(Organization.slug == ORG_SLUG)).first()
    if org is None:
        org = Organization(name=ORG_NAME, slug=ORG_SLUG, timezone="America/New_York")
        db.add(org)
        db.flush()
        log.info("seed.organization.created", slug=ORG_SLUG)
    return org


def ensure_players(db: Session, org: Organization) -> dict[str, Player]:
    """Create athletes and their TrackMan identity mappings.

    The mapping is explicit and created here on purpose: in production a human
    makes it through the identity-resolution queue. Nothing auto-matches names.
    """
    by_external: dict[str, Player] = {}

    for athlete in ATHLETES:
        identity = db.scalars(
            select(ExternalPlayerIdentity).where(
                ExternalPlayerIdentity.organization_id == org.id,
                ExternalPlayerIdentity.provider == "trackman",
                ExternalPlayerIdentity.external_id == athlete.external_id,
            )
        ).first()
        if identity is not None:
            by_external[athlete.external_id] = db.get(Player, identity.player_id)  # type: ignore[assignment]
            continue

        player = Player(
            organization_id=org.id,
            first_name=athlete.first_name,
            last_name=athlete.last_name,
            preferred_name=athlete.preferred_name,
            graduation_year=athlete.graduation_year,
            position=athlete.position,
            bats=Handedness(athlete.bats),
            throws=Handedness(athlete.throws),
            active=True,
        )
        db.add(player)
        db.flush()

        db.add(
            ExternalPlayerIdentity(
                organization_id=org.id,
                player_id=player.id,
                provider="trackman",
                external_id=athlete.external_id,
                external_display_name=f"{athlete.last_name}, {athlete.first_name}",
                player_metadata={"source": "seed"},
            )
        )
        by_external[athlete.external_id] = player

    db.flush()
    return by_external


def ensure_users(db: Session, org: Organization, players: dict[str, Player]) -> None:
    for subject, email, name, role, external_id in DEV_USERS:
        existing = db.scalars(
            select(User).where(User.auth_provider == "dev", User.auth_subject == subject)
        ).first()
        if existing is not None:
            continue
        player = players.get(external_id) if external_id else None
        db.add(
            User(
                organization_id=org.id,
                auth_provider="dev",
                auth_subject=subject,
                email=email,
                display_name=name,
                role=role,
                player_id=player.id if player else None,
            )
        )
    db.flush()


def ensure_metrics(db: Session, org: Organization) -> dict[str, MetricDefinition]:
    by_key: dict[str, MetricDefinition] = {}
    for seed in STARTER_METRICS:
        definition = db.scalars(
            select(MetricDefinition).where(
                MetricDefinition.organization_id == org.id, MetricDefinition.key == seed.key
            )
        ).first()
        if definition is None:
            definition = MetricDefinition(
                organization_id=org.id,
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
            db.flush()
        by_key[seed.key] = definition
    return by_key


def ensure_futures_mappings(
    db: Session, org: Organization, metrics: dict[str, MetricDefinition]
) -> None:
    for mapping_seed in STARTER_FUTURES_MAPPINGS:
        definition = metrics.get(mapping_seed.metric_key)
        if definition is None:
            continue
        existing = db.scalars(
            select(ExternalMetricMapping).where(
                ExternalMetricMapping.organization_id == org.id,
                ExternalMetricMapping.destination == "futures",
                ExternalMetricMapping.metric_definition_id == definition.id,
            )
        ).first()
        if existing is not None:
            continue
        db.add(
            ExternalMetricMapping(
                organization_id=org.id,
                metric_definition_id=definition.id,
                destination="futures",
                destination_field=mapping_seed.destination_field,
                destination_unit=(
                    mapping_seed.destination_unit.value if mapping_seed.destination_unit else None
                ),
                destination_precision=mapping_seed.destination_precision,
            )
        )
    db.flush()


def _training_days(today: date, weeks: int) -> list[date]:
    """Tuesdays, Thursdays and Saturdays -- a plausible training cadence.

    The anchor date is always included, even when it is not a training day.
    Otherwise a seed run on a Sunday produces a dashboard whose headline
    figures are all zero, which is correct but a poor first impression and
    easily mistaken for something being broken.
    """
    days: list[date] = []
    cursor = today - timedelta(weeks=weeks)
    while cursor <= today:
        if cursor.weekday() in (1, 3, 5):
            days.append(cursor)
        cursor += timedelta(days=1)

    if today not in days:
        days.append(today)
    return days


def ingest_history(
    db: Session,
    org: Organization,
    *,
    weeks: int,
    today: date,
    athletes: list[SyntheticAthlete],
) -> int:
    """Generate and ingest a synthetic training history, oldest day first."""
    settings = get_settings()
    service = IngestionService(db, org, TrackmanCsvProvider(), get_object_store(settings))

    days = _training_days(today, weeks)
    history_start = days[0] if days else today

    # One staged breakout on the most recent day, so the seeded database always
    # demonstrates a fresh personal record on the coach dashboard.
    latest = days[-1] if days else today
    bonus_by_day = {latest: {"TM-100377": 1.6, "TM-100482": 2.4}}

    imported = 0
    for day in days:
        payload = SourcePayload(
            data=build_day_csv(
                athletes,
                day,
                history_start=history_start,
                velocity_bonus=bonus_by_day.get(day),
            ),
            filename=f"trackman_{day.isoformat()}.csv",
            import_type="csv_seed",
        )
        outcome = service.ingest(payload)
        if not outcome.is_duplicate:
            imported += 1
    return imported


def seed(*, weeks: int = 14, today: date | None = None, reset: bool = False) -> None:
    settings = get_settings()
    if not settings.is_development:
        raise SystemExit(
            f"refusing to seed synthetic data into BSA_ENV={settings.env.value}. "
            "Seeding is a development-only operation."
        )

    today = today or date.today()
    with session_scope() as db:
        if reset:
            _reset(db)
        org = ensure_organization(db)
        players = ensure_players(db, org)
        ensure_users(db, org, players)
        metrics = ensure_metrics(db, org)
        ensure_futures_mappings(db, org, metrics)
        imported = ingest_history(db, org, weeks=weeks, today=today, athletes=ATHLETES)

    print(f"\nSeeded organization {ORG_NAME!r}")
    print(f"  athletes:        {len(ATHLETES)}")
    print(f"  metrics:         {len(STARTER_METRICS)}")
    print(f"  imports ingested:{imported}")
    print("\nDevelopment tokens (send as 'Authorization: Bearer <token>'):")
    for subject, _email, name, role, _ext in DEV_USERS:
        print(f"  {role.value:<6} {name:<16} {subject}")
    print()


def _reset(db: Session) -> None:
    """Drop all seeded rows. Development only, and never run automatically."""
    from bsa.db.base import Base

    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.flush()
    log.warning("seed.reset", tables=len(Base.metadata.sorted_tables))


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed synthetic development data.")
    parser.add_argument("--weeks", type=int, default=14, help="weeks of history (default 14)")
    parser.add_argument("--today", type=str, default=None, help="anchor date, YYYY-MM-DD")
    parser.add_argument(
        "--reset", action="store_true", help="delete all existing rows first (dev only)"
    )
    args = parser.parse_args()

    configure_logging(get_settings().log_level)
    seed(
        weeks=args.weeks,
        today=date.fromisoformat(args.today) if args.today else None,
        reset=args.reset,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
