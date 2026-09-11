"""Request and response bodies for the links API."""

from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

MAX_URL_LENGTH = 2048
ALLOWED_SCHEMES = ("http", "https")
URL_ERROR_MESSAGE = "url must be an absolute http or https URL"


class CreateLinkRequest(BaseModel):
    """Body of POST /links."""

    url: str = Field(max_length=MAX_URL_LENGTH)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        """Accept only absolute http(s) URLs with a non-empty host."""
        try:
            parts = urlsplit(value)
        except ValueError as exc:
            raise ValueError(URL_ERROR_MESSAGE) from exc
        if parts.scheme not in ALLOWED_SCHEMES or not parts.netloc:
            raise ValueError(URL_ERROR_MESSAGE)
        try:
            host = parts.hostname
        except ValueError as exc:
            raise ValueError(URL_ERROR_MESSAGE) from exc
        if not host:
            raise ValueError(URL_ERROR_MESSAGE)
        return value


class LinkOut(BaseModel):
    """Representation of a link returned by the API."""

    code: str
    url: str
    created_at: datetime
    expires_at: datetime | None
    hit_count: int
