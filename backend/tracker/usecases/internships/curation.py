"""Turning raw postings into verified opportunity records.

The Curator agent proposes each record's fields together with the verbatim quote each
one came from; `save_record` accepts a record only when every quote is found in that
posting's stored text. Company and URL are never taken from the model: they come from
the source and the posting. Same-role links are made by code where an exact key
matches, and by the Curator (`mark_same`) only between postings of the same company.
"""

import json
import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from tracker.state import canonicalize
from tracker.tools import ToolOutcome, validation_message
from tracker.usecases.internships.http import GuardedHttp, HttpFailure
from tracker.usecases.internships.store import OpportunityStore

UNKNOWN = "unknown"
MIN_QUOTE_CHARS = 3
TITLE_FILLER = set(
    [
        "intern",
        "interns",
        "internship",
        "summer",
        "fall",
        "spring",
        "winter",
        "co",
        "op",
        "coop",
        "the",
        "and",
        "of",
        "for",
        "a",
        "an",
    ]
)
COMPANY_SUFFIXES = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|hq)\b")
# Curly quotes, primes, dashes and the no-break space, by code point.
_QUOTES = str.maketrans(
    {
        **dict.fromkeys((0x2018, 0x2019, 0x201A, 0x201B, 0x2032), "'"),
        **dict.fromkeys((0x201C, 0x201D, 0x201E, 0x2033), '"'),
        **dict.fromkeys((0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2212), "-"),
        0x00A0: " ",
    }
)


def normalize(text: str) -> str:
    """NFKC, straight quotes and dashes, lowercase, single spaces."""
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES).lower()
    return " ".join(text.split())


def quote_found(quote: str, haystack: str) -> bool:
    q = normalize(quote)
    return len(q) >= MIN_QUOTE_CHARS and q in normalize(haystack)


def normalize_company(name: str) -> str:
    name = COMPANY_SUFFIXES.sub(" ", normalize(name))
    return re.sub(r"[^a-z0-9]+", "", name)


def _stem(word: str) -> str:
    """Crude stemming so "engineer" and "engineering", "model" and "models" match."""
    for suffix in ("ing", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def title_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", normalize(title))
    return {
        _stem(w) for w in words if w not in TITLE_FILLER and not re.fullmatch(r"(19|20)\d\d", w)
    }


def title_similarity(a: str, b: str) -> float:
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# The record


class FieldValue(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    value: str | list[str]
    quote: str | None = Field(default=None, max_length=600)

    @field_validator("value", mode="before")
    @classmethod
    def numbers_as_text(cls, value: Any) -> Any:
        # Models send pay as 180000; the quote ("$180,000") is what gets checked.
        def text(v: Any) -> Any:
            return str(v) if isinstance(v, int | float) and not isinstance(v, bool) else v

        return [text(v) for v in value] if isinstance(value, list) else text(value)

    @property
    def unknown(self) -> bool:
        return self.value == UNKNOWN or self.value == [] or self.value == ""


ROLE_TYPES = ("internship", "new_grad", "other", UNKNOWN)
REMOTE = ("onsite", "hybrid", "remote", UNKNOWN)
# Spellings models use for an allowed value. Only case, spacing and these words differ.
ALIASES = {"intern": "internship", "new_graduate": "new_grad", "on_site": "onsite"}


def _choice(v: FieldValue, allowed: tuple[str, ...], name: str) -> FieldValue:
    """The field with its value spelled as one of `allowed` ("Internship" -> "internship")."""
    if not isinstance(v.value, str):
        raise ValueError(f"{name} must be one of {', '.join(allowed)}")
    key = "_".join(v.value.lower().replace("-", " ").split())
    value = ALIASES.get(key, key)
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}")
    return FieldValue(value=value, quote=v.quote)


def _unknown() -> FieldValue:
    return FieldValue(value=UNKNOWN)


class OpportunityRecord(BaseModel):
    """What the Curator submits. Every known field carries its verbatim quote."""

    model_config = ConfigDict(extra="forbid")

    title: FieldValue
    role_type: FieldValue = Field(default_factory=_unknown)
    term: FieldValue = Field(default_factory=_unknown)
    locations: FieldValue = Field(default_factory=_unknown)
    remote: FieldValue = Field(default_factory=_unknown)
    compensation: FieldValue = Field(default_factory=_unknown)
    deadline: FieldValue = Field(default_factory=_unknown)
    work_authorization: FieldValue = Field(default_factory=_unknown)

    @field_validator("role_type")
    @classmethod
    def known_role(cls, v: FieldValue) -> FieldValue:
        return _choice(v, ROLE_TYPES, "role_type")

    @field_validator("remote")
    @classmethod
    def known_remote(cls, v: FieldValue) -> FieldValue:
        return _choice(v, REMOTE, "remote")

    @field_validator("locations")
    @classmethod
    def locations_list(cls, v: FieldValue) -> FieldValue:
        if isinstance(v.value, str) and v.value != UNKNOWN:
            return FieldValue(value=[v.value], quote=v.quote)
        return v

    @field_validator("title")
    @classmethod
    def title_known(cls, v: FieldValue) -> FieldValue:
        if v.unknown or not isinstance(v.value, str):
            raise ValueError("title is required")
        return v

    def fields(self) -> dict[str, FieldValue]:
        return {name: getattr(self, name) for name in type(self).model_fields}

    def stored(self) -> dict[str, Any]:
        """The record as stored: unknown fields carry no quote."""
        out: dict[str, Any] = {}
        for name, field in self.fields().items():
            out[name] = {"value": UNKNOWN} if field.unknown else field.model_dump()
        return out


def posting_text(posting: dict[str, Any]) -> str:
    """Everything a quote may come from: the board text, title, location and detail page."""
    parts = [posting["title"], posting.get("location") or "", posting["text"]]
    if posting.get("detail_text"):
        parts.append(posting["detail_text"])
    return "\n".join(parts)


def unverified_fields(record: OpportunityRecord, text: str) -> list[str]:
    """Names of known fields whose quote is missing or not in `text`."""
    return [
        name
        for name, field in record.fields().items()
        if not field.unknown and not (field.quote and quote_found(field.quote, text))
    ]


# Code-side matching


def link_exact(store: OpportunityStore, posting_id: int) -> int | None:
    """Link a posting to an opportunity that already has a posting with the same canonical URL.

    Returns the opportunity id when linked. This needs no model.
    """
    posting = store.posting(posting_id)
    if posting is None or posting["curation"] != "pending":
        return None
    for other in store.postings_with_canonical_url(posting["canonical_url"]):
        if other["id"] != posting_id and other["opportunity_id"] is not None:
            store.link(other["opportunity_id"], posting_id, "code", "same canonical URL")
            return other["opportunity_id"]
    return None


def candidates(
    store: OpportunityStore, posting: dict[str, Any], threshold: float = 0.5
) -> list[dict[str, Any]]:
    """Existing opportunities of the same company with a similar title, best first."""
    company = normalize_company(posting["company"])
    scored = []
    for opp in store.opportunities():
        if normalize_company(opp["company"]) != company:
            continue
        similarity = title_similarity(posting["title"], opp["title"])
        if similarity >= threshold:
            scored.append((similarity, opp))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [
        {
            "opportunity_id": opp["id"],
            "title": opp["title"],
            "locations": opp["locations"],
            "status": opp["status"],
            "similarity": round(sim, 2),
        }
        for sim, opp in scored
    ]


# The Curator's tools, as plain functions


def _pending(store: OpportunityStore, posting_id: int) -> tuple[dict[str, Any] | None, ToolOutcome]:
    posting = store.posting(posting_id)
    if posting is None:
        return None, ToolOutcome.failure("error", "unknown_posting", f"no posting {posting_id}")
    if posting["curation"] != "pending":
        return None, ToolOutcome.failure(
            "error", "already_processed", f"posting {posting_id} is {posting['curation']}"
        )
    return posting, ToolOutcome("ok", {})


def get_posting(store: OpportunityStore, posting_id: int, max_chars: int = 6000) -> ToolOutcome:
    posting = store.posting(posting_id)
    if posting is None:
        return ToolOutcome.failure("error", "unknown_posting", f"no posting {posting_id}")
    found = candidates(store, posting)
    text = posting_text(posting)[:max_chars]
    if found:
        # The model sees only the untrusted block, and candidate titles come from postings.
        text += "\n\nSame-company candidates for mark_same: " + json.dumps(found)
    data = {
        "posting_id": posting["id"],
        "company": posting["company"],
        "url": posting["url"],
        "curation": posting["curation"],
        "has_detail_page": bool(posting.get("detail_text")),
        "candidates": found,
    }
    return ToolOutcome(
        "ok", data, untrusted=text, attributes={"url": posting["url"], "posting": str(posting_id)}
    )


def fetch_posting_detail(
    store: OpportunityStore,
    posting_id: int,
    url: str,
    *,
    http: GuardedHttp,
    max_chars: int = 6000,
) -> ToolOutcome:
    """Fetch a posting's own page and keep its text for quotes. `http` allows only the
    agent's hosts, so a page elsewhere is blocked before any connection."""
    posting, check = _pending(store, posting_id)
    if posting is None:
        return check
    # Quotes are checked against this text, so it must be this posting's page.
    try:
        same = canonicalize(url) == posting["canonical_url"]
    except ValueError:
        same = False
    if not same:
        return ToolOutcome.failure(
            "error",
            "url_mismatch",
            f"url must be posting {posting_id}'s own page: {posting['url']}",
        )
    try:
        result = http.get(url)
    except HttpFailure as err:
        blocked = err.reason in {"blocked_address", "scheme_not_allowed", "host_not_allowed"}
        outcome = ToolOutcome.failure("blocked" if blocked else "error", err.reason, err.detail)
        outcome.requested = not blocked
        return outcome
    store.set_detail_text(posting_id, result.text)
    return ToolOutcome(
        "ok",
        {"posting_id": posting_id, "url": url, "chars": len(result.text)},
        untrusted=result.text[:max_chars],
        attributes={"url": url, "posting": str(posting_id)},
        requested=True,
    )


def save_record(
    store: OpportunityStore,
    posting_id: int,
    record: dict[str, Any],
    run_id: str,
    *,
    drop_unverified: bool = False,
) -> ToolOutcome:
    """Save a record whose quotes are all in the posting. With `drop_unverified` (the
    Curator's second try), fields whose quote is not found are saved as unknown instead;
    the title must still be found."""
    posting, check = _pending(store, posting_id)
    if posting is None:
        return check
    try:
        parsed = OpportunityRecord.model_validate(record)
    except ValidationError as err:
        return ToolOutcome.failure("error", "invalid_arguments", validation_message(err))
    missing = unverified_fields(parsed, posting_text(posting))
    if missing and (not drop_unverified or "title" in missing):
        return ToolOutcome.failure(
            "error",
            "quote_not_found",
            f"quote not found in the posting for: {', '.join(missing)}. Quote the posting "
            "word for word, or set the field to unknown. If you send quotes that are not "
            "in the posting again, those fields are saved as unknown.",
        )
    parsed = parsed.model_copy(update={name: _unknown() for name in missing})
    opportunity_id = store.create_opportunity(
        company=posting["company"],
        url=posting["url"],
        record=parsed.stored(),
        run_id=run_id,
        posting_id=posting_id,
        linked_by="record",
    )
    data = {"posting_id": posting_id, "opportunity_id": opportunity_id}
    if missing:
        data["saved_as_unknown"] = missing
    return ToolOutcome("ok", data)


def mark_same(
    store: OpportunityStore, posting_id: int, opportunity_id: int, reason: str
) -> ToolOutcome:
    posting, check = _pending(store, posting_id)
    if posting is None:
        return check
    opportunity = store.opportunity(opportunity_id)
    if opportunity is None:
        return ToolOutcome.failure(
            "error", "unknown_opportunity", f"no opportunity {opportunity_id}"
        )
    if normalize_company(opportunity["company"]) != normalize_company(posting["company"]):
        return ToolOutcome.failure(
            "error",
            "company_mismatch",
            f"posting is from {posting['company']}, opportunity from {opportunity['company']}",
        )
    reason = (reason or "").strip()[:300]
    if not reason:
        return ToolOutcome.failure("error", "invalid_arguments", "reason is required")
    store.link(opportunity_id, posting_id, "curator", reason)
    return ToolOutcome("ok", {"posting_id": posting_id, "opportunity_id": opportunity_id})


def flag_unclear(store: OpportunityStore, posting_id: int, reason: str) -> ToolOutcome:
    posting, check = _pending(store, posting_id)
    if posting is None:
        return check
    reason = (reason or "").strip()[:300] or "no reason given"
    store.set_curation(posting_id, "unclear", unclear_reason=reason)
    return ToolOutcome("ok", {"posting_id": posting_id, "curation": "unclear"})
