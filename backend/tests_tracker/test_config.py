"""tracker-config: policy validation, root discovery and secrets."""

from pathlib import Path

import pytest

from tests_tracker.conftest import BASE_POLICY, deep_merge
from tracker.config import CONFIG_NAME, TrackerSecrets, find_root, load_policy, policy_from_dict
from tracker.errors import PolicyError

REPO_ROOT = Path(__file__).resolve().parents[2]


def invalid(tmp_path: Path, **overrides) -> str:
    with pytest.raises(PolicyError) as err:
        policy_from_dict(deep_merge(BASE_POLICY, overrides), tmp_path)
    return str(err.value)


def test_valid_policy_loads(policy):
    assert policy.k == 3
    assert policy.limits.reserve == 3000
    assert policy.system_prompt() == (
        "You track Open-source robotics foundation models. Report the top 3 developments."
    )


def test_policy_is_frozen(policy):
    with pytest.raises(ValueError):
        policy.k = 9
    with pytest.raises(ValueError):
        policy.limits.max_steps = 1000


def test_k_out_of_range(tmp_path):
    assert "k must be between 3 and 10" in invalid(tmp_path, k=12)
    assert "k must be between 3 and 10" in invalid(tmp_path, k=2)


def test_missing_limit_is_named(tmp_path):
    data = deep_merge(BASE_POLICY, {})
    del data["limits"]["max_fetches"]
    with pytest.raises(PolicyError, match=r"limits\.max_fetches: Field required"):
        policy_from_dict(data, tmp_path)


def test_limits_must_be_positive(tmp_path):
    assert "limits.max_steps" in invalid(tmp_path, limits={"max_steps": 0})
    assert "limits.max_cost_usd" in invalid(tmp_path, limits={"max_cost_usd": -1})


def test_unknown_tool(tmp_path):
    message = invalid(tmp_path, tools=["search_web", "fetch_article", "finish", "send_email"])
    assert "unknown tool send_email" in message


def test_required_tool_disabled(tmp_path):
    assert "finish must be enabled" in invalid(tmp_path, tools=["search_web", "fetch_article"])


def test_unsafe_scheme(tmp_path):
    message = invalid(tmp_path, fetch={"allowed_schemes": ["https", "file"]})
    assert "fetch.allowed_schemes" in message
    assert "only http and https" in message


def test_wrong_type_and_typo_rejected(tmp_path):
    assert "limits.max_steps" in invalid(tmp_path, limits={"max_steps": "many"})
    assert "max_stepz" in invalid(tmp_path, limits={"max_stepz": 3})


def test_every_invalid_field_is_named(tmp_path):
    message = invalid(tmp_path, k=40, tools=["search_web", "fetch_article", "finish", "rm"])
    assert "k:" in message
    assert "tools:" in message


def test_model_provider_must_exist(tmp_path):
    assert "has no entry under providers" in invalid(tmp_path, model={"provider": "nope"})


def test_paths_resolve_against_config_dir(write_config, tmp_path):
    policy = load_policy(write_config())
    assert policy.state_file == tmp_path / ".tracker" / "state.sqlite"
    assert policy.reports_path == tmp_path / "reports"
    assert policy.traces_path == tmp_path / "traces"


def test_explicit_path_ignores_root_config(write_config):
    policy = load_policy(write_config(topic="Something else"))
    assert policy.topic == "Something else"


def test_unreadable_and_invalid_yaml(tmp_path):
    with pytest.raises(PolicyError, match="Cannot read policy file"):
        load_policy(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("topic: [unclosed")
    with pytest.raises(PolicyError, match="not valid YAML"):
        load_policy(bad)


def test_default_location_is_repo_root():
    assert find_root() == REPO_ROOT
    assert (REPO_ROOT / CONFIG_NAME).is_file()


def test_committed_config_is_valid():
    policy = load_policy()
    assert policy.model.provider == "groq"
    assert policy.model.name == "openai/gpt-oss-120b"
    assert set(policy.tools) == {"search_web", "fetch_article", "finish"}
    assert policy.state_file == REPO_ROOT / ".tracker" / "state.sqlite"


def test_policy_fixed_for_run(write_config):
    path = write_config()
    policy = load_policy(path)
    path.write_text(path.read_text().replace("k: 3", "k: 9"))
    assert policy.k == 3


# Secrets


def test_secrets_from_environment(policy, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_LLM_KEY", "llm-key")
    monkeypatch.setenv("FAKE_SEARCH_KEY", "search-key")
    keys = TrackerSecrets.load(policy, env_file=tmp_path / "none.env")
    assert keys == TrackerSecrets("llm-key", "search-key")


def test_secrets_from_env_file(policy, monkeypatch, tmp_path):
    monkeypatch.delenv("FAKE_LLM_KEY", raising=False)
    monkeypatch.delenv("FAKE_SEARCH_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("FAKE_LLM_KEY=from-file\nFAKE_SEARCH_KEY=also-file\n")
    assert TrackerSecrets.load(policy, env_file=env).model_key == "from-file"


def test_missing_key_message(policy, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_LLM_KEY", "llm-key")
    monkeypatch.setenv("FAKE_SEARCH_KEY", "  ")
    with pytest.raises(PolicyError) as err:
        TrackerSecrets.load(policy, env_file=tmp_path / "none.env")
    assert "FAKE_SEARCH_KEY is not set" in str(err.value)
    assert "backend/.env.example" in str(err.value)


def test_secrets_do_not_need_database_url(policy, monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FAKE_LLM_KEY", "a")
    monkeypatch.setenv("FAKE_SEARCH_KEY", "b")
    TrackerSecrets.load(policy, env_file=tmp_path / "none.env")


def test_env_example_lists_keys_without_values():
    lines = (REPO_ROOT / "backend" / ".env.example").read_text().splitlines()
    assert "GROQ_API_KEY=" in lines
    assert "TAVILY_API_KEY=" in lines
