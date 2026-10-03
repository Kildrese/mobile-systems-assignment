"""Client for OpenAI-compatible chat-completions APIs (Groq by default).

Raw httpx instead of a vendor SDK, so every retry happens in our code and shows up
in the trace. One call to `chat()` is one model step; retries inside it are traced
as separate attempts of the same step.
"""

import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from tracker.config import ModelSettings, Policy
from tracker.errors import send_with_retries
from tracker.trace import Trace


class ModelOutputError(Exception):
    """The provider rejected the model's own output (for example a malformed tool call).

    Not a provider failure: the loop tells the model and lets it try again.
    """


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    raw_arguments: str
    arguments: dict[str, Any] | None
    parse_error: str | None = None


@dataclass(frozen=True)
class Reply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)

    def as_message(self) -> dict[str, Any]:
        """The assistant message to append to the conversation."""
        message: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.raw_arguments},
                }
                for call in self.tool_calls
            ]
        return message


def _parse_tool_call(raw: dict[str, Any], index: int) -> ToolCall:
    function = raw.get("function") or {}
    raw_args = function.get("arguments") or "{}"
    if not isinstance(raw_args, str):
        raw_args = json.dumps(raw_args)
    try:
        args = json.loads(raw_args)
        error = None if isinstance(args, dict) else "arguments must be a JSON object"
    except json.JSONDecodeError as err:
        args, error = None, f"arguments are not valid JSON: {err.msg}"
    return ToolCall(
        id=str(raw.get("id") or f"call_{index}"),
        name=str(function.get("name") or ""),
        raw_arguments=raw_args,
        arguments=args if error is None else None,
        parse_error=error,
    )


def parse_reply(data: dict[str, Any]) -> Reply:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = data.get("usage") or {}
    return Reply(
        content=message.get("content"),
        tool_calls=[_parse_tool_call(c, i) for i, c in enumerate(message.get("tool_calls") or [])],
        usage=Usage(
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        ),
    )


def _is_model_output_error(response: httpx.Response) -> bool:
    # Groq answers 400 `tool_use_failed` when the model emitted a malformed tool call.
    return response.status_code == 400 and "tool_use_failed" in response.text


class ChatClient:
    def __init__(
        self,
        policy: Policy,
        api_key: str,
        trace: Trace,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        deadline: float | None = None,
        rng: Callable[[], float] = random.random,
        model: ModelSettings | None = None,
    ) -> None:
        self.policy = policy
        self.trace = trace
        self.model = model or policy.model
        self.provider = policy.model_provider(self.model.provider)
        self.url = policy.providers[self.model.provider].base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.Client(timeout=self.model.timeout_seconds)
        self._sleep = sleep
        self.deadline = deadline
        self._rng = rng

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        step: int,
        purpose: str = "step",
    ) -> Reply:
        model = self.model
        payload: dict[str, Any] = {
            "model": model.name,
            "messages": messages,
            "max_tokens": model.max_output_tokens,
        }
        if model.temperature is not None:
            payload["temperature"] = model.temperature
        if model.reasoning_effort is not None:
            payload["reasoning_effort"] = model.reasoning_effort
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        traced_args = {
            "purpose": purpose,
            "messages": len(messages),
            "tools": [t["function"]["name"] for t in tools or []],
        }

        def on_attempt(event: dict[str, Any]) -> None:
            self.trace.event("model", step=step, tool=model.name, args=traced_args, **event)

        response, attempt, latency_ms = send_with_retries(
            lambda: self._client.post(self.url, json=payload, headers=self._headers),
            provider=self.provider,
            retry=self.policy.retry,
            on_attempt=on_attempt,
            sleep=self._sleep,
            deadline=self.deadline,
            rng=self._rng,
            accept=_is_model_output_error,
        )
        if response.status_code >= 400:
            on_attempt(
                {
                    "status": "error",
                    "attempt": attempt,
                    "latency_ms": latency_ms,
                    "http_status": response.status_code,
                    "reason": "model_output_rejected",
                }
            )
            raise ModelOutputError(response.text[:500])
        reply = parse_reply(response.json())
        self.trace.event(
            "model",
            step=step,
            tool=model.name,
            args=traced_args,
            status="ok",
            attempt=attempt,
            latency_ms=latency_ms,
            http_status=response.status_code,
            prompt_tokens=reply.usage.prompt_tokens,
            completion_tokens=reply.usage.completion_tokens,
            total_tokens=reply.usage.total_tokens,
            result={
                "content": reply.content,
                "tool_calls": [
                    {"name": c.name, "arguments": c.raw_arguments} for c in reply.tool_calls
                ],
            },
        )
        return reply
