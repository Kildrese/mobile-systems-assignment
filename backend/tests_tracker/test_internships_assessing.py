"""fit-rating: the profile hash, the checks on the Assessor's ratings, and the Assess
stage run alone through the conductor with a scripted model."""

import pytest
import respx

from tests_tracker.conftest import LLM_URL, chat_body, read_trace, tool_call
from tests_tracker.internships_helpers import RUN1, add_board, open_store, posting, record
from tests_tracker.test_internships_pipeline import keys, policy_data, run  # noqa: F401
from tests_tracker.test_loop import FakeModel
from tracker import conductor
from tracker.config import policy_from_dict
from tracker.state import StateStore
from tracker.usecases.internships import wiring
from tracker.usecases.internships.assessing import finish_ratings, profile_hash
from tracker.usecases.internships.store import OpportunityStore

PROFILE = "An experienced engineer who wants a backend internship in NYC."
REASON = "A software internship in New York, as the profile asks."
ASSESSOR = {
    "tools": [],
    "limits": {"max_steps": 2, "max_tokens": 8000},
    "instructions": "You rate fit for this candidate:\n{profile}",
}


def assess_policy(tmp_path, **overrides):
    data = policy_data(agents={"assessor": ASSESSOR}, options={"profile": PROFILE})
    for name, value in overrides.items():
        data[name] = value
    return policy_from_dict(data, tmp_path)


def seed(path, n):
    state, store = open_store(path)
    try:
        source_id = add_board(store)
        pids = store.upsert_postings(source_id, [posting(str(i)) for i in range(n)], RUN1)
        return [
            store.create_opportunity(
                company="Acme",
                url=f"https://boards.greenhouse.io/acme/jobs/{i}",
                record=record(),
                run_id=RUN1,
                posting_id=pid,
                linked_by="record",
            )
            for i, pid in enumerate(pids)
        ]
    finally:
        state.close()


def fits(policy):
    state = StateStore(policy.state_file)
    try:
        return OpportunityStore(state).fits()
    finally:
        state.close()


def ratings(ids, fit=2, call_id="a1"):
    items = [{"opportunity_id": i, "fit": fit, "reason": REASON} for i in ids]
    return chat_body(tool_call("finish", {"ratings": items}, call_id))


def assess(policy, keys, run_id="run-1"):  # noqa: F811
    return conductor.run(policy, keys, [wiring.AssessStage()], run_id=run_id, sleep=lambda _: None)


def test_profile_hash():
    assert profile_hash(PROFILE) == profile_hash(f"\n  {PROFILE}\n")
    assert profile_hash(PROFILE) != profile_hash(PROFILE.replace("backend", "frontend"))


@pytest.mark.parametrize(
    ("item", "rejected"),
    [
        ({"fit": 2, "reason": REASON}, None),
        ({"fit": 5, "reason": REASON}, "invalid_fit"),
        ({"fit": -1, "reason": REASON}, "invalid_fit"),
        ({"opportunity_id": 99, "fit": 2, "reason": REASON}, "not_requested"),
        ({"fit": 2, "reason": "Strong fit. " * 20}, "reason longer than 200 characters"),
        ({"fit": 3, "reason": "Pays $60/hour."}, "mentions '60', which is not in the record"),
    ],
)
def test_finish_ratings(tmp_path, item, rejected):
    [oid] = seed(tmp_path / "s.sqlite", 1)
    state, store = open_store(tmp_path / "s.sqlite")
    try:
        outcome = finish_ratings(
            store, PROFILE, {"ratings": [{"opportunity_id": oid, **item}]}, {oid}
        )
        if rejected is None:
            assert outcome.data == {"accepted": [oid], "rejected": []}
            assert store.fits()[oid]["profile_hash"] == profile_hash(PROFILE)
        else:
            assert outcome.data["rejected"][0]["reason"] == rejected
            assert outcome.reason == "no_valid_ratings"
            assert store.fits() == {}
    finally:
        state.close()


def test_one_bad_rating_does_not_block_the_others(tmp_path):
    a, b = seed(tmp_path / "s.sqlite", 2)
    state, store = open_store(tmp_path / "s.sqlite")
    try:
        args = {
            "ratings": [
                {"opportunity_id": a, "fit": 5, "reason": REASON},
                {"opportunity_id": b, "fit": 1, "reason": REASON},
            ]
        }
        outcome = finish_ratings(store, PROFILE, args, {a, b})
        assert outcome.ok
        assert outcome.data == {
            "accepted": [b],
            "rejected": [{"opportunity_id": a, "reason": "invalid_fit"}],
        }
    finally:
        state.close()


def test_no_assessor(tmp_path):
    names = [s.name for s in wiring.stages(policy_from_dict(policy_data(), tmp_path))]
    assert "assess" not in names
    no_profile = assess_policy(tmp_path, options={"watchlist": []})
    assert "assess" not in [s.name for s in wiring.stages(no_profile)]
    assert "assess" in [s.name for s in wiring.stages(assess_policy(tmp_path))]


@respx.mock
def test_new_opportunities_rated(tmp_path, keys):  # noqa: F811
    policy = assess_policy(tmp_path)
    ids = seed(policy.state_file, 5)
    state, store = open_store(policy.state_file)
    for oid in ids[:2]:
        store.put_fit(oid, profile_hash(PROFILE), 3, REASON)
    state.close()
    model = FakeModel(ratings(ids[2:]))
    respx.post(LLM_URL).mock(side_effect=model)

    result = assess(policy, keys)

    assert result.status == "complete", result.message
    assert len(model.requests) == 1  # the 3 unrated, in one batch
    messages = model.requests[0]["messages"]
    assert PROFILE in messages[0]["content"]  # the {profile} placeholder
    assert "untrusted data" in messages[1]["content"]
    assert {i: f["fit"] for i, f in fits(policy).items()} == {
        ids[0]: 3,
        ids[1]: 3,
        ids[2]: 2,
        ids[3]: 2,
        ids[4]: 2,
    }


@respx.mock
def test_budget_runs_out(tmp_path, keys):  # noqa: F811
    policy = assess_policy(tmp_path)
    ids = seed(policy.state_file, 30)
    newest = ids[::-1]
    respx.post(LLM_URL).mock(
        side_effect=FakeModel(ratings(newest[:8]), ratings(newest[8:16], call_id="a2"))
    )

    result = assess(policy, keys)

    assert result.status == "partial"
    assert sorted(fits(policy)) == sorted(newest[:16])
    [stage] = read_trace(result.trace_path)[-1]["stages"]
    assert (stage["outcome"], stage["reason"]) == ("partial", "assessor.max_steps")
    assert stage["usage"]["rated"] == 16

    # The next run starts with the remaining 14, newest first.
    model = FakeModel(ratings(newest[16:24]), ratings(newest[24:], call_id="a2"))
    respx.post(LLM_URL).mock(side_effect=model)
    assert assess(policy, keys, "run-2").status == "complete"
    assert sorted(fits(policy)) == sorted(ids)


@respx.mock
def test_rejected_rating_is_returned_once(tmp_path, keys):  # noqa: F811
    policy = assess_policy(tmp_path)
    [oid] = seed(policy.state_file, 1)
    bad = ratings([oid], fit=5)
    model = FakeModel(bad, ratings([oid], fit=5, call_id="a2"))
    respx.post(LLM_URL).mock(side_effect=model)

    result = assess(policy, keys)

    # Corrected once, still invalid: the batch ends and the opportunity stays unrated.
    assert result.status == "complete"
    assert len(model.requests) == 2
    assert any("invalid_fit" in (m["content"] or "") for m in model.requests[1]["messages"])
    assert fits(policy) == {}
