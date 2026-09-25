from tests.conftest import assert_error, auth, login

URL = "/api/auth/change-password"


def test_requires_a_token(client):
    response = client.post(URL, json={"currentPassword": "x", "newPassword": "new-password"})
    assert_error(response, 401, "UNAUTHORIZED")


def test_wrong_current_password_is_403_and_keeps_the_token(client, ada):
    response = client.post(
        URL,
        json={"currentPassword": "wrong-one", "newPassword": "new-password"},
        headers=ada.headers,
    )
    assert_error(response, 403, "INVALID_PASSWORD")
    assert client.get("/api/auth/me", headers=ada.headers).status_code == 200


def test_short_new_password(client, ada):
    response = client.post(
        URL, json={"currentPassword": ada.password, "newPassword": "short7x"}, headers=ada.headers
    )
    assert_error(response, 400, "VALIDATION_ERROR")
    assert login(client, "ada", ada.password)


def test_change_password_revokes_every_session(client, ada):
    others = [login(client, "ada", ada.password) for _ in range(2)]
    response = client.post(
        URL,
        json={"currentPassword": ada.password, "newPassword": "new-password"},
        headers=ada.headers,
    )
    assert response.status_code == 200
    assert list(response.json()) == ["token"]
    new_token = response.json()["token"]

    for token in [ada.token, *others]:
        assert_error(client.get("/api/auth/me", headers=auth(token)), 401, "UNAUTHORIZED")
    assert client.get("/api/auth/me", headers=auth(new_token)).status_code == 200

    old = client.post("/api/auth/login", json={"username": "ada", "password": ada.password})
    assert_error(old, 401, "INVALID_CREDENTIALS")
    assert login(client, "ada", "new-password")


def test_change_email_is_gone(client, ada):
    response = client.post(
        "/api/auth/change-email",
        json={"newEmail": "ada@example.com", "currentPassword": ada.password},
        headers=ada.headers,
    )
    assert_error(response, 404, "NOT_FOUND")
