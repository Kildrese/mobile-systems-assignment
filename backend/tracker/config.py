"""The tracker's policy (`config.yaml`) and secrets (environment variables).

The policy is validated in full before the first network call and then frozen: nothing
during a run, neither model output nor retrieved text, can change it. Relative paths in
the policy resolve against the directory of the policy file, so the root `config.yaml`
puts reports, traces and state at the repository root.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from tracker.errors import PolicyError, Provider, RetrySettings

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
ENV_FILE = BACKEND_DIR / ".env"
CONFIG_NAME = "config.yaml"

KNOWN_TOOLS = ("search_web", "fetch_article", "finish")
REQUIRED_TOOLS = KNOWN_TOOLS
SAFE_SCHEMES = {"http", "https"}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelSettings(_Strict):
    provider: str
    name: str
    max_output_tokens: int = Field(gt=0)
    temperature: float | None = Field(default=None, ge=0, le=2)
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    timeout_seconds: float = Field(default=60, gt=0)


class ProviderSettings(_Strict):
    base_url: str
    key_env: str
    price_per_mtok_in: float = Field(ge=0)
    price_per_mtok_out: float = Field(ge=0)
    quota_patterns: tuple[str, ...] = ()


class SearchSettings(_Strict):
    provider: Literal["tavily"]
    key_env: str
    base_url: str = "https://api.tavily.com"
    max_results: int = Field(gt=0, le=20)
    depth: Literal["basic", "advanced"] = "basic"
    price_per_credit: float = Field(default=0, ge=0)
    timeout_seconds: float = Field(default=20, gt=0)
    quota_patterns: tuple[str, ...] = ()


class Limits(_Strict):
    max_steps: int = Field(gt=0)
    max_searches: int = Field(gt=0)
    max_fetches: int = Field(gt=0)
    max_tokens: int = Field(gt=0)
    # Held back from `max_tokens` for the final synthesis call of a partial report.
    # Defaults to 15% of `max_tokens`.
    reserve_tokens: int | None = Field(default=None, ge=0)
    max_cost_usd: float = Field(gt=0)
    max_wall_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def reserve_below_budget(self) -> "Limits":
        if self.reserve_tokens is not None and self.reserve_tokens >= self.max_tokens:
            raise ValueError("reserve_tokens must be smaller than max_tokens")
        return self

    @property
    def reserve(self) -> int:
        return (
            self.reserve_tokens if self.reserve_tokens is not None else self.max_tokens * 15 // 100
        )


class RetryPolicy(_Strict):
    max_attempts: int = Field(gt=0, le=10)
    base_seconds: float = Field(gt=0)
    max_wait_seconds: float = Field(gt=0)

    def settings(self) -> RetrySettings:
        return RetrySettings(self.max_attempts, self.base_seconds, self.max_wait_seconds)


class FetchSettings(_Strict):
    allowed_schemes: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    connect_timeout: float = Field(gt=0)
    read_timeout: float = Field(gt=0)
    deadline_seconds: float = Field(gt=0)
    max_bytes: int = Field(gt=0)
    max_redirects: int = Field(default=5, ge=0, le=20)
    max_chars_for_model: int = Field(gt=0)

    @field_validator("allowed_schemes")
    @classmethod
    def only_http(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        value = tuple(s.lower() for s in value)
        if not value:
            raise ValueError("at least one scheme is required")
        if unsafe := [s for s in value if s not in SAFE_SCHEMES]:
            raise ValueError(f"only http and https may be allowed, got {', '.join(unsafe)}")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def host_patterns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("at least one host pattern is required (use '*' for any)")
        for pattern in value:
            bare = pattern.removeprefix("*.")
            if pattern != "*" and (not bare or "*" in bare or "/" in bare):
                raise ValueError(f"'{pattern}' is not an exact host, '*.domain' or '*'")
        return tuple(p.lower().rstrip(".") for p in value)


class Policy(_Strict):
    topic: str = Field(min_length=1)
    k: int
    model: ModelSettings
    providers: dict[str, ProviderSettings]
    search: SearchSettings
    tools: tuple[str, ...]
    limits: Limits
    retry: RetryPolicy
    fetch: FetchSettings
    instructions: str = Field(min_length=1)
    state_path: str = ".tracker/state.sqlite"
    reports_dir: str = "reports"
    traces_dir: str = "traces"
    # The directory relative paths resolve against: the policy file's directory.
    base_dir: Path

    @field_validator("k")
    @classmethod
    def k_range(cls, value: int) -> int:
        if not 3 <= value <= 10:
            raise ValueError(f"k must be between 3 and 10, got {value}")
        return value

    @field_validator("tools")
    @classmethod
    def known_tools(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if unknown := [t for t in value if t not in KNOWN_TOOLS]:
            raise ValueError(
                f"unknown tool {', '.join(unknown)} (known tools: {', '.join(KNOWN_TOOLS)})"
            )
        if missing := [t for t in REQUIRED_TOOLS if t not in value]:
            raise ValueError(f"{', '.join(missing)} must be enabled")
        return value

    @model_validator(mode="after")
    def provider_exists(self) -> "Policy":
        if self.model.provider not in self.providers:
            raise ValueError(f"model.provider '{self.model.provider}' has no entry under providers")
        return self

    @property
    def provider(self) -> ProviderSettings:
        return self.providers[self.model.provider]

    def model_provider(self) -> Provider:
        p = self.provider
        return Provider(self.model.provider, p.key_env, p.quota_patterns)

    def search_provider(self) -> Provider:
        s = self.search
        return Provider(s.provider, s.key_env, s.quota_patterns)

    def path(self, value: str) -> Path:
        return (self.base_dir / value).resolve()

    @property
    def state_file(self) -> Path:
        return self.path(self.state_path)

    @property
    def reports_path(self) -> Path:
        return self.path(self.reports_dir)

    @property
    def traces_path(self) -> Path:
        return self.path(self.traces_dir)

    def system_prompt(self) -> str:
        # Plain replacement, so braces elsewhere in the instructions need no escaping.
        return self.instructions.replace("{topic}", self.topic).replace("{k}", str(self.k))


def find_root(start: Path = PACKAGE_DIR) -> Path:
    """The repository root: the nearest ancestor holding both `config.yaml` and `.git`."""
    for directory in (start, *start.parents):
        if (directory / CONFIG_NAME).is_file() and (directory / ".git").exists():
            return directory
    raise PolicyError(
        f"Could not find {CONFIG_NAME} next to .git above {start}. Pass --config PATH."
    )


def _format_errors(err: ValidationError) -> str:
    lines = []
    for e in err.errors():
        field = ".".join(str(part) for part in e["loc"]) or "config"
        message = e["msg"].removeprefix("Value error, ")
        lines.append(f"  {field}: {message}")
    return "\n".join(lines)


def policy_from_dict(data: Any, base_dir: Path) -> Policy:
    if not isinstance(data, dict):
        raise PolicyError("Invalid policy: the file must contain a YAML mapping.")
    if "base_dir" in data:
        raise PolicyError("Invalid policy:\n  base_dir: Extra inputs are not permitted")
    try:
        return Policy.model_validate({**data, "base_dir": base_dir})
    except ValidationError as err:
        raise PolicyError(f"Invalid policy:\n{_format_errors(err)}") from None


def load_policy(path: Path | str | None = None) -> Policy:
    """Load and validate the policy. Raises `PolicyError` naming every invalid field."""
    file = Path(path) if path is not None else find_root() / CONFIG_NAME
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
    except OSError as err:
        raise PolicyError(f"Cannot read policy file {file}: {err.strerror}") from None
    except yaml.YAMLError as err:
        raise PolicyError(f"Policy file {file} is not valid YAML: {err}") from None
    return policy_from_dict(data, file.resolve().parent)


@dataclass(frozen=True)
class TrackerSecrets:
    """API keys, read from the environment and `backend/.env`. Never from the policy.

    Kept separate from the app's settings so the tracker never requires `DATABASE_URL`.
    """

    model_key: str
    search_key: str

    @classmethod
    def load(
        cls, policy: Policy, *, model: bool = True, search: bool = True, env_file: Path = ENV_FILE
    ) -> "TrackerSecrets":
        """Read the keys the run needs. Raises `PolicyError` naming any that are missing."""
        file_values = dotenv_values(env_file) if env_file.is_file() else {}

        def read(name: str) -> str | None:
            value = os.environ.get(name) or file_values.get(name)
            return value.strip() if value and value.strip() else None

        needed: dict[str, str] = {}
        if model:
            needed["model"] = policy.provider.key_env
        if search:
            needed["search"] = policy.search.key_env
        values = {role: read(name) for role, name in needed.items()}
        if missing := [needed[role] for role, value in values.items() if value is None]:
            raise PolicyError(
                f"{', '.join(dict.fromkeys(missing))} is not set. Copy backend/.env.example "
                "to backend/.env and fill it in, or set it in the environment."
            )
        return cls(values.get("model") or "", values.get("search") or "")

    def values(self) -> list[str]:
        return [v for v in (self.model_key, self.search_key) if v]
