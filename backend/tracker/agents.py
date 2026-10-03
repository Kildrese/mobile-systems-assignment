"""One agent's loop: model call, tool calls, observations, repeated.

Code checks the budgets before every model call and every tool call. The agent sees only
its profile's tools, with fixed schemas from the registry; retrieved text reaches it only
inside untrusted data blocks. The loop ends when the finish handler accepts a `finish`
call, a budget runs out, or a provider fails for good.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from tracker.budget import Budget
from tracker.config import AgentProfile, Policy
from tracker.errors import TerminalError, WallClockExceeded
from tracker.llm import ChatClient, ModelOutputError
from tracker.tools import REGISTRY, Toolbox, ToolOutcome, validate_finish, validation_message
from tracker.trace import Trace
from tracker.untrusted import DATA_RULES, wrap

# Older tool results are shortened before each model call, to stay within per-minute
# token limits; the newest ones keep their full text.
KEEP_FULL_RESULTS = 3
SHORTENED_CHARS = 500

# (arguments, step, toolbox, trace) -> (content for the model, result or None to go on).
FinishHandler = Callable[[dict[str, Any], int, Toolbox, Trace], tuple[str, Any | None]]


@dataclass
class Stop:
    reason: str | None = None
    terminal: TerminalError | None = None
    finish: Any = None


@dataclass
class _ToolMessage:
    index: int
    source: str
    text: str
    attributes: dict[str, str]


def report_finish(k: int) -> FinishHandler:
    """The core finish handler: a ranked report citing only URLs this run has seen."""

    def handle(
        arguments: dict[str, Any], step: int, toolbox: Toolbox, trace: Trace
    ) -> tuple[str, Any | None]:
        try:
            result = validate_finish(arguments, k, toolbox.seen)
        except ValidationError as err:
            detail = validation_message(err)
            trace.event(
                "tool",
                step=step,
                tool="finish",
                args=arguments,
                status="error",
                reason="invalid_arguments",
                detail=detail,
            )
            return json.dumps({"error": "invalid_arguments", "detail": detail}), None
        trace.event(
            "tool",
            step=step,
            tool="finish",
            args=arguments,
            status="ok" if result.items else "error",
            reason=None if result.items else "no_valid_items",
            kept=len(result.items),
            dropped=result.dropped,
            truncated=result.truncated,
        )
        if not result.items:
            return json.dumps(
                {
                    "error": "no_valid_items",
                    "detail": "Every item cited only URLs this run never searched or fetched.",
                }
            ), None
        return "", result

    return handle


class AgentLoop:
    def __init__(
        self,
        policy: Policy,
        profile: AgentProfile,
        toolbox: Toolbox,
        budget: Budget,
        trace: Trace,
        chat: ChatClient,
        task_prompt: str,
        *,
        finish: FinishHandler | None = None,
        finish_schema: dict[str, Any] | None = None,
        nudge: str | None = None,
    ) -> None:
        self.policy = policy
        self.profile = profile
        self.toolbox = toolbox
        self.budget = budget
        self.trace = trace
        self.chat = chat
        self.task_prompt = task_prompt
        self.finish = finish or report_finish(policy.k)
        # `finish` is always offered: it is how an agent ends.
        self.tools = tuple(dict.fromkeys((*profile.tools, "finish")))
        self.schemas = [
            finish_schema or REGISTRY["finish"].schema
            if name == "finish"
            else REGISTRY[name].schema
            for name in self.tools
        ]
        self.nudge = nudge or (
            f"You did not call a tool. Call one of {', '.join(self.tools)}; "
            "call finish when you are done."
        )
        self.price = policy.providers[profile.model.provider]

    def system_prompt(self) -> str:
        return f"{self.policy.fill(self.profile.instructions)}\n\n{DATA_RULES}"

    def run(self) -> Stop:
        budget, trace, toolbox = self.budget, self.trace, self.toolbox
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt()},
            {"role": "user", "content": self.task_prompt},
        ]
        tool_messages: list[_ToolMessage] = []
        while True:
            if reason := budget.check_model_call():
                return Stop(reason=reason)
            budget.count(steps=1)
            step = budget.steps
            _shorten_old_results(messages, tool_messages)
            try:
                reply = self.chat.chat(messages, self.schemas, step)
            except ModelOutputError as err:
                messages.append(
                    {
                        "role": "user",
                        "content": "The provider rejected your last tool call as malformed "
                        f"({err.args[0][:200]}). Call one tool with valid JSON arguments.",
                    }
                )
                continue
            except TerminalError as err:
                return Stop(terminal=err)
            except WallClockExceeded:
                return Stop(reason="max_wall_seconds")
            budget.charge_tokens(
                reply.usage.prompt_tokens, reply.usage.completion_tokens, self.price
            )
            messages.append(reply.as_message())
            if not reply.tool_calls:
                messages.append({"role": "user", "content": self.nudge})
                continue

            for call in reply.tool_calls:
                if call.name == "finish" and call.arguments is not None:
                    content, finished = self.finish(call.arguments, step, toolbox, trace)
                    if finished is not None:
                        return Stop(finish=finished)
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
                    continue
                try:
                    outcome = self._dispatch(call.name, call.arguments, call.parse_error, step)
                except TerminalError as err:
                    return Stop(terminal=err)
                except WallClockExceeded:
                    return Stop(reason="max_wall_seconds")
                if outcome.ok and outcome.untrusted is not None:
                    content = wrap(call.name, outcome.untrusted, **outcome.attributes)
                    tool_messages.append(
                        _ToolMessage(
                            len(messages), call.name, outcome.untrusted, outcome.attributes
                        )
                    )
                else:
                    content = json.dumps(outcome.data, ensure_ascii=False)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})

    def _dispatch(
        self, name: str, arguments: dict[str, Any] | None, parse_error: str | None, step: int
    ) -> ToolOutcome:
        """Validate a tool call, check its budget and run it."""
        budget, toolbox = self.budget, self.toolbox

        def refuse(status: str, reason: str, detail: str) -> ToolOutcome:
            outcome = ToolOutcome.failure(status, reason, detail)
            self.trace.event(
                "tool",
                step=step,
                tool=name,
                args=arguments,
                status=status,
                reason=reason,
                detail=detail,
            )
            return outcome

        spec = REGISTRY.get(name) if name in self.tools else None
        if spec is None or spec.handler is None:
            budget.count(steps=1)  # an invalid call costs a step
            if name == "finish":
                return refuse("error", "invalid_arguments", parse_error or "items are required")
            return refuse(
                "error",
                "unknown_tool",
                f"'{name}' is not a tool. Allowed tools: {', '.join(self.tools)}",
            )
        if arguments is None:
            budget.count(steps=1)
            return refuse("error", "invalid_arguments", parse_error or "arguments missing")
        try:
            args = spec.args_model.model_validate(arguments)
        except ValidationError as err:
            budget.count(steps=1)
            return refuse("error", "invalid_arguments", validation_message(err))

        # A use-case tool may draw on the search or fetch budget; a cached article is free.
        kind = spec.budget or name
        cached = name == "fetch_article" and toolbox.is_cached(args.url)
        if not cached and (reason := budget.check_tool(kind)):
            return refuse("budget", "budget_exhausted", f"{reason} reached")
        outcome = spec.handler(toolbox, args, step)
        if kind == "search_web" and outcome.ok:
            budget.count(searches=1, credits=float(outcome.data.get("credits", 0)))
        elif kind == "fetch_article" and (
            outcome.status == "ok"
            or (outcome.status == "error" and outcome.reason != "invalid_arguments")
        ):
            budget.count(fetches=1)  # a request went out
        return outcome


def _shorten_old_results(messages: list[dict[str, Any]], tool_messages: list[_ToolMessage]) -> None:
    for record in tool_messages[:-KEEP_FULL_RESULTS]:
        if len(record.text) > SHORTENED_CHARS:
            shortened = record.text[:SHORTENED_CHARS] + "\n[... older result shortened ...]"
            messages[record.index]["content"] = wrap(record.source, shortened, **record.attributes)
            record.text = shortened
