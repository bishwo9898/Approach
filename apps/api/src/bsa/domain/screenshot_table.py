"""Reading TrackMan's pitch table out of a screenshot.

A pure function from positioned text to typed rows. No OCR engine, no files,
no database -- hand it recognized lines and it hands back rows and a list of
everything it refused to believe.

How it reads the table
----------------------
**By the header, never by pixel positions.** The screenshot must include the
header row -- PITCH SPEED, TOTAL SPIN, TILT, RELEASE HEIGHT, I. VERT. MOV,
HORZ. MOV, EXIT SPEED, SPIN RATE, LAUNCH ANGLE. Each header's horizontal centre
defines a column, and every cell below is assigned to the column it sits under.
That is what makes this survive a different window width, a different zoom, or
a retina display, none of which a hardcoded layout would survive.

It also means a screenshot without a header is **refused**, not guessed at.
Reading values into columns by position alone is how an exit speed becomes a
spin rate, and there is no way to notice afterwards.

What it refuses
---------------
Accuracy here is not "usually right". Every value lands on an athlete's page as
a measurement, so the parser rejects rather than approximates:

* a cell that is neither a number nor TrackMan's "-" for absent;
* a number outside the range its column can physically take;
* a row whose event number is missing or unreadable;
* **a gap in the event-number sequence.** The table runs #66, #65, #64 ... with
  no gaps, so a break means OCR dropped or garbled a row. This catches the
  failure that matters most -- a quietly missing pitch -- which no per-cell
  check can see.

Nothing is silently dropped. Every refusal comes back as a `RowProblem` naming
the row and the reason.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from enum import StrEnum


class Column(StrEnum):
    """The table's columns, keyed by what they become in the CSV."""

    PITCH_SPEED = "pitch_speed_mph"
    TOTAL_SPIN = "total_spin_rpm"
    TILT = "tilt_clock"
    RELEASE_HEIGHT = "release_height_ft"
    VERTICAL_MOVEMENT = "induced_vertical_movement_in"
    HORIZONTAL_MOVEMENT = "horizontal_movement_in"
    EXIT_SPEED = "exit_speed_mph"
    HIT_SPIN = "hit_spin_rate_rpm"
    LAUNCH_ANGLE = "launch_angle_deg"


#: How each column announces itself, and the range its values can take.
#:
#: The patterns are loose on spacing and punctuation because OCR is: "I. VERT.
#: MOV" comes back as "I.VERT.MOV" or "I VERT MOV" depending on the render.
#: The ranges are deliberately generous -- they exist to catch a decimal point
#: read as a digit or a column misassignment, not to judge an athlete.
@dataclass(frozen=True, slots=True)
class ColumnSpec:
    column: Column
    pattern: re.Pattern[str]
    low: float
    high: float
    #: Clock face ("12:45"), not a number.
    is_clock: bool = False
    #: Feet and inches (`5'2"`), which becomes a decimal number of feet.
    is_feet: bool = False


SPECS: tuple[ColumnSpec, ...] = (
    ColumnSpec(Column.PITCH_SPEED, re.compile(r"pitch\W*speed"), 10.0, 120.0),
    ColumnSpec(Column.TOTAL_SPIN, re.compile(r"total\W*spin"), 0.0, 5000.0),
    ColumnSpec(Column.TILT, re.compile(r"^tilt$"), 0.0, 0.0, is_clock=True),
    ColumnSpec(Column.RELEASE_HEIGHT, re.compile(r"release\W*height"), 0.0, 9.0, is_feet=True),
    ColumnSpec(Column.VERTICAL_MOVEMENT, re.compile(r"vert\W*mov"), -40.0, 40.0),
    ColumnSpec(Column.HORIZONTAL_MOVEMENT, re.compile(r"horz\W*mov|horiz\W*mov"), -40.0, 40.0),
    ColumnSpec(Column.EXIT_SPEED, re.compile(r"exit\W*speed"), 10.0, 140.0),
    ColumnSpec(Column.HIT_SPIN, re.compile(r"^spin\W*rate$"), 0.0, 10000.0),
    ColumnSpec(Column.LAUNCH_ANGLE, re.compile(r"launch\W*angle"), -90.0, 90.0),
)

#: The columns the hitting analytics are actually built from.
#:
#: A cell this module cannot read becomes "not measured", which is safe for a
#: column nothing computes from -- release height is context, and an absent one
#: changes no number on an athlete's page. For these two it is not safe: a
#: silently absent exit speed understates a best, and an absent launch angle
#: skews the line-drive window. So an unreadable value *here* withholds the
#: whole pitch, and anywhere else it only empties the cell.
MEASUREMENT_COLUMNS = frozenset({Column.EXIT_SPEED, Column.LAUNCH_ANGLE})

#: TrackMan prints this where it has no measurement. Several dashes, because
#: OCR picks whichever of them it likes the look of.
ABSENT = {"-", "--", "\u2014", "\u2013", "\u2212", ""}

#: `#66`, but also `*#54`, `X #42`, `8 #41` and `• #30`.
#:
#: The leading character is the row's marker icon: OCR sees a glyph where the
#: square, circle or crossed circle is drawn and reports its best guess at a
#: letter. That guess is discarded -- the marker is not a measurement, and
#: reading swings out of it is exactly the mistake this project already made
#: once. What matters is that its presence must not hide the pitch number, and
#: anchoring on `#` rather than on the start of the line is what ensures that.
_EVENT = re.compile(r"^\s*(?:\S{1,2}\s*)?#\s*(\d{1,4})\s*$")
#: The "Batter" label, with the helmet icon OCR tends to merge into it: the
#: real screenshot produced "6 Batter". Same shape of bug as the pitch number,
#: and it cost the athlete's name until it was allowed for.
_BATTER = re.compile(r"^\s*(?:\S{1,2}\s+)?batter\b[\s:]*(.*)$", re.IGNORECASE)
_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_CLOCK = re.compile(r"^(\d{1,2}):(\d{2})$")
#: `5'2"`, and every way OCR renders that inch mark: `5'2'`, `5'2`, `5'2i`,
#: `5'2''`. The foot mark is reliable; the inch mark is a single thin stroke
#: and comes back as whatever is nearest.
_FEET = re.compile(r"^(\d+)\s*'\s*(?:(\d+)\s*[\"'i\u2019\u201d]{0,2})?$")


@dataclass(frozen=True, slots=True)
class RowProblem:
    """Something the parser would not accept, and where.

    Severity is the difference between "do not trust this" and "you may want
    to look". Both are reported; only the first stops a row being used.
    """

    event_number: int | None
    column: str | None
    message: str
    #: True when the row cannot be trusted as read. False for things worth
    #: knowing that do not change any value -- chiefly a cell OCR did not emit
    #: where TrackMan was showing "-", which is a real omission but one whose
    #: correct reading is "no measurement" either way.
    blocking: bool = True


@dataclass(frozen=True, slots=True)
class TableRow:
    """One pitch, as read. Values are floats, or None where TrackMan showed "-"."""

    event_number: int
    values: dict[str, float | str | None]


@dataclass(frozen=True, slots=True)
class TableRead:
    """The outcome of reading one screenshot."""

    rows: list[TableRow] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    #: Columns found in the header, in the order they appear left to right.
    columns: list[Column] = field(default_factory=list)
    batter_name: str | None = None

    @property
    def blocking_problems(self) -> list[RowProblem]:
        return [p for p in self.problems if p.blocking]

    @property
    def notices(self) -> list[RowProblem]:
        return [p for p in self.problems if not p.blocking]

    @property
    def ok(self) -> bool:
        """Every row read cleanly. Notices do not count against this."""
        return bool(self.rows) and not self.blocking_problems

    @property
    def blocked_events(self) -> set[int]:
        """Pitches with a problem serious enough not to export."""
        return {p.event_number for p in self.blocking_problems if p.event_number is not None}

    @property
    def event_numbers(self) -> list[int]:
        return [row.event_number for row in self.rows]


# -- positioned text helpers -------------------------------------------------


@dataclass(frozen=True, slots=True)
class Cell:
    """The minimum this module needs from an OCR result."""

    text: str
    center_x: float
    center_y: float
    height: float


def group_rows(cells: list[Cell], tolerance: float = 0.6) -> list[list[Cell]]:
    """Cluster cells into visual rows by vertical position.

    The tolerance is a fraction of text height rather than a pixel count, so
    the same number works at any zoom or display scale.
    """
    ordered = sorted(cells, key=lambda c: c.center_y)
    rows: list[list[Cell]] = []
    for cell in ordered:
        if rows:
            last = rows[-1]
            reference = sum(c.height for c in last) / len(last)
            if abs(cell.center_y - last[-1].center_y) <= reference * tolerance:
                last.append(cell)
                continue
        rows.append([cell])
    return [sorted(row, key=lambda c: c.center_x) for row in rows]


# -- value parsing -----------------------------------------------------------


def parse_clock(text: str) -> str | None:
    """`"12:45"` stays a clock face -- it is an axis, not a quantity."""
    match = _CLOCK.match(text.strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (1 <= hour <= 12) or minute >= 60:
        return None
    return f"{hour}:{minute:02d}"


def parse_feet(text: str) -> float | None:
    """`5'2"` -> 5.1667 feet. `5'` -> 5.0."""
    normalized = text.strip().replace("\u201d", '"').replace("\u2019", "'")
    match = _FEET.match(normalized)
    if not match:
        return None
    feet = int(match.group(1))
    inches = int(match.group(2)) if match.group(2) else 0
    if inches >= 12:
        return None
    return round(feet + inches / 12.0, 4)


#: Every dash OCR might return where a minus sign was printed.
_DASHES = str.maketrans({"\u2212": "-", "\u2013": "-", "\u2014": "-"})


def parse_number(text: str) -> float | None:
    """A plain number. A trailing degree sign is tolerated and dropped.

    Returns None for anything else, including TrackMan's "-" -- the caller
    distinguishes "absent" from "unreadable", because they mean different
    things and only one of them is a problem.
    """
    cleaned = text.strip().translate(_DASHES).replace("\u00b0", "").replace(",", "")
    if not _NUMBER.match(cleaned):
        return None
    try:
        return float(cleaned)
    except ValueError:  # pragma: no cover -- guarded by the regex above
        return None


# -- reading the table -------------------------------------------------------


def _find_columns(rows: list[list[Cell]]) -> tuple[dict[Column, float], int]:
    """Locate the header row and each column's horizontal centre.

    Returns the centres and the index of the header row. Headers may wrap onto
    two visual rows (the name above its unit), so the unit row is skipped by
    matching on the names only.
    """
    for index, row in enumerate(rows):
        centers: dict[Column, float] = {}
        for cell in row:
            text = cell.text.strip().lower()
            for spec in SPECS:
                if spec.column not in centers and spec.pattern.search(text):
                    centers[spec.column] = cell.center_x
        # A real header carries most of the table. Matching one or two words
        # could just be a stray label somewhere else on screen.
        if len(centers) >= 6:
            return centers, index
    return {}, -1


def _assign(cell: Cell, centers: dict[Column, float]) -> Column | None:
    """The column a cell sits under, or None if it is nowhere near one."""
    if not centers:
        return None
    column, distance = min(
        ((c, abs(cell.center_x - x)) for c, x in centers.items()), key=lambda pair: pair[1]
    )
    spread = sorted(centers.values())
    # Half the narrowest column gap: beyond that a cell is between columns and
    # guessing which one it belongs to is exactly the mistake to avoid.
    gaps = [b - a for a, b in itertools.pairwise(spread)]
    limit = (min(gaps) / 2) if gaps else float("inf")
    return column if distance <= limit else None


def _batter_name(rows: list[list[Cell]]) -> str | None:
    """The athlete named in the table's own "Batter" row, if it is on screen."""
    for row in rows:
        for index, cell in enumerate(row):
            match = _BATTER.match(cell.text.strip())
            if not match:
                continue
            inline = match.group(1).strip()
            if inline:
                return re.sub(r"\s+", " ", inline)
            rest = " ".join(c.text.strip() for c in row[index + 1 :]).strip()
            if rest:
                return re.sub(r"\s+", " ", rest)
    return None


def read_table(cells: list[Cell]) -> TableRead:
    """Turn one screenshot's recognized text into verified rows.

    Refuses rather than approximates. See the module docstring for what it will
    not accept and why.
    """
    rows = group_rows(cells)
    centers, header_index = _find_columns(rows)

    if not centers:
        return TableRead(
            problems=[
                RowProblem(
                    None,
                    None,
                    "no column header found. The screenshot must include the header row "
                    "(PITCH SPEED, TOTAL SPIN, ... LAUNCH ANGLE) so columns are read by "
                    "name rather than by position.",
                )
            ]
        )

    ordered = [c for c, _ in sorted(centers.items(), key=lambda pair: pair[1])]
    out: list[TableRow] = []
    problems: list[RowProblem] = []

    for row in rows[header_index + 1 :]:
        event: int | None = None
        for cell in row:
            match = _EVENT.match(cell.text.strip())
            if match:
                event = int(match.group(1))
                break
        if event is None:
            continue  # not a pitch row -- a section heading, a footer, the batter line

        values: dict[str, float | str | None] = dict.fromkeys((c.value for c in centers), None)
        # Which columns actually had a cell under them. A column that produced
        # nothing is NOT the same as one showing TrackMan's "-": the first means
        # OCR dropped it, the second is a real absence. Both end up as None, so
        # without this they would be indistinguishable.
        seen: set[Column] = set()
        for cell in row:
            if _EVENT.match(cell.text.strip()):
                continue
            column = _assign(cell, centers)
            if column is None:
                continue
            seen.add(column)
            spec = next(s for s in SPECS if s.column is column)
            text = cell.text.strip()

            if text in ABSENT:
                values[column.value] = None
                continue

            if spec.is_clock:
                clock = parse_clock(text)
                if clock is None:
                    problems.append(
                        RowProblem(
                            event,
                            column.value,
                            f"{text!r} is not a clock face; read as no measurement",
                            blocking=column in MEASUREMENT_COLUMNS,
                        )
                    )
                else:
                    values[column.value] = clock
                continue

            number = parse_feet(text) if spec.is_feet else parse_number(text)
            if number is None:
                problems.append(
                    RowProblem(
                        event,
                        column.value,
                        f"{text!r} is not a number or a dash"
                        + ("" if column in MEASUREMENT_COLUMNS else "; read as no measurement"),
                        blocking=column in MEASUREMENT_COLUMNS,
                    )
                )
                continue
            if not (spec.low <= number <= spec.high):
                # A dropped decimal point is by far the most common way a
                # correct reading lands out of range: "11.5" comes back as
                # "115". Suggested, never applied -- a suggestion a human
                # confirms is help; the same guess applied silently is how a
                # wrong number reaches an athlete's page.
                hint = ""
                if spec.low <= number / 10 <= spec.high:
                    hint = f"; if a decimal point was missed this would be {number / 10:g}"
                problems.append(
                    RowProblem(
                        event,
                        column.value,
                        f"{number:g} is outside the plausible range "
                        f"{spec.low:g} to {spec.high:g}{hint}"
                        + ("" if column in MEASUREMENT_COLUMNS else "; read as no measurement"),
                        blocking=column in MEASUREMENT_COLUMNS,
                    )
                )
                continue
            values[column.value] = number

        for column in centers:
            if column not in seen:
                problems.append(
                    RowProblem(
                        event,
                        column.value,
                        "no cell was recognized here; read as no measurement. "
                        "TrackMan prints a dash for an absent value, and a lone "
                        "dash is the one glyph OCR routinely drops -- a printed "
                        "number is far more legible than a dash.",
                        blocking=False,
                    )
                )

        out.append(TableRow(event_number=event, values=values))

    problems.extend(_sequence_problems(out))
    return TableRead(
        rows=out,
        problems=problems,
        columns=ordered,
        batter_name=_batter_name(rows),
    )


def _sequence_problems(rows: list[TableRow]) -> list[RowProblem]:
    """Check the event numbers run consecutively.

    The strongest integrity check available, and the only one that can see the
    failure that matters most: a row OCR dropped entirely. Per-cell validation
    cannot notice a pitch that simply is not there, but a jump from #64 to #62
    is unmistakable.
    """
    numbers = [row.event_number for row in rows]
    if len(numbers) < 2:
        return []

    problems: list[RowProblem] = []
    duplicates = {n for n in numbers if numbers.count(n) > 1}
    for number in sorted(duplicates):
        problems.append(RowProblem(number, None, f"pitch #{number} appears more than once"))

    # The table is usually newest-first, but either direction is fine as long
    # as it has no holes.
    ascending = numbers == sorted(numbers)
    descending = numbers == sorted(numbers, reverse=True)
    if not ascending and not descending:
        problems.append(
            RowProblem(None, None, "pitch numbers are not in order; rows may have been mixed")
        )
        return problems

    ordered = sorted(set(numbers))
    expected = set(range(ordered[0], ordered[-1] + 1))
    for missing in sorted(expected - set(ordered)):
        problems.append(
            RowProblem(
                missing,
                None,
                f"pitch #{missing} is missing between #{ordered[0]} and #{ordered[-1]}; "
                "a row was probably not recognized",
            )
        )
    return problems


# -- combining several screenshots -------------------------------------------
#
# A session runs to dozens of pitches and a screen holds about fifteen, so a
# coach takes several and they overlap. The overlap is not waste: a pitch read
# twice is a pitch checked twice, and two screenshots disagreeing about the
# same value is the loudest possible signal that one of them was misread.


@dataclass(frozen=True, slots=True)
class SourcedRead:
    """One screenshot's result, with the file it came from."""

    source: str
    read: TableRead


@dataclass(frozen=True, slots=True)
class MergedTable:
    """Every pitch across a set of screenshots, reconciled."""

    rows: list[TableRow] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    batter_name: str | None = None
    #: Which screenshot each pitch was taken from.
    source_of: dict[int, str] = field(default_factory=dict)

    @property
    def blocking_problems(self) -> list[RowProblem]:
        return [p for p in self.problems if p.blocking]

    @property
    def notices(self) -> list[RowProblem]:
        return [p for p in self.problems if not p.blocking]

    @property
    def ok(self) -> bool:
        return bool(self.rows) and not self.blocking_problems


def merge_reads(reads: list[SourcedRead]) -> MergedTable:
    """Combine screenshots into one table, keyed by pitch number.

    Where two screenshots show the same pitch, their values must agree. A
    disagreement is reported and the pitch is withheld: we know one reading is
    wrong and have no basis for choosing between them.
    """
    rows: dict[int, TableRow] = {}
    source_of: dict[int, str] = {}
    problems: list[RowProblem] = []
    conflicted: set[int] = set()
    batter: str | None = None

    for sourced in reads:
        if sourced.read.batter_name and batter is None:
            batter = sourced.read.batter_name
        for problem in sourced.read.problems:
            problems.append(
                RowProblem(
                    problem.event_number,
                    problem.column,
                    f"{sourced.source}: {problem.message}",
                    blocking=problem.blocking,
                )
            )

        blocked = sourced.read.blocked_events
        for row in sourced.read.rows:
            if row.event_number in blocked:
                continue  # already reported; do not let a bad read win a merge
            existing = rows.get(row.event_number)
            if existing is None:
                rows[row.event_number] = row
                source_of[row.event_number] = sourced.source
                continue
            for column, value in row.values.items():
                other = existing.values.get(column)
                # None means "not measured here", which a second screenshot may
                # legitimately fill in; only two *present* values can conflict.
                if value is not None and other is not None and value != other:
                    conflicted.add(row.event_number)
                    problems.append(
                        RowProblem(
                            row.event_number,
                            column,
                            f"{source_of[row.event_number]} read {other!r} but "
                            f"{sourced.source} read {value!r} for the same pitch",
                        )
                    )
                elif value is not None and other is None:
                    existing.values[column] = value

    for event in conflicted:
        rows.pop(event, None)

    ordered = [rows[event] for event in sorted(rows)]
    # A pitch withheld above is already explained; reporting it again as a hole
    # in the sequence would say the same thing twice in different words.
    explained = {p.event_number for p in problems if p.blocking and p.event_number is not None}
    problems.extend(p for p in _sequence_problems(ordered) if p.event_number not in explained)
    return MergedTable(rows=ordered, problems=problems, batter_name=batter, source_of=source_of)
