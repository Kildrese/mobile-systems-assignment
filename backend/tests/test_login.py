import hashlib

import pytest

from tests.conftest import USER_KEYS, assert_error, login, register


@pytest.fixture
def registered(client):
    return register(client, "ada", "correct-horse")


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"password": "x"}, id="missing username"),
        pytest.param({"identifier": "ada", "password": "correct-horse"}, id="identifier"),
        pytest.param({"email": "ada", "password": "correct-horse"}, id="email"),
        pytest.param({"username": "ada"}, id="missing password"),
    ],
)
def test_invalid_body(client, registered, body):
    assert_error(client.post("/api/auth/login", json=body), 400, "VALIDATION_ERROR")


def test_malformed_json(client):
    response = client.post(
        "/api/auth/login", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert_error(response, 400, "VALIDATION_ERROR")


def test_wrong_password(client, registered):
    response = client.post("/api/auth/login", json={"username": "ada", "password": "wrong-one"})
    body = assert_error(response, 401, "INVALID_CREDENTIALS")
    assert body["error"]["message"] == "Invalid username or password"


@pytest.mark.parametrize("username", ["nobody", "a", "nobody@example.com"])
def test_unknown_or_malformed_username_looks_like_a_wrong_password(client, registered, username):
    wrong = client.post("/api/auth/login", json={"username": "ada", "password": "wrong-one"})
    other = client.post("/api/auth/login", json={"username": username, "password": "wrong-one"})
    assert other.status_code == 401
    assert other.content == wrong.content


def test_login_is_case_insensitive(client, sql, registered):
    response = client.post("/api/auth/login", json={"username": "ADA", "password": "correct-horse"})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == registered["id"]
    assert sorted(body["user"]) == USER_KEYS
    assert body["token"]
    assert "set-cookie" not in response.headers


def test_session_stores_the_token_hash_only(client, sql, registered):
    token = client.post(
        "/api/auth/login", json={"username": "ada", "password": "correct-horse"}
    ).json()["token"]
    digest = hashlib.sha256(token.encode()).hexdigest()
    assert (
        sql.scalar(
            "select count(*) from sessions where token_hash = :h and user_id = :u",
            h=digest,
            u=registered["id"],
        )
        == 1
    )
    assert sql.scalar("select count(*) from sessions where token_hash = :t", t=token) == 0


def test_each_login_gets_a_new_token(client, registered):
    tokens = {
        client.post(
            "/api/auth/login", json={"username": "ada", "password": "correct-horse"}
        ).json()["token"]
        for _ in range(2)
    }
    assert len(tokens) == 2


def test_unknown_username_still_costs_a_password_verify(client, monkeypatch):
    # Response times must not reveal which usernames exist.
    from app.services import accounts

    calls = []
    monkeypatch.setattr(accounts, "dummy_verify", calls.append)
    client.post("/api/auth/login", json={"username": "nobody", "password": "wrong-one"})
    assert calls == ["wrong-one"]


def test_login_deletes_the_users_expired_sessions(client, sql, ada, bob):
    active = login(client, "ada", ada.password)
    sql.run(
        "update sessions set expires_at = now() - interval '1 minute' "
        "where token_hash = :h or user_id = :bob",
        h=hashlib.sha256(ada.token.encode()).hexdigest(),
        bob=bob.id,
    )
    new = login(client, "ada", ada.password)

    remaining = {
        token_hash
        for (token_hash,) in sql.rows(
            "select token_hash from sessions where user_id = :u", u=ada.id
        )
    }
    assert remaining == {hashlib.sha256(t.encode()).hexdigest() for t in (active, new)}
    # Bob's expired session is left alone.
    assert sql.scalar("select count(*) from sessions where user_id = :u", u=bob.id) == 1


def test_failed_login_deletes_nothing(client, sql, ada):
    sql.run("update sessions set expires_at = now() - interval '1 minute'")
    response = client.post("/api/auth/login", json={"username": "ada", "password": "wrong-one"})
    assert response.status_code == 401
    assert sql.scalar("select count(*) from sessions") == 1
