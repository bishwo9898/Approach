"""Turning a roster export into accounts.

Every athlete name here is invented. The real export contains ~490 minors'
names and dates of birth and is gitignored; the shapes it taught us about --
double spaces, placeholder birth dates, four athletes sharing one name -- are
reproduced with made-up people instead.
"""

from __future__ import annotations

from datetime import date

import pytest

from bsa.domain.roster import (
    EmailPolicy,
    RosterError,
    collapse_spaces,
    email_local_part,
    group_rows,
    parse_date_of_birth,
    parse_player_id,
    parse_rows,
    plan_export,
    repeated_birth_dates,
    split_name,
)

DOMAIN = "approach.com"


def record(name: str, dob: str = "Jul. 4  2010", player_id: str = "") -> dict[str, str]:
    """One export line. Ids are generated so a test need not invent them."""
    return {
        "name": name,
        "dateOfBirth": dob,
        "number": "-",
        "team": "-",
        "playerId": player_id or f"{abs(hash(name + dob)) % 10**7 + 1000000} TrackMan",
    }


def plan_for(  # type: ignore[no-untyped-def]
    records: list[dict[str, str]],
    policy: EmailPolicy = EmailPolicy.UNIQUE_ONLY,
    *,
    merge_duplicates: bool = True,
):
    return plan_export(records, domain=DOMAIN, policy=policy, merge_duplicates=merge_duplicates)


def emails(plan) -> dict[str, str | None]:  # type: ignore[no-untyped-def]
    """Address per athlete, keyed by their first vendor id."""
    return {a.athlete.primary.external_id: a.email for a in plan.accounts}


# -- field parsing -----------------------------------------------------------


class TestNames:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Jordan  Avery ", "Jordan Avery"),
            ("  Riley Chen", "Riley Chen"),
            ("Sam\tOkafor", "Sam Okafor"),
        ],
    )
    def test_whitespace_is_normalized(self, raw: str, expected: str) -> None:
        """The real export is full of double and trailing spaces.

        Normalizing is what makes two spellings of one name collide visibly in
        the plan rather than silently becoming two athletes.
        """
        assert collapse_spaces(raw) == expected

    def test_an_email_is_derived_from_the_whole_name(self) -> None:
        assert email_local_part("Ana Marie Okafor") == "ana.marie.okafor"

    def test_digits_in_a_name_survive(self) -> None:
        """The export contains entries that are not personal names."""
        assert email_local_part("Devin 14u") == "devin.14u"

    def test_punctuation_folds_to_a_single_dot(self) -> None:
        assert email_local_part("Mary-Kate O'Brien") == "mary.kate.o.brien"

    def test_case_is_irrelevant(self) -> None:
        assert email_local_part("SJ Ruiz") == email_local_part("Sj  Ruiz ")

    def test_a_multi_word_surname_stays_intact(self) -> None:
        assert split_name("Ana Marie Okafor") == ("Ana", "Marie Okafor")

    def test_a_single_token_name_is_treated_as_a_surname(self) -> None:
        assert split_name("Okafor") == ("", "Okafor")


class TestDatesOfBirth:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Jul. 29  2006", date(2006, 7, 29)),
            ("Sep. 1  2015", date(2015, 9, 1)),
            ("May. 11  2007", date(2007, 5, 11)),
            ("Dec. 1  2008", date(2008, 12, 1)),
        ],
    )
    def test_the_export_format_is_read(self, raw: str, expected: str) -> None:
        assert parse_date_of_birth(raw) == expected

    @pytest.mark.parametrize("raw", ["", "-", "unknown", "Smarch. 4 2010", "Jul. 99 2006"])
    def test_an_unreadable_date_is_none_rather_than_an_error(self, raw: str) -> None:
        """Nothing in the app reads a birth date, so one bad cell must not stop
        the other 487 athletes from being provisioned."""
        assert parse_date_of_birth(raw) is None

    def test_an_impossible_date_is_rejected(self) -> None:
        assert parse_date_of_birth("Feb. 30 2011") is None


class TestPlayerIds:
    def test_the_vendor_suffix_is_split_off(self) -> None:
        assert parse_player_id("1000593912 TrackMan") == ("trackman", "1000593912")

    def test_other_vendors_are_recognized(self) -> None:
        assert parse_player_id("824726 MLB") == ("mlb", "824726")

    @pytest.mark.parametrize("raw", ["", "-", "1000593912", "1000593912 Hawkeye"])
    def test_anything_unrecognized_is_rejected(self, raw: str) -> None:
        """A guessed provider would make the identity unmatchable against the
        data that arrives later, which is worse than having no identity."""
        assert parse_player_id(raw) is None


# -- skipped rows ------------------------------------------------------------


class TestSkippedRows:
    def test_a_row_with_no_name_is_skipped(self) -> None:
        rows, skipped = parse_rows([record(""), record("Jordan Avery")])
        assert [r.full_name for r in rows] == ["Jordan Avery"]
        assert "no name" in skipped[0]

    def test_a_row_with_no_vendor_id_is_skipped(self) -> None:
        rows, skipped = parse_rows([record("Jordan Avery", player_id="-")])
        assert rows == []
        assert "no recognized vendor id" in skipped[0]

    def test_a_repeated_vendor_id_is_skipped(self) -> None:
        """The vendor id is the key later imports match on, so two rows cannot
        both claim one id."""
        rows, skipped = parse_rows(
            [
                record("Jordan Avery", player_id="100 TrackMan"),
                record("Riley Chen", player_id="100 TrackMan"),
            ]
        )
        assert [r.full_name for r in rows] == ["Jordan Avery"]
        assert "already used on line 2" in skipped[0]

    def test_the_same_id_from_two_vendors_is_kept(self) -> None:
        rows, _ = parse_rows(
            [
                record("Jordan Avery", player_id="100 TrackMan"),
                record("Riley Chen", player_id="100 MLB"),
            ]
        )
        assert len(rows) == 2

    def test_reported_line_numbers_point_at_the_file(self) -> None:
        """Line 1 is the header, so the first record is line 2."""
        rows, _ = parse_rows([record("Jordan Avery"), record("Riley Chen")])
        assert [r.line for r in rows] == [2, 3]


# -- the account plan --------------------------------------------------------


class TestUniqueNames:
    def test_an_unambiguous_name_gets_a_plain_address(self) -> None:
        plan, _ = plan_for([record("Jordan Avery")])
        assert plan.accounts[0].email == "jordan.avery@approach.com"
        assert plan.accounts[0].is_claimable
        assert plan.accounts[0].blocked_reason is None

    def test_spelling_variants_with_one_birth_date_are_one_person(self) -> None:
        """ "Sam  Okafor " and "Sam Okafor", same birth date: one athlete."""
        plan, _ = plan_for([record("Sam  Okafor "), record("Sam Okafor")])
        assert len(plan.accounts) == 1
        assert plan.accounts[0].email == "sam.okafor@approach.com"


class TestSharedNames:
    """63 of 488 real roster names belong to more than one vendor account."""

    @pytest.fixture
    def shared(self):  # type: ignore[no-untyped-def]
        plan, _ = plan_for(
            [
                record("Devin Ruiz", "Jul. 28  2006", "11 TrackMan"),
                record("Devin  Ruiz", "Oct. 29  2011", "22 TrackMan"),
                record("Jordan Avery", "Jun. 1  2009", "33 TrackMan"),
            ]
        )
        return plan

    def test_neither_claimant_gets_the_address(self, shared) -> None:  # type: ignore[no-untyped-def]
        """The decisive property. One address issued twice is one athlete able
        to read another athlete's sessions."""
        assert emails(shared) == {
            "11": None,
            "22": None,
            "33": "jordan.avery@approach.com",
        }

    def test_the_block_explains_itself_to_a_coach(self, shared) -> None:  # type: ignore[no-untyped-def]
        reason = shared.accounts[0].blocked_reason
        assert reason is not None
        assert "2 different athletes" in reason and "Devin Ruiz" in reason

    def test_collisions_are_reported_as_groups(self, shared) -> None:  # type: ignore[no-untyped-def]
        groups = shared.collision_groups
        assert list(groups) == ["devin.ruiz"]
        assert {a.primary.external_id for a in groups["devin.ruiz"]} == {"11", "22"}

    def test_unaffected_athletes_are_untouched(self, shared) -> None:  # type: ignore[no-untyped-def]
        assert len(shared.claimable) == 1

    def test_four_different_athletes_sharing_a_name_all_block(self) -> None:
        """The real export has one name used by four vendor accounts."""
        plan, _ = plan_for(
            [
                record("Alex Stone", f"Mar. {day}  201{day}", f"{day} TrackMan")
                for day in range(1, 5)
            ]
        )
        assert len(plan.blocked) == 4


class TestBirthYearPolicy:
    def test_shared_names_are_disambiguated_by_year(self) -> None:
        plan, _ = plan_for(
            [
                record("Devin Ruiz", "Jul. 28  2006", "11 TrackMan"),
                record("Devin Ruiz", "Oct. 29  2011", "22 TrackMan"),
            ],
            EmailPolicy.BIRTH_YEAR,
        )
        assert emails(plan) == {
            "11": "devin.ruiz.2006@approach.com",
            "22": "devin.ruiz.2011@approach.com",
        }

    def test_an_unambiguous_name_still_gets_the_plain_address(self) -> None:
        plan, _ = plan_for([record("Jordan Avery")], EmailPolicy.BIRTH_YEAR)
        assert plan.accounts[0].email == "jordan.avery@approach.com"

    def test_a_shared_birth_year_still_blocks(self) -> None:
        """Nine real groups share a name *and* a birth year. The year cannot
        separate those, so the policy must fall back to blocking rather than
        picking one."""
        plan, _ = plan_for(
            [
                record("Devin Ruiz", "Feb. 24  2015", "11 TrackMan"),
                record("Devin Ruiz", "Aug. 3  2015", "22 TrackMan"),
            ],
            EmailPolicy.BIRTH_YEAR,
        )
        assert emails(plan) == {"11": None, "22": None}

    def test_a_missing_birth_date_blocks(self) -> None:
        plan, _ = plan_for(
            [
                record("Devin Ruiz", "-", "11 TrackMan"),
                record("Devin Ruiz", "Oct. 29  2011", "22 TrackMan"),
            ],
            EmailPolicy.BIRTH_YEAR,
        )
        assert emails(plan)["11"] is None

    def test_a_disambiguated_address_cannot_steal_a_plain_one(self) -> None:
        """Contrived but checkable: an athlete literally named "Devin Ruiz 2011"
        wants the same address the year suffix would produce. Neither gets it."""
        plan, _ = plan_for(
            [
                record("Devin Ruiz", "Jul. 28  2006", "11 TrackMan"),
                record("Devin Ruiz", "Oct. 29  2011", "22 TrackMan"),
                record("Devin Ruiz 2011", "Jan. 2  2012", "33 TrackMan"),
            ],
            EmailPolicy.BIRTH_YEAR,
        )
        issued = [e for e in emails(plan).values() if e]
        assert len(issued) == len(set(issued))
        assert emails(plan)["22"] is None
        assert emails(plan)["33"] is None


class TestEnteredTwice:
    """The facility's rule: identical name *and* birth date is one person.

    TrackMan entered some athletes twice. Merging those rows is what stops one
    person owning two profiles and their sessions splitting across both. The
    rule is deliberately narrow -- everything weaker stays two people.
    """

    def test_identical_name_and_birth_date_is_one_athlete(self) -> None:
        plan, _ = plan_for(
            [
                record("Riley Chen", "Feb. 24  2015", "11 TrackMan"),
                record("Riley Chen", "Feb. 24  2015", "22 TrackMan"),
            ]
        )
        assert len(plan.accounts) == 1
        athlete = plan.accounts[0].athlete
        assert athlete.is_merged
        assert athlete.identities == (("trackman", "11"), ("trackman", "22"))

    def test_the_merged_athlete_gets_the_plain_address(self) -> None:
        """The name no longer identifies two people, so nothing is ambiguous."""
        plan, _ = plan_for(
            [
                record("Riley Chen", "Feb. 24  2015", "11 TrackMan"),
                record("Riley Chen", "Feb. 24  2015", "22 TrackMan"),
            ]
        )
        assert plan.accounts[0].email == "riley.chen@approach.com"
        assert not plan.blocked

    def test_four_rows_can_be_two_people(self) -> None:
        """Two duplicated athletes who happen to share a name."""
        plan, _ = plan_for(
            [
                record("Alex Stone", "Feb. 24  2015", "11 TrackMan"),
                record("Alex Stone", "Feb. 24  2015", "22 TrackMan"),
                record("Alex Stone", "Aug. 3  2011", "33 TrackMan"),
                record("Alex Stone", "Aug. 3  2011", "44 TrackMan"),
            ],
            EmailPolicy.BIRTH_YEAR,
        )
        assert len(plan.accounts) == 2
        assert all(a.athlete.is_merged for a in plan.accounts)
        assert emails(plan) == {
            "11": "alex.stone.2015@approach.com",
            "33": "alex.stone.2011@approach.com",
        }

    def test_a_different_birth_date_is_a_different_person(self) -> None:
        """One day apart is still two athletes. The rule is exact or nothing."""
        plan, _ = plan_for(
            [
                record("Devin Ruiz", "Jul. 28  2006", "11 TrackMan"),
                record("Devin Ruiz", "Jul. 29  2006", "22 TrackMan"),
            ]
        )
        assert len(plan.accounts) == 2
        assert not any(a.athlete.is_merged for a in plan.accounts)

    def test_a_shared_birth_year_is_not_enough(self) -> None:
        plan, _ = plan_for(
            [
                record("Devin Ruiz", "May. 24  2009", "11 TrackMan"),
                record("Devin Ruiz", "Jul. 24  2009", "22 TrackMan"),
            ]
        )
        assert len(plan.accounts) == 2

    def test_rows_with_no_birth_date_are_never_merged(self) -> None:
        """The evidence the rule rests on is missing, so it does not apply."""
        plan, _ = plan_for(
            [
                record("Devin Ruiz", "-", "11 TrackMan"),
                record("Devin Ruiz", "-", "22 TrackMan"),
            ]
        )
        assert len(plan.accounts) == 2

    def test_a_different_name_is_a_different_person(self) -> None:
        plan, _ = plan_for(
            [
                record("Devin Ruiz", "Feb. 24  2015", "11 TrackMan"),
                record("Devin Ruis", "Feb. 24  2015", "22 TrackMan"),
            ]
        )
        assert len(plan.accounts) == 2

    def test_merging_can_be_turned_off(self) -> None:
        """One athlete per vendor row, as the export literally states it."""
        rows = [
            record("Riley Chen", "Feb. 24  2015", "11 TrackMan"),
            record("Riley Chen", "Feb. 24  2015", "22 TrackMan"),
        ]
        plan, _ = plan_for(rows, merge_duplicates=False)
        assert len(plan.accounts) == 2
        assert plan.blocked

    def test_merges_resting_on_a_repeated_date_are_flagged(self) -> None:
        """A date the export repeats is a bulk-upload default, not a birthday.

        The merge then rests on the name alone, which is weaker than the rule
        claims. It still merges -- that is the facility's call -- but it says so.
        """
        crowd = [
            record(f"Athlete Number{n}", "Jul. 29  2006", f"{n}00 TrackMan") for n in range(1, 8)
        ]
        twice = [
            record("Riley Chen", "Jul. 29  2006", "11 TrackMan"),
            record("Riley Chen", "Jul. 29  2006", "22 TrackMan"),
        ]
        plan, _ = plan_for(crowd + twice)
        merged = plan.merged
        assert len(merged) == 1
        assert merged[0].shared_birth_date is True

    def test_a_genuinely_rare_date_is_not_flagged(self) -> None:
        twice = [
            record("Riley Chen", "Feb. 24  2015", "11 TrackMan"),
            record("Riley Chen", "Feb. 24  2015", "22 TrackMan"),
        ]
        plan, _ = plan_for(twice)
        assert plan.merged[0].shared_birth_date is False


def test_repeated_birth_dates_finds_the_bulk_upload_defaults() -> None:
    rows, _ = parse_rows(
        [record(f"Athlete Number{n}", "Jul. 29  2006", f"{n} TrackMan") for n in range(6)]
        + [record("Jordan Avery", "Mar. 3  2012", "99 TrackMan")]
    )
    assert repeated_birth_dates(rows) == {date(2006, 7, 29)}


def test_grouping_preserves_the_order_of_the_file() -> None:
    """A coach reads the report next to the export, so they must agree."""
    rows, _ = parse_rows(
        [
            record("Jordan Avery", "Jan. 1  2010", "11 TrackMan"),
            record("Riley Chen", "Feb. 2  2011", "22 TrackMan"),
            record("Jordan Avery", "Jan. 1  2010", "33 TrackMan"),
            record("Sam Okafor", "Mar. 3  2012", "44 TrackMan"),
        ]
    )
    athletes = group_rows(rows)
    assert [a.name_key for a in athletes] == ["jordan.avery", "riley.chen", "sam.okafor"]


def test_the_decision_does_not_depend_on_file_order() -> None:
    """File order is not evidence of who an address belongs to.

    A one-pass implementation would hand the address to whichever row came
    first, which is exactly the arbitrary choice this module must not make.
    """
    rows = [
        record("Devin Ruiz", "Feb. 24  2015", "11 TrackMan"),
        record("Devin Ruiz", "Aug. 3  2015", "22 TrackMan"),
        record("Jordan Avery", "Jun. 1  2009", "33 TrackMan"),
    ]
    forwards, _ = plan_for(rows, EmailPolicy.BIRTH_YEAR)
    backwards, _ = plan_for(list(reversed(rows)), EmailPolicy.BIRTH_YEAR)
    assert emails(forwards) == emails(backwards)


def test_no_plan_ever_issues_one_address_twice() -> None:
    """The invariant the whole module exists to hold, asserted directly."""
    from bsa.domain.roster import RosterAccount, RosterAthlete, _assert_unique_emails

    rows, _ = parse_rows([record("Jordan Avery", player_id=f"{i} TrackMan") for i in (1, 2)])
    duplicated = [
        RosterAccount(athlete=RosterAthlete(rows=(row,)), email="jordan.avery@approach.com")
        for row in rows
    ]
    with pytest.raises(RosterError, match="duplicate login email"):
        _assert_unique_emails(duplicated)


def test_an_empty_export_plans_nothing() -> None:
    plan, skipped = plan_for([])
    assert plan.accounts == () and skipped == []
