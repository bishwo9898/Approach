"""Who had a session, read off the History list.

The alternative is a hand-maintained players.txt, which is wrong the moment
somebody new hits. The History list already knows, so this reads it.

Two things make the reading safe rather than clever:

* It is **read-only**. Discovery screenshots and scrolls the list; it never
  clicks a row. `--list-sessions` runs exactly this and prints what it found,
  so a misread is caught before anything is captured.
* The result is a **plain text file you can edit**. If a name comes back wrong
  -- a hyphen lost, an initial merged -- fix the line rather than fighting the
  OCR. The capture run reads that file.

Dates are matched against the range you asked for, so the app's own date filter
is a convenience rather than something this depends on being set correctly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from src.ocr import TextLine, group_into_rows

#: Two or more capitalised words. Deliberately strict: a loose pattern turns
#: column headings and status words into athletes, and a missing athlete is far
#: easier to notice than an invented one.
NAME_PATTERN = r"^[A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’.-]+)+$"

#: Formats seen in TrackMan's History list. Year-less forms are resolved
#: against the range being searched.
DATE_FORMATS = ("%Y-%m-%d", "%d %b %Y", "%b %d %Y", "%d %B %Y", "%B %d %Y", "%m/%d/%Y")
SHORT_DATE_FORMATS = ("%d %b", "%b %d", "%d %B", "%B %d")

#: TrackMan shows an athlete id beside every name. A row carrying one but no
#: readable name means OCR dropped that athlete -- the one failure that would
#: otherwise be invisible, because a missing row looks exactly like a row that
#: was never there.
ID_PATTERN = r"TMBB[-\s]?\d{4,}"

#: Words that look like names but are furniture.
NOT_NAMES = {
    "all players", "all ipads", "this ipad", "all session types", "sync status",
    "session types", "recently used", "recently used players", "start date",
    "end date", "date range", "no results", "live at", "batting practice",
}


@dataclass(frozen=True, slots=True)
class Session:
    """One row of the History list."""

    player: str
    day: date | None

    def __str__(self) -> str:
        return f"{self.day.isoformat() if self.day else '????-??-??'}  {self.player}"


def clean_name(text: str) -> str:
    """Strip the avatar initials TrackMan draws beside each athlete.

    Vision reads the little circle and the name as one line, so "Sam
    Okafor" arrives as "SO Sam Okafor" and sometimes "(PN Peter Novak".
    Left alone, the initials either corrupt the name or stop it being
    recognised as one at all -- which silently drops that athlete.

    The leading block is only removed when its letters are the initials of the
    words that follow. That keeps athletes who genuinely go by initials: "JD
    Martinez" is left alone, because J and D are not the initials of
    "Martinez".
    """
    cleaned = " ".join(text.replace("(", " ").replace(")", " ").split())
    parts = cleaned.split()
    if len(parts) < 3:
        return cleaned

    head, rest = parts[0], parts[1:]
    if not (1 <= len(head) <= 3 and head.isalpha() and head.isupper()):
        return cleaned

    initials = [word[0].upper() for word in rest]
    position = 0
    for letter in head:
        while position < len(initials) and initials[position] != letter:
            position += 1
        if position == len(initials):
            return cleaned  # not an initials block; keep it
        position += 1
    return " ".join(rest)


def looks_like_a_name(text: str, pattern: str = NAME_PATTERN) -> bool:
    cleaned = clean_name(text)
    if cleaned.lower() in NOT_NAMES or len(cleaned) < 3:
        return False
    if cleaned.isupper():  # column headings
        return False
    return re.match(pattern, cleaned) is not None


def parse_day(text: str, *, around: date | None = None) -> date | None:
    """Parse a date cell. Year-less dates are resolved near `around`."""
    # Vision sometimes loses the space in "1 Oct 2026", reading "1Oct 2026".
    spaced = re.sub(r"(\d)([A-Za-z])", r"\1 \2", text.replace(",", " "))
    spaced = re.sub(r"([A-Za-z])(\d)", r"\1 \2", spaced)
    cleaned = " ".join(spaced.split())
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    if around is not None:
        # A year-less "Oct 9" inside a range that spans a new year could fall
        # either side of it, so each candidate year is tried explicitly and the
        # closest to the range wins. Parsing without a year would default to
        # 1900, which also cannot represent 29 February.
        candidates = []
        for fmt in SHORT_DATE_FORMATS:
            for year in (around.year - 1, around.year, around.year + 1):
                try:
                    candidates.append(
                        datetime.strptime(f"{cleaned} {year}", f"{fmt} %Y").date()
                    )
                except ValueError:
                    continue
            if candidates:
                return min(candidates, key=lambda day: abs((day - around).days))
    return None


def sessions_in_rows(
    lines: list[TextLine],
    *,
    around: date | None = None,
    name_pattern: str = NAME_PATTERN,
) -> list[Session]:
    """Read (athlete, date) pairs out of one screenshot of the History list.

    TrackMan groups rows under a date heading, so a row with a date and no name
    sets the date for the rows beneath it.
    """
    found: list[Session] = []
    current_day: date | None = None

    for row in group_into_rows(lines):
        texts = [" ".join(line.text.split()) for line in row]
        names = [clean_name(text) for text in texts if looks_like_a_name(text, name_pattern)]
        days = [day for day in (parse_day(text, around=around) for text in texts) if day]

        if days:
            current_day = days[0]
        if names:
            # The leftmost qualifying text is the athlete; anything further
            # right on the row is a count or a status.
            found.append(Session(player=names[0], day=days[0] if days else current_day))
    return found


def unreadable_rows(
    lines: list[TextLine],
    *,
    name_pattern: str = NAME_PATTERN,
    id_pattern: str = ID_PATTERN,
) -> int:
    """How many athlete ids appeared without a name beside them.

    Not an error on its own -- the id and the name are often separate lines, so
    this compares totals rather than pairing them up. A positive number means
    the list holds more athletes than were read, which is worth saying out loud.
    """
    ids = sum(1 for line in lines if re.search(id_pattern, line.text, re.I))
    names = sum(1 for line in lines if looks_like_a_name(line.text, name_pattern))
    return max(0, ids - names)


def merge(existing: list[Session], new: list[Session]) -> tuple[list[Session], int]:
    """Add sessions not already present. Returns (all, how many were added).

    Scrolling a list produces overlapping screenshots on purpose, so the same
    row is read several times; identity is (athlete, date).
    """
    seen = {(s.player, s.day) for s in existing}
    added = 0
    merged = list(existing)
    for session in new:
        key = (session.player, session.day)
        if key not in seen:
            seen.add(key)
            merged.append(session)
            added += 1
    return merged, added


def in_range(sessions: list[Session], start: date | None, end: date | None) -> list[Session]:
    """Sessions inside the requested range.

    A row whose date could not be read is kept: dropping it would silently lose
    an athlete, and the run reports unknown dates so they can be checked.
    """
    if start is None and end is None:
        return list(sessions)
    kept = []
    for session in sessions:
        if session.day is None:
            kept.append(session)
        elif (start is None or session.day >= start) and (end is None or session.day <= end):
            kept.append(session)
    return kept


def players(sessions: list[Session]) -> list[str]:
    """Distinct athletes, in the order they first appear."""
    seen: set[str] = set()
    out = []
    for session in sessions:
        if session.player not in seen:
            seen.add(session.player)
            out.append(session.player)
    return out


def write_roster(path, sessions: list[Session], start: date | None, end: date | None) -> None:
    """Save the athletes to an editable file the capture run reads."""
    header = [
        "# Athletes found in TrackMan's History list.",
        f"# Range: {start or 'any'} to {end or 'any'}",
        "# One per line. Edit a name if OCR got it wrong, or delete a line to skip them.",
        "# Lines starting with # are ignored.",
        "",
    ]
    names = players(sessions)
    path.write_text("\n".join(header + names) + "\n")


def read_roster(path) -> list[str]:
    names = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names
