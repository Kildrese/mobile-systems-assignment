"""Researcher tests: fakes only, no network.

The brief's blocked-URL row (169.254.169.254, localhost) applies to the verifier only,
which fetches pages and already tests it. The researcher fetches nothing.
"""

import importlib
import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import pytest

os.environ["RESEARCHER_TOKEN"] = "researcher-test-token"

from fastapi.testclient import TestClient

import main

AUTH = {"Authorization": "Bearer researcher-test-token"}
client = TestClient(main.app)


def body(k=5, **over):
    b = {
        "request_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "time_budget_ms": 60000,
        "budget": {"max_steps": 2, "max_fetches": 6, "max_tokens": 12000},
        "payload": {"topic": "Summer 2027 internships", "k": k},
    }
    b.update(over)
    return b


class Spy:
    def __init__(self):
        self.calls = 0
        self.gate: threading.Event | None = None
        self.entered = threading.Event()

    def sleep(self, _seconds):
        self.entered.set()
        if self.gate:
            self.gate.wait(5)


@pytest.fixture
def spy(monkeypatch):
    s = Spy()
    real = main.research

    def counted(req, log):
        s.calls += 1
        return real(req, log)

    monkeypatch.setattr(main, "research", counted)
    monkeypatch.setattr(main, "_sleep", s.sleep)
    monkeypatch.setattr(main, "DELAY_MS", 0)
    monkeypatch.setattr(main, "store", main.Store())
    return s


def test_healthz_needs_no_token():
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_no_token_is_401_before_schema(spy):
    assert client.post("/research", json={"junk": 1}).status_code == 401


def test_verifier_token_is_401(spy):
    r = client.post("/research", json=body(), headers={"Authorization": "Bearer verifier-token"})
    assert r.status_code == 401


@pytest.mark.parametrize("k", [0, 21])
def test_k_out_of_range_is_400(spy, k):
    r = client.post("/research", json=body(k=k), headers=AUTH)
    assert r.status_code == 400 and "payload.k" in r.json()["error"]["message"]


def test_extra_payload_field_is_400(spy):
    b = body()
    b["payload"]["reasoning"] = "x"
    assert client.post("/research", json=b, headers=AUTH).status_code == 400


def test_top_two_in_file_order(spy):
    r = client.post("/research", json=body(k=2), headers=AUTH).json()
    assert r["status"] == "complete" and r["error"] is None
    assert [d["id"] for d in r["result"]["developments"]] == [d.id for d in main.DEVELOPMENTS[:2]]
    assert r["usage"] == {"steps": 0, "fetches": 0, "tokens": 0}


def test_k_larger_than_file_returns_all(spy):
    r = client.post("/research", json=body(k=20), headers=AUTH).json()
    assert r["status"] == "complete"
    assert len(r["result"]["developments"]) == len(main.DEVELOPMENTS)


def test_every_source_url_is_https():
    assert all(c.source_url.startswith("https://") for d in main.DEVELOPMENTS for c in d.claims)


def test_tiny_time_budget_is_partial(spy, monkeypatch):
    monkeypatch.setattr(main, "DELAY_MS", 100)
    r = client.post("/research", json=body(time_budget_ms=1), headers=AUTH)
    j = r.json()
    assert r.status_code == 200 and j["status"] == "partial"
    assert j["error"]["code"] == "time_budget_exhausted"
    assert j["result"]["developments"] == []


def test_same_request_twice_runs_once(spy):
    b = body()
    first = client.post("/research", json=b, headers=AUTH)
    second = client.post("/research", json=b, headers=AUTH)
    assert first.json() == second.json() and spy.calls == 1


def test_reordered_keys_are_the_same_body(spy):
    b = body()
    client.post("/research", json=b, headers=AUTH)
    reordered = json.dumps(dict(reversed(list(b.items()))), indent=2)
    r = client.post(
        "/research", content=reordered, headers={**AUTH, "content-type": "application/json"}
    )
    assert r.status_code == 200 and spy.calls == 1


def test_same_id_different_k_is_409(spy):
    b = body(k=2)
    client.post("/research", json=b, headers=AUTH)
    b["payload"]["k"] = 3
    assert client.post("/research", json=b, headers=AUTH).status_code == 409


def test_duplicate_while_running_is_503(spy):
    spy.gate = threading.Event()
    b = body()
    results = {}
    t = threading.Thread(
        target=lambda: results.setdefault("first", client.post("/research", json=b, headers=AUTH))
    )
    t.start()
    assert spy.entered.wait(5)
    second = client.post("/research", json=b, headers=AUTH)
    spy.gate.set()
    t.join()
    assert second.status_code == 503 and second.headers["retry-after"] == "5"
    assert results["first"].status_code == 200
    assert spy.calls == 1


def test_log_follows_request_and_hides_secrets(spy, capsys):
    client.post("/research", json=body(), headers={"Authorization": "Bearer nope"})
    client.post("/research", json=body(k=0), headers=AUTH)
    b = body()
    client.post("/research", json=b, headers=AUTH)
    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    ok = [line for line in lines if line.get("request_id") == b["request_id"]]
    assert len(ok) == 1 and ok[0]["status"] == 200 and ok[0]["run_id"] == b["run_id"]
    assert ok[0]["service"] == "researcher" and ok[0]["direction"] == "in"
    assert "researcher-test-token" not in json.dumps(lines)


def test_invalid_file_raises_at_import(tmp_path):
    root = Path(main.__file__).parent
    data = json.loads((root / "developments.json").read_text(encoding="utf-8"))
    data[0]["claims"] = []
    (tmp_path / "developments.json").write_text(json.dumps(data))
    (tmp_path / "main.py").write_text((root / "main.py").read_text())
    r = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0 and "ValidationError" in r.stderr


def test_missing_token_refuses_to_start(monkeypatch):
    monkeypatch.delenv("RESEARCHER_TOKEN")
    with pytest.raises(RuntimeError):
        importlib.reload(main)
    monkeypatch.setenv("RESEARCHER_TOKEN", "researcher-test-token")
