"""Domain model for a short link."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Link:
    """A short code pointing at a URL, with optional expiry and a hit counter."""

    code: str
    url: str
    created_at: datetime
    expires_at: datetime | None = None
    hit_count: int = 0

    def is_expired(self, now: datetime) -> bool:
        """True when an expiry is set and it is at or before `now`."""
        return self.expires_at is not None and self.expires_at <= now
