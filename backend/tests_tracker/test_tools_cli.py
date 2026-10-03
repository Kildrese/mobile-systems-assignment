"""`python -m tracker.tools`: each tool runs without the model."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def run_tools(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tracker.tools", *args],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, **(env or {})},
    )


def test_fetch_blocked_url_makes_no_connection(write_config):
    # Listen on a port so a connection, if one were made, would be seen.
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        server.setblocking(False)
        port = server.getsockname()[1]
        result = run_tools(
            "--config", str(write_config()), "fetch_article", f"http://127.0.0.1:{port}/"
        )
        try:
            server.accept()
            connected = True
        except BlockingIOError:
            connected = False
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"] == "blocked_address"
    assert not connected


def test_fetch_file_url_rejected(write_config):
    result = run_tools("--config", str(write_config()), "fetch_article", "file:///etc/passwd")
    assert result.returncode != 0
    assert json.loads(result.stdout)["error"] == "scheme_not_allowed"


def test_finish_writes_report(write_config, tmp_path):
    report_json = tmp_path / "sample.json"
    report_json.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "title": f"Item {i}",
                        "summary": f"Summary {i}",
                        "sources": [f"https://e.com/{i}"],
                    }
                    for i in range(1, 6)
                ],
                "note": "Sample.",
            }
        )
    )
    out = tmp_path / "report.md"
    result = run_tools(
        "--config", str(write_config()), "finish", str(report_json), "--out", str(out)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"ok": True, "report_path": str(out), "items": 3, "truncated": 2}
    text = out.read_text()
    assert "### 1. Item 1" in text
    assert "Item 4" not in text


def test_finish_invalid_file(write_config, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    result = run_tools("--config", str(write_config()), "finish", str(bad))
    assert result.returncode != 0
    assert json.loads(result.stdout)["error"] == "invalid_json"


def test_search_without_key_fails_cleanly(write_config):
    env = {"FAKE_SEARCH_KEY": ""}
    result = run_tools("--config", str(write_config()), "search_web", "robots", env=env)
    assert result.returncode != 0
    assert "FAKE_SEARCH_KEY is not set" in json.loads(result.stdout)["detail"]
    assert "Traceback" not in result.stderr
