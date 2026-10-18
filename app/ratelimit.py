"""In-memory sliding-window rate limiter.

Deliberately simple: one dict of timestamp queues, one process.  No Redis,
no Celery -- the project rules say keep it simple.  It only has to stop a
runaway loop or a scraper from eating every worker and hammering the public
Overpass API we borrow for free.

Known limitation: with more than one worker process each keeps its own
window, so the effective limit becomes limit x workers.  Fine for now;
revisit when moving behind a real proxy.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Callable

from dotenv import load_dotenv

# Lets RATE_LIMIT_PER_MINUTE be set in .env as well as in the shell. It is a
# plain setting, not a secret; load_dotenv never overrides a real env var.
load_dotenv()

# How many /recommend calls one client may make per minute.  Not a secret,
# so an env override is a convenience, not a security measure.
DEFAULT_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
DEFAULT_WINDOW_S = 60.0


class RateLimiter:
    """Sliding-window limiter keyed by client. `clock` is injectable so
    tests can move time instead of sleeping."""

    def __init__(self, limit: int = DEFAULT_LIMIT, window_s: float = DEFAULT_WINDOW_S,
                 clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, float]:
        """Record a hit for `key` and report whether it is allowed.

        Returns (allowed, retry_after_seconds).  When allowed,
        retry_after is 0.0; when blocked it is the number of seconds until
        the oldest recorded hit slides out of the window.
        """
        now = self._clock()
        hits = self._hits[key]
        cutoff = now - self.window_s
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            return False, max(0.0, hits[0] + self.window_s - now)
        hits.append(now)
        return True, 0.0
