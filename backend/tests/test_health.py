from tests.conftest import auth


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"].startswith("application/json")


def test_healthz_ignores_credentials(client):
    assert client.get("/healthz", headers=auth("garbage")).status_code == 200
