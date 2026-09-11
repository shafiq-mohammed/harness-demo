"""API key authentication dependency."""

import secrets

from fastapi import Header, Request

from app.errors import ApiError

API_KEY_HEADER = "X-API-Key"

UNAUTHORIZED_MESSAGE = "A valid X-API-Key header is required."


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> str:
    """Return the caller's API key, or raise 401 unauthorized.

    The header must be present and match one of request.app.state.settings.api_keys. With no keys
    configured every request is rejected, which is the safe default.
    """
    if x_api_key is None:
        raise ApiError(401, "unauthorized", UNAUTHORIZED_MESSAGE)

    candidate = x_api_key.encode("utf-8")
    for key in request.app.state.settings.api_keys:
        if secrets.compare_digest(candidate, key.encode("utf-8")):
            return x_api_key

    raise ApiError(401, "unauthorized", UNAUTHORIZED_MESSAGE)
