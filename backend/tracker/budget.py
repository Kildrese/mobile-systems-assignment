"""Run budgets: checked in code before every model call and every tool call."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from tracker.config import Policy


@dataclass
class Budget:
    policy: Policy
    clock: Callable[[], float] = time.monotonic
    started: float = field(init=False)
    steps: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    searches: int = 0
    fetches: int = 0
    credits: float = 0.0

    def __post_init__(self) -> None:
        self.started = self.clock()

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self) -> float:
        provider = self.policy.provider
        return (
            self.prompt_tokens * provider.price_per_mtok_in / 1_000_000
            + self.completion_tokens * provider.price_per_mtok_out / 1_000_000
            + self.credits * self.policy.search.price_per_credit
        )

    @property
    def elapsed(self) -> float:
        return self.clock() - self.started

    @property
    def deadline(self) -> float:
        """The wall-clock deadline on the same clock, for retry waits."""
        return self.started + self.policy.limits.max_wall_seconds

    def check_model_call(self) -> str | None:
        """The name of the exhausted budget, or None when a model call may proceed."""
        limits = self.policy.limits
        if self.steps >= limits.max_steps:
            return "max_steps"
        if self.total_tokens >= limits.max_tokens - limits.reserve:
            return "max_tokens"
        if self.cost_usd >= limits.max_cost_usd:
            return "max_cost_usd"
        if self.elapsed >= limits.max_wall_seconds:
            return "max_wall_seconds"
        return None

    def check_tool(self, name: str) -> str | None:
        """The name of the exhausted budget, or None when the tool call may proceed."""
        limits = self.policy.limits
        if name == "search_web":
            if self.searches >= limits.max_searches:
                return "max_searches"
            if self.cost_usd + self.policy.search.price_per_credit > limits.max_cost_usd:
                return "max_cost_usd"
        if name == "fetch_article" and self.fetches >= limits.max_fetches:
            return "max_fetches"
        if self.elapsed >= limits.max_wall_seconds:
            return "max_wall_seconds"
        return None

    def can_synthesize(self) -> bool:
        """Whether the reserved final synthesis call still fits the token, cost and time budgets."""
        limits = self.policy.limits
        return (
            self.total_tokens + self.policy.model.max_output_tokens < limits.max_tokens
            and self.cost_usd < limits.max_cost_usd
            and self.elapsed < limits.max_wall_seconds
        )

    def remaining_tokens(self) -> int:
        return max(0, self.policy.limits.max_tokens - self.total_tokens)

    def charge_tokens(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion

    def usage(self) -> dict[str, float | int]:
        return {
            "steps": self.steps,
            "searches": self.searches,
            "fetches": self.fetches,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "credits": self.credits,
            "cost_usd": round(self.cost_usd, 6),
            "wall_seconds": round(self.elapsed, 2),
        }
