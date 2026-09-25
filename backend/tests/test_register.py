import uuid

import pytest

from tests.conftest import USER_KEYS, assert_error, login


def test_register(client, sql):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "Ada_L",
            "password": "correct-horse",
            "firstName": "Ada",
            "lastName": "Lovelace",
        },
    )
    assert response.status_code == 201
    user = response.json()
    assert sorted(user) == USER_KEYS
    assert "token" not in user
    uuid.UUID(user["id"])
    assert (user["username"], user["firstName"], user["lastName"]) == ("ada_l", "Ada", "Lovelace")

    row = sql.rows(
        "select username, first_name, last_name from users where id = :id", id=user["id"]
    )
    assert row == [("ada_l", "Ada", "Lovelace")]


def test_password_is_stored_as_argon2id_in_user_passwords_only(client, sql):
    user = client.post(
        "/api/auth/register", json={"username": "ada", "password": "correct-horse"}
    ).json()
    hashes = sql.rows("select hash from user_passwords where user_id = :id", id=user["id"])
    assert len(hashes) == 1
    assert hashes[0][0] != "correct-horse"
    assert hashes[0][0].startswith("$argon2id$")
    password_columns = sql.scalar(
        "select count(*) from information_schema.columns "
        "where table_name = 'users' and column_name like '%password%'"
    )
    assert password_columns == 0


def test_users_table_has_no_email_column(sql):
    count = sql.scalar(
        "select count(*) from information_schema.columns "
        "where table_name = 'users' and column_name = 'email'"
    )
    assert count == 0


def test_same_password_gets_different_hashes(client, sql):
    for name in ("ada", "bob"):
        client.post("/api/auth/register", json={"username": name, "password": "same-password"})
    assert sql.scalar("select count(distinct hash) from user_passwords") == 2


def test_duplicate_username_in_another_case(client):
    client.post("/api/auth/register", json={"username": "ada", "password": "correct-horse"})
    response = client.post(
        "/api/auth/register", json={"username": "ADA", "password": "correct-horse"}
    )
    assert_error(response, 409, "USERNAME_TAKEN")


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"username": "ada", "firstName": "Ada"}, id="missing password"),
        pytest.param({"username": "ada", "password": "s3cr7xx"}, id="7-char password"),
        pytest.param({"username": "ab", "password": "correct-horse"}, id="username too short"),
        pytest.param({"username": "has space", "password": "correct-horse"}, id="space"),
        pytest.param({"username": "has@at", "password": "correct-horse"}, id="at sign"),
        pytest.param({"username": "u" * 31, "password": "correct-horse"}, id="too long"),
        pytest.param({"password": "correct-horse"}, id="missing username"),
        pytest.param({"email": "ada@example.com", "password": "correct-horse"}, id="email only"),
        pytest.param({"username": "ada", "password": "correct-horse", "firstName": ""}, id="blank"),
        pytest.param({"username": "ada", "password": "correct-horse", "lastName": None}, id="null"),
    ],
)
def test_invalid_registration(client, sql, body):
    assert_error(client.post("/api/auth/register", json=body), 400, "VALIDATION_ERROR")
    assert sql.scalar("select count(*) from users") == 0


def test_validation_error_does_not_echo_the_password(client):
    response = client.post("/api/auth/register", json={"username": "ada", "password": "s3cr7xx"})
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert "s3cr7xx" not in response.text
    assert body["error"]["details"][0]["path"] == ["password"]


def test_malformed_json(client):
    response = client.post(
        "/api/auth/register", content="{not json", headers={"Content-Type": "application/json"}
    )
    body = assert_error(response, 400, "VALIDATION_ERROR")
    assert "valid JSON" in body["error"]["message"]


def test_extra_keys_are_ignored(client, sql):
    sent_id = str(uuid.uuid4())
    response = client.post(
        "/api/auth/register",
        json={
            "username": "extra",
            "password": "correct-horse",
            "id": sent_id,
            "email": "extra@example.com",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    assert sorted(response.json()) == USER_KEYS
    assert response.json()["id"] != sent_id
    assert "extra@example.com" not in response.text


def test_names_default_to_username_and_empty(client):
    response = client.post(
        "/api/auth/register", json={"username": "Solo", "password": "correct-horse"}
    )
    user = response.json()
    assert (user["username"], user["firstName"], user["lastName"]) == ("solo", "solo", "")
    assert login(client, "solo", "correct-horse")


def test_names_are_trimmed(client):
    response = client.post(
        "/api/auth/register",
        json={"username": "  ada ", "password": "correct-horse", "firstName": "  Ada  "},
    )
    assert (response.json()["username"], response.json()["firstName"]) == ("ada", "Ada")
