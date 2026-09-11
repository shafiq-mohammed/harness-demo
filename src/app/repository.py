"""Storage interface for links and the in-memory implementation."""

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
