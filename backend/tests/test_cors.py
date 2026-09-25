from tests.conftest import ALLOWED_ORIGIN, assert_error


def preflight(client, origin):
    return client.options(
        "/api/auth/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )


def test_preflight_from_the_allowed_origin(client):
    response = preflight(client, ALLOWED_ORIGIN)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in response.headers


def test_other_origins_get_no_cors_headers(client, ada):
    assert "access-control-allow-origin" not in preflight(client, "https://evil.example").headers
    response = client.get("/api/auth/me", headers={"Origin": "https://evil.example", **ada.headers})
    assert "access-control-allow-origin" not in response.headers


def test_errors_carry_cors_headers(client):
    response = client.get("/api/auth/me", headers={"Origin": ALLOWED_ORIGIN})
    assert_error(response, 401, "UNAUTHORIZED")
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
