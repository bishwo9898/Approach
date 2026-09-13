"""Authentication adapter contract.

We do not implement password storage, hashing or session management. That is
delegated to a proven provider (Clerk is the intended first one). What stays
ours is *authorization*: which organization a user belongs to, what role they
hold, and which athlete they may read. Those live in our database, because they
are business rules, not identity.

An adapter's only job is to turn a credential into a verified subject id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class VerifiedSubject:
    """The identity an auth provider vouches for.

    Deliberately thin: no role, no organization, no player. Anything an external
    provider asserts about permissions is ignored -- those are read from our own
    `users` table, so a compromised or misconfigured provider cannot grant
    itself access to an athlete's data.
    """

    provider: str
    subject: str
    email: str | None = None


@runtime_checkable
class AuthProvider(Protocol):
    name: str

    def verify(self, credential: str) -> VerifiedSubject:
        """Validate a bearer credential. Raises AuthenticationError if invalid."""
        ...
