"""Test setup: a dedicated Postgres database, migrated from scratch per run,
and emptied after every test.

The database is `TEST_DATABASE_URL` when set. Otherwise it is `DATABASE_URL`
(from the environment or `backend/.env`) with `_test` appended to the database
name, so `./scripts/db-up.sh` is all a local run needs. The derived URL must
point at localhost, so a Neon URL in `.env` is never touched.
"""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parent.parent
ALLOWED_ORIGIN = "http://localhost:5173"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _test_database_url() -> str:
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url
    from app.config import Settings

    base = make_url(Settings().database_url)
    if base.host not in LOCAL_HOSTS:
        raise SystemExit(
            f"DATABASE_URL points at {base.host}, not localhost. Set TEST_DATABASE_URL to run "
            "the tests against a non-local database."
        )
    return base.set(database=f"{base.database}_test").render_as_string(hide_password=False)


def _recreate_database(url: str) -> None:
    """Create the database if needed and empty its public schema."""
    from app.db import sqlalchemy_url

    target = make_url(sqlalchemy_url(url))
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("select 1 from pg_database where datname = :name"), {"name": target.database}
        )
        if not exists:
            conn.execute(text(f'create database "{target.database}"'))
    admin.dispose()

    engine = create_engine(target, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("drop schema public cascade"))
        conn.execute(text("create schema public"))
    engine.dispose()


TEST_DATABASE_URL = _test_database_url()
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# An unpooled URL in backend/.env would send the migrations elsewhere.
os.environ["DATABASE_URL_UNPOOLED"] = ""
os.environ["CORS_ORIGINS"] = ALLOWED_ORIGIN
os.environ["SESSION_TTL_DAYS"] = "7"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_engine  # noqa: E402

get_settings.cache_clear()

USER_KEYS = ["createdAt", "firstName", "id", "lastName", "updatedAt", "username"]
FORBIDDEN_KEYS = {"password", "passwordHash", "hash"}


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    _recreate_database(TEST_DATABASE_URL)
    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
    yield
    get_engine().dispose()


@pytest.fixture(autouse=True)
def _clean_tables(_database: None) -> Iterator[None]:
    yield
    with get_engine().begin() as conn:
        conn.execute(text("truncate users, user_passwords, sessions, tracker_runs cascade"))


class Sql:
    """Raw SQL against the test database, each call in its own transaction."""

    def rows(self, query: str, **params: Any) -> list[Any]:
        with get_engine().begin() as conn:
            return list(conn.execute(text(query), params).all())

    def scalar(self, query: str, **params: Any) -> Any:
        with get_engine().begin() as conn:
            return conn.scalar(text(query), params)

    def run(self, query: str, **params: Any) -> None:
        with get_engine().begin() as conn:
            conn.execute(text(query), params)


@pytest.fixture
def sql() -> Sql:
    return Sql()


def _keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


class ScanningClient(TestClient):
    """Fails the test when any response contains a stored password or token
    hash, or (outside the OpenAPI document) a password-like key."""

    def request(self, method: str, url: Any, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        response = super().request(method, url, *args, **kwargs)
        body = response.text
        hashes = Sql().rows(
            "select hash from user_passwords union all select token_hash from sessions"
        )
        for (stored,) in hashes:
            assert stored not in body, f"{method} {url}: response contains a stored hash"
        if str(url) != "/api/openapi.json" and "json" in response.headers.get("content-type", ""):
            found = FORBIDDEN_KEYS.intersection(_keys(response.json()))
            assert not found, f"{method} {url}: response contains {found}"
        return response


@pytest.fixture
def client() -> Iterator[ScanningClient]:
    from app.main import app

    with ScanningClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"]["code"] == code, body
    return body


def register(client: TestClient, username: str, password: str, **names: str) -> dict[str, Any]:
    response = client.post(
        "/api/auth/register", json={"username": username, "password": password, **names}
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


class Account:
    def __init__(self, client: TestClient, username: str, password: str, **names: str) -> None:
        self.username = username.lower()
        self.password = password
        self.user = register(client, username, password, **names)
        self.id: str = self.user["id"]
        self.token = login(client, username, password)

    @property
    def headers(self) -> dict[str, str]:
        return auth(self.token)


@pytest.fixture
def ada(client: TestClient) -> Account:
    return Account(client, "Ada", "correct-horse", firstName="Ada", lastName="Lovelace")


@pytest.fixture
def bob(client: TestClient) -> Account:
    return Account(client, "bob", "battery-staple", firstName="Bob", lastName="Builder")
