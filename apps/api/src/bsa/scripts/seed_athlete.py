"""Set up the testing roster from a real export: one coach, one athlete.

    python -m bsa.scripts.seed_athlete "CSV files/<athlete>/<export>.csv"

Unlike `bsa.scripts.seed`, this creates nothing synthetic. It reads the athlete
the export names, creates them, registers their TrackMan identity, ingests the
file through the ordinary pipeline, and then wires a coach and a player login.

Those two logins are ordinary local accounts with ordinary Argon2 hashes -- the
same ones `provision_roster --demo-accounts` makes, by calling the same
function. There is no bypass anywhere in the code, so signing in with them
exercises the real sign-in path.

The athlete is taken from the file rather than hardcoded. That keeps a real
person's name out of a public repository, and means the next athlete needs no
code change -- just their export.

Safe to re-run: accounts are created only if missing, and ingestion is
idempotent, so running it twice leaves the database exactly as it was.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from bsa.core.config import get_settings
from bsa.core.logging import configure_logging
from bsa.db.models import ExternalPlayerIdentity, Organization, Player
from bsa.db.session import session_scope
from bsa.integrations.storage import get_object_store
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.live_atbat import vendor_identity
from bsa.integrations.trackman.schema import SourcePayload
from bsa.scripts.provision_roster import (
    DEV_DEMO_PASSWORD,
    ensure_athlete_account,
    ensure_demo_accounts,
)
from bsa.services.ingestion import IngestionService

ORG_SLUG = "approach-baseball"
ORG_NAME = "Approach Baseball Performance"


def athlete_name_in(path: Path) -> str:
    """The athlete this export is about.

    Live at-bat exports name the batter in every row, so the first row is
    enough. Read here rather than hardcoded so no real name enters the repo.
    """
    reader = csv.DictReader(io.StringIO(path.read_bytes().decode("utf-8-sig")))
    for row in reader:
        name = (row.get("player_name") or "").strip()
        if name:
            return name
    raise SystemExit(f"{path} names no athlete in its player_name column")


def split_name(raw: str) -> tuple[str, str]:
    """Split "Last, First" or "First Last" into (first, last).

    Everything after the first token is the surname, so a multi-word surname
    survives intact.
    """
    name = raw.strip()
    if "," in name:
        last, _, first = name.partition(",")
        return first.strip(), last.strip()
    parts = name.split()
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], " ".join(parts[1:])


def ensure_organization(db: Session) -> Organization:
    org = db.scalars(select(Organization).where(Organization.slug == ORG_SLUG)).first()
    if org is None:
        org = Organization(name=ORG_NAME, slug=ORG_SLUG, timezone="America/New_York")
        db.add(org)
        db.flush()
    return org


def ensure_athlete(db: Session, org: Organization, display_name: str) -> Player:
    """Create the athlete and register their vendor identity.

    The export names athletes but gives them no id, so their vendor identity is
    the normalized name. Registering it here is the same explicit act a coach
    performs in the mapping queue -- done once, up front, for the athlete whose
    export we are loading.
    """
    first, last = split_name(display_name)
    player = db.scalars(
        select(Player).where(
            Player.organization_id == org.id,
            Player.first_name == first,
            Player.last_name == last,
        )
    ).first()

    if player is None:
        player = Player(organization_id=org.id, first_name=first, last_name=last, active=True)
        db.add(player)
        db.flush()

    external_id = vendor_identity(display_name)
    mapped = db.scalars(
        select(ExternalPlayerIdentity).where(
            ExternalPlayerIdentity.organization_id == org.id,
            ExternalPlayerIdentity.provider == "trackman",
            ExternalPlayerIdentity.external_id == external_id,
        )
    ).first()
    if mapped is None:
        db.add(
            ExternalPlayerIdentity(
                organization_id=org.id,
                player_id=player.id,
                provider="trackman",
                external_id=external_id,
                external_display_name=display_name,
                player_metadata={"source": "seed_athlete"},
            )
        )
    db.flush()
    return player


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create the testing roster from a real TrackMan export."
    )
    parser.add_argument("csv", type=Path, help="the export to load")
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="date used to infer a missing year in the export (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.is_development:
        raise SystemExit(f"refusing to run against BSA_ENV={settings.env.value}")

    if not args.csv.exists():
        print(f"error: {args.csv} does not exist", file=sys.stderr)
        return 2

    display_name = athlete_name_in(args.csv)
    today = date.fromisoformat(args.today) if args.today else date.today()

    with session_scope() as db:
        org = ensure_organization(db)
        athlete = ensure_athlete(db, org, display_name)
        service = IngestionService(
            db, org, TrackmanCsvProvider(today=today), get_object_store(settings)
        )
        outcome = service.ingest(
            SourcePayload(
                data=args.csv.read_bytes(),
                filename=args.csv.name,
                import_type="csv_seed",
            )
        )
        athlete_label = athlete.display_name
        # After ingestion, so the demo player login is the account of an
        # athlete who now actually has data rather than an empty profile.
        ensure_athlete_account(db, org, athlete, domain=settings.account_email_domain)
        logins = ensure_demo_accounts(
            db, org, domain=settings.account_email_domain, password=DEV_DEMO_PASSWORD
        )

    print(f"\n  Organization  {ORG_NAME}")
    print(f"  Athlete       {athlete_label}")
    print(f"\n  Import        {outcome.status.value}")
    print(f"    rows        {outcome.rows_accepted}/{outcome.rows_total}")
    print(f"    sessions    {outcome.sessions_created} created, {outcome.sessions_updated} updated")
    print(f"    events      {outcome.pitch_events} pitches, {outcome.hit_events} hits")
    if outcome.unresolved_players:
        print(f"    UNRESOLVED  {', '.join(outcome.unresolved_players)}")
    print("\n  Sign in at http://localhost:3000")
    for email, display_name, role in logins:
        print(f"    {role:<6} {email:<28} {display_name}")
    print(f"    password: {DEV_DEMO_PASSWORD}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
