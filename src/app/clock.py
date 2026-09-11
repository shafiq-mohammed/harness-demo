"""Injectable clocks so tests can control time deterministically."""

from datetime import UTC, datetime, timedelta
from typing import Protocol


def _require_aware(value: datetime) -> datetime:
    """Return value unchanged, raising ValueError if it is naive."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class Clock(Protocol):
    """Source of the current time. Always returns tz-aware UTC datetimes."""

    def now(self) -> datetime: ...


class SystemClock:
    """Clock backed by the real wall clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Clock that only moves when a test moves it."""

    def __init__(self, now: datetime) -> None:
        self._now = _require_aware(now)

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = _require_aware(now)

    def advance(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)
