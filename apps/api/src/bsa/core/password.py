"""Password hashing and the password policy.

Two separate concerns live here, both pure and both unit-tested:

* **Hashing** is delegated to argon2-cffi (Argon2id), the algorithm OWASP
  recommends first. We do not invent a scheme, and we do not use a fast hash:
  a leaked `user_credentials` table must not be bulk-crackable.
* **The policy** is a pure function returning *every* reason a password was
  rejected, so the UI can list them all at once instead of making someone
  discover them one submit at a time.

The frontend mirrors this policy for live feedback (`apps/web/src/lib/password.ts`),
but that copy is a convenience. This module is the only thing that decides.
"""

from __future__ import annotations

import contextlib
import re
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

#: Argon2id at OWASP's recommended minimum: 19 MiB, 2 iterations, 1 lane.
#:
#: Deliberately not the library defaults (64 MiB, 4 lanes). The API runs on a
#: small shared instance, and 4 lanes against a fraction of a CPU makes every
#: login slow enough that the lockout below would be reached by honest typos.
#: 19 MiB/t=2 is still far out of reach of GPU cracking.
_HASHER = PasswordHasher(
    time_cost=2, memory_cost=19 * 1024, parallelism=1, hash_len=32, salt_len=16
)

MIN_LENGTH = 10
#: Argon2 itself is happy with long input, but an unbounded password is an
#: unbounded amount of hashing work for an unauthenticated caller.
MAX_LENGTH = 128

#: Not a serious dictionary -- a serious one is a 100MB file and a service.
#: These are the shapes a teenager actually picks when told "letters and a
#: number", which is exactly the gap the length rule alone does not close.
_OBVIOUS = frozenset(
    {
        "password1",
        "password12",
        "password123",
        "password1234",
        "passw0rd123",
        "qwerty12345",
        "qwertyuiop1",
        "1234567890",
        "12345678901",
        "letmein123",
        "iloveyou123",
        "baseball1",
        "baseball12",
        "baseball123",
        "baseball2026",
        "approach123",
        "trackman123",
        "changeme123",
        "welcome1234",
        "abc123456789",
    }
)


def _normalize(value: str) -> str:
    """Casefold and strip accents for comparison purposes only.

    Used when checking whether a password merely restates the person's name --
    "Jósé2026" should be caught just as "jose2026" is. Never applied to the
    password that gets hashed.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def policy_summary() -> list[str]:
    """The rules, phrased for a person. Shown next to the password field."""
    return [
        f"At least {MIN_LENGTH} characters",
        "At least one letter and one number",
        "Not your name or email",
    ]


def password_problems(password: str, *, personal: tuple[str, ...] = ()) -> list[str]:
    """Every reason this password is unacceptable. Empty list means it is fine.

    `personal` carries strings the password must not restate -- the email local
    part and the athlete's names. A password that is just the athlete's own name
    is the single most likely weak choice here, and it is also the one an
    attacker who already guessed the email would try first.
    """
    problems: list[str] = []

    if len(password) < MIN_LENGTH:
        problems.append(f"Use at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        problems.append(f"Use at most {MAX_LENGTH} characters.")

    if not re.search(r"[A-Za-z]", password):
        problems.append("Include at least one letter.")
    if not re.search(r"\d", password):
        problems.append("Include at least one number.")

    # Whitespace is allowed inside a passphrase but not at the edges, where it
    # is invisible and survives a copy-paste that the next login will not repeat.
    if password != password.strip():
        problems.append("Remove the space at the start or end.")

    normalized = _normalize(password)
    if normalized in _OBVIOUS or _normalize(password.replace(" ", "")) in _OBVIOUS:
        problems.append("That password is too common. Pick something else.")

    # A single repeated character, or a straight run off the keyboard, passes
    # every rule above while being trivially guessable.
    if len(set(password)) < 5:
        problems.append("Use a greater variety of characters.")

    letters_only = re.sub(r"[^a-z]", "", normalized)
    for item in personal:
        candidate = re.sub(r"[^a-z]", "", _normalize(item))
        if len(candidate) >= 4 and candidate in letters_only:
            problems.append("Don't use your name or email in your password.")
            break

    return problems


def hash_password(password: str) -> str:
    """An encoded Argon2id hash, salt and parameters included.

    Self-describing by design: a future parameter change does not invalidate
    existing hashes, because each hash still carries the parameters it was made
    with. `needs_rehash` below is how those get upgraded.
    """
    return _HASHER.hash(password)


def verify_password(encoded: str, password: str) -> bool:
    """Whether `password` produced `encoded`. Never raises on a bad input."""
    try:
        return _HASHER.verify(encoded, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(encoded: str) -> bool:
    """True when this hash was made with weaker parameters than we now use.

    Called after a *successful* verification, which is the only moment the
    plaintext is available to re-hash with.
    """
    try:
        return _HASHER.check_needs_rehash(encoded)
    except InvalidHashError:  # pragma: no cover -- a corrupt stored hash
        return False


def dummy_verify() -> None:
    """Spend the same time as a real verification, and learn nothing.

    Called when a login names an email that has no account, so the response
    time does not reveal which emails exist. Without this, the enumeration the
    activation step deliberately allows would extend to the login endpoint,
    where it is not wanted.
    """
    with contextlib.suppress(VerifyMismatchError, VerificationError, InvalidHashError):
        _HASHER.verify(_DUMMY_HASH, "not the password")


_DUMMY_HASH = _HASHER.hash("timing equalizer, never a real credential")
