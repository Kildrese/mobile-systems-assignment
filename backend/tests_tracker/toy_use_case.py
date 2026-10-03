"""A toy use case for the conductor tests: one tool, generic agent and code stages."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from tracker.conductor import StageContext, StageOutcome
from tracker.tools import ToolOutcome, ToolSpec, register


class EchoArgs(BaseModel):
    text: str


register(
    ToolSpec(
        "echo",
        EchoArgs,
        {"type": "function", "function": {"name": "echo", "description": "Echo text back."}},
        lambda toolbox, args, step: ToolOutcome("ok", {"echo": args.text}),
        cli=True,
    )
)


def accept_anything(args: dict[str, Any], step: int, toolbox: Any, trace: Any):
    return "", args


@dataclass
class AgentStage:
    name: str
    agent: str
    required: bool = False
    kind = "agent"
    providers = frozenset()

    def run(self, ctx: StageContext) -> StageOutcome:
        stop, _ = ctx.run_agent("Do your job, then call finish.", finish=accept_anything)
        return StageOutcome.from_stop(stop)


@dataclass
class CodeStage:
    name: str
    work: Callable[[StageContext], None] = lambda ctx: None
    required: bool = False
    kind = "code"
    agent = None
    providers = frozenset()

    def run(self, ctx: StageContext) -> StageOutcome:
        self.work(ctx)
        return StageOutcome("complete")


def stages(policy: Any) -> list[Any]:
    return [AgentStage("scout", "scout"), CodeStage("note")]
