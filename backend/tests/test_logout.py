from tests.conftest import assert_error, auth, login


def test_requires_a_token(client):
    assert_error(client.post("/api/auth/logout"), 401, "UNAUTHORIZED")


def test_logout_revokes_only_that_session(client, ada):
    other = login(client, "ada", ada.password)
    response = client.post("/api/auth/logout", headers=ada.headers)
    assert response.status_code == 204
    assert response.content == b""

    assert_error(client.get("/api/auth/me", headers=ada.headers), 401, "UNAUTHORIZED")
    assert_error(client.post("/api/auth/logout", headers=ada.headers), 401, "UNAUTHORIZED")
    assert client.get("/api/auth/me", headers=auth(other)).status_code == 200
