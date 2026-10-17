"""Make an explicit CSV the active roster without deleting athlete history.

The input is deliberately kept outside the repository because it contains real
athlete names. Required columns are ``first_name`` and ``last_name``. Add
``date_of_birth`` (YYYY-MM-DD) or ``external_id`` when a name is shared.

Preview first::

    python -m bsa.scripts.filter_roster regular-roster.csv

Apply only after every row resolves to exactly one athlete::

    python -m bsa.scripts.filter_roster regular-roster.csv --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from bsa.core.config import get_settings
from bsa.core.logging import configure_logging
from bsa.db.models import ExternalPlayerIdentity, Organization, Player, User, UserSession
from bsa.db.session import session_scope
from bsa.domain.enums import Role
from bsa.domain.roster import collapse_spaces
from bsa.scripts.provision_roster import ORG_SLUG


@dataclass(frozen=True, slots=True)
class RosterEntry:
    first_name: str
    last_name: str
    date_of_birth: date | None = None
    external_id: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass(frozen=True, slots=True)
class FilterPlan:
    selected_ids: frozenset[uuid.UUID]
    activate_players: int
    deactivate_players: int
    activate_accounts: int
    deactivate_accounts: int
    revoke_sessions: int


class RosterResolutionError(ValueError):
    """One or more CSV rows did not identify exactly one athlete."""


def read_roster(path: Path) -> list[RosterEntry]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"first_name", "last_name"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise RosterResolutionError(
                f"expected CSV columns first_name,last_name; found {reader.fieldnames}"
            )

        entries: list[RosterEntry] = []
        for line, row in enumerate(reader, start=2):
            first_name = collapse_spaces(row["first_name"])
            last_name = collapse_spaces(row["last_name"])
            if not first_name or not last_name:
                raise RosterResolutionError(f"line {line}: first_name and last_name are required")
            raw_dob = (row.get("date_of_birth") or "").strip()
            raw_external_id = (row.get("external_id") or "").strip()
            try:
                dob = date.fromisoformat(raw_dob) if raw_dob else None
            except ValueError as exc:
                raise RosterResolutionError(
                    f"line {line}: date_of_birth must be YYYY-MM-DD"
                ) from exc
            entries.append(
                RosterEntry(
                    first_name=first_name,
                    last_name=last_name,
                    date_of_birth=dob,
                    external_id=raw_external_id or None,
                )
            )
    if not entries:
        raise RosterResolutionError("the roster CSV is empty")
    return entries


def _name_key(first_name: str, last_name: str) -> str:
    return collapse_spaces(f"{first_name} {last_name}").casefold()


def resolve_entries(
    db: Session, organization: Organization, entries: list[RosterEntry]
) -> frozenset[uuid.UUID]:
    players = list(
        db.scalars(select(Player).where(Player.organization_id == organization.id))
    )
    identities = list(
        db.scalars(
            select(ExternalPlayerIdentity).where(
                ExternalPlayerIdentity.organization_id == organization.id
            )
        )
    )
    external_ids: dict[uuid.UUID, set[str]] = {}
    for identity in identities:
        external_ids.setdefault(identity.player_id, set()).add(identity.external_id)

    selected: set[uuid.UUID] = set()
    problems: list[str] = []
    for entry in entries:
        matches = [
            player
            for player in players
            if _name_key(player.first_name, player.last_name)
            == _name_key(entry.first_name, entry.last_name)
        ]
        if entry.date_of_birth is not None:
            matches = [player for player in matches if player.date_of_birth == entry.date_of_birth]
        if entry.external_id is not None:
            matches = [
                player
                for player in matches
                if entry.external_id in external_ids.get(player.id, set())
            ]

        if len(matches) != 1:
            qualifier = []
            if entry.date_of_birth:
                qualifier.append(f"DOB {entry.date_of_birth.isoformat()}")
            if entry.external_id:
                qualifier.append(f"external id {entry.external_id}")
            detail = f" ({', '.join(qualifier)})" if qualifier else ""
            problems.append(f"{entry.full_name}{detail}: matched {len(matches)} athletes")
            continue
        if matches[0].id in selected:
            problems.append(f"{entry.full_name}: selects an athlete already listed")
            continue
        selected.add(matches[0].id)

    if problems:
        raise RosterResolutionError("\n".join(problems))
    return frozenset(selected)


def build_plan(
    db: Session, organization: Organization, selected_ids: frozenset[uuid.UUID]
) -> FilterPlan:
    players = list(
        db.scalars(select(Player).where(Player.organization_id == organization.id))
    )
    player_users = list(
        db.scalars(
            select(User).where(
                User.organization_id == organization.id,
                User.role == Role.PLAYER,
                User.player_id.is_not(None),
            )
        )
    )
    disabled_user_ids = {
        user.id for user in player_users if user.player_id not in selected_ids and user.active
    }
    live_sessions = 0
    if disabled_user_ids:
        live_sessions = len(
            list(
                db.scalars(
                    select(UserSession).where(
                        UserSession.user_id.in_(disabled_user_ids),
                        UserSession.revoked_at.is_(None),
                    )
                )
            )
        )
    return FilterPlan(
        selected_ids=selected_ids,
        activate_players=sum(not player.active for player in players if player.id in selected_ids),
        deactivate_players=sum(
            player.active for player in players if player.id not in selected_ids
        ),
        activate_accounts=sum(
            not user.active for user in player_users if user.player_id in selected_ids
        ),
        deactivate_accounts=len(disabled_user_ids),
        revoke_sessions=live_sessions,
    )


def apply_plan(db: Session, organization: Organization, plan: FilterPlan) -> None:
    db.execute(
        update(Player)
        .where(Player.organization_id == organization.id)
        .values(active=Player.id.in_(plan.selected_ids))
    )
    db.execute(
        update(User)
        .where(
            User.organization_id == organization.id,
            User.role == Role.PLAYER,
            User.player_id.is_not(None),
        )
        .values(active=User.player_id.in_(plan.selected_ids))
    )
    disabled_user_ids = select(User.id).where(
        User.organization_id == organization.id,
        User.role == Role.PLAYER,
        User.player_id.is_not(None),
        User.player_id.not_in(plan.selected_ids),
    )
    db.execute(
        update(UserSession)
        .where(
            UserSession.user_id.in_(disabled_user_ids),
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )


def print_plan(plan: FilterPlan, *, applied: bool) -> None:
    verb = "Applied" if applied else "Preview"
    print(f"{verb}: {len(plan.selected_ids)} athletes on the active roster")
    print(f"  players activated:    {plan.activate_players}")
    print(f"  players deactivated:  {plan.deactivate_players}")
    print(f"  accounts activated:   {plan.activate_accounts}")
    print(f"  accounts deactivated: {plan.deactivate_accounts}")
    print(f"  sessions revoked:     {plan.revoke_sessions}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Make a CSV the active roster while preserving athlete history."
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument("--organization", default=ORG_SLUG, help="organization slug")
    parser.add_argument("--apply", action="store_true", help="write the previewed changes")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)
    if not args.csv.is_file():
        print(f"error: {args.csv} does not exist", file=sys.stderr)
        return 2
    try:
        entries = read_roster(args.csv)
        with session_scope() as db:
            organization = db.scalars(
                select(Organization).where(Organization.slug == args.organization)
            ).first()
            if organization is None:
                raise RosterResolutionError(
                    f"organization {args.organization!r} does not exist"
                )
            selected_ids = resolve_entries(db, organization, entries)
            plan = build_plan(db, organization, selected_ids)
            if args.apply:
                apply_plan(db, organization, plan)
            else:
                db.rollback()
    except RosterResolutionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print_plan(plan, applied=args.apply)
    if not args.apply:
        print("  no changes written; re-run with --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
