"""Storage interface for links and the in-memory implementation."""

from __future__ import annotations

from typing import Protocol

from app.models import Link


class CodeAlreadyExistsError(Exception):
    """Raised when adding a link whose code is already stored."""


class LinkNotFoundError(Exception):
    """Raised when an operation targets a code that is not stored."""


class LinkRepository(Protocol):
    """The storage operations routes are allowed to rely on."""

    def add(self, link: Link) -> None:
        """Insert. Raises CodeAlreadyExistsError if link.code exists."""

    def get(self, code: str) -> Link | None:
        """Return the link with that code, or None."""

    def increment_hits(self, code: str) -> None:
        """Atomically add 1 to hit_count. Raises LinkNotFoundError if unknown."""

    def list(self, *, limit: int, after_code: str | None = None) -> list[Link]:
        """Up to `limit` links with code > after_code (or from the start), by code ascending."""


class InMemoryLinkRepository:
    """Dict-backed implementation of LinkRepository.

    Not thread-safe; fine for a single uvicorn worker and for tests.
    """

    def __init__(self) -> None:
        self._links: dict[str, Link] = {}

    def add(self, link: Link) -> None:
        """Insert. Raises CodeAlreadyExistsError if link.code exists."""
        if link.code in self._links:
            raise CodeAlreadyExistsError(link.code)
        self._links[link.code] = link

    def get(self, code: str) -> Link | None:
        """Return the link with that code, or None."""
        return self._links.get(code)

    def increment_hits(self, code: str) -> None:
        """Add 1 to the stored link's hit_count. Raises LinkNotFoundError if unknown."""
        link = self._links.get(code)
        if link is None:
            raise LinkNotFoundError(code)
        link.hit_count += 1

    def list(self, *, limit: int, after_code: str | None = None) -> list[Link]:
        """Return up to `limit` links after `after_code`, ordered by code ascending.

        Keyset paging: codes are compared as plain strings, so an unknown cursor simply starts
        after wherever that value would sort. The module uses postponed annotations
        (`from __future__ import annotations`), so this method's name does not shadow the
        builtin `list` inside annotations.
        """
        codes = sorted(self._links)
        if after_code is not None:
            codes = [code for code in codes if code > after_code]
        return [self._links[code] for code in codes[:limit]]
