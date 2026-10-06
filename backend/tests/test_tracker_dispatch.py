"""The cron-only tracker dispatch: who can reach it, and that a day dispatches once."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import get_settings
from app.routers.internal import DISPATCH_URL
from tests.conftest import Account, assert_error, auth

PATH = "/api/internal/tracker-dispatch"
SECRET = "test-cron-secret-0123456789"
TOKEN = "github_pat_test"
CRON = auth(SECRET)


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "cron_secret", SECRET)
    monkeypatch.setattr(get_settings(), "github_dispatch_token", TOKEN)


@pytest.fixture
def github():
    with respx.mock(assert_all_called=False) as mock:
        yield mock.post(DISPATCH_URL)


def _rows(sql) -> list:
    return sql.rows("select status, attempts, error from tracker_dispatches")


@pytest.mark.parametrize(
    "headers",
    [{}, auth("wrong-secret"), {"Authorization": SECRET}, {"Authorization": "Bearer "}],
    ids=["no header", "wrong secret", "not bearer", "empty bearer"],
)
def test_without_the_secret_it_is_an_unknown_path(client, sql, github, headers) -> None:
    unknown = client.get("/api/internal/nothing-here")
    response = client.get(PATH, headers=headers)
    assert_error(response, 404, "NOT_FOUND")
    assert response.json() == unknown.json()
    assert not github.called
    assert _rows(sql) == []


def test_a_signed_in_user_cannot_dispatch(client, sql, github, ada: Account) -> None:
    assert_error(client.get(PATH, headers=ada.headers), 404, "NOT_FOUND")
    assert not github.called
    assert _rows(sql) == []


def test_without_a_configured_secret_nothing_gets_in(client, sql, github, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "cron_secret", "")
    assert_error(client.get(PATH, headers=auth("")), 404, "NOT_FOUND")
    assert_error(client.get(PATH, headers=CRON), 404, "NOT_FOUND")
    assert not github.called


def test_dispatches_once_a_day(client, sql, github) -> None:
    github.respond(204)

    first = client.get(PATH, headers=CRON)
    assert first.status_code == 202
    assert first.json() == {"status": "dispatched"}
    assert github.call_count == 1
    request = github.calls.last.request
    assert json.loads(request.content) == {"ref": "master"}
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert _rows(sql) == [("dispatched", 1, None)]

    second = client.get(PATH, headers=CRON)
    assert second.status_code == 200
    assert second.json() == {"status": "already_dispatched"}
    assert github.call_count == 1


def test_a_failed_day_can_be_claimed_again(client, sql, github) -> None:
    github.respond(401, json={"message": "Bad credentials"})
    response = client.get(PATH, headers=CRON)
    assert response.status_code == 502
    assert response.json() == {"status": "failed"}
    assert _rows(sql) == [("failed", 1, "401: Bad credentials")]

    github.respond(204)
    assert client.get(PATH, headers=CRON).status_code == 202
    assert github.call_count == 2
    assert _rows(sql) == [("dispatched", 2, None)]


def test_an_unreachable_github_fails_the_day(client, sql, github) -> None:
    github.side_effect = httpx.ConnectTimeout("timed out")
    assert client.get(PATH, headers=CRON).status_code == 502
    [(status, _, error)] = _rows(sql)
    assert status == "failed"
    assert error.startswith("ConnectTimeout")


def test_without_a_token_the_day_fails_and_github_is_not_called(
    client, sql, github, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "github_dispatch_token", None)
    assert client.get(PATH, headers=CRON).status_code == 502
    assert not github.called
    assert _rows(sql) == [("failed", 1, "GITHUB_DISPATCH_TOKEN is not set")]


@pytest.mark.parametrize(("age", "dispatches"), [("6 minutes", True), ("1 minute", False)])
def test_a_stale_claim_is_taken_over(client, sql, github, age, dispatches) -> None:
    github.respond(204)
    sql.run(
        "insert into tracker_dispatches (day, status, claimed_at, attempts) "
        f"values ((now() at time zone 'utc')::date, 'claimed', now() - interval '{age}', 1)"
    )
    response = client.get(PATH, headers=CRON)
    assert response.status_code == (202 if dispatches else 200)
    assert github.called is dispatches


def test_two_calls_at_once_dispatch_once(sql, github) -> None:
    from app.main import app

    # GitHub answers slowly, so the second call arrives while the first holds the claim.
    gate = threading.Barrier(2)

    def slow(_request):
        time.sleep(0.5)
        return httpx.Response(204)

    github.side_effect = slow

    def call() -> int:
        with TestClient(app) as client:
            gate.wait()
            return client.get(PATH, headers=CRON).status_code

    with ThreadPoolExecutor(2) as pool:
        statuses = sorted(pool.map(lambda _: call(), range(2)))

    assert statuses == [200, 202]
    assert github.call_count == 1
    assert _rows(sql) == [("dispatched", 1, None)]


def test_not_in_the_openapi_document(client) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    assert not [path for path in paths if path.startswith("/api/internal")]
