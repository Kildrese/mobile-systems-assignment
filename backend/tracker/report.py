"""Markdown reports: one per run, complete or partial."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STOP_REASONS = {
    "max_steps": "the step budget (limits.max_steps) ran out",
    "max_tokens": "the token budget (limits.max_tokens) ran out",
    "max_cost_usd": "the cost budget (limits.max_cost_usd) ran out",
    "max_wall_seconds": "the wall-clock budget (limits.max_wall_seconds) ran out",
}


@dataclass(frozen=True)
class ReportMeta:
    topic: str
    run_id: str
    timestamp: str
    status: str  # complete | partial
    stop_reason: str | None
    usage: dict[str, Any]
    stop_detail: str | None = None


@dataclass(frozen=True)
class Source:
    title: str
    url: str


@dataclass(frozen=True)
class ReportBody:
    items: list[dict[str, Any]] = field(default_factory=list)
    note: str | None = None
    # For a report built by code alone: the sources gathered, without summaries.
    sources: list[Source] = field(default_factory=list)


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def describe_stop(reason: str | None, detail: str | None = None) -> str:
    text = STOP_REASONS.get(reason or "", reason or "unknown")
    return f"{text}: {detail}" if detail else text


def render(meta: ReportMeta, body: ReportBody) -> str:
    status = meta.status
    if status == "partial":
        status += f" (stopped because {describe_stop(meta.stop_reason, meta.stop_detail)})"
    u = meta.usage
    lines = [
        f"# Tracker report: {_one_line(meta.topic)}",
        "",
        f"- **Run:** `{meta.run_id}`",
        f"- **Time:** {meta.timestamp}",
        f"- **Status:** {status}",
        (
            f"- **Budget used:** {u.get('steps', 0)} steps, {u.get('searches', 0)} searches, "
            f"{u.get('fetches', 0)} fetches, {u.get('total_tokens', 0)} tokens, "
            f"{u.get('credits', 0):g} search credits, ${u.get('cost_usd', 0):.4f}, "
            f"{u.get('wall_seconds', 0)} s"
        ),
        "",
    ]
    if body.items:
        lines += ["## Top developments", ""]
        for rank, item in enumerate(body.items, start=1):
            lines.append(f"### {rank}. {_one_line(item['title'])}")
            lines += ["", _one_line(item["summary"]), ""]
            lines += [f"- <{url}>" for url in item["sources"]]
            lines.append("")
    if body.sources:
        lines += [
            "## Sources gathered",
            "",
            "No summaries: this report was built by code from the evidence gathered before "
            "the run stopped.",
            "",
        ]
        lines += [f"- [{_one_line(s.title) or s.url}](<{s.url}>)" for s in body.sources]
        lines.append("")
    if not body.items and not body.sources:
        lines += ["No evidence was gathered before the run stopped.", ""]
    if body.note:
        lines += ["## Note", "", body.note.strip(), ""]
    return "\n".join(lines)


def write(path: Path, markdown: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path
