"""The catch-all redirect endpoint, GET /{code}."""

from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse

from app.errors import ApiError

router = APIRouter()

NOT_FOUND_MESSAGE = "No link exists for that code."


@router.get("/{code}")
async def follow_link(code: str, request: Request) -> RedirectResponse:
    """Redirect an anonymous caller to the stored URL and count the hit.

    RedirectResponse defaults to 307, so 302 Found is passed explicitly (see SPEC A7).
    An unknown code is a 404 in the error envelope and is not counted.
    """
    repo = request.app.state.repo
    link = repo.get(code)
    if link is None:
        raise ApiError(404, "not_found", NOT_FOUND_MESSAGE)

    response = RedirectResponse(url=link.url, status_code=status.HTTP_302_FOUND)
    repo.increment_hits(code)
    return response
