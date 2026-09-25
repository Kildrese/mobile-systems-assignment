import json

import pytest

from tests.conftest import BACKEND, USER_KEYS

PROTECTED = [
    ("get", "/api/auth/me"),
    ("post", "/api/auth/logout"),
    ("post", "/api/auth/change-password"),
    ("get", "/api/users/{id}"),
    ("patch", "/api/users/{id}"),
    ("delete", "/api/users/{id}"),
]
PUBLIC = [("get", "/healthz"), ("post", "/api/auth/register"), ("post", "/api/auth/login")]


@pytest.fixture(scope="module")
def document():
    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).get("/api/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_served_document_matches_the_committed_file(document):
    committed = json.loads((BACKEND.parent / "openapi" / "openapi.json").read_text())
    assert document == committed
    assert document["openapi"].startswith("3.1")


@pytest.mark.parametrize(("method", "path"), PUBLIC + PROTECTED)
def test_every_endpoint_is_documented(document, method, path):
    assert method in document["paths"][path]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_endpoints_declare_bearer_auth_and_401(document, method, path):
    operation = document["paths"][path][method]
    assert "bearerAuth" in json.dumps(operation["security"])
    assert "401" in operation["responses"]


def test_error_codes_and_user_schema(document):
    assert "/api/auth/change-email" not in document["paths"]
    assert "403" in document["paths"]["/api/auth/change-password"]["post"]["responses"]
    codes = document["components"]["schemas"]["ErrorCode"]["enum"]
    assert {"INVALID_PASSWORD", "USERNAME_TAKEN"} <= set(codes)
    assert "EMAIL_TAKEN" not in codes
    assert sorted(document["components"]["schemas"]["User"]["properties"]) == USER_KEYS


def test_no_422_responses(document):
    for path in document["paths"].values():
        for operation in path.values():
            assert "422" not in operation["responses"]


def test_swagger_ui(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
