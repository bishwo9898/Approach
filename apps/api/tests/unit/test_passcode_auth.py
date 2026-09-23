"""The shared-passcode gate.

A demo control rather than identity: everyone holding a passcode is the same
user. These tests cover the two things it must still get right.
"""

from __future__ import annotations

import pytest

from bsa.core.errors import AuthenticationError, IntegrationNotConfiguredError
from bsa.integrations.auth.passcode import PasscodeAuthProvider


def provider() -> PasscodeAuthProvider:
    return PasscodeAuthProvider({"coach": "coach-code", "player": "player-code"})


def test_a_passcode_resolves_to_its_role() -> None:
    assert provider().verify("coach-code").subject == "coach"
    assert provider().verify("player-code").subject == "player"


def test_surrounding_whitespace_is_tolerated() -> None:
    """People paste passcodes, and a trailing space is not a wrong passcode."""
    assert provider().verify("  coach-code \n").subject == "coach"


def test_a_wrong_passcode_is_refused_without_saying_why() -> None:
    with pytest.raises(AuthenticationError) as caught:
        provider().verify("not-it")

    # The message names neither the roles nor how many passcodes exist.
    message = str(caught.value)
    assert "coach" not in message
    assert "player" not in message


def test_an_empty_passcode_is_refused() -> None:
    for attempt in ("", "   "):
        with pytest.raises(AuthenticationError):
            provider().verify(attempt)


def test_a_partial_match_is_refused() -> None:
    """Guards against a prefix comparison creeping in."""
    for attempt in ("coach", "coach-cod", "coach-codes"):
        with pytest.raises(AuthenticationError):
            provider().verify(attempt)


def test_no_configured_passcodes_is_a_configuration_error() -> None:
    """Refuse to start rather than silently accept nothing."""
    with pytest.raises(IntegrationNotConfiguredError):
        PasscodeAuthProvider({"coach": "", "player": ""})


def test_a_partially_configured_gate_still_works() -> None:
    """One role configured is a valid deployment; the other simply cannot sign in."""
    only_coach = PasscodeAuthProvider({"coach": "coach-code", "player": ""})

    assert only_coach.verify("coach-code").subject == "coach"
    with pytest.raises(AuthenticationError):
        only_coach.verify("")
