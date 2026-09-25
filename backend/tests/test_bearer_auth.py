from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import USER_KEYS, assert_error, auth


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no header"),
        pytest.param({"Authorization": "Basic abc"}, id="basic"),
        pytest.param({"Authorization": "Bearer"}, id="bare bearer"),
        pytest.param({"Authorization": "Bearer    "}, id="blank bearer"),
        pytest.param(auth("not-a-real-token"), id="garbage"),
    ],
)
def test_bad_credentials(client, ada, headers):
    assert_error(client.get("/api/auth/me", headers=headers), 401, "UNAUTHORIZED")


def test_truncated_token(client, ada):
    response = client.get("/api/auth/me", headers=auth(ada.token[:10]))
    assert_error(response, 401, "UNAUTHORIZED")


def test_cookie_is_ignored(client, ada):
    client.cookies.set("session", ada.token)
    assert_error(client.get("/api/auth/me"), 401, "UNAUTHORIZED")


def test_me(client, ada):
    response = client.get("/api/auth/me", headers=ada.headers)
    assert response.status_code == 200
    assert sorted(response.json()) == USER_KEYS
    assert response.json()["id"] == ada.id
    assert response.headers["cache-control"] == "no-store"


def test_expired_token(client, sql, ada):
    sql.run("update sessions set expires_at = now() - interval '1 minute'")
    assert_error(client.get("/api/auth/me", headers=ada.headers), 401, "UNAUTHORIZED")


def expires_at(sql):
    return sql.scalar("select expires_at from sessions")


def test_recently_extended_session_is_not_touched(client, sql, ada):
    before = expires_at(sql)
    client.get("/api/auth/me", headers=ada.headers)
    assert expires_at(sql) == before


def test_session_older_than_a_day_is_extended(client, sql, ada):
    sql.run("update sessions set expires_at = now() + interval '5 days'")
    client.get("/api/auth/me", headers=ada.headers)
    extended = expires_at(sql)
    assert extended > datetime.now(UTC) + timedelta(days=6, hours=23)
