import uuid

import pytest

from tests.conftest import USER_KEYS, assert_error, auth


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
@pytest.mark.parametrize("headers", [{}, auth("garbage")], ids=["no token", "garbage"])
def test_requires_a_token(client, ada, method, headers):
    response = client.request(
        method, f"/api/users/{ada.id}", json={"firstName": "X"}, headers=headers
    )
    assert_error(response, 401, "UNAUTHORIZED")


def test_get_own_user(client, ada):
    response = client.get(f"/api/users/{ada.id}", headers=ada.headers)
    assert response.status_code == 200
    assert sorted(response.json()) == USER_KEYS


def test_others_nonexistent_and_invalid_ids_are_identical_404s(client, ada, bob):
    bodies = []
    for target in (bob.id, str(uuid.uuid4()), "not-a-uuid"):
        response = client.get(f"/api/users/{target}", headers=ada.headers)
        assert_error(response, 404, "NOT_FOUND")
        bodies.append(response.content)
    assert len(set(bodies)) == 1


def test_cannot_touch_another_user(client, sql, ada, bob):
    patch = client.patch(f"/api/users/{bob.id}", json={"firstName": "Hacked"}, headers=ada.headers)
    assert_error(patch, 404, "NOT_FOUND")
    delete = client.delete(f"/api/users/{bob.id}", headers=ada.headers)
    assert_error(delete, 404, "NOT_FOUND")
    assert sql.scalar("select first_name from users where id = :id", id=bob.id) == "Bob"


def test_patch_first_name(client, ada):
    response = client.patch(
        f"/api/users/{ada.id}", json={"firstName": "Augusta"}, headers=ada.headers
    )
    assert response.status_code == 200
    user = response.json()
    assert sorted(user) == USER_KEYS
    assert (user["firstName"], user["lastName"]) == ("Augusta", "Lovelace")
    assert user["updatedAt"] > user["createdAt"]


def test_patch_last_name_to_empty(client, ada):
    response = client.patch(f"/api/users/{ada.id}", json={"lastName": ""}, headers=ada.headers)
    assert response.status_code == 200
    assert response.json()["lastName"] == ""


def test_patch_username_to_a_taken_one(client, ada, bob):
    response = client.patch(
        f"/api/users/{ada.id}", json={"username": bob.username}, headers=ada.headers
    )
    assert_error(response, 409, "USERNAME_TAKEN")


def test_patch_username_to_own_in_another_case(client, ada):
    response = client.patch(f"/api/users/{ada.id}", json={"username": "ADA"}, headers=ada.headers)
    assert response.status_code == 200
    assert response.json()["username"] == "ada"


def test_patch_username(client, ada):
    response = client.patch(
        f"/api/users/{ada.id}", json={"username": "Augusta"}, headers=ada.headers
    )
    assert response.status_code == 200
    assert response.json()["username"] == "augusta"
    old = client.post("/api/auth/login", json={"username": "ada", "password": ada.password})
    assert_error(old, 401, "INVALID_CREDENTIALS")
    new = client.post("/api/auth/login", json={"username": "augusta", "password": ada.password})
    assert new.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="empty"),
        pytest.param({"username": "no spaces"}, id="invalid username"),
        pytest.param({"email": "new@example.com"}, id="email"),
        pytest.param({"password": "x"}, id="password"),
        pytest.param({"id": "00000000-0000-0000-0000-000000000000"}, id="id"),
        pytest.param({"firstName": None}, id="null first name"),
        pytest.param({"firstName": "   "}, id="blank first name"),
    ],
)
def test_invalid_patch(client, sql, ada, body):
    response = client.patch(f"/api/users/{ada.id}", json=body, headers=ada.headers)
    assert_error(response, 400, "VALIDATION_ERROR")
    row = sql.rows("select username, first_name from users where id = :id", id=ada.id)
    assert row == [("ada", "Ada")]


def test_delete_own_user_cascades(client, sql, ada):
    response = client.delete(f"/api/users/{ada.id}", headers=ada.headers)
    assert response.status_code == 204
    assert response.content == b""
    for table, column in (("users", "id"), ("user_passwords", "user_id"), ("sessions", "user_id")):
        count = sql.scalar(f"select count(*) from {table} where {column} = :id", id=ada.id)
        assert count == 0, table
    assert_error(client.get("/api/auth/me", headers=ada.headers), 401, "UNAUTHORIZED")
    login = client.post("/api/auth/login", json={"username": "ada", "password": ada.password})
    assert_error(login, 401, "INVALID_CREDENTIALS")
