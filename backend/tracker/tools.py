"""The tracker's tools: `search_web`, `fetch_article` and `finish`.

Each tool validates its arguments, returns errors as results with a machine-readable
reason (so the model can choose another action), and raises only for a terminal
provider failure. Each also runs without the model:

    uv run python -m tracker.tools search_web "open-source robotics foundation model"
    uv run python -m tracker.tools fetch_article https://example.com/
    uv run python -m tracker.tools finish report.json
"""

import argparse
import json
import socket
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from tracker import report
from tracker.config import Policy, TrackerSecrets, load_policy
from tracker.errors import PolicyError, StateLocked, TerminalError
from tracker.fetch import FetchError, fetch_page
from tracker.guard import Blocked, Resolver, check
from tracker.search import SearchClient, SearchResult
from tracker.state import StateStore, canonicalize
from tracker.trace import Trace
from tracker.untrusted import injection_suspected

MAX_QUERY_CHARS = 400


# Argument schemas


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SearchArgs(_Args):
    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)


class FetchArgs(_Args):
    url: str = Field(min_length=1, max_length=2048)


class ReportItem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    rank: int | None = None
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=2000)
    sources: list[str] = Field(min_length=1, max_length=10)

    @field_validator("sources")
    @classmethod
    def strip_sources(cls, value: list[str]) -> list[str]:
        return [s.strip() for s in value if s.strip()]


class FinishArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    items: list[ReportItem] = Field(min_length=1, max_length=50)
    note: str | None = Field(default=None, max_length=2000)


ARG_MODELS: dict[str, type[BaseModel]] = {
    "search_web": SearchArgs,
    "fetch_article": FetchArgs,
    "finish": FinishArgs,
}

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "search_web": {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web. Returns results with title, url and snippet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query, at most 400 chars"}
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    "fetch_article": {
        "type": "function",
        "function": {
            "name": "fetch_article",
            "description": "Download a web page and return its title and readable text.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "http(s) URL"}},
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
    "finish": {
        "type": "function",
        "function": {
            "name": "finish",
            "description": (
                "Submit the final ranked report and end the run. Every source must be a URL "
                "returned by search_web or fetched with fetch_article in this run."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "Ranked developments, most important first",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "summary": {"type": "string", "description": "2-4 sentences"},
                                "sources": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["title", "summary", "sources"],
                        },
                    },
                    "note": {"type": "string", "description": "Optional overall note"},
                },
                "required": ["items"],
            },
        },
    },
}


def validation_message(err: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in err.errors()
    )


# Results


@dataclass
class ToolOutcome:
    status: str  # ok | cached | error | blocked | budget
    data: dict[str, Any]
    reason: str | None = None
    # Retrieved text for the model, wrapped as untrusted data by the loop.
    untrusted: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "cached")

    @classmethod
    def failure(cls, status: str, reason: str, detail: str) -> "ToolOutcome":
        return cls(status, {"error": reason, "detail": detail}, reason=reason)


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    text: str


@dataclass
class FinishResult:
    items: list[dict[str, Any]]
    note: str | None
    dropped: list[dict[str, Any]]
    truncated: int


def validate_finish(raw: dict[str, Any], k: int, seen: set[str] | None = None) -> FinishResult:
    """Validate a `finish` report: drop unseen sources and items left without any, keep top K.

    `seen` holds the canonical URLs this run searched or fetched. None skips that check
    (the command-line `finish`, which has no run).
    """
    args = FinishArgs.model_validate(raw)
    ordered = sorted(
        enumerate(args.items),
        key=lambda pair: (pair[1].rank if pair[1].rank is not None else pair[0] + 1, pair[0]),
    )
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for _, item in ordered:
        sources = [s for s in item.sources if seen is None or canonicalize(s) in seen]
        if not sources:
            dropped.append(
                {"title": item.title, "sources": item.sources, "reason": "unseen_source"}
            )
            continue
        kept.append({"title": item.title, "summary": item.summary, "sources": sources})
    truncated = max(0, len(kept) - k)
    return FinishResult(kept[:k], args.note, dropped, truncated)


class Toolbox:
    """Runs tools for one run (or one command-line call) and traces each call."""

    def __init__(
        self,
        policy: Policy,
        trace: Trace,
        run_id: str,
        *,
        state: StateStore | None,
        search_client: SearchClient | None = None,
        resolver: Resolver = socket.getaddrinfo,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.policy = policy
        self.trace = trace
        self.run_id = run_id
        self.state = state
        self.search_client = search_client
        self.resolver = resolver
        self.transport = transport
        self.seen: set[str] = set()
        self.articles: list[Article] = []
        self.search_results: list[SearchResult] = []

    def _trace(
        self, step: int, tool: str, args: dict, outcome: ToolOutcome, started: float, **extra: Any
    ) -> None:
        self.trace.event(
            "tool",
            step=step,
            tool=tool,
            args=args,
            status=outcome.status,
            reason=outcome.reason,
            latency_ms=round((time.monotonic() - started) * 1000, 1),
            **extra,
        )

    def search_web(self, query: str, step: int = 0) -> ToolOutcome:
        started = time.monotonic()
        try:
            args = SearchArgs(query=query)
        except ValidationError as err:
            outcome = ToolOutcome.failure("error", "invalid_arguments", validation_message(err))
            self._trace(step, "search_web", {"query": query}, outcome, started)
            return outcome
        if self.search_client is None:
            raise RuntimeError("search_web needs a search client")
        response = self.search_client.search(args.query, step)  # raises TerminalError
        results = [r.as_dict() for r in response.results]
        for result in response.results:
            self.seen.add(canonicalize(result.url))
            self.search_results.append(result)
        if self.state is not None:
            self.state.add_search(self.run_id, args.query, results)
        outcome = ToolOutcome(
            "ok",
            {"query": args.query, "results": results},
            untrusted=json.dumps(results, ensure_ascii=False, indent=1),
            attributes={"query": args.query},
        )
        self._trace(
            step,
            "search_web",
            {"query": args.query},
            outcome,
            started,
            credits=response.credits,
            attempt=response.attempt,
            results=len(results),
        )
        outcome.data["credits"] = response.credits
        return outcome

    def is_cached(self, url: str) -> bool:
        if self.state is None:
            return False
        try:
            return self.state.get_article(url) is not None
        except ValueError:
            return False

    def fetch_article(self, url: str, step: int = 0) -> ToolOutcome:
        started = time.monotonic()
        traced = {"url": url}
        try:
            args = FetchArgs(url=url)
            check(args.url, self.policy.fetch, resolve=False)  # scheme and host, no DNS
            cached = self.state.get_article(args.url) if self.state is not None else None
            if cached is not None:
                return self._article_outcome(
                    step,
                    traced,
                    started,
                    cached["title"],
                    cached["canonical_url"],
                    cached["text"],
                    cached=True,
                )
            page = fetch_page(
                args.url, self.policy.fetch, resolver=self.resolver, transport=self.transport
            )
        except ValidationError as err:
            outcome = ToolOutcome.failure("error", "invalid_arguments", validation_message(err))
        except Blocked as err:
            outcome = ToolOutcome.failure("blocked", err.reason, err.detail)
        except FetchError as err:
            outcome = ToolOutcome.failure("error", err.reason, err.detail)
        else:
            canonical = canonicalize(args.url)
            if self.state is not None:
                canonical = self.state.put_article(args.url, page.title, page.text, self.run_id)
            self.seen.add(canonicalize(page.final_url))
            return self._article_outcome(
                step, traced, started, page.title, canonical, page.text, cached=False
            )
        self._trace(step, "fetch_article", traced, outcome, started)
        return outcome

    def _article_outcome(
        self,
        step: int,
        traced: dict,
        started: float,
        title: str,
        canonical: str,
        text: str,
        *,
        cached: bool,
    ) -> ToolOutcome:
        self.seen.add(canonical)
        if all(a.url != canonical for a in self.articles):
            self.articles.append(Article(title, canonical, text))
        limit = self.policy.fetch.max_chars_for_model
        shown = text[:limit]
        data = {
            "title": title,
            "url": canonical,
            "text": shown,
            "text_len": len(text),
            "truncated": len(text) > limit,
            "cached": cached,
        }
        outcome = ToolOutcome(
            "cached" if cached else "ok",
            data,
            untrusted=f"Title: {title}\nURL: {canonical}\n\n{shown}",
            attributes={"url": canonical},
        )
        self._trace(
            step,
            "fetch_article",
            traced,
            outcome,
            started,
            text_len=len(text),
            injection_suspected=injection_suspected(text),
        )
        return outcome


# Command line


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _manual_run_id() -> str:
    return "manual-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tracker.tools", description="Run one tracker tool without the model."
    )
    parser.add_argument("--config", help="policy file (default: config.yaml at the repo root)")
    sub = parser.add_subparsers(dest="tool", required=True)
    p_search = sub.add_parser("search_web", help="search the web")
    p_search.add_argument("query", nargs="+")
    p_fetch = sub.add_parser("fetch_article", help="fetch one page within the guardrails")
    p_fetch.add_argument("url")
    p_finish = sub.add_parser("finish", help="render a report from a JSON file")
    p_finish.add_argument("report_json")
    p_finish.add_argument("--out", help="report path (default: reports/<id>.md)")
    args = parser.parse_args(argv)

    try:
        policy = load_policy(args.config)
    except PolicyError as err:
        _print({"ok": False, "error": "invalid_policy", "detail": str(err)})
        return 1

    if args.tool == "finish":
        return _finish_cli(policy, Path(args.report_json), args.out)

    state: StateStore | None = None
    try:
        secrets = TrackerSecrets.load(policy, model=False, search=args.tool == "search_web")
    except PolicyError as err:
        _print({"ok": False, "error": "missing_key", "detail": str(err)})
        return 1
    trace = Trace(None, "cli", secrets.values())
    try:
        try:
            state = StateStore(policy.state_file)
        except StateLocked:
            print("State file is locked by a run; continuing without the cache.", file=sys.stderr)
        search_client = (
            SearchClient(policy, secrets.search_key, trace) if args.tool == "search_web" else None
        )
        toolbox = Toolbox(policy, trace, "cli", state=state, search_client=search_client)
        if args.tool == "search_web":
            outcome = toolbox.search_web(" ".join(args.query))
        else:
            outcome = toolbox.fetch_article(args.url)
    except TerminalError as err:
        _print({"ok": False, "error": err.kind, "provider": err.provider, "detail": err.message})
        return 3
    finally:
        if state is not None:
            state.close()
    _print({"ok": outcome.ok, **outcome.data})
    return 0 if outcome.ok else 1


def _finish_cli(policy: Policy, file: Path, out: str | None) -> int:
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
        result = validate_finish(raw, policy.k)
    except OSError as err:
        _print({"ok": False, "error": "unreadable_file", "detail": f"{file}: {err.strerror}"})
        return 1
    except json.JSONDecodeError as err:
        _print({"ok": False, "error": "invalid_json", "detail": str(err)})
        return 1
    except ValidationError as err:
        _print({"ok": False, "error": "invalid_arguments", "detail": validation_message(err)})
        return 1
    run_id = _manual_run_id()
    meta = report.ReportMeta(
        topic=policy.topic,
        run_id=run_id,
        timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        status="complete",
        stop_reason=None,
        usage={},
    )
    path = Path(out) if out else policy.reports_path / f"{run_id}.md"
    report.write(path, report.render(meta, report.ReportBody(result.items, result.note)))
    _print(
        {
            "ok": True,
            "report_path": str(path),
            "items": len(result.items),
            "truncated": result.truncated,
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
