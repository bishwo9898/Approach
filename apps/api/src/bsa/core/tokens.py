"""Generating and storing the two random credentials this system issues.

Both come from `secrets`, never `random`: `random` is a Mersenne Twister whose
internal state can be recovered from its own output, which would make every
subsequent token predictable.
"""

from __future__ import annotations

import hashlib
import secrets

#: 32 bytes = 256 bits. Far beyond guessable, and still a short header value.
_SESSION_TOKEN_BYTES = 32

#: Deliberately excludes 0/O, 1/I/L and 5/S. An activation code is read off a
#: screen or a printout and typed by a twelve-year-old; a character pair that
#: looks identical in a sans-serif font turns into a support request.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRTUVWXYZ2346789"
_CODE_LENGTH = 8


def new_session_token() -> str:
    """An opaque bearer token. The only copy is the one handed to the client."""
    return secrets.token_urlsafe(_SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """The value stored in `user_sessions.token_hash`.

    SHA-256 with no salt and no stretching, which is correct *here* and would be
    wrong for a password: the input is 256 bits of uniform randomness, so there
    is no dictionary and no plausible precomputation to defend against. The
    property we need is only that the stored value cannot be used to sign in.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_activation_code() -> str:
    """A one-time code a coach reads out, e.g. "K7MP-R3WX".

    8 characters from a 29-symbol alphabet is about 39 bits -- not a password,
    but it does not need to be. It is single-use, it only ever guards an
    account that holds no data yet, and the account locks after a handful of
    wrong attempts, which is what actually bounds an online guess.
    """
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_activation_code(value: str) -> str:
    """Accept what a person types: spaces, lower case, missing dash.

    Normalizing on both sides means "k7mpr3wx" and "K7MP-R3WX" are the same
    code, so a correct code is never rejected over punctuation.
    """
    stripped = "".join(c for c in value.upper() if c.isalnum())
    return f"{stripped[:4]}-{stripped[4:]}" if len(stripped) == _CODE_LENGTH else stripped
