from tests.conftest import ALLOWED_ORIGIN, assert_error


def test_unknown_route(client):
    assert_error(client.get("/nope"), 404, "NOT_FOUND")


def test_wrong_method(client):
    assert_error(client.get("/api/auth/login"), 405, "METHOD_NOT_ALLOWED")


def test_unexpected_error_is_a_generic_500_with_cors(client, monkeypatch):
    from app.services import accounts

    def boom(*_args, **_kwargs):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(accounts, "register", boom)
    response = client.post(
        "/api/auth/register",
        json={"username": "ada", "password": "correct-horse"},
        headers={"Origin": ALLOWED_ORIGIN},
    )
    body = assert_error(response, 500, "INTERNAL")
    assert body["error"]["message"] == "Internal server error"
    assert "secret detail" not in response.text
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
