"""Create an account for every athlete on a TrackMan roster export.

    python -m bsa.scripts.provision_roster "roster.csv" --dry-run
    python -m bsa.scripts.provision_roster "roster.csv" --codes

Accounts are provisioned, not registered: the facility creates them from its own
roster and the athlete later claims one by proving which address is theirs. So
this script creates `users` rows with **no password**, which is the normal
starting state -- see `bsa.services.accounts`.

What it will not do
-------------------
Guess. A roster export is a list of vendor accounts, and 63 names in the real
export of 488 belong to more than one of them, one of them to four. Since a
login address is derived from a name, a duplicated name is a duplicated address,
and a duplicated address would let one athlete read another's sessions. Rows
like that are created as athletes -- so their data still lands correctly, keyed
by TrackMan id -- but are issued no address until a coach says which account
belongs to whom. `--emails birth-year` is the opt-in that disambiguates them
automatically; it is not the default, because it only works if somebody tells
each athlete which year is theirs.

Likewise `--link-existing` is off by default. Without it, a roster row whose
name matches an athlete already in the database becomes a *second* athlete. That
is wrong, but it is the safe wrong: a duplicate athlete shows an empty report,
whereas a bad link shows one athlete another athlete's data.

Re-running is safe. Athletes are matched on (provider, external id), accounts on
the athlete they belong to, and nothing already activated is modified.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bsa.core.config import Settings, get_settings
from bsa.core.logging import configure_logging
from bsa.core.password import hash_password
from bsa.db.models import (
    ExternalPlayerIdentity,
    HitEvent,
    MetricObservation,
    Organization,
    PersonalRecord,
    PersonalRecordEvent,
    PitchEvent,
    Player,
    SessionVideo,
    SyncJob,
    User,
    UserCredential,
)
from bsa.db.session import session_scope
from bsa.domain.enums import Role
from bsa.domain.roster import (
    EmailPolicy,
    RosterAccount,
    RosterAthlete,
    RosterPlan,
    RosterRow,
    collapse_spaces,
    email_local_part,
    plan_export,
)
from bsa.services import accounts

ORG_SLUG = "approach-baseball"
ORG_NAME = "Approach Baseball Performance"

#: Only ever used when --demo-accounts runs in development. Any other
#: environment must pass --demo-password explicitly, because a printed password
#: in a deployed database is a real account anyone reading this file can use.
DEV_DEMO_PASSWORD = "SpringTraining26"  # noqa: S105 -- development fixture, not a secret


@dataclass
class Outcome:
    players_created: int = 0
    players_linked: int = 0
    identities_created: int = 0
    accounts_created: int = 0
    accounts_existing: int = 0
    codes_issued: int = 0
    #: Rows deliberately left without a login address.
    blocked: list[RosterAccount] = field(default_factory=list)
    #: (row, existing holder) -- the address was already somebody else's.
    email_taken: list[tuple[RosterAccount, str]] = field(default_factory=list)
    #: (row, existing athlete) -- same name, no --link-existing, so duplicated.
    name_matches: list[tuple[RosterRow, Player]] = field(default_factory=list)
    #: (row, other addresses) -- this athlete now holds more than one account.
    extra_accounts: list[tuple[RosterAccount, tuple[str, ...]]] = field(default_factory=list)
    #: Athletes the export had entered more than once.
    merged: list[RosterAthlete] = field(default_factory=list)
    #: Separate athlete records folded into one, from an earlier run.
    players_folded: int = 0
    #: (athlete, why) -- a record that could not be retired automatically.
    merge_blocked: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    issued_codes: list[tuple[str, str, str]] = field(default_factory=list)


def read_export(path: Path) -> list[dict[str, str]]:
    text = path.read_bytes().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "name" not in reader.fieldnames:
        raise SystemExit(
            f"{path} does not look like a roster export: expected a 'name' column, "
            f"found {reader.fieldnames}"
        )
    return [dict(row) for row in reader]


def ensure_organization(db: Session) -> Organization:
    org = db.scalars(select(Organization).where(Organization.slug == ORG_SLUG)).first()
    if org is None:
        org = Organization(name=ORG_NAME, slug=ORG_SLUG, timezone="America/New_York")
        db.add(org)
        db.flush()
    return org


def _players_by_name(db: Session, org: Organization) -> dict[str, list[Player]]:
    """Existing athletes grouped by normalized full name.

    Used only to *report* possible duplicates, and to act on them when
    --link-existing is given. Never consulted during ingestion.
    """
    grouped: dict[str, list[Player]] = {}
    for player in db.scalars(select(Player).where(Player.organization_id == org.id)):
        key = collapse_spaces(f"{player.first_name} {player.last_name}").lower()
        grouped.setdefault(key, []).append(player)
    return grouped


def _carries_data(db: Session, player_id: uuid.UUID) -> bool:
    """Whether anything at all has been recorded against this athlete.

    Enumerated rather than inferred: every table carrying a `players.id` is
    listed here, so adding one and forgetting it would be caught by the test
    that walks the foreign keys rather than by a silent data loss.
    """
    checks = (
        select(PitchEvent.id).where(PitchEvent.player_id == player_id),
        select(PitchEvent.id).where(PitchEvent.batter_id == player_id),
        select(HitEvent.id).where(HitEvent.player_id == player_id),
        select(MetricObservation.id).where(MetricObservation.player_id == player_id),
        select(PersonalRecord.id).where(PersonalRecord.player_id == player_id),
        select(PersonalRecordEvent.id).where(PersonalRecordEvent.player_id == player_id),
        select(SessionVideo.id).where(SessionVideo.player_id == player_id),
        select(SyncJob.id).where(SyncJob.player_id == player_id),
    )
    return any(db.scalars(check.limit(1)).first() is not None for check in checks)


def _claimed_account(db: Session, player_id: uuid.UUID) -> User | None:
    """An account for this athlete that somebody has already set a password on."""
    return db.scalars(
        select(User)
        .join(UserCredential, UserCredential.user_id == User.id)
        .where(User.player_id == player_id, UserCredential.password_hash.is_not(None))
    ).first()


def _fold_into_one(
    db: Session, org: Organization, players: list[Player], outcome: Outcome
) -> Player:
    """Collapse athletes the database created separately into a single record.

    Only reached when a previous run split one person across several rows --
    the roster said two vendor accounts, and only later did the merge rule say
    they were one athlete. Moving the vendor ids onto one record is what makes
    the next import land in one place.

    Refuses to retire a record that carries data or a claimed account. Both
    cases need a decision this script cannot make: moving sessions between
    athletes, or taking away a login somebody is already using.
    """

    # Which record survives is chosen to avoid the refusals below, not left to
    # chance. `created_at` cannot break the tie on its own: it defaults to the
    # transaction timestamp, so records created by one run all share it, and the
    # survivor would really be decided by a random UUID.
    #
    #   1. the one carrying imported data -- moving sessions is what we refuse
    #   2. the one with a claimed login  -- taking that away is what we refuse
    #   3. the oldest, then the lowest id, purely so the result is repeatable
    def rank(player: Player) -> tuple[int, int, datetime, str]:
        return (
            0 if _carries_data(db, player.id) else 1,
            0 if _claimed_account(db, player.id) else 1,
            player.created_at,
            str(player.id),
        )

    survivor = min(players, key=rank)

    for player in players:
        if player.id == survivor.id:
            continue
        blocker = (
            "carries imported data"
            if _carries_data(db, player.id)
            else ("has a claimed account" if _claimed_account(db, player.id) else None)
        )
        if blocker is not None:
            outcome.merge_blocked.append((player.display_name, blocker))
            continue

        for identity in db.scalars(
            select(ExternalPlayerIdentity).where(ExternalPlayerIdentity.player_id == player.id)
        ):
            identity.player_id = survivor.id
        # The account goes with the athlete it belonged to. Deactivated rather
        # than deleted: the address stays taken, so it cannot be re-issued to
        # somebody else, and the history of it stays readable.
        for user in db.scalars(select(User).where(User.player_id == player.id)):
            user.active = False
            user.player_id = None
        player.active = False
        db.flush()
        outcome.players_folded += 1

    return survivor


def _resolve_player(
    db: Session,
    org: Organization,
    athlete: RosterAthlete,
    *,
    existing_by_name: dict[str, list[Player]],
    link_existing: bool,
    ambiguous_name: bool,
    outcome: Outcome,
) -> Player:
    """The athlete these roster rows refer to, created if never seen before.

    Matched on (provider, external id) -- the vendor key every later import
    also matches on, and the only identifier trusted here. A merged athlete
    brings several of those, which is exactly how data filed under either
    TrackMan account ends up on one person.
    """
    known: dict[uuid.UUID, Player] = {}
    mapped: set[tuple[str, str]] = set()
    for provider, external_id in athlete.identities:
        identity = db.scalars(
            select(ExternalPlayerIdentity).where(
                ExternalPlayerIdentity.organization_id == org.id,
                ExternalPlayerIdentity.provider == provider,
                ExternalPlayerIdentity.external_id == external_id,
            )
        ).first()
        if identity is None:
            continue
        mapped.add((provider, external_id))
        found = db.get(Player, identity.player_id)
        if found is not None:
            known[found.id] = found

    player: Player | None = None
    if len(known) > 1:
        player = _fold_into_one(db, org, list(known.values()), outcome)
    elif known:
        player = next(iter(known.values()))

    name_key = collapse_spaces(athlete.full_name).lower()

    if player is None:
        candidates = existing_by_name.get(name_key, [])
        # Linking requires an unambiguous match on both sides: exactly one
        # existing athlete with this name, and a name used by exactly one
        # person in the export. Either being ambiguous is precisely the case
        # where a link could attach one athlete's TrackMan account to another.
        if candidates and not ambiguous_name and len(candidates) == 1:
            if link_existing:
                player = candidates[0]
                outcome.players_linked += 1
            else:
                outcome.name_matches.append((athlete.primary, candidates[0]))

    if player is None:
        primary = athlete.primary
        player = Player(
            organization_id=org.id,
            first_name=primary.first_name,
            last_name=primary.last_name,
            date_of_birth=primary.date_of_birth,
            active=True,
        )
        db.add(player)
        db.flush()
        outcome.players_created += 1
        existing_by_name.setdefault(name_key, []).append(player)

    for row in athlete.rows:
        if (row.provider, row.external_id) in mapped:
            continue
        db.add(
            ExternalPlayerIdentity(
                organization_id=org.id,
                player_id=player.id,
                provider=row.provider,
                external_id=row.external_id,
                external_display_name=row.full_name,
                player_metadata={"source": "roster_export", "line": row.line},
            )
        )
        outcome.identities_created += 1
    db.flush()

    if athlete.is_merged:
        outcome.merged.append(athlete)
    return player


def _ensure_account(
    db: Session,
    org: Organization,
    account: RosterAccount,
    player: Player,
    *,
    issue_codes: bool,
    outcome: Outcome,
) -> None:
    """Create the athlete's login, if a safe address was decided for them.

    Keyed on the address the plan decided, not on the athlete, because the
    address is what a person types and what the unique constraint protects.
    Keying on the athlete instead would let an unrelated account that merely
    points at them -- a demo login, say -- silently consume their slot and
    leave them with no address of their own.
    """
    if account.email is None:
        outcome.blocked.append(account)
        return

    holder = db.scalars(select(User).where(User.email == account.email)).first()
    if holder is not None:
        if holder.player_id == player.id:
            outcome.accounts_existing += 1
            _ensure_credential(db, holder, issue_codes=issue_codes, outcome=outcome)
        else:
            # Somebody else already signs in with this address. Minting a
            # second would break the unique constraint; reusing it would hand
            # this athlete that person's account.
            outcome.email_taken.append((account, holder.display_name))
        return

    # Not an error, just worth saying: re-running with a different --emails
    # policy, or a demo login pointed at this athlete, leaves them holding two.
    others = db.scalars(
        select(User).where(
            User.organization_id == org.id,
            User.player_id == player.id,
            User.auth_provider == accounts.LOCAL_PROVIDER,
        )
    ).all()
    if others:
        outcome.extra_accounts.append((account, tuple(u.email for u in others)))

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        organization_id=org.id,
        auth_provider=accounts.LOCAL_PROVIDER,
        # The user's own id, so changing an email address never orphans a
        # live session. See LocalAuthProvider.verify.
        auth_subject=str(user_id),
        email=account.email,
        display_name=player.display_name,
        role=Role.PLAYER,
        player_id=player.id,
    )
    db.add(user)
    db.flush()
    outcome.accounts_created += 1
    _ensure_credential(db, user, issue_codes=issue_codes, outcome=outcome)


def _ensure_credential(
    db: Session, user: User, *, issue_codes: bool, outcome: Outcome
) -> UserCredential:
    credential = db.get(UserCredential, user.id)
    if credential is None:
        credential = UserCredential(user_id=user.id)
        db.add(credential)
        db.flush()

    # An activated account keeps its password and is never handed a new code --
    # a fresh code on a claimed account would be a way back in for whoever
    # holds the printout.
    if issue_codes and not credential.has_password and credential.activation_code_hash is None:
        code = accounts.issue_activation_code(db, credential)
        outcome.codes_issued += 1
        outcome.issued_codes.append((user.email, user.display_name, code))
    return credential


def apply_plan(
    db: Session,
    org: Organization,
    plan: RosterPlan,
    *,
    link_existing: bool,
    issue_codes: bool,
    skipped: list[str],
) -> Outcome:
    outcome = Outcome(skipped=list(skipped))
    existing_by_name = _players_by_name(db, org)

    for account in plan.accounts:
        player = _resolve_player(
            db,
            org,
            account.athlete,
            existing_by_name=existing_by_name,
            link_existing=link_existing,
            ambiguous_name=bool(account.shares_name_with),
            outcome=outcome,
        )
        _ensure_account(db, org, account, player, issue_codes=issue_codes, outcome=outcome)

    return outcome


# -- demo accounts -----------------------------------------------------------


def ensure_athlete_account(
    db: Session, org: Organization, player: Player, *, domain: str
) -> User | None:
    """The athlete's own login, minted from their name if they have none yet.

    For the single-athlete seed script, which creates an athlete directly
    rather than from a roster export. Returns None if the derived address
    already belongs to somebody else -- the one case where a name is not enough
    to decide, and the same case the roster planner refuses to guess at.
    """
    existing = db.scalars(
        select(User).where(
            User.organization_id == org.id,
            User.player_id == player.id,
            User.auth_provider == accounts.LOCAL_PROVIDER,
            User.role == Role.PLAYER,
        )
    ).first()
    if existing is not None:
        return existing

    email = accounts.normalize_email(f"{email_local_part(player.full_name)}@{domain}")
    if db.scalars(select(User).where(User.email == email)).first() is not None:
        return None

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        organization_id=org.id,
        auth_provider=accounts.LOCAL_PROVIDER,
        auth_subject=str(user_id),
        email=email,
        display_name=player.display_name,
        role=Role.PLAYER,
        player_id=player.id,
    )
    db.add(user)
    db.add(UserCredential(user_id=user.id))
    db.flush()
    return user


def _busiest_athlete_account(db: Session, org: Organization) -> User | None:
    """The account of the athlete with the most imported events.

    Chosen so that signing in as the demo player shows a real session report
    rather than an empty state. Athletes with no account -- a shared name left
    for a coach to resolve -- are skipped rather than given one here.
    """
    events = (
        select(PitchEvent.batter_id.label("player_id"))
        .where(PitchEvent.organization_id == org.id, PitchEvent.batter_id.is_not(None))
        .union_all(
            select(HitEvent.player_id.label("player_id")).where(HitEvent.organization_id == org.id)
        )
        .subquery()
    )
    ranked = (
        select(events.c.player_id, func.count().label("n"))
        .group_by(events.c.player_id)
        .order_by(func.count().desc())
        .limit(25)
    )
    for player_id, _count in db.execute(ranked):
        user = db.scalars(
            select(User).where(
                User.organization_id == org.id,
                User.player_id == player_id,
                User.auth_provider == accounts.LOCAL_PROVIDER,
                User.role == Role.PLAYER,
            )
        ).first()
        if user is not None:
            return user
    return None


def _activate(db: Session, user: User, password: str) -> None:
    credential = db.get(UserCredential, user.id)
    if credential is None:
        credential = UserCredential(user_id=user.id)
        db.add(credential)
    credential.password_hash = hash_password(password)
    credential.password_set_at = credential.activated_at = datetime.now(UTC)
    credential.failed_attempts = 0
    credential.locked_until = None
    db.flush()


def ensure_demo_accounts(
    db: Session, org: Organization, *, domain: str, password: str
) -> list[tuple[str, str, str]]:
    """A coach login, plus a player login belonging to an athlete who has data.

    The player login is the athlete's **own** roster account with a known
    password set on it, not a parallel account pointed at them. That keeps one
    account per athlete, and it means testing the demo tests the exact account
    a real athlete signs in to. Both are ordinary accounts with ordinary Argon2
    hashes -- there is no bypass anywhere in the code.
    """
    created: list[tuple[str, str, str]] = []

    coach_email = accounts.normalize_email(f"coach@{domain}")
    coach = db.scalars(select(User).where(User.email == coach_email)).first()
    if coach is None:
        coach_id = uuid.uuid4()
        coach = User(
            id=coach_id,
            organization_id=org.id,
            auth_provider=accounts.LOCAL_PROVIDER,
            auth_subject=str(coach_id),
            email=coach_email,
            display_name="Coach",
            role=Role.COACH,
        )
        db.add(coach)
        db.flush()
    _activate(db, coach, password)
    created.append((coach.email, coach.display_name, coach.role.value))

    athlete_account = _busiest_athlete_account(db, org)
    if athlete_account is None:
        return created
    _activate(db, athlete_account, password)
    created.append(
        (athlete_account.email, athlete_account.display_name, athlete_account.role.value)
    )
    return created


# -- reporting ---------------------------------------------------------------


def write_review_file(path: Path, plan: RosterPlan, outcome: Outcome) -> int:
    """Every row a human still has to decide about, as a CSV to work through."""
    rows: list[dict[str, str]] = []
    for account in outcome.blocked:
        rows.append(
            {
                "line": str(account.row.line),
                "name": account.row.full_name,
                "date_of_birth": (
                    account.row.date_of_birth.isoformat() if account.row.date_of_birth else ""
                ),
                "provider": account.row.provider,
                "external_id": account.row.external_id,
                "suggested_email": (
                    f"{account.row.name_key}.{account.row.date_of_birth.year}@{plan.domain}"
                    if account.row.date_of_birth
                    else ""
                ),
                "reason": account.blocked_reason or "",
            }
        )
    for account, holder in outcome.email_taken:
        rows.append(
            {
                "line": str(account.row.line),
                "name": account.row.full_name,
                "date_of_birth": (
                    account.row.date_of_birth.isoformat() if account.row.date_of_birth else ""
                ),
                "provider": account.row.provider,
                "external_id": account.row.external_id,
                "suggested_email": "",
                "reason": f"{account.email} already belongs to {holder}",
            }
        )

    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_codes_file(path: Path, codes: list[tuple[str, str, str]]) -> None:
    """The one readable copy of each activation code.

    Written to `var/`, which is gitignored: this file is the credential, and the
    database keeps only its hash.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["email", "athlete", "activation_code"])
        writer.writerows(codes)


def print_report(plan: RosterPlan, outcome: Outcome | None, *, dry_run: bool) -> None:
    total = len(plan.accounts)
    print()
    print(f"  Roster            {total} entries, {len(plan.claimable)} with a login address")
    print(f"  Email policy      {plan.policy.value} @{plan.domain}")

    merged = plan.merged
    if merged:
        print()
        print(f"  Entered twice     {len(merged)} athletes appear under more than one TrackMan id")
        print("                    same name and same date of birth, so one person")
        thin = [a for a in merged if a.shared_birth_date]
        for athlete in merged[:6]:
            ids = ", ".join(external for _, external in athlete.identities)
            mark = "  <- on a date the export repeats" if athlete.shared_birth_date else ""
            print(f"    {athlete.name_key:<24} {ids}{mark}")
        if len(merged) > 6:
            print(f"    ... and {len(merged) - 6} more")
        if thin:
            print()
            print(f"  CHECK THESE       {len(thin)} of those merges rest on a repeated date")
            print("                    the date is a bulk-upload default, so only the")
            print("                    name is really saying they are the same person")

    groups = plan.collision_groups
    if groups:
        print()
        print(f"  Shared names      {len(groups)} names used by more than one athlete")
        for key, athletes in list(groups.items())[:5]:
            detail = ", ".join(
                f"{a.primary.external_id} "
                f"({a.date_of_birth.isoformat() if a.date_of_birth else 'no dob'})"
                for a in athletes
            )
            print(f"    {key:<24} {detail}")
        if len(groups) > 5:
            print(f"    ... and {len(groups) - 5} more")

    if outcome is None:
        print()
        print("  Dry run -- nothing was written.")
        return

    print()
    print(f"  Athletes created  {outcome.players_created}")
    if outcome.players_folded:
        print(f"  Athletes folded   {outcome.players_folded} duplicate records retired")
    if outcome.players_linked:
        print(f"  Athletes linked   {outcome.players_linked} (existing records, --link-existing)")
    print(f"  Identities        {outcome.identities_created} TrackMan ids mapped")
    print(f"  Accounts created  {outcome.accounts_created}")
    if outcome.accounts_existing:
        print(f"  Accounts kept     {outcome.accounts_existing} (already provisioned)")
    if outcome.codes_issued:
        print(f"  Codes issued      {outcome.codes_issued}")

    if outcome.blocked:
        print()
        print(f"  NEEDS A DECISION  {len(outcome.blocked)} entries have no login address")
        print("                    they exist as athletes; their data will still import")
    if outcome.email_taken:
        print(f"  ADDRESS IN USE    {len(outcome.email_taken)} entries")
    if outcome.merge_blocked:
        print()
        print(f"  COULD NOT FOLD    {len(outcome.merge_blocked)} duplicate records kept separate")
        for name, reason in outcome.merge_blocked[:5]:
            print(f"    {name:<24} {reason}")
        print("                    moving sessions between athletes, or taking away a")
        print("                    login in use, is not this script's decision to make")
    if outcome.extra_accounts:
        print()
        print(f"  Second account    {len(outcome.extra_accounts)} athletes now hold more than one")
        for account, others in outcome.extra_accounts[:5]:
            print(f"    {account.email:<34} alongside {', '.join(others)}")
    if outcome.name_matches:
        print()
        print(
            f"  Possible repeats  {len(outcome.name_matches)} entries share a name with an "
            "athlete already in the database"
        )
        for row, player in outcome.name_matches[:5]:
            print(f"    {row.full_name:<24} existing {player.id}")
        print("                    re-run with --link-existing to attach the TrackMan id")
        print("                    to the existing athlete instead of creating a new one")
    if outcome.skipped:
        print()
        print(f"  Skipped rows      {len(outcome.skipped)}")
        for message in outcome.skipped[:5]:
            print(f"    {message}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provision an account for every athlete on a TrackMan roster export."
    )
    parser.add_argument("csv", type=Path, help="the roster export")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would happen and write nothing",
    )
    parser.add_argument(
        "--emails",
        type=EmailPolicy,
        choices=list(EmailPolicy),
        default=EmailPolicy.UNIQUE_ONLY,
        help=(
            "unique-only (default): only unambiguous names get an address. "
            "birth-year: shared names get their birth year appended, which "
            "requires telling each athlete which year is theirs."
        ),
    )
    parser.add_argument(
        "--link-existing",
        action="store_true",
        help=(
            "attach a roster id to an athlete already in the database when the "
            "name matches exactly one of each. Off by default -- a wrong link "
            "shows one athlete another athlete's data."
        ),
    )
    parser.add_argument(
        "--keep-duplicates",
        action="store_true",
        help=(
            "one athlete per vendor row, as the export literally states it. "
            "By default, rows with an identical name AND date of birth are "
            "treated as one athlete entered twice, which is the facility's rule."
        ),
    )
    parser.add_argument(
        "--codes",
        action="store_true",
        help="issue an activation code per unclaimed account and write them to var/",
    )
    parser.add_argument(
        "--demo-accounts",
        action="store_true",
        help="also create an activated coach and player login for testing",
    )
    parser.add_argument(
        "--demo-password",
        default=None,
        help="password for the demo accounts (required outside development)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("var"),
        help="directory for the review and code files (default: var/)",
    )
    args = parser.parse_args()

    settings: Settings = get_settings()
    configure_logging(settings.log_level)

    if not args.csv.exists():
        print(f"error: {args.csv} does not exist", file=sys.stderr)
        return 2

    demo_password = args.demo_password or (DEV_DEMO_PASSWORD if settings.is_development else None)
    if args.demo_accounts and demo_password is None:
        print(
            f"error: --demo-password is required when BSA_ENV={settings.env.value}. "
            "A password printed by a script has no business in a deployed database "
            "unless you chose it deliberately.",
            file=sys.stderr,
        )
        return 2

    records = read_export(args.csv)
    plan, skipped = plan_export(
        records,
        domain=settings.account_email_domain,
        policy=args.emails,
        merge_duplicates=not args.keep_duplicates,
    )

    if args.dry_run:
        print_report(plan, None, dry_run=True)
        for message in skipped:
            print(f"    skip: {message}")
        return 0

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    with session_scope() as db:
        org = ensure_organization(db)
        outcome = apply_plan(
            db,
            org,
            plan,
            link_existing=args.link_existing,
            issue_codes=args.codes,
            skipped=skipped,
        )
        demo: list[tuple[str, str, str]] = []
        if args.demo_accounts:
            assert demo_password is not None  # noqa: S101 -- guarded above
            demo = ensure_demo_accounts(
                db, org, domain=settings.account_email_domain, password=demo_password
            )

    print_report(plan, outcome, dry_run=False)

    review_path = args.out / f"roster-review-{stamp}.csv"
    if write_review_file(review_path, plan, outcome):
        print()
        print(f"  Review file       {review_path}")
    if outcome.issued_codes:
        codes_path = args.out / f"activation-codes-{stamp}.csv"
        write_codes_file(codes_path, outcome.issued_codes)
        print(f"  Activation codes  {codes_path}")
        print("                    the database keeps only hashes; this file is the only copy")
    if demo:
        print()
        print("  Demo logins")
        for email, display_name, role in demo:
            print(f"    {role:<6} {email:<34} {display_name}")
        print(f"    password: {demo_password}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
