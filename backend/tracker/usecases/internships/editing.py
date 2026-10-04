"""The Editor's tools, as plain functions, and the checks on its summaries.

The Editor reads records and postings and writes short summaries. It cannot change
ranks, statuses, sources or records. A summary is accepted only for an opportunity it
was asked about, in at most three sentences, and without numbers, amounts, dates or
months that are not in the record: those are where an invented fact shows first.
"""

import calendar
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tracker.tools import ToolOutcome, validation_message
from tracker.usecases.internships.store import OpportunityStore

MAX_SENTENCES = 3
MAX_CHARS = 600
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# Full and short month names. "May" is left out: it is far more often the verb.
_MONTHS = [m for m in (*calendar.month_name[1:], *calendar.month_abbr[1:], "Sept") if m != "May"]
_MONTH = re.compile(r"\b(" + "|".join(_MONTHS) + r")\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")


def wanted(store: OpportunityStore, run_id: str, k: int) -> list[dict[str, Any]]:
    """Opportunities whose summary the report shows, by this run's rank: the first K new
    ones (the rest are a one-line list) and the top K. At most 2K, so one reply fits."""
    ranks = store.ranks(run_id)
    live = [o for o in store.opportunities(("open",)) if o["id"] in ranks]
    live.sort(key=lambda o: ranks[o["id"]]["rank"])
    shown = {o["id"] for o in [o for o in live if o["first_seen_run"] == run_id][:k]}
    return [o for o in live if o["id"] in shown or ranks[o["id"]]["top_k"]]


def get_opportunities(store: OpportunityStore, run_id: str, k: int) -> ToolOutcome:
    items = [
        {
            "opportunity_id": o["id"],
            "company": o["company"],
            "title": o["title"],
            "fields": o["fields"],
            "url": o["url"],
        }
        for o in wanted(store, run_id, k)
    ]
    return ToolOutcome(
        "ok",
        {"ids": [i["opportunity_id"] for i in items], "count": len(items)},
        # Field values and quotes come from postings: untrusted text.
        untrusted=json.dumps(items, ensure_ascii=False, indent=1),
    )


def _record_text(opp: dict[str, Any]) -> str:
    parts = [opp["company"], opp["title"]]
    for field in opp["fields"].values():
        value = field.get("value")
        parts += value if isinstance(value, list) else [str(value)]
        if field.get("quote"):
            parts.append(field["quote"])
    return "\n".join(parts)


def summary_problem(text: str, opp: dict[str, Any]) -> str | None:
    """Why a summary is rejected, or None when it is acceptable."""
    text = " ".join(text.split())
    if not text:
        return "empty"
    if len(text) > MAX_CHARS:
        return f"longer than {MAX_CHARS} characters"
    if len(_SENTENCE_END.findall(text)) > MAX_SENTENCES:
        return f"more than {MAX_SENTENCES} sentences"
    record = _record_text(opp)
    digits = {n.replace(",", "") for n in _NUMBER.findall(record)}
    for number in _NUMBER.findall(text):
        if number.replace(",", "") not in digits:
            return f"mentions '{number}', which is not in the record"
    record_months = {m.lower()[:3] for m in _MONTH.findall(record)}
    for month in _MONTH.findall(text):
        if month.lower()[:3] not in record_months:
            return f"mentions '{month}', which is not in the record"
    return None


class SummaryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    opportunity_id: int
    text: str = Field(min_length=1, max_length=2000)


class SummariesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summaries: list[SummaryItem] = Field(min_length=1, max_length=50)


def finish_summaries(
    store: OpportunityStore, run_id: str, arguments: dict[str, Any], allowed_ids: set[int]
) -> ToolOutcome:
    """The Editor's `finish`: store each acceptable summary, report the rejected ones."""
    try:
        args = SummariesArgs.model_validate(arguments)
    except ValidationError as err:
        return ToolOutcome.failure("error", "invalid_arguments", validation_message(err))
    accepted, rejected = [], []
    for item in args.summaries:
        opp = store.opportunity(item.opportunity_id)
        if opp is None or item.opportunity_id not in allowed_ids:
            rejected.append({"opportunity_id": item.opportunity_id, "reason": "not_requested"})
            continue
        if problem := summary_problem(item.text, opp):
            rejected.append({"opportunity_id": item.opportunity_id, "reason": problem})
            continue
        store.put_summary(run_id, item.opportunity_id, " ".join(item.text.split()))
        accepted.append(item.opportunity_id)
    status = "ok" if accepted else "error"
    return ToolOutcome(
        status,
        {"accepted": accepted, "rejected": rejected},
        reason=None if accepted else "no_valid_summaries",
    )
