"""Static-token auth for local development and tests.

Tokens are seeded, unencrypted and printed to the console by the seed script.
They are not secrets and must never reach a deployed environment, which
`Settings._guard_production` enforces by refusing to boot.
"""

from __future__ import annotations

from bsa.core.errors import AuthenticationError
from bsa.integrations.auth.base import VerifiedSubject


class DevAuthProvider:
    """Treats the token itself as the subject id.

    The seed script creates users whose `auth_subject` is a readable string like
    "dev|coach", so a developer can switch roles by changing one header.
    """

    name = "dev"
    PREFIX = "dev|"

    def verify(self, credential: str) -> VerifiedSubject:
        token = credential.strip()
        if not token.startswith(self.PREFIX) or len(token) <= len(self.PREFIX):
            raise AuthenticationError("invalid development token")
        return VerifiedSubject(provider=self.name, subject=token)
