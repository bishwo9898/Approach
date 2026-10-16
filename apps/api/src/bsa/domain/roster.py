"""Turning a TrackMan roster export into accounts, without guessing.

A roster export is a list of *vendor accounts*, not a list of people. The two
differ, and the difference is the only hard problem in this module:

    Devin  Ruiz ,Jul. 29  2006,-,-,1000593912 TrackMan
    Devin Ruiz,Oct. 29  2011,-,-,1000568270 TrackMan

Two rows, one name, five years apart. Almost certainly two different athletes.
Meanwhile one name appears four times, and across the real export 109
rows share the birth date "Jul. 29 2006" -- a placeholder a bulk upload left
behind, not a birthday. So neither the name nor the date of birth identifies a
person on its own.

Login emails are derived from names, so a duplicated name is a duplicated
email, and a duplicated email means one athlete could claim another athlete's
account and read their data. This module therefore:

* creates one player per vendor row and **never merges two rows into one
  athlete**, because the vendor is asserting these are distinct accounts and
  collapsing them would attribute one athlete's data to another;
* issues a claimable email only when the name identifies exactly one row;
* reports every collision instead of resolving it quietly, so a coach -- who
  knows which TrackMan account belongs to which kid -- makes that call.

Everything here is a pure function over parsed rows. No database, no network.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

#: Vendor suffix on the export's `playerId` column, e.g. "1000593912 TrackMan".
_PROVIDERS = {"trackman": "trackman", "mlb": "mlb"}

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip


class EmailPolicy(StrEnum):
    """How to handle two athletes whose names produce the same email.

    `UNIQUE_ONLY` is the default because it is the only option that cannot
    hand one athlete another athlete's login.
    """

    #: Only unambiguous names get an email. Collisions are left for a human.
    UNIQUE_ONLY = "unique-only"
    #: Collisions get their birth year appended. Requires the coach to tell each
    #: athlete which year is theirs -- an informed trade, not a default.
    BIRTH_YEAR = "birth-year"


class RosterError(ValueError):
    """The export could not be read as a roster at all."""


@dataclass(frozen=True, slots=True)
class RosterRow:
    """One line of the export, parsed and nothing more."""

    line: int
    raw_name: str
    full_name: str
    first_name: str
    last_name: str
    date_of_birth: date | None
    provider: str
    external_id: str

    @property
    def name_key(self) -> str:
        """Identity of the *name*, not of the person. Collision detector."""
        return email_local_part(self.full_name)


@dataclass(frozen=True, slots=True)
class RosterAccount:
    """A row, plus the account decision made for it."""

    row: RosterRow
    #: None when no email could be issued safely -- see `blocked_reason`.
    email: str | None
    #: Other rows sharing this row's name. Empty when the name is unique.
    shares_name_with: tuple[RosterRow, ...] = ()

    @property
    def is_claimable(self) -> bool:
        return self.email is not None

    @property
    def blocked_reason(self) -> str | None:
        if self.email is not None:
            return None
        others = len(self.shares_name_with)
        if others:
            return (
                f"{others + 1} roster entries are named {self.row.full_name!r}; "
                "a coach must say which TrackMan account belongs to which athlete"
            )
        return f"no usable email could be formed from {self.row.raw_name!r}"


@dataclass(frozen=True, slots=True)
class RosterPlan:
    """Every row, decided. The provisioning script applies this verbatim."""

    accounts: tuple[RosterAccount, ...]
    policy: EmailPolicy
    domain: str

    @property
    def claimable(self) -> tuple[RosterAccount, ...]:
        return tuple(a for a in self.accounts if a.is_claimable)

    @property
    def blocked(self) -> tuple[RosterAccount, ...]:
        return tuple(a for a in self.accounts if not a.is_claimable)

    @property
    def collision_groups(self) -> dict[str, tuple[RosterRow, ...]]:
        """Name key -> every row carrying that name, for names used twice."""
        groups: dict[str, list[RosterRow]] = defaultdict(list)
        for account in self.accounts:
            if account.shares_name_with:
                groups[account.row.name_key].append(account.row)
        return {key: tuple(rows) for key, rows in sorted(groups.items())}


# -- parsing -----------------------------------------------------------------


def collapse_spaces(value: str) -> str:
    """`"Devin  Ruiz "` -> `"Devin Ruiz"`.

    The export is full of double spaces and trailing spaces. Normalizing them
    away is what makes two spellings of one name collide *visibly* here rather
    than silently becoming two players later.
    """
    return re.sub(r"\s+", " ", value).strip()


def email_local_part(full_name: str) -> str:
    """The `first.last` of an email address, from a display name.

    Keeps digits (the export contains entries like `Devin 14u`) and folds everything else to
    a single dot, so punctuation and spacing cannot produce two spellings of
    one address.
    """
    slug = re.sub(r"[^a-z0-9]+", ".", collapse_spaces(full_name).lower())
    return slug.strip(".")


def split_name(full_name: str) -> tuple[str, str]:
    """(first, last). Everything after the first token is the surname.

    "Ana Marie Okafor" keeps "Marie Okafor" intact rather than guessing at
    a middle name, because a wrong guess here shows up on the athlete's own page.
    """
    parts = collapse_spaces(full_name).split(" ")
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], " ".join(parts[1:])


def parse_date_of_birth(value: str) -> date | None:
    """`"Jul. 29  2006"` -> `date(2006, 7, 29)`; anything unreadable -> None.

    Returns None rather than raising: a missing birth date costs nothing here
    (nothing in the app reads it), so one unparseable cell must not stop 487
    other athletes from being provisioned.
    """
    text = collapse_spaces(value).replace(".", "").replace(",", " ")
    text = collapse_spaces(text)
    match = re.fullmatch(r"([A-Za-z]{3,})\s+(\d{1,2})\s+(\d{4})", text)
    if not match:
        return None
    month = _MONTHS.get(match.group(1)[:3].lower())
    if month is None:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(2)))
    except ValueError:
        return None


def parse_player_id(value: str) -> tuple[str, str] | None:
    """`"1000593912 TrackMan"` -> `("trackman", "1000593912")`.

    An unrecognized vendor returns None instead of being stored under a guessed
    provider name: a wrong provider would make the identity unmatchable against
    the data that arrives later, which is worse than having no identity at all.
    """
    text = collapse_spaces(value)
    if not text:
        return None
    parts = text.split(" ")
    if len(parts) < 2:
        return None
    external_id, vendor = " ".join(parts[:-1]), parts[-1].lower()
    provider = _PROVIDERS.get(vendor)
    if provider is None or not external_id:
        return None
    return provider, external_id


def parse_rows(records: list[dict[str, str]]) -> tuple[list[RosterRow], list[str]]:
    """Parse export records into rows, returning (rows, skipped-row messages).

    A row is skipped only when it has no name or no usable vendor id -- without
    either, there is nothing to create and nothing to attach data to.
    """
    rows: list[RosterRow] = []
    skipped: list[str] = []
    seen_ids: dict[tuple[str, str], int] = {}

    for index, record in enumerate(records, start=2):  # start=2: line 1 is the header
        raw_name = record.get("name") or ""
        full_name = collapse_spaces(raw_name)
        identity = parse_player_id(record.get("playerId") or "")

        if not full_name:
            skipped.append(f"line {index}: no name")
            continue
        if identity is None:
            skipped.append(f"line {index}: {full_name!r} has no recognized vendor id")
            continue

        provider, external_id = identity
        previous = seen_ids.get((provider, external_id))
        if previous is not None:
            # The vendor id is the key every later import matches on, so two
            # rows claiming one id cannot both become players.
            skipped.append(
                f"line {index}: {provider} id {external_id} already used on line {previous}"
            )
            continue
        seen_ids[(provider, external_id)] = index

        first, last = split_name(full_name)
        rows.append(
            RosterRow(
                line=index,
                raw_name=raw_name,
                full_name=full_name,
                first_name=first,
                last_name=last,
                date_of_birth=parse_date_of_birth(record.get("dateOfBirth") or ""),
                provider=provider,
                external_id=external_id,
            )
        )

    return rows, skipped


# -- planning ----------------------------------------------------------------


def build_plan(
    rows: list[RosterRow],
    *,
    domain: str,
    policy: EmailPolicy = EmailPolicy.UNIQUE_ONLY,
) -> RosterPlan:
    """Decide an email, or deliberately no email, for every row."""
    by_name: dict[str, list[RosterRow]] = defaultdict(list)
    for row in rows:
        by_name[row.name_key].append(row)

    # Two passes. The first proposes an address for every row; the second
    # issues it only if exactly one row proposed it. Deciding in one pass would
    # mean the row that happened to come first in the file won the address, and
    # file order is not evidence of who the address belongs to.
    proposed: list[str | None] = []
    for row in rows:
        siblings_count = len(by_name[row.name_key]) - 1
        local = row.name_key
        if not local:
            proposed.append(None)
        elif siblings_count == 0:
            proposed.append(f"{local}@{domain}".lower())
        elif policy is EmailPolicy.BIRTH_YEAR and row.date_of_birth is not None:
            proposed.append(f"{local}.{row.date_of_birth.year}@{domain}".lower())
        else:
            proposed.append(None)

    wanted: dict[str, int] = defaultdict(int)
    for candidate in proposed:
        if candidate:
            wanted[candidate] += 1

    accounts = [
        RosterAccount(
            row=row,
            email=(candidate if candidate and wanted[candidate] == 1 else None),
            shares_name_with=tuple(o for o in by_name[row.name_key] if o is not row),
        )
        for row, candidate in zip(rows, proposed, strict=True)
    ]

    _assert_unique_emails(accounts)
    return RosterPlan(accounts=tuple(accounts), policy=policy, domain=domain)


def _assert_unique_emails(accounts: list[RosterAccount]) -> None:
    """Invariant: no address is issued twice.

    This is an assertion rather than a recoverable error because every path
    above already prevents it. If it ever fires, the plan is unsafe to apply and
    stopping is the correct outcome -- one duplicated address is one athlete
    able to read another's data.
    """
    counts: dict[str, int] = defaultdict(int)
    for account in accounts:
        if account.email:
            counts[account.email] += 1
    duplicated = sorted(email for email, count in counts.items() if count > 1)
    if duplicated:
        raise RosterError(f"plan would issue a duplicate login email: {', '.join(duplicated)}")
