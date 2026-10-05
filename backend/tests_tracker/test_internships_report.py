"""opportunity-report: ranking in code, the Editor's summary checks, and the report that
compares this run's top K with the last run's: New / Still in top K / Dropped / Also open."""

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
from tracker.usecases.internships.lifecycle import run_liveness
from tracker.usecases.internships.ranking import RankingSettings, rank_open, score
from tracker.usecases.internships.report import render, sections

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    state, store = open_store(tmp_path / "s.sqlite")
    yield store
    state.close()


def opp(**overrides):
    base = {
        "id": 1,
        "company": "Acme",
        "title": "Software Engineering Intern",
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
    assert full == pytest.approx(3 + 3 + 2 + (1 - 1 / 30) + 3)  # role, term, place, age, focus
    assert score(opp(term="unknown"), s, NOW) == pytest.approx(full - 1.5)
    assert score(opp(term="Fall 2026"), s, NOW) == pytest.approx(full - 3)
    assert score(opp(locations=["London"], remote="remote"), s, NOW) == pytest.approx(full)
    assert score(opp(locations=["London"]), s, NOW) == pytest.approx(full - 2)
    # Not a software, ML or data role: below the same internship that is one.
    assert score(opp(title="Product Design Intern"), s, NOW) == pytest.approx(full - 3)
    assert score(opp(title="ML Research Intern"), s, NOW) == pytest.approx(full)
    assert score(opp(title="HTML Email Designer Intern"), s, NOW) == pytest.approx(full - 3)


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


def test_editor_is_asked_only_for_summaries_the_report_shows(store):
    # 6 new: the report shows the first K in full and lists the others on one line.
    _seed(store, 6)
    ranked = [o["id"] for o in rank_open(store, RUN1, RankingSettings(), 2, NOW)]
    assert [o["id"] for o in wanted(store, RUN1, 2)] == ranked[:2]


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
    allowed = {o["id"] for o in wanted(store, RUN1, 3)}
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
    outcome = get_opportunities(store, RUN1, 3)
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


def finish(store, run_id, *, rank=True, k=3):
    """Run the code stages of one run and record it as finished."""
    with store.db:
        store.db.execute(
            "INSERT INTO runs (id, started_at, ended_at, topic, k, status) "
            "VALUES (?, ?, ?, 'internships', ?, 'complete')",
            (run_id, run_id, run_id, k),
        )
    if rank:
        run_liveness(store, run_id)
        rank_open(store, run_id, RankingSettings(), k, NOW)


RUN3 = "20261003T120000Z-cccc"


def test_previous_ranked_run_skips_a_run_that_failed_before_rank(store):
    _seed(store, 1)
    assert store.previous_ranked_run(RUN1) is None
    finish(store, RUN1)
    finish(store, RUN2, rank=False)  # a terminal failure in the Scout
    assert store.previous_ranked_run(RUN3) == RUN1
    finish(store, RUN3)
    assert store.previous_ranked_run("20261004T120000Z-dddd") == RUN3


def _opportunity(store, source_id, external_id, run_id):
    [pid] = store.upsert_postings(source_id, [posting(external_id)], run_id)
    return save_record(store, pid, record(), run_id).data["opportunity_id"]


def test_section_rules(store):
    """Each rule of design D2, with ranks set by hand."""
    source_id = add_board(store)
    a, b, c, d, x, y, z, r = (_opportunity(store, source_id, str(i), RUN1) for i in range(8))
    store.set_status(z, "closed", RUN1, "gone in run 1")
    store.set_status(r, "closed", RUN1, "gone in run 1")
    store.put_ranks(
        RUN1,
        [(a, 9, True), (b, 8, True), (c, 7, True), (d, 6, False), (x, 5, False), (y, 4, False)],
    )
    finish(store, RUN1, rank=False)

    n = _opportunity(store, source_id, "new", RUN2)
    store.set_status(b, "closed", RUN2, "absent from Acme board")
    store.set_status(y, "closed", RUN2, "absent from Acme board")
    store.set_status(r, "open", RUN2, "listed again")  # reopened: keeps its first-seen run
    store.put_ranks(
        RUN2,
        [(n, 9, True), (a, 8, True), (r, 7, True), (d, 6, True), (x, 5, False), (c, 4, False)],
    )

    s = sections(store, RUN2)
    assert s.previous_run == RUN1
    assert [o["id"] for o in s.new] == [n]
    assert s.new[0]["top_k"]
    assert [(o["id"], o["rank"], o["previous_rank"], o["was_top_k"]) for o in s.top_k] == [
        (a, 2, 1, True),  # still in the top K
        (r, 3, None, False),  # reopened into the top K: entered it
        (d, 4, 4, False),  # entered the top K
    ]
    assert [(o["id"], o["drop_reason"], o["rank"]) for o in s.dropped] == [
        (b, "closed", None),  # was 2nd
        (c, "outranked", 6),  # was 3rd
        (y, "closed", None),  # closed this run, never in the top K
    ]
    assert [o["id"] for o in s.also_open] == [x]
    listed = [o["id"] for o in s.new + s.top_k + s.dropped + s.also_open]
    assert len(listed) == len(set(listed))
    assert z not in listed  # closed in an earlier run

    text = render(meta(RUN2), store, 3)
    assert "| 3 | entered the top K |" in text
    assert "| 2 | 1 |" in text
    assert "(was #2): closed: absent from Acme board" in text
    assert "(was #3): outranked, now #6" in text


def test_first_run(store):
    _seed(store, 2)
    finish(store, RUN1)
    s = sections(store, RUN1)
    assert len(s.new) == 2
    assert s.top_k == s.dropped == s.also_open == []
    text = render(meta(RUN1), store, 3)
    assert text.count("No earlier run to compare with.") == 2


def test_second_day_report(store):
    """Run 1's top 5 is A-E. In run 2 a new F ranks 2nd, C closes and E ranks 7th."""
    source_id = add_board(store)
    ids = [_opportunity(store, source_id, str(i), RUN1) for i in range(1, 8)]
    a, b, c, d, e, g, h = ids
    store.put_ranks(RUN1, [(o, 10 - i, i < 5) for i, o in enumerate(ids)])
    finish(store, RUN1, rank=False, k=5)

    f = _opportunity(store, source_id, "8", RUN2)
    store.set_status(c, "closed", RUN2, "absent from Acme board")
    ranked = [a, f, b, d, g, h, e]
    store.put_ranks(RUN2, [(o, 10 - i, i < 5) for i, o in enumerate(ranked)])

    s = sections(store, RUN2)
    assert [o["id"] for o in s.new] == [f]
    assert [o["id"] for o in s.top_k] == [a, b, d, g]
    assert [(o["id"], o["drop_reason"]) for o in s.dropped] == [(c, "closed"), (e, "outranked")]
    assert [o["id"] for o in s.also_open] == [h]

    text = render(meta(RUN2), store, 5, stages=[{"name": "collect", "outcome": "complete"}])
    assert text.index("## New since last run (1)") < text.index("## Still in top K (4)")
    assert text.index("## Still in top K (4)") < text.index("## Dropped (2)")
    assert text.index("## Dropped (2)") < text.index("## Also open (1)")
    assert "(top K)" in text
    assert "outranked, now #7" in text
    assert '"must be authorized to work in the US"' in text


def test_also_open_accumulates(store):
    source_id, [oid] = _seed(store, 1)
    finish(store, RUN1, k=0)
    for run in (RUN2, RUN3, "20261004T120000Z-dddd"):
        store.upsert_postings(source_id, [posting("1")], run)
        store.mark_source_read(source_id, run, "ok")
        finish(store, run, k=0)
        s = sections(store, run)
        assert [o["id"] for o in s.also_open] == [oid]
        assert s.new == []


def test_unverified_note_when_board_unreadable(store):
    source_id, _ = _seed(store, 1)
    finish(store, RUN1)
    store.mark_source_read(source_id, RUN2, "unreadable")
    run_liveness(store, RUN2)
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
    finish(store, RUN1)
    store.mark_source_read(source_id, RUN2, "ok")
    store.upsert_postings(source_id, [posting("1", title="Intern | Platform")], RUN2)
    finish(store, RUN2)  # in the Still in top K table
    assert "Intern \\| Platform" in render(meta(RUN2), store, 3)


def test_postings_waiting_for_review_are_counted(store):
    source_id = add_board(store)
    store.upsert_postings(source_id, [posting("1"), posting("2")], RUN1)
    text = render(meta(RUN1, "partial"), store, 3)
    assert "**Waiting for review:** 2 postings listed in this run" in text
    assert "Waiting for review" not in render(meta(RUN2), store, 3)  # not listed in RUN2
