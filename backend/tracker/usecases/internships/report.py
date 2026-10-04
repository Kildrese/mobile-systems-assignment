"""The cumulative internship report: New since last run, Still open, Closed since last run.

Every opportunity appears in exactly one section. "Still open" accumulates across runs:
an opportunity is new once, then stays listed until it closes. The current top K are
marked wherever they appear. Fields come from verified records; a summary appears only
if the Editor's summary passed its checks.
"""

from dataclasses import dataclass, field
from typing import Any

from tracker.report import ReportMeta, describe_stop
from tracker.usecases.internships.store import OpportunityStore


@dataclass
class Sections:
    new: list[dict[str, Any]] = field(default_factory=list)
    still_open: list[dict[str, Any]] = field(default_factory=list)
    closed: list[dict[str, Any]] = field(default_factory=list)


def sections(store: OpportunityStore, run_id: str) -> Sections:
    ranks = store.ranks(run_id)

    def rank_of(opp: dict[str, Any]) -> tuple[int, int]:
        r = ranks.get(opp["id"])
        return (r["rank"] if r else 10**9, opp["id"])

    out = Sections()
    for opp in store.opportunities():
        r = ranks.get(opp["id"])
        opp = {
            **opp,
            "rank": r["rank"] if r else None,
            "top_k": bool(r and r["top_k"]),
            "verified": opp["checked_run"] == run_id and opp["status"] == "open",
        }
        if opp["status"] == "open" and opp["first_seen_run"] == run_id:
            out.new.append(opp)
        elif opp["status"] == "open":
            out.still_open.append(opp)
        elif opp["status"] == "closed" and opp["closed_run"] == run_id:
            out.closed.append(opp)
    out.new.sort(key=rank_of)
    out.still_open.sort(key=rank_of)
    out.closed.sort(key=lambda o: (o["company"], o["id"]))
    return out


def _one_line(text: Any) -> str:
    return " ".join(str(text).split())


def _cell(text: Any) -> str:
    return _one_line(text).replace("|", "\\|") or "-"


def _value(opp: dict[str, Any], name: str) -> str:
    value = (opp["fields"].get(name) or {}).get("value", "unknown")
    return ", ".join(value) if isinstance(value, list) else str(value)


def _quote(opp: dict[str, Any], name: str) -> str | None:
    return (opp["fields"].get(name) or {}).get("quote")


def _locations(opp: dict[str, Any]) -> str:
    places = ", ".join(opp["locations"]) if opp["locations"] else "unknown"
    return f"{places} ({opp['remote']})" if opp["remote"] not in ("unknown", "onsite") else places


def _header(meta: ReportMeta, stages: list[dict[str, Any]]) -> list[str]:
    status = meta.status
    if status == "partial":
        status += f" (stopped because {describe_stop(meta.stop_reason, meta.stop_detail)})"
    u = meta.usage
    lines = [
        f"# Internship report: {_one_line(meta.topic)}",
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
    if stages:
        lines += ["| Stage | Outcome | Note |", "| --- | --- | --- |"]
        for stage in stages:
            lines.append(
                f"| {_cell(stage['name'])} | {_cell(stage['outcome'])} | "
                f"{_cell(stage.get('reason') or '')} |"
            )
        lines.append("")
    return lines


def _full_entry(opp: dict[str, Any], summary: str | None, number: int) -> list[str]:
    star = " **(top K)**" if opp["top_k"] else ""
    lines = [f"### {number}. {_one_line(opp['title'])}, {_one_line(opp['company'])}{star}", ""]
    if summary:
        lines += [_one_line(summary), ""]
    lines += [
        f"- **Location:** {_one_line(_locations(opp))}",
        f"- **Term:** {_one_line(opp['term'])}",
    ]
    for name, label in (("compensation", "Pay"), ("deadline", "Deadline")):
        if _value(opp, name) != "unknown":
            lines.append(f"- **{label}:** {_one_line(_value(opp, name))}")
    if quote := _quote(opp, "work_authorization"):
        lines.append(f'- **Work authorization (quoted):** "{_one_line(quote)}"')
    if not opp["verified"]:
        lines.append("- **Note:** could not be checked in this run")
    lines += [f"- <{opp['url']}>", ""]
    return lines


def render(
    meta: ReportMeta,
    store: OpportunityStore,
    k: int,
    stages: list[dict[str, Any]] | None = None,
    note: str | None = None,
) -> str:
    s = sections(store, meta.run_id)
    summaries = store.summaries(meta.run_id)
    lines = _header(meta, stages or [])
    if waiting := len(store.pending_postings(meta.run_id)):
        lines += [
            f"**Waiting for review:** {waiting} posting{'s' if waiting != 1 else ''} listed "
            "in this run could not be curated before the budget ran out. They are not in the "
            "sections below; the next run starts with them, most relevant first.",
            "",
        ]

    lines += [f"## New since last run ({len(s.new)})", ""]
    if not s.new:
        lines += ["Nothing new in this run.", ""]
    for number, opp in enumerate(s.new[:k], start=1):
        lines += _full_entry(opp, summaries.get(opp["id"]), number)
    if len(s.new) > k:
        lines += ["More new opportunities:", ""]
        lines += [
            f"- {_one_line(o['title'])}, {_one_line(o['company'])}, "
            f"{_one_line(_locations(o))}: <{o['url']}>"
            for o in s.new[k:]
        ]
        lines.append("")

    lines += [f"## Still open ({len(s.still_open)})", ""]
    if not s.still_open:
        lines += ["No earlier opportunities are still open.", ""]
    else:
        lines += [
            "| Rank | Opportunity | Company | Location | Term | First seen | Link |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for opp in s.still_open:
            rank = f"{opp['rank']}" if opp["rank"] else "-"
            if opp["top_k"]:
                rank += " (top K)"
            title = _cell(opp["title"])
            if not opp["verified"]:
                title += " (not checked this run)"
            lines.append(
                f"| {rank} | {title} | {_cell(opp['company'])} | {_cell(_locations(opp))} | "
                f"{_cell(opp['term'])} | `{opp['first_seen_run']}` | <{opp['url']}> |"
            )
        lines.append("")
        top = [o for o in s.still_open if o["top_k"] and summaries.get(o["id"])]
        for opp in top:
            lines += [f"- **{_one_line(opp['title'])}:** {_one_line(summaries[opp['id']])}"]
        if top:
            lines.append("")

    lines += [f"## Closed since last run ({len(s.closed)})", ""]
    if not s.closed:
        lines += ["Nothing closed in this run.", ""]
    for opp in s.closed:
        lines.append(
            f"- {_one_line(opp['title'])}, {_one_line(opp['company'])}: "
            f"{_one_line(opp['status_evidence'] or 'closed')} (<{opp['url']}>)"
        )
    if s.closed:
        lines.append("")

    if note:
        lines += ["## Note", "", note.strip(), ""]
    return "\n".join(lines)
