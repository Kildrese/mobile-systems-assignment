"""One error shape for every failure: `{"error": {"code", "message", "details"?}}`."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas import Error, ErrorBody, ErrorCode, ValidationIssue

logger = logging.getLogger("app")


class ApiError(Exception):
    def __init__(self, status: int, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


# Every error a route raises, so the same case always gets the same message.
# NOT_FOUND is shared by "not yours / doesn't exist / not a UUID".
NOT_FOUND = ApiError(404, ErrorCode.NOT_FOUND, "Not found")
UNAUTHORIZED = ApiError(401, ErrorCode.UNAUTHORIZED, "Authentication required")
# Same body for an unknown email or username and a wrong password.
INVALID_CREDENTIALS = ApiError(
    401, ErrorCode.INVALID_CREDENTIALS, "Invalid email, username or password"
)
# 403, not 401: clients treat 401 as "token dead, sign out", and a typo in
# the current password shouldn't sign the user out.
INVALID_PASSWORD = ApiError(403, ErrorCode.INVALID_PASSWORD, "Current password is incorrect")
EMAIL_TAKEN = ApiError(409, ErrorCode.EMAIL_TAKEN, "Email is already registered")
USERNAME_TAKEN = ApiError(409, ErrorCode.USERNAME_TAKEN, "Username is already taken")


def error_response(
    status: int,
    code: ErrorCode,
    message: str,
    details: list[ValidationIssue] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = Error(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(
        body.model_dump(mode="json", by_alias=True, exclude_none=True),
        status_code=status,
        headers=headers,
    )


def internal_error() -> JSONResponse:
    return error_response(500, ErrorCode.INTERNAL, "Internal server error")


async def _api_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return error_response(exc.status, exc.code, exc.message)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # Only the location, type and message; never Pydantic's `input`, which
    # would echo passwords back.
    details = []
    for issue in exc.errors():
        loc = list(issue.get("loc", ()))
        if loc and loc[0] in ("body", "path", "query"):
            loc = loc[1:]
        details.append(ValidationIssue(path=loc, code=issue["type"], message=issue["msg"]))
    json_invalid = any(d.code == "json_invalid" for d in details)
    message = (
        "Request body must be valid JSON (Content-Type: application/json)"
        if json_invalid
        else "Request body failed validation"
    )
    return error_response(400, ErrorCode.VALIDATION_ERROR, message, details)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code == 404:
        return error_response(404, ErrorCode.NOT_FOUND, "Not found")
    if exc.status_code == 405:
        return error_response(
            405, ErrorCode.METHOD_NOT_ALLOWED, "Method not allowed", headers=exc.headers
        )
    # Nothing else raises HTTPException today; keep its status, in our shape.
    code = ErrorCode.INTERNAL if exc.status_code >= 500 else ErrorCode.VALIDATION_ERROR
    return error_response(exc.status_code, code, str(exc.detail), headers=exc.headers)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)

    # Unhandled exceptions are caught here rather than with an `Exception`
    # handler: Starlette runs those outside every middleware, so the 500 would
    # miss the CORS headers. Registered before CORS, so CORS wraps it.
    @app.middleware("http")
    async def catch_all(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            # The method and path only, never the request body.
            logger.exception("%s %s failed", request.method, request.url.path)
            return internal_error()
