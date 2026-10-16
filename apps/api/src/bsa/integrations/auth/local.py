"""Session-token auth for accounts this facility provisions itself.

The adapter contract in `base.py` says we delegate password storage to a proven
provider. That is still the intent, and `clerk.py` is still the destination.
This provider is the honest interim: the athletes are minors added from a
TrackMan roster export, there is no identity provider configured, and a demo
link protected by one shared passcode cannot tell two athletes apart -- which
is unacceptable the moment real sessions are in the database.

It stays within the spirit of the contract by doing one thing: turning a bearer
token into a verified subject. It decides nothing about roles, organizations or
which athlete may be read; `bsa.api.deps` reads all of that from our own tables,
exactly as it does for every other provider.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from bsa.core.errors import AuthenticationError
from bsa.integrations.auth.base import VerifiedSubject
from bsa.services import accounts


class LocalAuthProvider:
    """Validates an opaque session token against the `user_sessions` table.

    Holds the request's database session, so it is constructed per request
    rather than cached -- it is not a client to anything, just a lookup.
    """

    name = "local"

    def __init__(self, db: Session) -> None:
        self._db = db

    def verify(self, credential: str) -> VerifiedSubject:
        user_id = accounts.user_id_for_token(self._db, credential.strip())
        if user_id is None:
            raise AuthenticationError("your session has expired, please sign in again")
        # The subject is the user's own id, so a later change of email address
        # cannot orphan a live session.
        return VerifiedSubject(provider=self.name, subject=str(user_id))
