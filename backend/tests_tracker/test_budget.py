"""Budget checks for every exhaustion path."""

from tracker.budget import Budget


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_fresh_budget_allows_everything(policy):
    budget = Budget(policy, Clock())
    assert budget.check_model_call() is None
    assert budget.check_tool("search_web") is None
    assert budget.check_tool("fetch_article") is None


def test_steps(policy):
    budget = Budget(policy, Clock())
    budget.steps = policy.limits.max_steps
    assert budget.check_model_call() == "max_steps"


def test_tokens_stop_at_reserve(policy):
    budget = Budget(policy, Clock())
    limits = policy.limits
    budget.charge_tokens(limits.max_tokens - limits.reserve - 1, 0)
    assert budget.check_model_call() is None
    budget.charge_tokens(1, 0)
    assert budget.check_model_call() == "max_tokens"
    assert budget.can_synthesize()


def test_cost(make_policy):
    policy = make_policy(
        providers={"fake": {"price_per_mtok_in": 10.0}}, limits={"max_cost_usd": 0.01}
    )
    budget = Budget(policy, Clock())
    budget.charge_tokens(1000, 0)
    assert budget.cost_usd == 0.01
    assert budget.check_model_call() == "max_cost_usd"


def test_search_credits_count_toward_cost(make_policy):
    policy = make_policy(search={"price_per_credit": 0.2}, limits={"max_cost_usd": 0.5})
    budget = Budget(policy, Clock())
    budget.credits = 2
    assert budget.check_tool("search_web") == "max_cost_usd"


def test_wall_clock(policy):
    clock = Clock()
    budget = Budget(policy, clock)
    clock.now = policy.limits.max_wall_seconds
    assert budget.check_model_call() == "max_wall_seconds"
    assert budget.check_tool("fetch_article") == "max_wall_seconds"
    assert not budget.can_synthesize()


def test_tool_budgets(policy):
    budget = Budget(policy, Clock())
    budget.searches = policy.limits.max_searches
    budget.fetches = policy.limits.max_fetches
    assert budget.check_tool("search_web") == "max_searches"
    assert budget.check_tool("fetch_article") == "max_fetches"
    assert budget.check_model_call() is None


def test_usage_totals(policy):
    budget = Budget(policy, Clock())
    budget.charge_tokens(100, 20)
    usage = budget.usage()
    assert usage["total_tokens"] == 120
    assert set(usage) >= {"steps", "searches", "fetches", "credits", "cost_usd", "wall_seconds"}
