"""The FastAPI app: routers, CORS, error handlers and the OpenAPI document."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.config import get_settings
from app.errors import install_error_handlers
from app.routers import auth, health, internal, internships, users

DESCRIPTION = (
    "JSON API for accounts, users and the daily internship report. Log in with "
    "`POST /api/auth/login`, then send the token as `Authorization: Bearer <token>`."
)


def _openapi(app: FastAPI) -> dict[str, Any]:
    """FastAPI's document without its automatic `422` responses and their
    schemas: validation errors are `400` with the `Error` shape here."""
    if app.openapi_schema:
        return app.openapi_schema
    doc = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
        separate_input_output_schemas=False,
    )
    for path in doc["paths"].values():
        for operation in path.values():
            operation["responses"].pop("422", None)
    schemas = doc["components"]["schemas"]
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)
    app.openapi_schema = doc
    return doc


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Mobile Systems API",
        version="0.1.0",
        description=DESCRIPTION,
        openapi_url="/api/openapi.json",
        docs_url="/docs",
        redoc_url=None,
        openapi_tags=[
            {"name": "Health"},
            {"name": "Auth"},
            {"name": "Users"},
            {"name": "Internships"},
        ],
        separate_input_output_schemas=False,
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(internships.router)
    app.include_router(internal.router)
    app.openapi = lambda: _openapi(app)

    # Middleware added later wraps middleware added earlier, so the order is
    # CORS → no-store → catch-all → routes: every response, 500s included,
    # gets the CORS headers.
    install_error_handlers(app)

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    # Bearer tokens, no cookies: no credentials, and an explicit allow-list
    # even so, never `*`.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )
    return app


app = create_app()
