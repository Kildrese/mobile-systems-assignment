"""agent-orchestration: profiles, two-level budgets, privileges, trace binding, conductor."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx
import yaml

from tests_tracker import toy_use_case
from tests_tracker.conftest import (
    BASE_POLICY,
    LLM_URL,
    MODEL_KEY,
    PUBLIC_IP,
    SEARCH_KEY,
    SEARCH_URL,
    chat_body,
    deep_merge,
    read_trace,
    resolver_for,
    search_body,
    tool_call,
)
from tests_tracker.test_fetch import HTML, PAGE
from tests_tracker.test_loop import FakeModel
from tests_tracker.test_run_cli import (  # noqa: F401
    BACKEND,
    config_for,
    providers,
    report_and_trace,
)
from tests_tracker.toy_use_case import AgentStage, CodeStage
from tracker import conductor, tools
from tracker.budget import Budget
from tracker.config import TrackerSecrets, policy_from_dict
from tracker.errors import PolicyError, TerminalError
from tracker.trace import Trace

LLM2_URL = "https://llm2.test/v1/chat/completions"
OTHER_KEY = "sk-other-provider-key-555"
DOCS = BACKEND.parent / "docs" / "tracker.md"

AGENTS = {
    "scout": {
        "tools": ["search_web"],
        "limits": {"max_steps": 3, "max_tokens": 8000, "max_searches": 2},
        "instructions": "You scout {topic}.",
    },
    "reader": {
        "tools": ["fetch_article"],
        "limits": {"max_steps": 3, "max_tokens": 8000, "max_fetches": 2},
        "instructions": "You read pages.",
        "model": {"name": "reader-model"},
    },
    "writer": {
        "tools": [],
        "limits": {"max_steps": 2, "max_tokens": 3000},
        "instructions": "You write.",
        "model": {"provider": "other"},
    },
}
OTHER_PROVIDER = {
    "base_url": "https://llm2.test/v1",
    "key_env": "FAKE_LLM2_KEY",
    "price_per_mtok_in": 0,
    "price_per_mtok_out": 0,
}


def multi(**overrides):
    return deep_merge({"agents": AGENTS, "providers": {"other": OTHER_PROVIDER}}, overrides)


def invalid(tmp_path, **overrides) -> str:
    with pytest.raises(PolicyError) as err:
        policy_from_dict(deep_merge(BASE_POLICY, multi(**overrides)), tmp_path)
    return str(err.value)


@pytest.fixture
def mpolicy(make_policy):
    return make_policy(**multi())


@pytest.fixture
def mkeys():
    return TrackerSecrets(MODEL_KEY, SEARCH_KEY, {"other": OTHER_KEY})


def finish(call_id="cf"):
    return chat_body(tool_call("finish", {"done": True}, call_id))


def run(policy, keys, stages, **kwargs):
    return conductor.run(
        policy,
        keys,
        stages,
        run_id="multi-run",
        resolver=resolver_for(PUBLIC_IP),
        sleep=lambda _: None,
        **kwargs,
    )


# Profiles and validation


def test_profile_inherits_model_fields(make_policy):
    policy = make_policy(model={"temperature": 0.3}, **multi())
    reader = policy.agents["reader"].model
    assert (reader.provider, reader.name, reader.temperature) == ("fake", "reader-model", 0.3)
    assert reader.max_output_tokens == policy.model.max_output_tokens
    assert policy.agents["writer"].model.provider == "other"


def test_profile_validation(tmp_path):
    assert "tools: Extra inputs are not permitted" in invalid(tmp_path, tools=["send_email"])
    message = invalid(tmp_path, agents={"scout": {"tools": ["search_web", "send_email"]}})
    assert "agents.scout.tools" in message and "send_email" in message
    assert "lowercase identifier" in invalid(tmp_path, agents={"Bad-Name": AGENTS["writer"]})
    message = invalid(
        tmp_path,
        fetch={"allowed_hosts": ["*.example.com"]},
        agents={"reader": {"fetch_hosts": ["jobs.example.com", "other.example.org"]}},
    )
    assert "agents.reader.fetch_hosts: other.example.org" in message
    assert "jobs.example.com" not in message.split("fetch_hosts:")[1]
    message = invalid(tmp_path, limits={"max_tokens": 18000})
    assert "limits.max_tokens: enabled agents add up to 19,000, more than 18,000" in message
    assert "agents.writer.model.provider 'gone'" in invalid(
        tmp_path, agents={"writer": {"model": {"provider": "gone"}}}
    )
    assert "max_searches is required" in invalid(
        tmp_path, agents={"writer": {"tools": ["search_web"]}}
    )


def test_disabled_agents_do_not_count(make_policy):
    policy = make_policy(
        limits={"max_tokens": 12000}, **multi(agents={"scout": {"enabled": False}})
    )
    assert not policy.agents["scout"].enabled


def test_unknown_use_case(tmp_path):
    assert "use_case 'nope' is not a known use case" in invalid(tmp_path, use_case="nope")


def test_keys_for_every_agent_provider(mpolicy, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_LLM_KEY", MODEL_KEY)
    monkeypatch.setenv("FAKE_SEARCH_KEY", SEARCH_KEY)
    monkeypatch.delenv("FAKE_LLM2_KEY", raising=False)
    with pytest.raises(PolicyError, match="FAKE_LLM2_KEY is not set"):
        TrackerSecrets.load(mpolicy, env_file=tmp_path / "none")
    monkeypatch.setenv("FAKE_LLM2_KEY", OTHER_KEY)
    keys = TrackerSecrets.load(mpolicy, env_file=tmp_path / "none")
    assert keys.key_for("other") == OTHER_KEY and keys.key_for("fake") == MODEL_KEY
    assert OTHER_KEY in keys.values()


# Budgets


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def test_agent_limit_hit_first(mpolicy):
    budget = Budget(mpolicy, Clock())
    scout = budget.child("scout", mpolicy.agents["scout"].limits)
    scout.count(steps=3, searches=2)
    assert scout.check_model_call() == "scout.max_steps"
    assert scout.check_tool("search_web") == "scout.max_searches"
    assert budget.check_model_call() is None
    assert (budget.steps, budget.searches) == (3, 2)


def test_global_limit_hit_first(mpolicy):
    budget = Budget(mpolicy, Clock())
    budget.charge_tokens(mpolicy.limits.max_tokens - mpolicy.limits.reserve_tokens, 0)
    reader = budget.child("reader", mpolicy.agents["reader"].limits)
    assert reader.check_model_call() == "max_tokens"


def test_both_levels_charged_wall_and_cost_global(make_policy):
    policy = make_policy(
        **multi(providers={"other": {"price_per_mtok_in": 1000.0}}), limits={"max_cost_usd": 0.5}
    )
    clock = Clock()
    budget = Budget(policy, clock)
    writer = budget.child("writer", policy.agents["writer"].limits)
    writer.charge_tokens(500, 100, policy.providers["other"])
    assert (writer.total_tokens, budget.total_tokens) == (600, 600)
    assert budget.cost_usd == writer.cost_usd == 0.5
    assert writer.check_model_call() == "max_cost_usd"  # cost has no agent level
    fresh = Budget(policy, clock)
    clock.now = policy.limits.max_wall_seconds
    assert fresh.child("scout", policy.agents["scout"].limits).check_model_call() == (
        "max_wall_seconds"
    )


# Privileges


@respx.mock
def test_tool_outside_profile_is_unknown(mpolicy, mkeys):
    model = FakeModel(chat_body(tool_call("fetch_article", {"url": "https://e.com/"})), finish())
    respx.post(LLM_URL).mock(side_effect=model)
    page = respx.get(url__regex=r".*").respond(200)

    result = run(mpolicy, mkeys, [AgentStage("scout", "scout")])

    assert not page.called
    reply = model.requests[1]["messages"][-1]
    assert "unknown_tool" in reply["content"]
    assert "Allowed tools: search_web, finish" in reply["content"]
    summary = read_trace(result.trace_path)[-1]
    assert summary["stages"][0]["usage"]["steps"] == 3  # two model calls and the bad call


@respx.mock
def test_agent_fetch_hosts(make_policy, keys):
    policy = make_policy(**multi(agents={"reader": {"fetch_hosts": ["jobs.example.com"]}}))
    route = respx.get(url__regex=r".*").respond(200, headers=HTML, content=PAGE)
    hosts = policy.agents["reader"].fetch_hosts
    toolbox = tools.Toolbox(
        policy,
        Trace(None, "r"),
        "r",
        state=None,
        resolver=resolver_for("10.0.0.5"),
        fetch_hosts=hosts,
    )
    off = toolbox.fetch_article("https://other.example.org/")
    assert (off.status, off.reason) == ("blocked", "host_not_allowed")
    on = toolbox.fetch_article("https://jobs.example.com/")
    assert (on.status, on.reason) == ("blocked", "blocked_address")  # core checks still run
    assert not route.called
    toolbox.resolver = resolver_for(PUBLIC_IP)
    assert toolbox.fetch_article("https://jobs.example.com/").ok


# Trace


def test_bound_trace(tmp_path):
    path = tmp_path / "t.jsonl"
    trace = Trace(path, "r", [MODEL_KEY])
    trace.bind(stage="scan", agent="scout").event("tool", detail=f"key {MODEL_KEY}")
    trace.bind(stage="store").event("tool", status="ok")
    first, second = read_trace(path)
    assert (first["stage"], first["agent"]) == ("scan", "scout")
    assert MODEL_KEY not in path.read_text()
    assert second["stage"] == "store" and "agent" not in second


# Conductor


@respx.mock
def test_all_complete(mpolicy, mkeys):
    respx.post(LLM_URL).mock(side_effect=FakeModel(finish(), finish()))
    respx.post(LLM2_URL).mock(side_effect=FakeModel(finish()))
    stages = [
        AgentStage("scan", "scout"),
        CodeStage("store"),
        AgentStage("read", "reader"),
        AgentStage("write", "writer"),
    ]

    result = run(mpolicy, mkeys, stages)

    assert (result.status, result.exit_code) == ("complete", 0)
    events = read_trace(result.trace_path)
    summary = events[-1]
    assert [(s["name"], s["outcome"]) for s in summary["stages"]] == [
        ("scan", "complete"),
        ("store", "complete"),
        ("read", "complete"),
        ("write", "complete"),
    ]
    assert summary["stages"][0]["usage"]["steps"] == 1 and summary["steps"] == 3
    for event in events[:-1]:
        if event["kind"] in ("model", "tool"):
            assert event["stage"] in ("scan", "read", "write") and event["agent"]
    assert "| store |  | complete |" in result.report_path.read_text()


@respx.mock
def test_agent_limit_partial_and_later_stages_run(make_policy, mkeys):
    policy = make_policy(**multi(agents={"scout": {"limits": {"max_steps": 1}}}))
    model = FakeModel(chat_body(tool_call("search_web", {"query": "q"})), finish())
    respx.post(LLM_URL).mock(side_effect=model)
    respx.post(SEARCH_URL).respond(json=search_body("https://e.com/1"))

    result = run(policy, mkeys, [AgentStage("scan", "scout"), AgentStage("read", "reader")])

    assert (result.status, result.exit_code, result.stop_reason) == (
        "partial",
        2,
        "scout.max_steps",
    )
    stages = read_trace(result.trace_path)[-1]["stages"]
    assert [(s["outcome"], s["reason"]) for s in stages] == [
        ("partial", "scout.max_steps"),
        ("complete", None),
    ]


@respx.mock
def test_terminal_failure_skips_that_provider(mpolicy, mkeys):
    fake = FakeModel(httpx.Response(429, text="Rate limit reached on requests per day (RPD)"))
    respx.post(LLM_URL).mock(side_effect=fake)
    respx.post(LLM2_URL).mock(side_effect=FakeModel(finish()))
    ran = []
    stages = [
        AgentStage("scan", "scout"),
        CodeStage("store", lambda ctx: ran.append("store")),
        AgentStage("read", "reader"),
        AgentStage("write", "writer"),
    ]

    result = run(mpolicy, mkeys, stages)

    assert (result.status, result.exit_code) == ("partial", 2)
    assert ran == ["store"]
    assert len(fake.requests) == 1
    stages = read_trace(result.trace_path)[-1]["stages"]
    assert [(s["outcome"], s["reason"]) for s in stages] == [
        ("partial", "terminal:quota"),
        ("complete", None),
        ("skipped", "terminal:quota"),
        ("complete", None),
    ]
    assert result.report_path.is_file()


@respx.mock
def test_required_code_stage_failure(mpolicy, mkeys):
    def boom(ctx):
        raise TerminalError("fake", "auth", "fake rejected the API key")

    stages = [CodeStage("store", boom, required=True), CodeStage("after")]

    result = run(mpolicy, mkeys, stages)

    assert (result.status, result.exit_code) == ("failed", 3)
    text = result.report_path.read_text()
    assert "| store |  | failed |" in text and "fake rejected the API key" in text
    assert "stage store failed" in result.message


@respx.mock
def test_disabled_stage_is_skipped(make_policy, mkeys):
    policy = make_policy(**multi(agents={"writer": {"enabled": False}}))
    respx.post(LLM_URL).mock(side_effect=FakeModel(finish()))
    stages = [AgentStage("scan", "scout"), CodeStage("store"), AgentStage("write", "writer")]

    result = run(policy, mkeys, stages)

    assert result.status == "complete"
    assert read_trace(result.trace_path)[-1]["stages"][2] | {"usage": None} == {
        "name": "write",
        "agent": "writer",
        "outcome": "skipped",
        "reason": "disabled",
        "usage": None,
    }
    with pytest.raises(PolicyError, match="required stage write"):
        run(policy, mkeys, [AgentStage("write", "writer", required=True)])


@respx.mock
def test_no_transcript_leaks_between_agents(mpolicy, mkeys):
    model = FakeModel(
        chat_body(tool_call("search_web", {"query": "q"}), content="scout musing"),
        finish(),
        finish(),
    )
    respx.post(LLM_URL).mock(side_effect=model)
    respx.post(SEARCH_URL).respond(json=search_body("https://e.com/scouted"))

    run(mpolicy, mkeys, [AgentStage("scan", "scout"), AgentStage("read", "reader")])

    first_of_reader = model.requests[2]
    assert first_of_reader["model"] == "reader-model"
    assert [m["role"] for m in first_of_reader["messages"]] == ["system", "user"]
    text = json.dumps(first_of_reader)
    assert "scouted" not in text and "scout musing" not in text and "You scout" not in text


# Tool registry and command lines


def test_registered_tool_runs_from_cli(write_config, capsys):
    assert tools.main(["--config", str(write_config()), "echo", "hello"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "echo": "hello"}


PATCHED_MAIN = (
    "import sys; from tracker import config; "
    "config.USE_CASES['toy'] = 'tests_tracker.toy_use_case'; "
    "from tracker.__main__ import main; sys.exit(main(sys.argv[1:]))"
)


def run_patched(config: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k.lower() not in ("http_proxy", "https_proxy")}
    env.update(FAKE_LLM_KEY=MODEL_KEY, FAKE_SEARCH_KEY=SEARCH_KEY, NO_PROXY="*")
    return subprocess.run(
        [sys.executable, "-c", PATCHED_MAIN, "run", "--config", str(config)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


def test_run_routes_to_conductor(providers, write_config):  # noqa: F811
    providers.chat_replies = [(200, finish())]
    config = config_for(write_config, providers.url)
    data = yaml.safe_load(config.read_text())
    data.update(use_case="toy", agents={"scout": AGENTS["scout"]})
    config.write_text(yaml.safe_dump(data))

    result = run_patched(config)

    assert result.returncode == 0, result.stdout + result.stderr
    report, trace = report_and_trace(result)
    assert [s["name"] for s in trace[-1]["stages"]] == ["scout", "note"]
    assert "| scout | scout | complete |" in report


def test_run_rejects_unknown_use_case_and_half_config(write_config):
    result = run_patched(write_config(use_case="nope", agents={"scout": AGENTS["scout"]}))
    assert result.returncode == 1
    assert "use_case 'nope' is not a known use case" in result.stderr
    result = run_patched(write_config(agents={"scout": AGENTS["scout"]}))
    assert result.returncode == 1
    assert "agents and use_case must be set together" in result.stderr
    assert "Traceback" not in result.stderr


# Docs


def test_docs_example_validates(tmp_path):
    block = re.search(r"<!-- agents-example -->\n```yaml\n(.*?)```", DOCS.read_text(), re.S)
    assert block, "docs/tracker.md lost its multi-agent example"
    example = yaml.safe_load(block.group(1))
    del example["use_case"]  # a placeholder: no use case is built in yet
    policy = policy_from_dict(deep_merge(BASE_POLICY, example), tmp_path)
    assert set(policy.agents) == {"scout", "reader"}


assert toy_use_case  # imported for its `echo` registration


def test_provider_failure_decides_the_status_over_an_earlier_budget_stop():
    stages = [CodeStage("a"), CodeStage("b")]
    budget_stop = conductor.StageOutcome("partial", "scout.max_steps", stage="a")
    failure = TerminalError("groq", "quota", "daily quota")
    terminal = conductor.StageOutcome("partial", "terminal:quota", terminal=failure, stage="b")
    status, decider = conductor.run_status(stages, [budget_stop, terminal])
    assert (status, decider) == ("partial", terminal)
    assert conductor.run_status(stages, [budget_stop])[1] is budget_stop
