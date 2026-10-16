"""A small per-client rate limit for unauthenticated endpoints.

The account lockout in `services.accounts` bounds guessing against *one*
account. It does nothing against a caller who tries one attempt on each of five
hundred addresses, which is what enumerating the roster would look like. This
bounds that.

Honest about what it is: an in-process counter. Two instances means two budgets,
and a restart clears it. That is a real limitation and the right trade at this
size -- the alternative is Redis, which is another service to run and pay for to
protect a class list the athletes already have. If this ever runs on more than
one instance, the counter belongs in the database or in Redis instead.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from bsa.core.errors import BsaError


class RateLimitedError(BsaError):
    status_code = 429
    code = "rate_limited"


class SlidingWindowLimiter:
    """At most `limit` events per `window_seconds`, per key."""

    def __init__(self, *, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        """Record one event, or raise if the key is over budget."""
        now = time.monotonic()
        hits = self._hits[key]
        cutoff = now - self._window

        while hits and hits[0] < cutoff:
            hits.popleft()

        if len(hits) >= self._limit:
            retry_in = max(1, int(hits[0] + self._window - now) + 1)
            raise RateLimitedError(
                f"Too many attempts. Try again in {retry_in} second{'s' if retry_in != 1 else ''}.",
                details={"retry_after_seconds": retry_in},
            )

        hits.append(now)
        # Keys with nothing left in the window are dropped, so a long-running
        # process does not accumulate one entry per address ever tried.
        if not hits:  # pragma: no cover -- unreachable, we just appended
            del self._hits[key]
        self._forget_idle(cutoff)

    def _forget_idle(self, cutoff: float) -> None:
        if len(self._hits) < 512:
            return
        for key in [k for k, v in self._hits.items() if not v or v[-1] < cutoff]:
            del self._hits[key]

    def reset(self) -> None:
        """For tests. Never called in a request path."""
        self._hits.clear()
