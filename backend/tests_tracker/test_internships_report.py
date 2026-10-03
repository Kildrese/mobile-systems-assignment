"""opportunity-report: ranking in code, the Editor's summary checks, and the cumulative
New / Still open / Closed report over two runs."""

from datetime import UTC, datetime

import pytest

from tests_tracker.internships_helpers import RUN1, RUN2, add_board, open_store, posting, record
from tracker.report import ReportMeta
from tracker.usecases.internships.curation import save_record
from tracker.usecases.internships.editing import (
    finish_summaries,
    get_opportunities,
    summary_problem,
    wanted,
)
from tracker.usecases.internships.lifecycle import LifecycleSettings, run_liveness
from tracker.usecases.internships.ranking import RankingSettings, rank_open, score
from tracker.usecases.internships.report import render, sections

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)


class NoHttp:
    def get(self, url, **_):
        raise AssertionError(f"no request expected, got {url}")


@pytest.fixture
def store(tmp_path):
    state, store = open_store(tmp_path / "s.sqlite")
    yield store
    state.close()


def opp(**overrides):
    base = {
        "id": 1,
        "company": "Acme",
        "role_type": "internship",
        "term": "Summer 2027",
        "locations": ["New York, NY"],
        "remote": "onsite",
        "first_seen_at": "2026-10-01T12:00:00+00:00",
        "fields": {},
    }
    base.update(overrides)
    return base


# Ranking


def test_score_matches_and_unknowns():
    s = RankingSettings()
    full = score(opp(), s, NOW)
    assert full == pytest.approx(3 + 3 + 2 + (1 - 1 / 30))
    assert score(opp(term="unknown"), s, NOW) == pytest.approx(full - 1.5)
    assert score(opp(term="Fall 2026"), s, NOW) == pytest.approx(full - 3)
    assert score(opp(locations=["London"], remote="remote"), s, NOW) == pytest.approx(full)
    assert score(opp(locations=["London"]), s, NOW) == pytest.approx(full - 2)


def test_work_authorization_does_not_change_score():
    s = RankingSettings()
    plain = opp()
    restricted = opp(
        fields={"work_authorization": {"value": "x", "quote": "No visa sponsorship available"}}
    )
    assert score(plain, s, NOW) == score(restricted, s, NOW)


def _seed(store, n, run_id=RUN1, start=1):
    source_id = add_board(store)
    ids = []
    for i in range(start, start + n):
        [pid] = store.upsert_postings(source_id, [posting(str(i))], run_id)
        ids.append(save_record(store, pid, record(), run_id).data["opportunity_id"])
    store.mark_source_read(source_id, run_id, "ok")
    return source_id, ids


def test_ranking_is_deterministic(store):
    _seed(store, 4)
    first = [o["id"] for o in rank_open(store, RUN1, RankingSettings(), 2, NOW)]
    second = [o["id"] for o in rank_open(store, RUN1, RankingSettings(), 2, NOW)]
    assert first == second
    ranks = store.ranks(RUN1)
    assert [ranks[i]["top_k"] for i in first] == [1, 1, 0, 0]


# Summaries


def test_summary_with_invented_salary(store):
    _, [oid] = _seed(store, 1)
    o = store.opportunity(oid)
    o["fields"]["compensation"] = {"value": "unknown"}
    assert "45" in summary_problem("A NYC internship paying $45/hour.", o)


def test_summary_checks(store):
    _, [oid] = _seed(store, 1)
    o = store.opportunity(oid)
    assert summary_problem("A paid Summer 2027 internship in New York, at $45/hour.", o) is None
    assert "'1'" in summary_problem("Apply by Nov 1.", o)
    assert "November" in summary_problem("Applications close in November.", o)
    assert "sentences" in summary_problem("One. Two. Three. Four.", o)
    assert summary_problem("You may apply in New York.", o) is None  # "may" is not a month


def test_finish_summaries(store):
    _, [a, b] = _seed(store, 2)
    rank_open(store, RUN1, RankingSettings(), 5, NOW)
    allowed = {o["id"] for o in wanted(store, RUN1)}
    outcome = finish_summaries(
        store,
        RUN1,
        {
            "summaries": [
                {"opportunity_id": a, "text": "Summer 2027 software internship in New York."},
                {"opportunity_id": b, "text": "Pays $60/hour."},
                {"opportunity_id": 999, "text": "Not asked for."},
            ]
        },
        allowed,
    )
    assert outcome.ok
    assert outcome.data["accepted"] == [a]
    reasons = {r["opportunity_id"]: r["reason"] for r in outcome.data["rejected"]}
    assert "60" in reasons[b]
    assert reasons[999] == "not_requested"
    assert store.summaries(RUN1) == {a: "Summer 2027 software internship in New York."}


def test_get_opportunities_is_untrusted(store):
    _seed(store, 2)
    rank_open(store, RUN1, RankingSettings(), 1, NOW)
    outcome = get_opportunities(store, RUN1)
    assert outcome.data["count"] == 2  # both are new in RUN1, one is the top K
    assert '"company": "Acme"' in outcome.untrusted


# The cumulative report


def meta(run_id, status="complete"):
    return ReportMeta(
        topic="Summer 2027 internships at NYC startups",
        run_id=run_id,
        timestamp="2026-10-02T12:00:00+00:00",
        status=status,
        stop_reason=None,
        stop_detail=None,
        usage={"steps": 3, "total_tokens": 1000},
    )


def test_second_day_report(store):
    """Run 1 finds 6; run 2 finds 2 new, 5 of the 6 still open, 1 closed."""
    source_id, run1_ids = _seed(store, 6)
    run_liveness(store, RUN1, NoHttp(), LifecycleSettings())
    rank_open(store, RUN1, RankingSettings(), 3, NOW)

    # Run 2: the board lists jobs 1-5 (job 6 was taken down) plus new jobs 7 and 8.
    store.upsert_postings(source_id, [posting(str(i)) for i in range(1, 6)], RUN2)
    _, run2_ids = _seed(store, 2, RUN2, start=7)
    store.mark_source_read(source_id, RUN2, "ok")
    run_liveness(store, RUN2, NoHttp(), LifecycleSettings())
    rank_open(store, RUN2, RankingSettings(), 3, NOW)

    s = sections(store, RUN2)
    assert sorted(o["id"] for o in s.new) == sorted(run2_ids)
    assert sorted(o["id"] for o in s.still_open) == sorted(run1_ids[:5])
    assert [o["id"] for o in s.closed] == [run1_ids[5]]
    listed = [o["id"] for o in s.new + s.still_open + s.closed]
    assert len(listed) == len(set(listed)) == 8

    text = render(meta(RUN2), store, 3, stages=[{"name": "collect", "outcome": "complete"}])
    assert "## New since last run (2)" in text
    assert "## Still open (5)" in text
    assert "## Closed since last run (1)" in text
    assert "(top K)" in text
    assert "absent from Acme board" in text
    assert '"must be authorized to work in the US"' in text


def test_still_open_accumulates(store, tmp_path):
    source_id, [oid] = _seed(store, 1)
    for run in (RUN2, "20261003T120000Z-cccc", "20261004T120000Z-dddd"):
        store.upsert_postings(source_id, [posting("1")], run)
        store.mark_source_read(source_id, run, "ok")
        run_liveness(store, run, NoHttp(), LifecycleSettings())
        rank_open(store, run, RankingSettings(), 3, NOW)
        s = sections(store, run)
        assert [o["id"] for o in s.still_open] == [oid]
        assert s.new == []


def test_unverified_note_when_board_unreadable(store):
    source_id, _ = _seed(store, 1)
    store.mark_source_read(source_id, RUN2, "unreadable")
    run_liveness(store, RUN2, NoHttp(), LifecycleSettings())
    rank_open(store, RUN2, RankingSettings(), 3, NOW)
    text = render(meta(RUN2, "partial"), store, 3)
    assert "(not checked this run)" in text


def test_report_without_summaries_still_lists_fields(store):
    _seed(store, 1)
    rank_open(store, RUN1, RankingSettings(), 3, NOW)
    text = render(meta(RUN1), store, 3)
    assert "**Location:** New York, NY" in text
    assert "**Term:** Summer 2027" in text
    assert "**Pay:** $45/hour" in text
    assert "<https://boards.greenhouse.io/acme/jobs/1>" in text


def test_pipe_in_title_does_not_break_table(store):
    source_id = add_board(store)
    [pid] = store.upsert_postings(
        source_id, [posting("1", title="Intern | Platform", text="Intern | Platform role")], RUN1
    )
    rec = record(
        title={"value": "Intern | Platform", "quote": "Intern | Platform"},
        role_type={"value": "unknown"},
        term={"value": "unknown"},
        locations={"value": "unknown"},
        compensation={"value": "unknown"},
        work_authorization={"value": "unknown"},
    )
    assert save_record(store, pid, rec, RUN1).ok
    store.mark_source_read(source_id, RUN2, "ok")
    store.upsert_postings(source_id, [posting("1", title="Intern | Platform")], RUN2)
    run_liveness(store, RUN2, NoHttp(), LifecycleSettings())
    rank_open(store, RUN2, RankingSettings(), 3, NOW)
    assert "Intern \\| Platform" in render(meta(RUN2), store, 3)
