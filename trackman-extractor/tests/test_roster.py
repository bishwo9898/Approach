"""Reading athletes out of the History list.

The risk here is not missing a name -- that is visible in --list-sessions and
easy to fix by editing the roster file. The risk is *inventing* one: a column
heading or a status word read as an athlete produces a folder of screenshots
belonging to nobody. These tests mostly guard that direction.
"""

from __future__ import annotations

from datetime import date

from src.ocr import TextLine
from src.roster import (
    Session,
    in_range,
    looks_like_a_name,
    merge,
    parse_day,
    players,
    read_roster,
    sessions_in_rows,
    write_roster,
)

TODAY = date(2026, 10, 9)


def line(text: str, y: float, x: float = 0.0) -> TextLine:
    return TextLine(text, 1.0, x, y, 120.0, 18.0)


def test_real_names_are_recognised() -> None:
    for name in ("Jordan Avery", "Riley Chen", "Devin Ruiz", "O'Brien Smith",
                 "Mary Jo Clarke", "Jean-Luc Picard"):
        assert looks_like_a_name(name), name


def test_interface_text_is_never_read_as_an_athlete() -> None:
    """Everything visible in the History panel that is not a person."""
    for text in ("EXIT SPEED", "All players", "All iPads", "This iPad only",
                 "All session types", "Sync. status", "Date", "Players", "Plays",
                 "Videos", "RHP", "Start date", "End date", "Recently used players",
                 "HISTORY", "Apply", "Clear", "", "   ", "A"):
        assert not looks_like_a_name(text), text


def test_a_single_word_is_not_a_name() -> None:
    """Column headings are single words far more often than athletes are."""
    assert not looks_like_a_name("Okafor")


def test_dates_are_read_in_the_formats_trackman_shows() -> None:
    assert parse_day("2026-10-09") == date(2026, 10, 9)
    assert parse_day("9 Oct 2026") == date(2026, 10, 9)
    assert parse_day("15 Oct 2026") == date(2026, 10, 15)
    assert parse_day("10/09/2026") == date(2026, 10, 9)


def test_a_date_without_a_year_is_resolved_near_the_range() -> None:
    assert parse_day("Oct 9", around=TODAY) == date(2026, 10, 9)
    # A January row read while searching late December belongs to the next year.
    assert parse_day("Jan 3", around=date(2026, 12, 28)) == date(2027, 1, 3)


def test_text_that_is_not_a_date_returns_nothing() -> None:
    for text in ("Players", "", "Sync. status", "32"):
        assert parse_day(text, around=TODAY) is None


def test_rows_pair_each_athlete_with_their_date() -> None:
    lines = [
        line("9 Oct 2026", 10), line("Jordan Avery", 10, 200),
        line("9 Oct 2026", 40), line("Riley Chen", 40, 200),
    ]

    found = sessions_in_rows(lines, around=TODAY)

    assert found == [
        Session("Jordan Avery", date(2026, 10, 9)),
        Session("Riley Chen", date(2026, 10, 9)),
    ]


def test_a_date_heading_applies_to_the_rows_under_it() -> None:
    """TrackMan groups sessions under a date, so most rows carry no date."""
    lines = [
        line("9 Oct 2026", 10),
        line("Jordan Avery", 40, 200),
        line("Riley Chen", 70, 200),
        line("8 Oct 2026", 100),
        line("Devin Ruiz", 130, 200),
    ]

    found = sessions_in_rows(lines, around=TODAY)

    assert found == [
        Session("Jordan Avery", date(2026, 10, 9)),
        Session("Riley Chen", date(2026, 10, 9)),
        Session("Devin Ruiz", date(2026, 10, 8)),
    ]


def test_counts_and_statuses_on_a_row_are_ignored() -> None:
    lines = [line("9 Oct 2026", 10), line("Jordan Avery", 10, 200),
             line("32", 10, 400), line("Synced", 10, 500)]

    assert sessions_in_rows(lines, around=TODAY) == [
        Session("Jordan Avery", date(2026, 10, 9))
    ]


def test_overlapping_reads_do_not_duplicate_an_athlete() -> None:
    """Scrolling the list re-reads rows on purpose."""
    first = [Session("Jordan Avery", TODAY), Session("Riley Chen", TODAY)]
    second = [Session("Riley Chen", TODAY), Session("Devin Ruiz", TODAY)]

    merged, added = merge(first, second)

    assert added == 1
    assert players(merged) == ["Jordan Avery", "Riley Chen", "Devin Ruiz"]


def test_the_same_athlete_on_two_days_is_two_sessions_but_one_athlete() -> None:
    merged, added = merge(
        [Session("Jordan Avery", date(2026, 10, 8))],
        [Session("Jordan Avery", date(2026, 10, 9))],
    )

    assert added == 1
    assert players(merged) == ["Jordan Avery"]


def test_sessions_outside_the_range_are_dropped() -> None:
    sessions = [
        Session("Early", date(2026, 9, 30)),
        Session("Inside", date(2026, 10, 5)),
        Session("Late", date(2026, 10, 20)),
    ]

    kept = in_range(sessions, date(2026, 10, 1), date(2026, 10, 15))

    assert players(kept) == ["Inside"]


def test_the_range_includes_both_ends() -> None:
    sessions = [Session("First", date(2026, 10, 1)), Session("Last", date(2026, 10, 15))]

    assert len(in_range(sessions, date(2026, 10, 1), date(2026, 10, 15))) == 2


def test_a_row_with_an_unreadable_date_is_kept_not_dropped() -> None:
    """Dropping it would silently lose an athlete; the run reports these instead."""
    sessions = [Session("Unknown Date", None), Session("Outside", date(2020, 1, 1))]

    kept = in_range(sessions, date(2026, 10, 1), date(2026, 10, 15))

    assert players(kept) == ["Unknown Date"]


def test_the_roster_file_round_trips_and_is_editable(tmp_path) -> None:
    path = tmp_path / "roster.txt"
    write_roster(path, [Session("Jordan Avery", TODAY), Session("Riley Chen", TODAY)],
                 date(2026, 10, 1), date(2026, 10, 15))

    text = path.read_text()
    assert "# " in text  # explains itself
    assert read_roster(path) == ["Jordan Avery", "Riley Chen"]

    # An operator deletes a line to skip someone, and fixes a misread name.
    path.write_text(text.replace("Riley Chen", "# Riley Chen")
                        .replace("Jordan Avery", "Jordan Averie"))
    assert read_roster(path) == ["Jordan Averie"]


# -- cases found by running against real TrackMan screenshots -----------------


def test_avatar_initials_are_stripped_from_a_name() -> None:
    """Vision reads the little circle and the name as one line.

    Real reads carried the avatar's initials: 'SO Sam Okafor', '(PN Ptetr Novak'.
    Left alone the first corrupts the name and the others are not recognised as
    names at all, which drops those athletes silently.
    """
    from src.roster import clean_name

    assert clean_name("SO Sam Okafor") == "Sam Okafor"
    assert clean_name("(PN Ptetr Novak") == "Ptetr Novak"
    assert clean_name("(CD Chris Dale") == "Chris Dale"
    assert clean_name("R Riley Chen") == "Riley Chen"


def test_an_athlete_who_goes_by_initials_keeps_them() -> None:
    """The reason stripping is conditional rather than unconditional."""
    from src.roster import clean_name

    assert clean_name("JD Martinez Jr") == "JD Martinez Jr"
    assert clean_name("CC Sabathia Jones") == "CC Sabathia Jones"


def test_a_two_word_name_is_never_shortened() -> None:
    from src.roster import clean_name

    assert clean_name("Jordan Avery") == "Jordan Avery"
    assert clean_name("TJ Walsh") == "TJ Walsh"


def test_names_with_stripped_initials_are_recognised() -> None:
    assert looks_like_a_name("SO Sam Okafor")
    assert looks_like_a_name("(PN Ptetr Novak")


def test_a_date_that_lost_its_space_still_parses() -> None:
    """Vision read the picker's '1 Oct 2026' as '1Oct 2026'."""
    assert parse_day("1Oct 2026") == date(2026, 10, 1)
    assert parse_day("15Oct 2026") == date(2026, 10, 15)


def test_an_id_without_a_name_is_counted_as_unread() -> None:
    """The failure that would otherwise be invisible: a dropped athlete."""
    from src.roster import unreadable_rows

    lines = [
        line("Jordan Avery", 10), line("RHP. TMBB-1000622446", 30),
        line("RHP. TMBB-1000556488", 60),  # Noa Fine: id read, name not
    ]

    assert unreadable_rows(lines) == 1


def test_nothing_is_flagged_when_every_row_was_read() -> None:
    from src.roster import unreadable_rows

    lines = [
        line("Jordan Avery", 10), line("RHP. TMBB-1000622446", 30),
        line("Riley Chen", 60), line("RHP. TMBB-1000557951", 80),
    ]

    assert unreadable_rows(lines) == 0


def test_the_filter_bar_yields_no_athletes() -> None:
    """Read from the real History filter bar; none of it is a person."""
    lines = [line(text, index * 20) for index, text in enumerate([
        "HISTORY", "All iPads", "Date v", "All players v", "L AllB1s V",
        "og All session types v", "D This iPad only", "Videos", "Players",
        "Plays", "Sync. status",
    ])]

    assert sessions_in_rows(lines, around=TODAY) == []
