"""The password policy and the hashing around it.

The policy is the only thing standing between "set a password" and a password
of "password123", so each rule is pinned individually -- a rule that silently
stops firing is indistinguishable from no rule at all.
"""

from __future__ import annotations

import time

import pytest

from bsa.core.password import (
    MAX_LENGTH,
    MIN_LENGTH,
    dummy_verify,
    hash_password,
    needs_rehash,
    password_problems,
    policy_summary,
    verify_password,
)

GOOD = "RisingFastball26"


def test_a_reasonable_password_is_accepted() -> None:
    assert password_problems(GOOD) == []


@pytest.mark.parametrize(
    ("password", "fragment"),
    [
        ("Short1", "at least 10"),
        ("nodigitsatall", "one number"),
        ("12345678901", "one letter"),
        ("baseball123", "too common"),
        ("aaaaaaaaaa1", "variety"),
        (" Leading12345", "space at the start or end"),
        ("Trailing12345 ", "space at the start or end"),
    ],
)
def test_weak_passwords_are_rejected(password: str, fragment: str) -> None:
    problems = password_problems(password)
    assert problems, f"{password!r} should have been rejected"
    assert any(fragment in p for p in problems)


def test_every_problem_is_reported_at_once() -> None:
    """A person should not discover the rules one submit at a time."""
    problems = password_problems("abc")
    assert len(problems) >= 2


def test_an_over_long_password_is_rejected() -> None:
    """Unbounded input is unbounded hashing work for an unauthenticated caller."""
    assert any("at most" in p for p in password_problems("Aa1" + "x" * MAX_LENGTH))


def test_minimum_length_is_exactly_enforced() -> None:
    assert password_problems("Abcdefg12") != []  # 9
    assert password_problems("Abcdefg123") == []  # 10
    assert MIN_LENGTH == 10


class TestPersonalTerms:
    """A password must not simply restate the identity it protects."""

    def test_rejects_the_athletes_own_name(self) -> None:
        problems = password_problems("JordanAvery2026", personal=("Jordan", "Avery"))
        assert any("your name or email" in p for p in problems)

    def test_rejects_the_email_local_part(self) -> None:
        problems = password_problems("jordan.avery99", personal=("jordan.avery",))
        assert any("your name or email" in p for p in problems)

    def test_is_case_and_accent_insensitive(self) -> None:
        assert password_problems("jOsé.swing12", personal=("Jose",)) != []

    def test_ignores_short_terms(self) -> None:
        """A three-letter name would otherwise ban most English words."""
        assert password_problems("Tigerswing12", personal=("Ty",)) == []

    def test_allows_a_password_that_merely_shares_letters(self) -> None:
        assert password_problems("RisingFastball26", personal=("Jordan", "Avery")) == []


class TestHashing:
    def test_round_trips(self) -> None:
        encoded = hash_password(GOOD)
        assert verify_password(encoded, GOOD)
        assert not verify_password(encoded, GOOD + "x")

    def test_the_hash_does_not_contain_the_password(self) -> None:
        assert GOOD not in hash_password(GOOD)

    def test_is_salted(self) -> None:
        """Two accounts with one password must not share a hash."""
        assert hash_password(GOOD) != hash_password(GOOD)

    def test_is_argon2id(self) -> None:
        assert hash_password(GOOD).startswith("$argon2id$")

    def test_a_corrupt_stored_hash_is_a_failed_login_not_a_crash(self) -> None:
        assert not verify_password("not a hash at all", GOOD)
        assert not needs_rehash("not a hash at all")

    def test_current_parameters_need_no_rehash(self) -> None:
        assert not needs_rehash(hash_password(GOOD))

    def test_a_weaker_hash_is_flagged_for_rehash(self) -> None:
        from argon2 import PasswordHasher

        weak = PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1).hash(GOOD)
        assert needs_rehash(weak)

    def test_dummy_verify_costs_about_the_same_as_a_real_one(self) -> None:
        """Otherwise sign-in timing reveals which addresses have accounts."""
        encoded = hash_password(GOOD)
        verify_password(encoded, GOOD)  # warm up

        start = time.perf_counter()
        verify_password(encoded, "the wrong password")
        real = time.perf_counter() - start

        start = time.perf_counter()
        dummy_verify()
        dummy = time.perf_counter() - start

        # Generous bound: this runs on shared CI hardware, and the property
        # being protected is "same order of magnitude", not a tight constant.
        assert 0.2 < dummy / real < 5.0, f"real={real:.4f}s dummy={dummy:.4f}s"


def test_policy_summary_is_shown_to_people() -> None:
    summary = policy_summary()
    assert summary and all(isinstance(line, str) and line for line in summary)
    assert any(str(MIN_LENGTH) in line for line in summary)
