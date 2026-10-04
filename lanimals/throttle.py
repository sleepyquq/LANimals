"""In-memory login failure throttling keyed by client address."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Failures:
    count: int
    last_failure: float
    locked_until: float


class LoginThrottle:
    """Allow a few wrong passwords, then lock the address with doubling waits.

    State lives in this process only, matching the single-worker deployment.
    """

    FREE_ATTEMPTS = 5
    BASE_LOCKOUT_SECONDS = 30
    MAX_LOCKOUT_SECONDS = 15 * 60
    FORGET_AFTER_SECONDS = 60 * 60

    def __init__(self, *, clock: Callable[[], float] = time.time, max_tracked: int = 4096) -> None:
        self._clock = clock
        self._max_tracked = max_tracked
        self._entries: dict[str, _Failures] = {}

    def retry_after(self, address: str) -> int:
        entry = self._current(address)
        if entry is None:
            return 0
        remaining = entry.locked_until - self._clock()
        return max(0, int(-(-remaining // 1)))

    def record_failure(self, address: str) -> None:
        now = self._clock()
        entry = self._current(address)
        if entry is None:
            self._make_room()
            entry = self._entries[address] = _Failures(count=0, last_failure=now, locked_until=0.0)
        entry.count += 1
        entry.last_failure = now
        if entry.count >= self.FREE_ATTEMPTS:
            doublings = entry.count - self.FREE_ATTEMPTS
            lockout = self.BASE_LOCKOUT_SECONDS * 2 ** min(doublings, 16)
            entry.locked_until = now + min(lockout, self.MAX_LOCKOUT_SECONDS)

    def record_success(self, address: str) -> None:
        self._entries.pop(address, None)

    def _current(self, address: str) -> _Failures | None:
        entry = self._entries.get(address)
        if entry is None:
            return None
        now = self._clock()
        if now >= entry.locked_until and now - entry.last_failure > self.FORGET_AFTER_SECONDS:
            del self._entries[address]
            return None
        return entry

    def _make_room(self) -> None:
        if len(self._entries) < self._max_tracked:
            return
        now = self._clock()
        for address in [
            key
            for key, entry in self._entries.items()
            if now >= entry.locked_until and now - entry.last_failure > self.FORGET_AFTER_SECONDS
        ]:
            del self._entries[address]
        while len(self._entries) >= self._max_tracked:
            oldest = min(self._entries, key=lambda key: self._entries[key].last_failure)
            del self._entries[oldest]
