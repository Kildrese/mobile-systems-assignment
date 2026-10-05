"""The internship report: New since last run, Still in top K, Dropped, Also open.

The report compares this run's top K with the last run's (the newest earlier finished
run that has ranks). Every opportunity appears in at most one section, the first that
applies. "Also open" accumulates across runs: an opportunity is new once, then stays
listed until it closes. Fields come from verified records; a summary appears only if the
Editor's summary passed its checks. Fit appears only when the run has a profile to rate
against.
"""

from dataclasses import dataclass, field
from typing import Any

from tracker.report import ReportMeta, describe_stop
from tracker.usecases.internships.store import OpportunityStore


@dataclass
class Sections:
    previous_run: str | None = None
    new: list[dict[str, Any]] = field(default_factory=list)
    top_k: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    also_open: list[dict[str, Any]] = field(default_factory=list)


def sections(store: OpportunityStore, run_id: str) -> Sections:
    ranks = store.ranks(run_id)
    out = Sections(previous_run=store.previous_ranked_run(run_id))
    before = store.ranks(out.previous_run) if out.previous_run else {}
    fits = store.fits()

    def rank_of(opp: dict[str, Any]) -> tuple[int, int]:
        return (opp["rank"] or 10**9, opp["id"])

    for opp in store.opportunities():
        r, p, f = ranks.get(opp["id"]), before.get(opp["id"]), fits.get(opp["id"])
        opp = {
            **opp,
            "rank": r["rank"] if r else None,
            "top_k": bool(r and r["top_k"]),
            "previous_rank": p["rank"] if p else None,
            "was_top_k": bool(p and p["top_k"]),
            "drop_reason": None,
            "fit": f["fit"] if f else None,
            "fit_reason": f["reason"] if f else None,
            "verified": opp["checked_run"] == run_id and opp["status"] == "open",
        }
        is_open = opp["status"] == "open"
        # With nothing to compare with, every open opportunity is new to the reader.
        if is_open and (opp["first_seen_run"] == run_id or out.previous_run is None):
            out.new.append(opp)
        elif out.previous_run is None:
            continue
        elif opp["top_k"]:
            out.top_k.append(opp)
        elif opp["was_top_k"]:
            opp["drop_reason"] = "closed" if opp["status"] == "closed" else "outranked"
            out.dropped.append(opp)
        elif opp["status"] == "closed" and opp["closed_run"] == run_id:
            opp["drop_reason"] = "closed"
            out.dropped.append(opp)
        elif is_open:
            out.also_open.append(opp)
    for section in (out.new, out.top_k, out.also_open):
        section.sort(key=rank_of)
    # Dropped from the last top K first, in their old order, then the other closings.
    out.dropped.sort(key=lambda o: (o["previous_rank"] or 10**9, o["company"], o["id"]))
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


def _was(opp: dict[str, Any]) -> str:
    """Where a Still-in-top-K opportunity stood in the last run."""
    if opp["was_top_k"]:
        return str(opp["previous_rank"])
    return "entered the top K"


def _fit(opp: dict[str, Any]) -> str:
    return "-" if opp["fit"] is None else f"{opp['fit']}/3"


def _full_entry(opp: dict[str, Any], summary: str | None, number: int, show_fit: bool) -> list[str]:
    star = " **(top K)**" if opp["top_k"] else ""
    lines = [f"### {number}. {_one_line(opp['title'])}, {_one_line(opp['company'])}{star}", ""]
    if summary:
        lines += [_one_line(summary), ""]
    lines += [
        f"- **Location:** {_one_line(_locations(opp))}",
        f"- **Term:** {_one_line(opp['term'])}",
    ]
    if show_fit and opp["fit"] is not None:
        lines.append(f"- **Fit:** {_fit(opp)}, {_one_line(opp['fit_reason'])}")
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
    show_fit: bool = False,
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
        lines += _full_entry(opp, summaries.get(opp["id"]), number, show_fit)
    if len(s.new) > k:
        lines += ["More new opportunities:", ""]
        lines += [
            f"- {_one_line(o['title'])}, {_one_line(o['company'])}, "
            f"{_one_line(_locations(o))}: <{o['url']}>"
            for o in s.new[k:]
        ]
        lines.append("")

    no_previous = "No earlier run to compare with."
    lines += [f"## Still in top K ({len(s.top_k)})", ""]
    if s.previous_run is None:
        lines += [no_previous, ""]
    elif not s.top_k:
        lines += ["No earlier opportunity is in the top K.", ""]
    else:
        fit_head, fit_rule = (" Fit |", " --- |") if show_fit else ("", "")
        lines += [
            f"| Rank | Last run | Opportunity | Company | Location | Term |{fit_head} Link |",
            f"| --- | --- | --- | --- | --- | --- |{fit_rule} --- |",
        ]
        for opp in s.top_k:
            title = _cell(opp["title"])
            if not opp["verified"]:
                title += " (not checked this run)"
            fit = f" {_fit(opp)} |" if show_fit else ""
            lines.append(
                f"| {opp['rank']} | {_was(opp)} | {title} | {_cell(opp['company'])} | "
                f"{_cell(_locations(opp))} | {_cell(opp['term'])} |{fit} <{opp['url']}> |"
            )
        lines.append("")
        top = [o for o in s.top_k if summaries.get(o["id"])]
        for opp in top:
            lines += [f"- **{_one_line(opp['title'])}:** {_one_line(summaries[opp['id']])}"]
        if top:
            lines.append("")

    lines += [f"## Dropped ({len(s.dropped)})", ""]
    if s.previous_run is None:
        lines += [no_previous, ""]
    elif not s.dropped:
        lines += ["Nothing dropped out of the top K or closed in this run.", ""]
    for opp in s.dropped:
        if opp["drop_reason"] == "closed":
            why = f"closed: {_one_line(opp['status_evidence'] or 'no longer listed')}"
        else:
            why = f"outranked, now #{opp['rank']}"
        was = f" (was #{opp['previous_rank']})" if opp["was_top_k"] else ""
        lines.append(
            f"- {_one_line(opp['title'])}, {_one_line(opp['company'])}{was}: {why} (<{opp['url']}>)"
        )
    if s.dropped:
        lines.append("")

    lines += [f"## Also open ({len(s.also_open)})", ""]
    if not s.also_open:
        lines += ["No other earlier opportunities are still open.", ""]
    else:
        fit_head, fit_rule = (" Fit |", " --- |") if show_fit else ("", "")
        lines += [
            f"| Rank | Opportunity | Company | Location | Term |{fit_head} First seen | Link |",
            f"| --- | --- | --- | --- | --- |{fit_rule} --- | --- |",
        ]
        for opp in s.also_open:
            title = _cell(opp["title"])
            if not opp["verified"]:
                title += " (not checked this run)"
            fit = f" {_fit(opp)} |" if show_fit else ""
            lines.append(
                f"| {opp['rank'] or '-'} | {title} | {_cell(opp['company'])} | "
                f"{_cell(_locations(opp))} | {_cell(opp['term'])} |{fit} "
                f"`{opp['first_seen_run']}` | <{opp['url']}> |"
            )
        lines.append("")

    if note:
        lines += ["## Note", "", note.strip(), ""]
    return "\n".join(lines)
