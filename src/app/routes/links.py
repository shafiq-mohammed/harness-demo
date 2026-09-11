"""Endpoints under /links."""

import json

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.auth import require_api_key
from app.codes import generate_code
from app.errors import ApiError
from app.models import Link
from app.repository import CodeAlreadyExistsError
from app.schemas import CreateLinkRequest, LinkOut, LinkPage

router = APIRouter()

MAX_CODE_ATTEMPTS = 5

DEFAULT_PAGE_LIMIT = 20
MIN_PAGE_LIMIT = 1
MAX_PAGE_LIMIT = 100

NOT_FOUND_MESSAGE = "No link exists for that code."


def _to_link_out(link: Link) -> LinkOut:
    """Render a stored link as the public representation."""
    return LinkOut(
        code=link.code,
        url=link.url,
        created_at=link.created_at,
        expires_at=link.expires_at,
        hit_count=link.hit_count,
    )


async def _parse_create_request(request: Request) -> CreateLinkRequest:
    """Validate the request body once the caller is authenticated.

    The body is read by hand so that authentication is resolved first and an unauthenticated
    caller learns nothing about the validity of the body. Every parsing or validation failure
    becomes a RequestValidationError, which the error handlers render as 422 validation_error.
    """
    raw = await request.body()
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise RequestValidationError(
            [{"type": "json_invalid", "loc": ("body",), "msg": f"Invalid JSON: {exc}"}]
        ) from exc

    try:
        return CreateLinkRequest.model_validate(payload)
    except ValidationError as exc:
        raise RequestValidationError(
            [{**error, "loc": ("body", *error.get("loc", ()))} for error in exc.errors()]
        ) from exc


@router.post("/links", status_code=status.HTTP_201_CREATED, response_model=LinkOut)
async def create_link(request: Request, _: str = Depends(require_api_key)) -> LinkOut:
    """Store a new link for the given URL and return it with its generated code."""
    payload = await _parse_create_request(request)

    repo = request.app.state.repo
    created_at = request.app.state.clock.now()

    for _attempt in range(MAX_CODE_ATTEMPTS):
        link = Link(code=generate_code(), url=payload.url, created_at=created_at)
        try:
            repo.add(link)
        except CodeAlreadyExistsError:
            continue
        return LinkOut(
            code=link.code,
            url=link.url,
            created_at=link.created_at,
            expires_at=link.expires_at,
            hit_count=link.hit_count,
        )

    raise RuntimeError("could not generate an unused short code")


@router.get("/links", response_model=LinkPage)
async def list_links(
    request: Request,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=MIN_PAGE_LIMIT, le=MAX_PAGE_LIMIT),
    cursor: str | None = Query(None),
    _: str = Depends(require_api_key),
) -> LinkPage:
    """Return one keyset page of links ordered by code ascending.

    One extra link is fetched to learn whether anything remains after this page; if so the page
    is truncated and the last code becomes the cursor for the next request. An unknown cursor is
    not an error, it simply starts after that value.
    """
    links = request.app.state.repo.list(limit=limit + 1, after_code=cursor)

    next_cursor: str | None = None
    if len(links) > limit:
        links = links[:limit]
        next_cursor = links[-1].code

    return LinkPage(items=[_to_link_out(link) for link in links], next_cursor=next_cursor)


@router.get("/links/{code}", response_model=LinkOut)
async def get_link(code: str, request: Request, _: str = Depends(require_api_key)) -> LinkOut:
    """Return the stored link, including its live hit count."""
    link = request.app.state.repo.get(code)
    if link is None:
        raise ApiError(404, "not_found", NOT_FOUND_MESSAGE)
    return _to_link_out(link)
