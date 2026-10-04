"""Documented error responses, shared by the routers."""

from typing import Any

from app.schemas import Error


def _error(description: str) -> dict[str, Any]:
    return {"model": Error, "description": description}


BAD_REQUEST = {400: _error("The body is not valid JSON or fails validation.")}
UNAUTHORIZED = {401: _error("Missing, malformed, unknown or expired token.")}
NOT_FOUND = {
    404: _error(
        "The id is not your own. Same response whether it belongs to someone else, "
        "doesn't exist or isn't a UUID."
    )
}
FORBIDDEN = {403: _error("The current password is wrong.")}
INTERNAL = {500: _error("Unexpected server error.")}


def conflict(description: str) -> dict[int, dict[str, Any]]:
    return {409: _error(description)}


def unauthenticated(description: str) -> dict[int, dict[str, Any]]:
    return {401: _error(description)}


def not_found(description: str) -> dict[int, dict[str, Any]]:
    return {404: _error(description)}
