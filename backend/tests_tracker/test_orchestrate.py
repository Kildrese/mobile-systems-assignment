"""The orchestrate command's run: both workers faked with one httpx transport, no
network, no Postgres."""

import json

import httpx
import pytest

from tests_tracker.conftest import BASE_POLICY, deep_merge, read_trace
from tracker.config import TrackerSecrets, policy_from_dict
from tracker.errors import PolicyError
from tracker.orchestrate import orchestrate

R_TOKEN = "researcher-secret-token"
V_TOKEN = "verifier-secret-token"
SECRETS = TrackerSecrets(
    "",
    "",
    verifier_url="https://verifier.test",
    verifier_token=V_TOKEN,
    researcher_url="http://127.0.0.1:8101",
    researcher_token=R_TOKEN,
)
SHARE = {"max_steps": 1, "max_fetches": 1, "max_tokens": 1000, "cold_start_ms": 0}
LAST = {
    "run_id": "old-run",
    "started_at": "2026-11-14T09:00:00+00:00",
    "offers": [
        {
            "rank": r,
            "title": f"Old {r}",
            "url": f"https://jobs.test/old{r}",
            "claims": [{"field": "term", "text": "T", "verdict": "supported", "evidence": "E"}],
        }
        for r in (1, 2)
    ],
}


def policy(tmp_path, **verifier):
    data = deep_merge(
        BASE_POLICY,
        {
            "use_case": "internships",
            "limits": {"max_steps": 20, "max_fetches": 20, "max_tokens": 50000},
            "options": {
                "researcher": {**SHARE, "max_attempts": 3},
                "verifier": {**SHARE, "max_requests": 3, "max_attempts": 3, **verifier},
            },
        },
    )
    return policy_from_dict(data, tmp_path)


def dev(i):
    return {
        "id": f"d{i}",
        "title": f"Role {i}, Co",
        "summary": f"Summary {i}",
        "claims": [
            {"claim_id": f"d{i}:{f}", "text": f"{f} {i}", "source_url": f"https://jobs.test/{i}"}
            for f in ("title", "term")
        ],
    }


def answer(body, result, status="complete", error=None, usage=None):
    return httpx.Response(
        200,
        json={
            "request_id": body["request_id"],
            "run_id": body["run_id"],
            "status": status,
            "result": result,
            "usage": usage or {"steps": 0, "fetches": 0, "tokens": 0},
            "error": error,
        },
    )


class Workers:
    """`research` and `verify` are each a callable (body -> response) or an exception."""

    def __init__(self, research=None, verify=None, n=3):
        self.research = research or (
            lambda b: answer(b, {"developments": [dev(i) for i in range(1, n + 1)]})
        )
        self.verify = verify or (
            lambda b: answer(
                b,
                {
                    "verdicts": [
                        {"claim_id": c["claim_id"], "verdict": "supported", "evidence": "quote"}
                        for c in b["payload"]["claims"]
                    ]
                },
                usage={"steps": 1, "fetches": 1, "tokens": 500},
            )
        )
        self.seen: list[tuple[str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        token = R_TOKEN if path == "/research" else V_TOKEN
        assert request.headers["authorization"] == f"Bearer {token}"
        body = json.loads(request.content)
        self.seen.append((path, body))
        handler = self.research if path == "/research" else self.verify
        if isinstance(handler, Exception):
            raise handler
        return handler(body)

    def paths(self):
        return [p for p, _ in self.seen]


def run(tmp_path, workers, last=None, **verifier):
    return orchestrate(
        policy(tmp_path, **verifier),
        SECRETS,
        last,
        transport=httpx.MockTransport(workers),
        sleep=lambda _: None,
    )


def test_all_good(tmp_path):
    w = Workers()
    out = run(tmp_path, w)
    assert out.exit_code == 0 and out.run["status"] == "complete"
    assert out.run["failed_services"] == [] and out.run["stop_reason"] is None
    assert [o["rank"] for o in out.offers] == [1, 2, 3]
    assert {c["verdict"] for o in out.offers for c in o["claims"]} == {"supported"}
    assert out.offers[0]["claims"][1] == {
        "field": "term",
        "text": "term 1",
        "verdict": "supported",
        "evidence": "quote",
    }
    assert out.offers[0]["url"] == "https://jobs.test/1" and out.offers[0]["company"] == ""
    assert w.paths() == ["/research", "/verify", "/verify", "/verify"]
    research = w.seen[0][1]
    assert research["payload"] == {"topic": BASE_POLICY["topic"], "k": 3}
    assert {b["run_id"] for _, b in w.seen} == {out.run["id"]}
    # Each answer's usage once: 3 x (1 step, 1 fetch, 500 tokens).
    assert "3 steps, 3 fetches, 1500 tokens" in out.markdown
    assert "### 1. Role 1, Co" in out.markdown
    assert "- **supported:** term 1 (https://jobs.test/1)\n  > quote" in out.markdown


def test_researcher_down_shows_last_top_k_stale(tmp_path):
    w = Workers(research=httpx.ConnectError("refused"))
    out = run(tmp_path, w, LAST)
    assert out.exit_code == 2 and out.run["failed_services"] == ["researcher"]
    assert out.run["stop_reason"] == "service:researcher"
    assert w.paths() == ["/research"] * 3 and out.offers == []
    assert "## No new results" in out.markdown
    assert "## Last run's top K (stale, run old-run, 2026-11-14T09:00:00+00:00)" in out.markdown
    assert "### 1. Old 1 (stale)" in out.markdown and "### 2. Old 2 (stale)" in out.markdown
    assert "- **supported:** T (https://jobs.test/old1)" in out.markdown


def test_researcher_down_without_earlier_run(tmp_path):
    out = run(tmp_path, Workers(research=httpx.ConnectError("refused")))
    assert "No earlier run to show." in out.markdown


def test_more_developments_than_k_is_researcher_down(tmp_path):
    w = Workers(n=4)
    out = run(tmp_path, w, LAST)
    assert out.run["failed_services"] == ["researcher"] and out.offers == []
    assert "invalid_response" in out.markdown and "Role 1" not in out.markdown
    assert "/verify" not in w.paths()


def test_researcher_401_is_not_retried(tmp_path):
    w = Workers(research=lambda b: httpx.Response(401))
    out = run(tmp_path, w)
    assert w.paths() == ["/research"]
    assert out.run["failed_services"] == ["researcher"]
    assert "the researcher refused the token" in out.markdown


def test_researcher_partial_with_developments_is_verified(tmp_path):
    error = {"code": "time_budget_exhausted", "message": "stopped", "retryable": False}
    w = Workers(
        research=lambda b: answer(
            b, {"developments": [dev(1), dev(2)]}, status="partial", error=error
        )
    )
    out = run(tmp_path, w)
    assert out.exit_code == 2 and out.run["failed_services"] == ["researcher"]
    assert w.paths().count("/verify") == 2 and len(out.offers) == 2
    assert "researcher (time_budget_exhausted: stopped)" in out.markdown


def test_verifier_down_leaves_claims_unverified(tmp_path):
    out = run(tmp_path, Workers(verify=httpx.ConnectError("refused")))
    assert out.exit_code == 2 and out.run["failed_services"] == ["verifier"]
    assert out.run["stop_reason"] == "service:verifier"
    assert len(out.offers) == 3
    assert {c["verdict"] for o in out.offers for c in o["claims"]} == {"unverified"}


def test_unknown_claim_id_discards_that_answer(tmp_path):
    def verify(b):
        claims = b["payload"]["claims"]
        first = claims[0]["claim_id"]
        cid = "d9:title" if first.startswith("d1:") else first
        return answer(
            b, {"verdicts": [{"claim_id": cid, "verdict": "unsupported", "evidence": None}]}
        )

    out = run(tmp_path, Workers(verify=verify))
    assert out.run["failed_services"] == ["verifier"]
    assert {c["verdict"] for c in out.offers[0]["claims"]} == {"unverified"}
    assert out.offers[1]["claims"][0]["verdict"] == "unsupported"


def test_max_requests_leaves_the_rest_unverified(tmp_path):
    w = Workers(n=2)
    out = run(tmp_path, w, max_requests=1)
    assert w.paths().count("/verify") == 1
    assert out.exit_code == 2 and out.run["failed_services"] == []
    assert out.run["stop_reason"] == "verifier.max_requests"
    assert {c["verdict"] for c in out.offers[1]["claims"]} == {"unverified"}


def test_over_allocated_shares_refused_before_any_request(tmp_path):
    w = Workers()
    data = deep_merge(
        BASE_POLICY,
        {
            "use_case": "internships",
            "limits": {"max_steps": 20, "max_tokens": 60000, "reserve_tokens": 1000},
            "options": {
                "researcher": {**SHARE, "max_tokens": 20000},
                "verifier": {**SHARE, "max_requests": 5, "max_tokens": 12000},
            },
        },
    )
    with pytest.raises(PolicyError, match=r"limits\.max_tokens: .* 80,000, more than 59,000"):
        orchestrate(
            policy_from_dict(data, tmp_path), SECRETS, None, transport=httpx.MockTransport(w)
        )
    assert w.seen == []


def test_trace_has_one_event_per_attempt_and_no_token(tmp_path):
    out = run(tmp_path, Workers(n=1))
    path = tmp_path / "traces" / f"orchestrate-{out.run['id']}.jsonl"
    text = path.read_text()
    assert R_TOKEN not in text and V_TOKEN not in text
    events = read_trace(path)
    assert [e["endpoint_or_tool"] for e in events] == ["researcher:/research", "verifier:/verify"]
    for e in events:
        assert e["service"] == "orchestrator" and e["run_id"] == out.run["id"]
        assert e["request_id"] and e["attempt"] == 1 and isinstance(e["latency_ms"], int)
