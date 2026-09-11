"""The JSON error envelope and the handlers that produce it."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

STATUS_ERROR_CODES: dict[int, str] = {
    401: "unauthorized",
    404: "not_found",
    405: "method_not_allowed",
    410: "link_expired",
    422: "validation_error",
}
DEFAULT_ERROR_CODE = "error"

STATUS_MESSAGES: dict[int, str] = {
    401: "A valid X-API-Key header is required.",
    404: "The requested resource was not found.",
    405: "The request method is not allowed for this resource.",
    410: "This link has expired.",
    422: "The request was not valid.",
}
DEFAULT_ERROR_MESSAGE = "The request could not be processed."


class ApiError(Exception):
    """A client-caused error that is rendered as the JSON error envelope."""

    def __init__(self, status_code: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message


def error_response(status_code: int, error: str, message: str, **extra: object) -> JSONResponse:
    """Build the envelope response for a single error."""
    content: dict[str, object] = {"error": error, "message": message}
    content.update(extra)
    return JSONResponse(status_code=status_code, content=content)


def register_error_handlers(app: FastAPI) -> None:
    """Register handlers turning every client-caused error into the envelope."""

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.error, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        error = STATUS_ERROR_CODES.get(exc.status_code, DEFAULT_ERROR_CODE)
        message = exc.detail if isinstance(exc.detail, str) and exc.detail else None
        if message is None:
            message = STATUS_MESSAGES.get(exc.status_code, DEFAULT_ERROR_MESSAGE)
        return error_response(exc.status_code, error, message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {"loc": list(error.get("loc", ())), "msg": error.get("msg", "")}
            for error in exc.errors()
        ]
        return error_response(
            422,
            "validation_error",
            STATUS_MESSAGES[422],
            details=details,
        )
