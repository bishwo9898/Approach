"""Shared-passcode authentication.

One passcode per role. This is a **demo gate**, not identity: everyone holding
a passcode is the same user, there is no per-person account, and nothing can be
attributed to an individual. It exists so a deployed link is not wide open
while the real identity provider (Clerk) is still unconfigured.

What it does get right:

* Passcodes are compared in constant time, so the endpoint cannot be used to
  recover one character at a time.
* Production refuses to start unless the passcodes are set explicitly, so a
  deployment can never inherit the development defaults.
"""

from __future__ import annotations

import secrets

from bsa.core.errors import AuthenticationError, IntegrationNotConfiguredError
from bsa.integrations.auth.base import VerifiedSubject


class PasscodeAuthProvider:
    name = "passcode"

    def __init__(self, by_role: dict[str, str]) -> None:
        """`by_role` maps a role subject ("coach", "player") to its passcode."""
        usable = {role: code for role, code in by_role.items() if code}
        if not usable:
            raise IntegrationNotConfiguredError(
                "No passcodes are configured. Set BSA_COACH_PASSCODE and BSA_PLAYER_PASSCODE."
            )
        self._by_role = usable

    def verify(self, credential: str) -> VerifiedSubject:
        candidate = credential.strip()

        # Every passcode is checked even after a match, so the time taken does
        # not reveal which role matched or how many are configured.
        matched: str | None = None
        for role, passcode in self._by_role.items():
            if secrets.compare_digest(candidate, passcode):
                matched = role

        if matched is None:
            raise AuthenticationError("that passcode is not recognized")
        return VerifiedSubject(provider=self.name, subject=matched)
