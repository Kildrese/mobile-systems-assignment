import uuid

import pytest
from agentkit.contract import (
    MAX_CV_B64,
    MAX_TEXT_BYTES,
    DraftRequest,
    DraftResponse,
    ResearchRequest,
    ResearchResponse,
    VerifyRequest,
    VerifyResponse,
    body_hash,
)
from pydantic import ValidationError


def _request(**over):
    body = {
        "request_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "time_budget_ms": 60000,
        "budget": {"max_steps": 2, "max_fetches": 6, "max_tokens": 12000},
        "payload": {"claims": [{"claim_id": "1:term", "text": "t", "source_url": "https://a.io"}]},
    }
    body.update(over)
    return body


def test_hash_ignores_key_order():
    body = _request()
    reordered = dict(reversed(list(body.items())))
    assert body_hash(body) == body_hash(reordered)
    assert body_hash(body) != body_hash({**body, "time_budget_ms": 1})


def test_duplicate_claim_ids_rejected():
    claim = {"claim_id": "x", "text": "t", "source_url": "https://a.io"}
    with pytest.raises(ValidationError):
        VerifyRequest.model_validate(_request(payload={"claims": [claim, claim]}))


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        VerifyRequest.model_validate(_request(extra=1))


def test_response_with_unsent_claim_rejected():
    req = VerifyRequest.model_validate(_request())
    resp = VerifyResponse.model_validate(
        {
            "request_id": str(req.request_id),
            "run_id": str(req.run_id),
            "status": "complete",
            "result": {
                "verdicts": [{"claim_id": "9:pay", "verdict": "unreachable", "evidence": None}]
            },
            "usage": {"steps": 0, "fetches": 0, "tokens": 0},
            "error": None,
        }
    )
    with pytest.raises(ValueError, match="not sent"):
        resp.check_against(req)


def test_supported_needs_evidence():
    with pytest.raises(ValidationError):
        VerifyResponse.model_validate(
            {
                "request_id": str(uuid.uuid4()),
                "run_id": str(uuid.uuid4()),
                "status": "complete",
                "result": {
                    "verdicts": [{"claim_id": "a", "verdict": "supported", "evidence": None}]
                },
                "usage": {"steps": 1, "fetches": 1, "tokens": 5},
                "error": None,
            }
        )


# The drafter's contract


def _draft(**profile):
    return {
        "request_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "time_budget_ms": 120000,
        "budget": {"max_steps": 3, "max_fetches": 6, "max_tokens": 60000},
        "payload": {
            "posting_url": "https://jobs.example.com/1",
            "company": "Ramp",
            "title": "Software Engineer Intern",
            "cover_letter": False,
            "profile": {
                "cv_docx_b64": "UEsDBA==",
                "fact_bank_yaml": "- id: a",
                "rules_md": "# rules",
                "checks_yaml": "banned_words: []",
                **profile,
            },
        },
    }


def test_draft_round_trip():
    req = DraftRequest.model_validate(_draft())
    assert DraftRequest.model_validate_json(req.model_dump_json()) == req
    resp = DraftResponse.model_validate(
        {
            "request_id": str(req.request_id),
            "run_id": str(req.run_id),
            "status": "complete",
            "result": {
                "role_type": "swe",
                "cv_docx_b64": "UEsDBA==",
                "cover_letter_docx_b64": None,
                "cover_letter_text": None,
                "checks": [{"name": "scope_word", "outcome": "fallback", "detail": "led"}],
            },
            "usage": {"steps": 1, "fetches": 1, "tokens": 9000},
            "error": None,
        }
    )
    resp.check_against(req)
    with pytest.raises(ValueError):
        resp.check_against(DraftRequest.model_validate(_draft()))


def test_draft_size_limits():
    DraftRequest.model_validate(_draft(cv_docx_b64="A" * MAX_CV_B64))
    with pytest.raises(ValidationError):
        DraftRequest.model_validate(_draft(cv_docx_b64="A" * (MAX_CV_B64 + 1)))
    DraftRequest.model_validate(_draft(rules_md="a" * MAX_TEXT_BYTES))
    with pytest.raises(ValidationError):  # counted in bytes, not characters
        DraftRequest.model_validate(_draft(rules_md="é" * (MAX_TEXT_BYTES // 2 + 1)))
    with pytest.raises(ValidationError):
        DraftRequest.model_validate(_draft(checks_yaml=""))


def _research(**payload):
    body = _request(payload={"topic": "t", "k": 2, **payload})
    return ResearchRequest.model_validate(body)


def _dev(i, *claim_ids):
    cl = [{"claim_id": c, "text": "t", "source_url": "https://a.io"} for c in claim_ids]
    return {"id": f"d{i}", "title": "T", "summary": "", "claims": cl}


def _answer(req, devs, **over):
    body = {
        "request_id": str(req.request_id),
        "run_id": str(req.run_id),
        "status": "complete",
        "result": {"developments": devs},
        "usage": {"steps": 0, "fetches": 0, "tokens": 0},
        "error": None,
    }
    body.update(over)
    return ResearchResponse.model_validate(body)


@pytest.mark.parametrize("k", [0, 21])
def test_research_k_bounds(k):
    with pytest.raises(ValidationError):
        _research(k=k)


def test_research_extra_payload_field_rejected():
    with pytest.raises(ValidationError):
        _research(extra=1)


def test_development_needs_a_claim():
    with pytest.raises(ValidationError):
        _answer(_research(), [_dev(1)])


def test_research_check_against():
    req = _research()
    _answer(req, [_dev(1, "a"), _dev(2, "b")]).check_against(req)
    bad = [
        _answer(req, [_dev(1, "a")], request_id=str(uuid.uuid4())),
        _answer(req, [_dev(1, "a")], run_id=str(uuid.uuid4())),
        _answer(req, [_dev(1, "a"), _dev(2, "b"), _dev(3, "c")]),
        _answer(req, [_dev(1, "a"), _dev(1, "b")]),
        _answer(req, [_dev(1, "a"), _dev(2, "a")]),
    ]
    for r in bad:
        with pytest.raises(ValueError):
            r.check_against(req)
