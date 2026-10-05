"""The Assessor's batch task and the checks on its fit ratings.

The Assessor rates how well each open opportunity fits the profile in `options.profile`,
0 to 3 with a one-sentence reason. It reads records and the start of each posting as
untrusted data, and its only tool is `finish`. A rating is stored only for an
opportunity in its batch, with a fit from 0 to 3 and a short reason that passes the
Editor's summary check, so the reason shown to the user adds nothing the record lacks.
"""

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tracker.tools import ToolOutcome, validation_message
from tracker.untrusted import wrap
from tracker.usecases.internships.curation import posting_text
from tracker.usecases.internships.editing import summary_problem
from tracker.usecases.internships.store import OpportunityStore

BATCH_SIZE = 8
POSTING_CHARS = 1500
MAX_REASON_CHARS = 200


def profile_hash(profile: str) -> str:
    return hashlib.sha256(profile.strip().encode()).hexdigest()


def batch_data(store: OpportunityStore, opportunities: list[dict[str, Any]]) -> str:
    """The batch as the model sees it: records and the start of each posting."""
    items = []
    for opp in opportunities:
        postings = store.linked_postings(opp["id"])
        items.append(
            {
                "opportunity_id": opp["id"],
                "company": opp["company"],
                "title": opp["title"],
                "fields": opp["fields"],
                "posting": posting_text(postings[0])[:POSTING_CHARS] if postings else "",
            }
        )
    return json.dumps(items, ensure_ascii=False, indent=1)


def task(data: str) -> str:
    return (
        "Rate how well each opportunity below fits the profile in your instructions: "
        "0 does not fit, 1 weak, 2 good, 3 strong. Give each a reason of one sentence, at "
        f"most {MAX_REASON_CHARS} characters, using only facts in the record. Submit every "
        "rating in one finish call.\n\n" + wrap("assess_batch", data)
    )


class RatingItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    opportunity_id: int
    fit: int
    reason: str = Field(min_length=1, max_length=2000)


class RatingsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ratings: list[RatingItem] = Field(min_length=1, max_length=50)


def finish_ratings(
    store: OpportunityStore, profile: str, arguments: dict[str, Any], allowed_ids: set[int]
) -> ToolOutcome:
    """The Assessor's `finish`: store each acceptable rating, report the rejected ones."""
    try:
        args = RatingsArgs.model_validate(arguments)
    except ValidationError as err:
        return ToolOutcome.failure("error", "invalid_arguments", validation_message(err))
    digest = profile_hash(profile)
    accepted, rejected = [], []
    for item in args.ratings:
        opp = store.opportunity(item.opportunity_id)
        reason = " ".join(item.reason.split())
        if opp is None or item.opportunity_id not in allowed_ids:
            problem = "not_requested"
        elif not 0 <= item.fit <= 3:
            problem = "invalid_fit"
        elif len(reason) > MAX_REASON_CHARS:
            problem = f"reason longer than {MAX_REASON_CHARS} characters"
        else:
            problem = summary_problem(reason, opp)
        if problem:
            rejected.append({"opportunity_id": item.opportunity_id, "reason": problem})
            continue
        store.put_fit(item.opportunity_id, digest, item.fit, reason)
        accepted.append(item.opportunity_id)
    return ToolOutcome(
        "ok" if accepted else "error",
        {"accepted": accepted, "rejected": rejected},
        reason=None if accepted else "no_valid_ratings",
    )
