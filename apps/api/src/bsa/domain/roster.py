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

Taken *together* they do, in one direction only. The facility's rule, from the
people who know these athletes: **identical first name, last name and date of
birth means TrackMan entered the same person twice.** Those rows become one
athlete holding both vendor ids, which is what `ExternalPlayerIdentity` was
always shaped for. Everything weaker than that -- a shared name, a shared birth
*year* -- is still two people until a human says otherwise.

The one place this rule is thin is called out rather than hidden: when the date
the rows agree on is one the export repeats dozens of times, it is a default
and not a birthday, so the merge rests almost entirely on the name.
`RosterAthlete.shared_birth_date` marks those, and the provisioner prints them.

Login emails are derived from names, so a duplicated name is a duplicated
email, and a duplicated email means one athlete could claim another athlete's
account and read their data. This module therefore:

* creates one player per *person*, merging vendor rows only on the exact rule
  above and never on anything looser, because collapsing two athletes would
  attribute one's data to the other;
* issues a claimable email only when the name identifies exactly one person;
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
class RosterAthlete:
    """One person, and every vendor account the export holds for them.

    Usually a single row. More than one when `group_rows` found the export had
    entered the same athlete twice, in which case the resulting player carries
    every one of those TrackMan ids -- so data arriving under either id lands on
    the same athlete, which is the whole point of merging them.
    """

    #: At least one, in the order they appear in the export.
    rows: tuple[RosterRow, ...]
    #: True when the birth date these rows agree on is one the export repeats
    #: many times over. It is then a bulk-upload default rather than a birthday,
    #: so the merge is resting almost entirely on the name being identical.
    shared_birth_date: bool = False

    @property
    def primary(self) -> RosterRow:
        """The row the athlete's details come from: the first in the file."""
        return self.rows[0]

    @property
    def full_name(self) -> str:
        return self.primary.full_name

    @property
    def name_key(self) -> str:
        return self.primary.name_key

    @property
    def date_of_birth(self) -> date | None:
        return self.primary.date_of_birth

    @property
    def identities(self) -> tuple[tuple[str, str], ...]:
        """Every (provider, external id) this person should answer to."""
        return tuple((row.provider, row.external_id) for row in self.rows)

    @property
    def is_merged(self) -> bool:
        return len(self.rows) > 1


@dataclass(frozen=True, slots=True)
class RosterAccount:
    """A person, plus the account decision made for them."""

    athlete: RosterAthlete
    #: None when no email could be issued safely -- see `blocked_reason`.
    email: str | None
    #: Other *people* sharing this name. Empty when the name identifies one.
    shares_name_with: tuple[RosterAthlete, ...] = ()

    @property
    def row(self) -> RosterRow:
        """The athlete's first roster row, for reporting."""
        return self.athlete.primary

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
                f"{others + 1} different athletes are named {self.athlete.full_name!r}; "
                "a coach must say which TrackMan account belongs to which athlete"
            )
        return f"no usable email could be formed from {self.athlete.primary.raw_name!r}"


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
    def collision_groups(self) -> dict[str, tuple[RosterAthlete, ...]]:
        """Name key -> every athlete carrying that name, for names shared."""
        groups: dict[str, list[RosterAthlete]] = defaultdict(list)
        for account in self.accounts:
            if account.shares_name_with:
                groups[account.athlete.name_key].append(account.athlete)
        return {key: tuple(found) for key, found in sorted(groups.items())}

    @property
    def merged(self) -> tuple[RosterAthlete, ...]:
        """Athletes the export had entered more than once."""
        return tuple(a.athlete for a in self.accounts if a.athlete.is_merged)


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


# -- grouping rows into people -----------------------------------------------

#: A birth date carried by at least this many roster entries is a bulk-upload
#: default, not a birthday. With ~490 athletes spread over twenty years of
#: dates, five sharing one day does not happen by chance -- the real export has
#: one date on 109 rows and another on 55.
PLACEHOLDER_DATE_THRESHOLD = 5


def repeated_birth_dates(
    rows: list[RosterRow], *, threshold: int = PLACEHOLDER_DATE_THRESHOLD
) -> set[date]:
    """Birth dates the export repeats often enough to be defaults."""
    counts: dict[date, int] = defaultdict(int)
    for row in rows:
        if row.date_of_birth is not None:
            counts[row.date_of_birth] += 1
    return {day for day, count in counts.items() if count >= threshold}


def group_rows(rows: list[RosterRow], *, merge_duplicates: bool = True) -> list[RosterAthlete]:
    """Collapse rows that are the same person into one athlete each.

    The rule, and nothing looser: identical name **and** identical date of
    birth. A shared name alone is two people. A shared birth *year* is two
    people. Rows with no readable birth date are never merged, because the
    evidence the rule depends on is missing.

    `merge_duplicates=False` turns this off entirely -- one athlete per vendor
    row, as the export literally states it.
    """
    if not merge_duplicates:
        return [RosterAthlete(rows=(row,)) for row in rows]

    defaults = repeated_birth_dates(rows)
    buckets: dict[tuple[str, date], list[RosterRow]] = {}
    first_seen: dict[tuple[str, date], int] = {}
    alone: list[tuple[int, RosterRow]] = []

    for index, row in enumerate(rows):
        if row.date_of_birth is None:
            alone.append((index, row))
            continue
        key = (row.name_key, row.date_of_birth)
        buckets.setdefault(key, []).append(row)
        first_seen.setdefault(key, index)

    # Emitted in the order each athlete first appears, so the plan reads in the
    # same order as the file a coach is looking at.
    ordered: list[tuple[int, RosterAthlete]] = [
        (
            first_seen[key],
            RosterAthlete(rows=tuple(group), shared_birth_date=key[1] in defaults),
        )
        for key, group in buckets.items()
    ]
    ordered += [(index, RosterAthlete(rows=(row,))) for index, row in alone]
    return [athlete for _, athlete in sorted(ordered, key=lambda entry: entry[0])]


# -- planning ----------------------------------------------------------------


def build_plan(
    athletes: list[RosterAthlete],
    *,
    domain: str,
    policy: EmailPolicy = EmailPolicy.UNIQUE_ONLY,
) -> RosterPlan:
    """Decide an email, or deliberately no email, for every athlete."""
    by_name: dict[str, list[RosterAthlete]] = defaultdict(list)
    for athlete in athletes:
        by_name[athlete.name_key].append(athlete)

    # Two passes. The first proposes an address for every athlete; the second
    # issues it only if exactly one athlete proposed it. Deciding in one pass
    # would mean whoever came first in the file won the address, and file order
    # is not evidence of who the address belongs to.
    proposed: list[str | None] = []
    for athlete in athletes:
        others = len(by_name[athlete.name_key]) - 1
        local = athlete.name_key
        if not local:
            proposed.append(None)
        elif others == 0:
            proposed.append(f"{local}@{domain}".lower())
        elif policy is EmailPolicy.BIRTH_YEAR and athlete.date_of_birth is not None:
            proposed.append(f"{local}.{athlete.date_of_birth.year}@{domain}".lower())
        else:
            proposed.append(None)

    wanted: dict[str, int] = defaultdict(int)
    for candidate in proposed:
        if candidate:
            wanted[candidate] += 1

    accounts = [
        RosterAccount(
            athlete=athlete,
            email=(candidate if candidate and wanted[candidate] == 1 else None),
            shares_name_with=tuple(
                other for other in by_name[athlete.name_key] if other is not athlete
            ),
        )
        for athlete, candidate in zip(athletes, proposed, strict=True)
    ]

    _assert_unique_emails(accounts)
    return RosterPlan(accounts=tuple(accounts), policy=policy, domain=domain)


def plan_export(
    records: list[dict[str, str]],
    *,
    domain: str,
    policy: EmailPolicy = EmailPolicy.UNIQUE_ONLY,
    merge_duplicates: bool = True,
) -> tuple[RosterPlan, list[str]]:
    """Parse, group and plan an export in one call. Returns (plan, skipped)."""
    rows, skipped = parse_rows(records)
    athletes = group_rows(rows, merge_duplicates=merge_duplicates)
    return build_plan(athletes, domain=domain, policy=policy), skipped


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
