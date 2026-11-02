"""The Verify stage: claims from records, the verifier client, and the stage in a run.
The verifier is faked with an httpx transport; nothing touches the network."""

import json

import httpx
import pytest
import respx

from tests_tracker.conftest import LLM_URL, SEARCH_URL, read_trace, resolver_for, search_body
from tests_tracker.internships_helpers import RUN1, add_board, open_store, posting, record
from tests_tracker.test_internships_pipeline import (
    EVIDENCE,
    PUBLIC_IP,
    curate_script,
    edit_script,
    mock_boards,
    policy_data,
    scout_script,
)
from tests_tracker.test_loop import FakeModel
from tracker import conductor
from tracker.budget import Budget
from tracker.config import TrackerSecrets, policy_from_dict
from tracker.errors import PolicyError
from tracker.trace import Trace
from tracker.usecases.internships import ranking, verifying, wiring
from tracker.usecases.internships.ranking import RankingSettings

VERIFIER = "https://verifier.example.com"
TOKEN = "verifier-secret-token"
SETTINGS = verifying.VerifierSettings(max_attempts=3, max_steps=1, max_fetches=1, max_tokens=1000)


def opp(store):
    source = add_board(store)
    [pid] = store.upsert_postings(source, [posting()], RUN1)
    oid = store.create_opportunity(
        company="Acme",
        url=posting().url,
        record=record(),
        run_id=RUN1,
        posting_id=pid,
        linked_by="record",
    )
    return store.opportunity(oid)


class FakeVerifier:
    """Answers every claim `supported`, or follows a script of responses per call."""

    def __init__(self, *script):
        self.script = list(script)
        self.requests: list[dict] = []
        self.bodies: list[bytes] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        self.bodies.append(request.content)
        body = json.loads(request.content)
        self.requests.append(body)
        step = self.script.pop(0) if self.script else "ok"
        if isinstance(step, Exception):
            raise step
        if isinstance(step, httpx.Response):
            return step
        verdict = step if step != "ok" else "supported"
        verdicts = [
            {
                "claim_id": c["claim_id"],
                "verdict": verdict,
                "evidence": "Summer 2027" if verdict == "supported" else None,
            }
            for c in body["payload"]["claims"]
        ]
        return httpx.Response(
            200,
            json={
                "request_id": body["request_id"],
                "run_id": body["run_id"],
                "status": "complete",
                "result": {"verdicts": verdicts},
                "usage": {"steps": 1, "fetches": 1, "tokens": 900},
                "error": None,
            },
        )


def client(trace, fake, settings=SETTINGS):
    return verifying.Client(
        VERIFIER, TOKEN, settings, trace, transport=httpx.MockTransport(fake), sleep=lambda _: None
    )


@pytest.fixture
def env(tmp_path):
    policy = policy_from_dict(policy_data(options={"verifier": {}}), tmp_path)
    state, store = open_store(tmp_path / "s.sqlite")
    trace = Trace(tmp_path / "t.jsonl", "run-1", [TOKEN])
    yield policy, store, trace, Budget(policy)
    state.close()
    trace.close()


# Claims


def test_claims_skip_unknown_fields_and_never_carry_quotes(tmp_path):
    _, store = open_store(tmp_path / "s.sqlite")
    o = opp(store)
    claims = verifying.claims_for(o)
    fields = [c["claim_id"].split(":")[1] for c in claims]
    assert "deadline" not in fields and "remote" not in fields  # unknown in the record
    assert fields[:3] == ["title", "role_type", "term"]
    pay = next(c for c in claims if c["claim_id"].endswith(":compensation"))
    assert pay["text"] == 'Acme\'s "Software Engineering Intern" posting lists pay of $45/hour.'
    assert pay["source_url"] == o["url"]
    auth = next(c for c in claims if c["claim_id"].endswith(":work_authorization"))
    assert "must be" not in auth["text"]  # the value, not the Curator's quote


# Client


def test_timeout_then_stored_copy_is_charged_once(env):
    _, store, trace, budget = env
    o = opp(store)
    fake = FakeVerifier(httpx.ReadTimeout("slow"), "ok")
    result = verifying.verify_top_k(store, RUN1, [o], client(trace, fake), SETTINGS, budget)
    assert result.failure is None and result.requests == 1
    # The retry is the same request, byte for byte.
    assert len(fake.bodies) == 2 and fake.bodies[0] == fake.bodies[1]
    assert budget.total_tokens == 900 and budget.steps == 1
    events = [e for e in read_trace(trace.path) if e["kind"] == "service"]
    assert [(e["attempt"], e["status"]) for e in events] == [(1, "timeout"), (2, 200)]
    assert len({e["request_id"] for e in events}) == 1


def test_unknown_claim_id_discards_the_response(env):
    _, store, trace, budget = env
    o = opp(store)

    def bad(request):
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "request_id": body["request_id"],
                "run_id": body["run_id"],
                "status": "complete",
                "result": {
                    "verdicts": [
                        {"claim_id": "999:term", "verdict": "unreachable", "evidence": None}
                    ]
                },
                "usage": {"steps": 0, "fetches": 0, "tokens": 0},
                "error": None,
            },
        )

    result = verifying.verify_top_k(store, RUN1, [o], client(trace, bad), SETTINGS, budget)
    assert result.failure.reason == "invalid_response"
    assert store.verdicts(o["id"], store.record_hash(o)) == {}
    # No valid answer: charged the full share.
    assert budget.total_tokens == SETTINGS.max_tokens


def test_unauthorized_stops_without_retry(env):
    _, store, trace, budget = env
    a = opp(store)
    b = {**a, "id": a["id"] + 100}  # a second top-K entry
    fake = FakeVerifier(httpx.Response(401))
    result = verifying.verify_top_k(store, RUN1, [a, b], client(trace, fake), SETTINGS, budget)
    assert result.failure.reason == "unauthorized"
    assert len(fake.requests) == 1


@pytest.mark.parametrize("status", [400, 409, 500])
def test_terminal_statuses_are_not_retried(env, status):
    _, store, trace, budget = env
    fake = FakeVerifier(httpx.Response(status, json={"error": {"message": "no"}}))
    result = verifying.verify_top_k(
        store, RUN1, [opp(store)], client(trace, fake), SETTINGS, budget
    )
    assert result.failure.reason == f"http_{status}" and len(fake.requests) == 1


def test_never_answered_is_charged_its_full_share(env):
    _, store, trace, budget = env
    fake = FakeVerifier(*[httpx.ConnectError("refused")] * 3)
    result = verifying.verify_top_k(
        store, RUN1, [opp(store)], client(trace, fake), SETTINGS, budget
    )
    assert result.failure.reason == "no_answer" and len(fake.requests) == 3
    assert (budget.steps, budget.fetches, budget.total_tokens) == (1, 1, 1000)


def test_retry_after_is_honoured(env):
    _, store, trace, budget = env
    waits = []
    fake = FakeVerifier(httpx.Response(503, headers={"Retry-After": "9"}), "ok")
    c = verifying.Client(
        VERIFIER, TOKEN, SETTINGS, trace, transport=httpx.MockTransport(fake), sleep=waits.append
    )
    verifying.verify_top_k(store, RUN1, [opp(store)], c, SETTINGS, budget)
    assert waits and waits[0] >= 9


def test_no_request_past_the_run_budget(env):
    _, store, trace, budget = env
    budget.count(steps=budget.policy.limits.max_steps)
    fake = FakeVerifier()
    result = verifying.verify_top_k(
        store, RUN1, [opp(store)], client(trace, fake), SETTINGS, budget
    )
    assert fake.requests == [] and result.skipped_for_budget == 1


def test_token_never_in_trace(env):
    _, store, trace, budget = env
    verifying.verify_top_k(
        store, RUN1, [opp(store)], client(trace, FakeVerifier()), SETTINGS, budget
    )
    assert TOKEN not in trace.path.read_text()


# Stored verdicts


def test_verdicts_reused_until_record_changes_and_unreachable_retried(env):
    _, store, trace, budget = env
    o = opp(store)
    fake = FakeVerifier("ok")
    verifying.verify_top_k(store, RUN1, [o], client(trace, fake), SETTINGS, budget)
    verifying.verify_top_k(store, RUN1, [o], client(trace, fake), SETTINGS, budget)
    assert len(fake.requests) == 1  # unchanged record: nothing sent again

    changed = {**o, "fields": {**o["fields"], "term": {"value": "Fall 2027", "quote": "x"}}}
    verifying.verify_top_k(store, RUN1, [changed], client(trace, fake), SETTINGS, budget)
    assert len(fake.requests) == 2

    fake = FakeVerifier("unreachable", "ok")
    other = {**o, "url": "https://boards.greenhouse.io/acme/jobs/2"}
    verifying.verify_top_k(store, RUN1, [other], client(trace, fake), SETTINGS, budget)
    verifying.verify_top_k(store, RUN1, [other], client(trace, fake), SETTINGS, budget)
    assert len(fake.requests) == 2  # unreachable claims are tried again next run
    view = verifying.claims_view(store, other)
    assert {c["verdict"] for c in view} == {"supported"}


def test_unsupported_field_ranks_as_unknown(env):
    _, store, _, _ = env
    o = opp(store)
    settings = RankingSettings()
    before = ranking.rank_open(store, RUN1, settings, 3)[0]["score"]
    store.put_verdicts(
        [
            {
                "opportunity_id": o["id"],
                "field": "term",
                "record_hash": store.record_hash(o),
                "text": "t",
                "verdict": "unsupported",
                "evidence": None,
                "run_id": RUN1,
                "request_id": "r",
            }
        ]
    )
    after = ranking.rank_open(store, RUN1, settings, 3)[0]["score"]
    assert after == pytest.approx(before - settings.weights.term * 0.5)


def test_unreachable_changes_no_score(env):
    _, store, trace, budget = env
    o = opp(store)
    before = ranking.rank_open(store, RUN1, RankingSettings(), 3)[0]["score"]
    verifying.verify_top_k(
        store, RUN1, [o], client(trace, FakeVerifier("unreachable")), SETTINGS, budget
    )
    assert ranking.rank_open(store, RUN1, RankingSettings(), 3)[0]["score"] == before


# The stage in a run


def run(policy, keys, fake, run_id):
    return conductor.run(
        policy,
        keys,
        wiring.stages(policy),
        wiring.report_writer,
        run_id=run_id,
        resolver=resolver_for(PUBLIC_IP),
        sleep=lambda _: None,
        service_transport=httpx.MockTransport(fake),
    )


VERIFIER_OPTIONS = {
    "verifier": {"max_requests": 3, "max_steps": 1, "max_fetches": 1, "max_tokens": 1000}
}


@pytest.fixture
def vpolicy(tmp_path):
    limits = {"max_fetches": 10, "max_steps": 25, "max_tokens": 40000}
    return policy_from_dict(policy_data(options=VERIFIER_OPTIONS, limits=limits), tmp_path)


def keys():
    from tests_tracker.conftest import MODEL_KEY, SEARCH_KEY

    return TrackerSecrets(MODEL_KEY, SEARCH_KEY, verifier_url=VERIFIER, verifier_token=TOKEN)


def mock_run():
    respx.post(LLM_URL).mock(
        side_effect=FakeModel(*scout_script(), *curate_script(), *edit_script())
    )
    respx.post(SEARCH_URL).respond(200, json=search_body(EVIDENCE))
    mock_boards()


@respx.mock
def test_verify_runs_after_rank_and_unchanged_records_are_not_resent(vpolicy):
    mock_run()
    fake = FakeVerifier()
    first = run(vpolicy, keys(), fake, "run-1")
    assert first.status == "complete", first.message
    stages = [s["name"] for s in read_trace(first.trace_path)[-1]["stages"]]
    assert stages == ["scout", "collect", "curate", "liveness", "rank", "verify", "edit"]
    assert len(fake.requests) == 2  # Acme and Gamma, one request each
    report = first.report_path.read_text()
    assert "supported" in report and "> Summer 2027" in report

    respx.routes.clear()
    respx.post(LLM_URL).mock(side_effect=FakeModel(*[]))
    respx.post(SEARCH_URL).respond(200, json=search_body(EVIDENCE))
    mock_boards(acme=lambda r: httpx.Response(304), gamma=lambda r: httpx.Response(304))
    run(vpolicy, keys(), fake, "run-2")
    assert len(fake.requests) == 2


@respx.mock
def test_verifier_down_is_a_partial_run(vpolicy):
    mock_run()
    fake = FakeVerifier(*[httpx.ConnectError("refused")] * 20)
    result = run(vpolicy, keys(), fake, "run-1")
    assert result.status == "partial" and result.exit_code == 2
    report = result.report_path.read_text()
    assert "verifier" in report and "unverified" in report
    stages = {s["name"]: s for s in read_trace(result.trace_path)[-1]["stages"]}
    assert stages["verify"]["outcome"] == "partial" and stages["edit"]["outcome"] == "complete"
    state, store = open_store(vpolicy.state_file)
    assert store.failed_services("run-1") == ["verifier"]
    state.close()


@respx.mock
def test_missing_url_fails_soft(vpolicy):
    from tests_tracker.conftest import MODEL_KEY, SEARCH_KEY

    mock_run()
    result = run(vpolicy, TrackerSecrets(MODEL_KEY, SEARCH_KEY), FakeVerifier(), "run-1")
    assert result.status == "partial" and "verifier" in result.message


def test_no_verifier_configured(tmp_path):
    policy = policy_from_dict(policy_data(), tmp_path)
    assert "verify" not in [s.name for s in wiring.stages(policy)]


def test_verifier_share_must_fit_the_run(tmp_path):
    policy = policy_from_dict(policy_data(options={"verifier": {"max_requests": 50}}), tmp_path)
    with pytest.raises(PolicyError, match="agents and verifier add up"):
        wiring.validate(policy)
