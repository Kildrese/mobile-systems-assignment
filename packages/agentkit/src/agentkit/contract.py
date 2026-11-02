"""The wire contract between the orchestrator and its workers.

Both sides validate against these models: the worker every request, the orchestrator
every response. Unknown fields are rejected in both directions.
"""

import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Verdict = Literal["supported", "unsupported", "unreachable"]
MAX_EVIDENCE_CHARS = 300


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Budget(_Strict):
    max_steps: int = Field(gt=0)
    max_fetches: int = Field(gt=0)
    max_tokens: int = Field(gt=0)


class Claim(_Strict):
    claim_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=500)
    source_url: str = Field(min_length=1, max_length=2000)


class VerifyPayload(_Strict):
    claims: list[Claim] = Field(min_length=1, max_length=20)

    @field_validator("claims")
    @classmethod
    def unique_ids(cls, claims: list[Claim]) -> list[Claim]:
        ids = [c.claim_id for c in claims]
        if len(ids) != len(set(ids)):
            raise ValueError("claim_id values must be unique")
        return claims


class VerifyRequest(_Strict):
    request_id: UUID
    run_id: UUID
    time_budget_ms: int = Field(gt=0)
    budget: Budget
    payload: VerifyPayload


class Usage(_Strict):
    steps: int = Field(ge=0)
    fetches: int = Field(ge=0)
    tokens: int = Field(ge=0)


class WorkerError(_Strict):
    code: str
    message: str
    retryable: bool


class VerdictItem(_Strict):
    claim_id: str
    verdict: Verdict
    evidence: str | None

    @model_validator(mode="after")
    def evidence_only_when_supported(self) -> "VerdictItem":
        if self.verdict == "supported":
            if not self.evidence or len(self.evidence) > MAX_EVIDENCE_CHARS:
                raise ValueError(f"supported needs evidence of 1-{MAX_EVIDENCE_CHARS} characters")
        elif self.evidence is not None:
            raise ValueError("evidence must be null unless supported")
        return self


class VerifyResult(_Strict):
    verdicts: list[VerdictItem]


class VerifyResponse(_Strict):
    request_id: UUID
    run_id: UUID
    status: Literal["complete", "partial", "failed"]
    result: VerifyResult
    usage: Usage
    error: WorkerError | None

    def check_against(self, request: VerifyRequest) -> None:
        """Raise ValueError unless this answers `request`: same ids, only claims it sent,
        each at most once."""
        if self.request_id != request.request_id or self.run_id != request.run_id:
            raise ValueError("response is for another request")
        sent = {c.claim_id for c in request.payload.claims}
        seen = [v.claim_id for v in self.result.verdicts]
        if unknown := set(seen) - sent:
            raise ValueError(f"verdicts for claims not sent: {sorted(unknown)}")
        if len(seen) != len(set(seen)):
            raise ValueError("a claim has more than one verdict")


class ModelVerdict(_Strict):
    """What the verifier's model proposes for one claim, before code checks it."""

    claim_id: str
    verdict: Literal["supported", "unsupported"]
    evidence: str | None = None


class ModelVerdicts(_Strict):
    verdicts: list[ModelVerdict]


def body_hash(body: Any) -> str:
    """SHA-256 of the parsed JSON body: key order and whitespace don't change it."""
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


# The drafter: one posting plus the applicant's profile in, a tailored CV (and letter) out.

MAX_CV_BYTES = 2 * 1024 * 1024
MAX_TEXT_BYTES = 200 * 1024
MAX_CV_B64 = 4 * -(-MAX_CV_BYTES // 3)  # base64 of a 2 MB file


class ProfileFiles(_Strict):
    cv_docx_b64: str = Field(min_length=1, max_length=MAX_CV_B64)
    fact_bank_yaml: str = Field(min_length=1, max_length=MAX_TEXT_BYTES)
    rules_md: str = Field(max_length=MAX_TEXT_BYTES)
    checks_yaml: str = Field(min_length=1, max_length=MAX_TEXT_BYTES)

    @field_validator("fact_bank_yaml", "rules_md", "checks_yaml")
    @classmethod
    def utf8_size(cls, value: str) -> str:
        if len(value.encode()) > MAX_TEXT_BYTES:
            raise ValueError(f"at most {MAX_TEXT_BYTES} bytes")
        return value


class DraftPayload(_Strict):
    posting_url: str = Field(min_length=1, max_length=2000)
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    cover_letter: bool
    profile: ProfileFiles


class DraftRequest(_Strict):
    request_id: UUID
    run_id: UUID
    time_budget_ms: int = Field(gt=0)
    budget: Budget
    payload: DraftPayload


class CheckRecord(_Strict):
    """Something code changed or rejected in the model's plan, shown to the applicant."""

    name: str = Field(max_length=100)
    outcome: Literal["fallback", "dropped", "refilled", "cut", "rejected", "note"]
    detail: str = Field(max_length=500)


class DraftResult(_Strict):
    role_type: str | None
    cv_docx_b64: str | None
    cover_letter_docx_b64: str | None
    cover_letter_text: str | None
    checks: list[CheckRecord]


class DraftResponse(_Strict):
    request_id: UUID
    run_id: UUID
    status: Literal["complete", "partial", "failed"]
    result: DraftResult
    usage: Usage
    error: WorkerError | None

    def check_against(self, request: DraftRequest) -> None:
        if self.request_id != request.request_id or self.run_id != request.run_id:
            raise ValueError("response is for another request")
